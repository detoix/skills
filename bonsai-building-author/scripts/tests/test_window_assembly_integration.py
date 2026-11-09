"""Exercise stock and HST declarations through the actual IFC emitter.

The selected compiled batches run against a real in-memory IFC4 file. No
Blender process, artifact files, or substitute window emitter is involved.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
import math
import re
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from building_author import (  # noqa: E402
    AuthoringError, Building, building, covering, layer, material, project,
    site, space, storey, wall, wall_type, window, window_type,
)
from building_author import compiler, window_assemblies  # noqa: E402
from building_author.openings import (  # noqa: E402
    balcony_window_type, lift_slide_window_type, sliding_window,
)

try:
    import numpy as np
    import ifcopenshell
    import ifcopenshell.api as ifc_api
    import ifcopenshell.geom
    import ifcopenshell.util.element
    import ifcopenshell.util.placement
    import ifcopenshell.validate
    from ifcopenshell.api.geometry.add_window_representation import (
        WindowLiningProperties, WindowPanelProperties,
    )
    for _module in ("root", "unit", "context", "aggregate", "geometry",
                    "spatial", "material", "type", "feature", "pset"):
        __import__(f"ifcopenshell.api.{_module}")
except ImportError:
    ifcopenshell = None


WIDTH, HEIGHT = 3.0, 2.3
WALL_ANGLE, WALL_BASE = .37, 3.35


def base_model():
    model = Building("window-assembly-integration")
    project(model, "project", name="Window assembly regression")
    site(model, "site", project="project")
    building(model, "building", site="site")
    storey(model, "upper", building="building", elevation=3.2)
    for key in ("masonry", "lining", "frame", "glass"):
        material(model, key, ifc_name=key, category=key,
                 base_color=(.5, .5, .5), roughness=.4)
    wall_type(model, "wall.type", layers=[layer("masonry", .47, priority=90)])
    start = (12.75, -8.5)
    end = (start[0] + 8 * math.cos(WALL_ANGLE),
           start[1] + 8 * math.sin(WALL_ANGLE))
    wall(model, "host", storey="upper", wall_type="wall.type", axis=(start, end),
         height=3.6, base_offset=.15, direction_sense="NEGATIVE")
    return model


def declared(*, hst=True, side="LEFT", offset=0.0, direction="POSITIVE", **section):
    model = base_model()
    if hst:
        lift_slide_window_type(model, "unit.type", sliding_side=side, offset=offset, **section)
    else:
        balcony_window_type(model, "unit.type", hinge_side=side)
    window(model, "unit", wall="host", window_type="unit.type", along=4.0,
           sill_height=0.0, overall_width=WIDTH, overall_height=HEIGHT,
           direction_sense=direction, lining_material="lining",
           framing_material="frame", glazing_material="glass", is_external=True)
    return model


def type_parameters(model):
    return next(item.parameters for item in model.operations if item.key == "unit.type")


def window_batch(declaration):
    """Compile the real type and occurrence loops and their direct helpers."""
    parsed = ast.parse(declaration.ifc_source())
    helpers = {"generator_kwargs", "snake", "axis_placement", "extruded_rectangle",
               "placement_matrix", "stable_guid", "root_entity"}
    functions = [node for node in parsed.body
                 if isinstance(node, ast.FunctionDef) and node.name in helpers]
    start = next(index for index, node in enumerate(parsed.body)
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "opening_types"
                         for target in node.targets))
    end = next(index for index, node in enumerate(parsed.body[start:], start)
               if isinstance(node, ast.For) and isinstance(node.iter, ast.Name)
               and node.iter.id == "OPENINGS")
    if len(functions) != len(helpers):
        raise AssertionError("A real compiled window helper is missing")
    return compile(ast.Module(body=functions + parsed.body[start:end + 1], type_ignores=[]),
                   "<compiled-window-assembly>", "exec")


def make_ifc(declaration):
    """Return a round-tripped IFC fixture using the real type/opening emitter.

    Builds the declared hierarchy, materials and straight wall hosts only;
    this isolated window harness is not a substitute for the full IFC phase.
    The returned file is independent of Blender and its active IFCStore.
    """
    declaration.validate()
    file = ifcopenshell.file(schema="IFC4")
    entities = {}
    classes = {"project": "IfcProject", "site": "IfcSite",
               "building": "IfcBuilding", "storey": "IfcBuildingStorey"}
    for operation in declaration.operations:
        if operation.kind not in classes:
            continue
        entity = ifc_api.root.create_entity(file, ifc_class=classes[operation.kind],
                                            name=operation.parameters["name"])
        if operation.kind == "storey":
            entity.Elevation = operation.parameters["elevation"]
        entities[operation.key] = entity
        for reference in operation.references.values():
            if reference in entities:
                ifc_api.aggregate.assign_object(file, products=[entity], relating_object=entities[reference])
    length = ifc_api.unit.add_si_unit(file, unit_type="LENGTHUNIT")
    ifc_api.unit.assign_unit(file, units=[length])
    context = ifc_api.context.add_context(file, context_type="Model")
    body = ifc_api.context.add_context(file, context_type="Model", context_identifier="Body",
                                       target_view="MODEL_VIEW", parent=context)
    for host in compiler.wall_payload(declaration)["walls"]:
        entity = ifc_api.root.create_entity(file, ifc_class="IfcWall", name=host["key"])
        entity.Tag = host["key"]
        dx, dy = host["end"][0] - host["start"][0], host["end"][1] - host["start"][1]
        angle = math.atan2(dy, dx)
        matrix = np.eye(4)
        matrix[:2, :2] = ((math.cos(angle), -math.sin(angle)), (math.sin(angle), math.cos(angle)))
        matrix[:3, 3] = (*host["start"], host["base_z"])
        ifc_api.geometry.edit_object_placement(file, product=entity, matrix=matrix)
        representation = ifc_api.geometry.add_wall_representation(
            file, context=body, length=math.hypot(dx, dy), height=host["height"], thickness=host["thickness"],
            offset=host["offset_from_reference_line"], direction_sense=host["direction_sense"])
        ifc_api.geometry.assign_representation(file, product=entity, representation=representation)
        ifc_api.spatial.assign_container(file, products=[entity], relating_structure=entities[host["storey"]])
        entities[host["key"]] = entity
    materials = {operation.key: ifc_api.material.add_material(file, name=operation.parameters["ifc_name"])
                 for operation in declaration.operations if operation.kind == "material"}
    namespace = dict(math=math, np=np, uuid=uuid, json=json, re=re, dataclasses=dataclasses,
                     ifcopenshell=ifcopenshell, ifc_api=ifc_api, model=file,
                     BUILD_NAME=declaration.name, body_context=body, entities=entities,
                     materials=materials, window_assemblies=window_assemblies,
                     WindowLiningProperties=WindowLiningProperties,
                     WindowPanelProperties=WindowPanelProperties,
                     OPENINGS=compiler.opening_payload(declaration),
                     OPERATIONS=[item.as_dict() for item in declaration.operations])
    exec(window_batch(declaration), namespace)
    return ifcopenshell.file.from_string(file.to_string())


class WindowAssemblyDeclarationTest(unittest.TestCase):
    def test_core_and_helper_keep_identical_parameters_and_payloads(self):
        helper = declared(side="RIGHT", offset=-.073, head_height=.063,
                          sash_bottom_height=.105, threshold_height=.018)
        parameters = copy.deepcopy(type_parameters(helper))
        core = base_model()
        window_type(core, "unit.type", **parameters)
        occurrence = next(item for item in helper.operations if item.key == "unit")
        window(core, "unit", **occurrence.references, **occurrence.parameters)
        helper.validate()
        core.validate()
        self.assertEqual(type_parameters(helper), type_parameters(core))
        self.assertEqual(compiler.opening_payload(helper), compiler.opening_payload(core))
        self.assertEqual(compiler.covering_payload(helper), {"main": [], "thresholds": []})
        self.assertEqual(compiler.opening_payload(helper)[0]["base"], 0.0)
        self.assertEqual(compiler.opening_payload(helper)[0]["opening_size"]["height"], HEIGHT)
        self.assertEqual(compiler.opening_payload(helper)[0]["lining"]["LiningOffset"], -.073)

    def test_assembly_rejects_inconsistent_stock_properties(self):
        original = type_parameters(declared())
        mutations = (
            ("lining", "LiningDepth", .18),
            ("lining", "LiningThickness", .07),
            ("lining", "LiningToPanelOffsetX", .025),
            ("lining", "LiningToPanelOffsetY", .025),
            ("lining", "MullionThickness", .07),
            ("lining", "FirstMullionOffset", .5),
            ("panel", "FrameDepth", .08),
            ("panel", "OperationType", "FIXEDCASEMENT"),
            ("panel", "PanelPosition", "RIGHT"),
            ("assembly", "kind", "SIMPLE_SLIDING"),
            ("assembly", "track_spacing", .07),
        )
        for section, field, value in mutations:
            with self.subTest(section=section, field=field):
                parameters = copy.deepcopy(original)
                target = parameters["panels"][0] if section == "panel" else parameters[section]
                target[field] = value
                with self.assertRaises(AuthoringError):
                    window_type(base_model(), "bad", **parameters)
        for field, value in (("partitioning_type", "DOUBLE_PANEL_HORIZONTAL"),
                             ("predefined_type", "SKYLIGHT")):
            parameters = copy.deepcopy(original)
            parameters[field] = value
            with self.assertRaises(AuthoringError):
                window_type(base_model(), "bad", **parameters)

    def test_invalid_occurrence_size_and_handedness_fail_before_ifc(self):
        for width, height in ((.35, HEIGHT), (WIDTH, .2)):
            model = base_model()
            lift_slide_window_type(model, "unit.type")
            window(model, "bad", wall="host", window_type="unit.type", along=4,
                   sill_height=0, overall_width=width, overall_height=height)
            with self.assertRaisesRegex(AuthoringError, "bad"):
                model.validate()
        for helper, keyword in ((lift_slide_window_type, "sliding_side"),
                                (balcony_window_type, "hinge_side")):
            with self.assertRaises(AuthoringError):
                helper(base_model(), "bad", **{keyword: "MIDDLE"})

    def test_hst_rejects_full_wall_flooring_patch_and_wrapper_forwards_ownership(self):
        for hst in (False, True):
            model = base_model()
            (lift_slide_window_type if hst else balcony_window_type)(model, "unit.type")
            space(model, "room", storey="upper", at=(13, -7), height=2.5, base_offset=.15)
            covering(model, "room.floor", space="room", material="masonry", thickness=.02)
            sliding_window(model, "unit", wall="host", window_type="unit.type", along=4,
                           sill_height=0, overall_width=WIDTH, overall_height=HEIGHT,
                           threshold_space="room")
            operation = next(item for item in model.operations if item.key == "unit")
            self.assertEqual(operation.references["threshold_space"], "room")
            if hst:
                with self.assertRaisesRegex(AuthoringError, "lift-slide.*threshold_space"):
                    model.validate()
            else:
                model.validate()
                thresholds = compiler.covering_payload(model)["thresholds"]
                self.assertEqual(len(thresholds), 1)
                self.assertEqual(thresholds[0]["key"], "unit.threshold-flooring")


@unittest.skipIf(ifcopenshell is None, "IfcOpenShell is required for emitted IFC checks")
class WindowAssemblyIfcTest(unittest.TestCase):
    def setUp(self):
        self.shapes = []

    def emit(self, declaration):
        return make_ifc(declaration)

    def points(self, entity, *, world=False):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, world)
        shape = ifcopenshell.geom.create_shape(settings, entity)
        self.shapes.append(shape)
        geometry = shape.geometry if hasattr(shape, "geometry") else shape
        return np.asarray(geometry.verts).reshape(-1, 3)

    def test_roundtrip_type_contracts_roles_and_single_filling_for_both_families(self):
        for hst in (False, True):
            with self.subTest(hst=hst):
                declaration = declared(hst=hst)
                file = self.emit(declaration)
                logger = ifcopenshell.validate.json_logger()
                ifcopenshell.validate.validate(file, logger)
                self.assertEqual(logger.statements, [])
                unit, = file.by_type("IfcWindow")
                opening, = file.by_type("IfcOpeningElement")
                unit_type, = file.by_type("IfcWindowType")
                self.assertEqual(unit.IsTypedBy[0].RelatingType, unit_type)
                self.assertEqual(unit.FillsVoids[0].RelatingOpeningElement, opening)
                self.assertEqual(len(opening.VoidsElements), 1)
                self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement.Tag, "host")
                self.assertEqual(len(unit.ContainedInStructure), 1)
                self.assertEqual(len(file.by_type("IfcRelFillsElement")), 1)
                self.assertEqual(file.by_type("IfcCovering"), [])
                self.assertEqual(file.by_type("IfcDoor"), [])
                body, = unit.Representation.Representations
                self.assertEqual(body.RepresentationType, "SweptSolid")
                self.assertTrue(all(item.is_a("IfcExtrudedAreaSolid") for item in body.Items))
                aspects = {aspect.Name: [item for representation in aspect.ShapeRepresentations
                                        for item in representation.Items]
                           for aspect in unit.Representation.HasShapeAspects}
                self.assertEqual(set(aspects), {"Lining", "Framing", "Glazing"})
                self.assertEqual({item.id() for items in aspects.values() for item in items},
                                 {item.id() for item in body.Items})
                constituents = ifcopenshell.util.element.get_material(unit).MaterialConstituents
                self.assertEqual({item.Name: item.Material.Name for item in constituents},
                                 {"Lining": "lining", "Framing": "frame", "Glazing": "glass"})
                if hst:
                    self.assertFalse(unit_type.ParameterTakesPrecedence)
                    pset = ifcopenshell.util.element.get_pset(unit_type, "BA_WindowAssembly")
                    self.assertEqual((pset["Kind"], pset["Version"], pset["LengthUnit"]),
                                     ("LIFT_SLIDE", 1, "METRE"))
                    self.assertEqual(json.loads(pset["Data"]), type_parameters(declaration)["assembly"])
                    self.assertIsNone(ifcopenshell.util.element.get_pset(unit, "BBIM_Window"))
                    self.assertEqual({key: len(items) for key, items in aspects.items()},
                                     {"Lining": 4, "Framing": 4, "Glazing": 2})
                else:
                    self.assertIsNone(ifcopenshell.util.element.get_pset(unit_type, "BA_WindowAssembly"))
                    self.assertIsNotNone(ifcopenshell.util.element.get_pset(unit, "BBIM_Window"))
                points = self.points(unit)
                self.assertAlmostEqual(points[:, 2].min(), 0.0)
                self.assertAlmostEqual(points[:, 2].max(), HEIGHT)

    def test_handedness_offset_and_direction_preserve_one_correctly_placed_body(self):
        for side in ("LEFT", "RIGHT"):
            for direction in ("POSITIVE", "NEGATIVE"):
                with self.subTest(side=side, direction=direction):
                    offset = -.061
                    declaration = declared(side=side, offset=offset, direction=direction)
                    file = self.emit(declaration)
                    unit, = file.by_type("IfcWindow")
                    assembly = type_parameters(declaration)["assembly"]
                    points = self.points(unit)
                    np.testing.assert_allclose(points.min(axis=0), (0, offset, 0), atol=1e-9)
                    np.testing.assert_allclose(points.max(axis=0),
                                               (WIDTH, offset + assembly["frame_depth"], HEIGHT), atol=1e-9)
                    named = {item.SweptArea.ProfileName: self.points(item)
                             for item in unit.Representation.Representations[0].Items}
                    fixed, sliding = named["Fixed sash"], named["Sliding sash"]
                    self.assertGreater(sliding[:, 1].min(), fixed[:, 1].max())
                    self.assertEqual(sliding[:, 0].mean() < fixed[:, 0].mean(), side == "LEFT")
                    self.assertAlmostEqual(named["Low threshold"][:, 2].max(), assembly["threshold_height"])
                    self.assertAlmostEqual(sliding[:, 2].min(),
                                           assembly["threshold_height"] + assembly["rail_height"])
                    matrix = ifcopenshell.util.placement.get_local_placement(unit.ObjectPlacement)
                    expected_world = (matrix[:3, :3] @ points.T).T + matrix[:3, 3]
                    world = self.points(unit, world=True)
                    np.testing.assert_allclose(world.min(axis=0), expected_world.min(axis=0), atol=1e-8)
                    np.testing.assert_allclose(world.max(axis=0), expected_world.max(axis=0), atol=1e-8)
                    self.assertAlmostEqual(world[:, 2].min(), WALL_BASE)
                    self.assertAlmostEqual(world[:, 2].max(), WALL_BASE + HEIGHT)
                    payload, = compiler.opening_payload(declaration)
                    self.assertAlmostEqual(payload["angle"], WALL_ANGLE + (math.pi if direction == "NEGATIVE" else 0))
                    opening = unit.FillsVoids[0].RelatingOpeningElement
                    cut_points = self.points(opening, world=True)
                    self.assertAlmostEqual(cut_points[:, 2].min(), WALL_BASE)
                    self.assertAlmostEqual(cut_points[:, 2].max(), WALL_BASE + HEIGHT)


if __name__ == "__main__":
    unittest.main()
