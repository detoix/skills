"""Execute the compiled corner emitter against real IFC4 geometry, without Blender.

Only the corner batch and its actual template helpers are extracted from the
compiled source. IfcOpenShell creates the fixture hosts and performs the cuts;
neither relationship creation nor placement is mocked.
"""

from __future__ import annotations

import ast
import math
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from building_author import (  # noqa: E402
    Building, building, corner_opening, layer, material, project, site,
    storey, wall, wall_type,
)
from building_author import compiler  # noqa: E402

try:
    import numpy as np
    import ifcopenshell
    import ifcopenshell.api as ifc_api
    import ifcopenshell.api.context
    import ifcopenshell.api.feature
    import ifcopenshell.api.geometry
    import ifcopenshell.api.root
    import ifcopenshell.api.unit
    import ifcopenshell.geom
    import ifcopenshell.util.placement
    import ifcopenshell.util.shape
    import ifcopenshell.validate
except ImportError:
    ifcopenshell = None


def corner_model() -> Building:
    model = Building("corner-opening-ifc-regression")
    project(model, "project", name="Corner Opening Regression")
    site(model, "site", project="project")
    building(model, "building", site="site")
    storey(model, "upper", building="building", elevation=3.2)
    material(model, "masonry", ifc_name="Masonry", category="brick",
             base_color=(0.6, 0.4, 0.3), roughness=0.8)
    wall_type(model, "wall.300", layers=[layer("masonry", 0.30, priority=90)])
    wall_type(model, "wall.460", layers=[layer("masonry", 0.46, priority=90)])
    angle = 0.37
    corner = (12.75, -8.5)
    a_start = (corner[0] + 6.0 * math.cos(angle),
               corner[1] + 6.0 * math.sin(angle))
    b_end = (corner[0] - 6.0 * math.sin(angle),
             corner[1] + 6.0 * math.cos(angle))
    wall(model, "wall-a", storey="upper", wall_type="wall.300",
         axis=(a_start, corner), height=3.0, base_offset=0.15)
    wall(model, "wall-b", storey="upper", wall_type="wall.460",
         axis=(corner, b_end), height=3.0, base_offset=0.15,
         direction_sense="NEGATIVE")
    corner_opening(model, "corner", walls=("wall-a", "wall-b"),
                   base=0.90, height=1.40, reach=0.05)
    return model


def corner_batch(model: Building):
    """Select the real generated loop and helpers, leaving Blender untouched."""

    parsed = ast.parse(model.ifc_source())
    helpers = {"axis_placement", "extruded_rectangle", "placement_matrix", "stable_guid"}
    selected = [
        node for node in parsed.body
        if (isinstance(node, ast.FunctionDef) and node.name in helpers)
        or (isinstance(node, ast.For)
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "CORNER_OPENINGS")
    ]
    if len(selected) != len(helpers) + 1:
        raise AssertionError("The compiled corner emitter or its helpers were not found")
    return compile(ast.Module(body=selected, type_ignores=[]), "<compiled-corner>", "exec")


@unittest.skipIf(ifcopenshell is None, "IfcOpenShell is required for emitted IFC geometry checks")
class CornerOpeningIfcTest(unittest.TestCase):
    def setUp(self):
        # The native geometry buffers are owned by their shape results.
        self.shapes = []

    def make_fixture(self):
        declaration = corner_model()
        model = ifcopenshell.file(schema="IFC4")
        ifc_api.root.create_entity(model, ifc_class="IfcProject", name="Regression")
        length = ifc_api.unit.add_si_unit(model, unit_type="LENGTHUNIT")
        ifc_api.unit.assign_unit(model, units=[length])
        context = ifc_api.context.add_context(model, context_type="Model")
        body = ifc_api.context.add_context(
            model, context_type="Model", context_identifier="Body",
            target_view="MODEL_VIEW", parent=context,
        )
        namespace = {
            "math": math, "np": np, "uuid": uuid,
            "ifcopenshell": ifcopenshell, "ifc_api": ifc_api,
            "BUILD_NAME": declaration.name, "model": model,
            "body_context": body, "entities": {},
            "CORNER_OPENINGS": compiler.corner_opening_payload(declaration),
        }
        for host in compiler.wall_payload(declaration)["walls"]:
            entity = ifc_api.root.create_entity(
                model, ifc_class="IfcWall", name=host["key"], predefined_type="STANDARD"
            )
            entity.Tag = host["key"]
            dx = host["end"][0] - host["start"][0]
            dy = host["end"][1] - host["start"][1]
            angle = math.atan2(dy, dx)
            matrix = np.eye(4)
            matrix[:2, :2] = ((math.cos(angle), -math.sin(angle)),
                             (math.sin(angle), math.cos(angle)))
            matrix[:3, 3] = (*host["start"], host["base_z"])
            ifc_api.geometry.edit_object_placement(model, product=entity, matrix=matrix)
            representation = ifc_api.geometry.add_wall_representation(
                model, context=body, length=math.hypot(dx, dy), height=host["height"],
                thickness=host["thickness"], offset=host["offset_from_reference_line"],
                direction_sense=host["direction_sense"],
            )
            ifc_api.geometry.assign_representation(
                model, product=entity, representation=representation
            )
            namespace["entities"][host["key"]] = entity
        return declaration, namespace

    def emit(self):
        declaration, namespace = self.make_fixture()
        exec(corner_batch(declaration), namespace)
        return namespace

    def geometry(self, entity):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, entity)
        self.shapes.append(shape)
        return shape.geometry

    def test_each_host_has_a_schema_valid_opening_after_ifc_round_trip(self):
        namespace = self.emit()
        model = ifcopenshell.file.from_string(namespace["model"].to_string())
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(model, logger)
        self.assertEqual(logger.statements, [])
        openings = model.by_type("IfcOpeningElement")
        self.assertEqual(len(openings), 2)
        self.assertEqual(
            {opening.VoidsElements[0].RelatingBuildingElement.Tag for opening in openings},
            {"wall-a", "wall-b"},
        )
        for opening in openings:
            self.assertEqual(len(opening.VoidsElements), 1)
            host = opening.VoidsElements[0].RelatingBuildingElement
            self.assertEqual(host.HasOpenings[0].RelatedOpeningElement, opening)
            self.assertEqual(opening.ObjectPlacement.PlacementRelTo, host.ObjectPlacement)
        self.assertEqual(
            openings[0].Representation.Representations[0],
            openings[1].Representation.Representations[0],
        )

    def test_both_hosts_lose_the_expected_material_only_in_the_opening_span(self):
        declaration, namespace = self.make_fixture()
        before = {
            key: ifcopenshell.util.shape.get_volume(self.geometry(entity))
            for key, entity in namespace["entities"].items()
        }
        exec(corner_batch(declaration), namespace)
        # Each straight host ends on the common cutter centre. This independently
        # predicts half the cutter width along that host times its thickness.
        expected_removed = {"wall-a": 0.30 * 0.28 * 1.40,
                            "wall-b": 0.46 * 0.20 * 1.40}
        for key, removed in expected_removed.items():
            with self.subTest(host=key):
                geometry = self.geometry(namespace["entities"][key])
                self.assertAlmostEqual(
                    before[key] - ifcopenshell.util.shape.get_volume(geometry),
                    removed, places=7,
                )
                z = np.asarray(geometry.verts).reshape(-1, 3)[:, 2]
                np.testing.assert_allclose(
                    sorted(set(np.round(z, 7))), [3.35, 4.25, 5.65, 6.35], atol=1e-7
                )

    def test_world_cutter_frames_coincide_despite_distinct_host_relative_placements(self):
        namespace = self.emit()
        matrices = []
        for opening in namespace["model"].by_type("IfcOpeningElement"):
            matrices.append(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement))
            geometry = self.geometry(opening)
            z = np.asarray(geometry.verts).reshape(-1, 3)[:, 2]
            self.assertAlmostEqual(min(z), 4.25, places=7)
            self.assertAlmostEqual(max(z), 5.65, places=7)
        np.testing.assert_allclose(matrices[0], matrices[1], atol=1e-10)
        np.testing.assert_allclose(matrices[0][:3, 3], [12.75, -8.5, 4.25], atol=1e-10)
        self.assertNotEqual(
            namespace["model"].by_type("IfcOpeningElement")[0].ObjectPlacement,
            namespace["model"].by_type("IfcOpeningElement")[1].ObjectPlacement,
        )

    def test_opening_and_relationship_guids_are_unique_and_stable_per_host(self):
        def identities():
            namespace = self.emit()
            return {
                opening.VoidsElements[0].RelatingBuildingElement.Tag:
                (opening.Tag, opening.GlobalId, opening.VoidsElements[0].GlobalId)
                for opening in namespace["model"].by_type("IfcOpeningElement")
            }
        first = identities()
        self.assertEqual(first, identities())
        ids = [guid for values in first.values() for guid in values[1:]]
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual({values[0] for values in first.values()},
                         {"corner.opening.wall-a", "corner.opening.wall-b"})


if __name__ == "__main__":
    unittest.main()
