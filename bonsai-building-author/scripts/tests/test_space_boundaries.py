"""Regress room/floor boundaries against real regenerated IFC wall bodies.

The actual compiled wall and space/covering batches run in an in-memory IFC4
file. No Blender, substitute join solver, or saved fixture is involved.
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
    Building, building, covering, door, layer, material, project, site,
    space, storey, virtual_element, wall, wall_type,
)
from building_author import compiler, polygons  # noqa: E402
from building_author.openings import panel_door_type  # noqa: E402

try:
    import numpy as np
    import shapely
    import ifcopenshell
    import ifcopenshell.api as ifc_api
    import ifcopenshell.geom
    import ifcopenshell.util.element
    import ifcopenshell.util.placement
    import ifcopenshell.validate
    for _module in ("root", "unit", "context", "aggregate", "geometry",
                    "spatial", "material", "type", "feature"):
        __import__(f"ifcopenshell.api.{_module}")
except ImportError:
    ifcopenshell = None


RECTANGLE = ((0, 0), (8, 0), (8, 6), (0, 6))
REENTRANT = ((0, 0), (3, 0), (3, 1), (5, 1), (5, 0), (8, 0), (8, 6), (0, 6))
L_SHAPE = ((0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6))


def declared(outline=RECTANGLE, *, elevation=0.0):
    model = Building("native-space-boundary-regression")
    project(model, "project", name="Native space regression")
    site(model, "site", project="project")
    building(model, "building", site="site")
    storey(model, "ground", building="building", elevation=elevation)
    for key in ("masonry", "finish", "tile"):
        material(model, key, ifc_name=key, category=key,
                 base_color=(.5, .5, .5), roughness=.8)
    wall_type(model, "external", layers=[layer("masonry", .47, priority=90)])
    wall_type(model, "partition", layers=[layer("masonry", .12, priority=80)])
    for index, start in enumerate(outline):
        wall(model, f"wall.{index}", storey="ground", wall_type="external",
             axis=(start, outline[(index + 1) % len(outline)]), height=3.0)
    return model


def room(model, key, at, *, base=0.0, finish="finish", thickness=.015):
    space(model, key, storey="ground", at=at, height=2.5, base_offset=base)
    covering(model, f"{key}.floor", space=key, material=finish, thickness=thickness)


def compiled_batches(declaration):
    """Extract only real native geometry work; never execute live-state setup."""
    nodes = ast.parse(declaration.ifc_source()).body
    helpers = {"stable_guid", "root_entity", "add_layer_set"}
    functions = [node for node in nodes
                 if isinstance(node, ast.FunctionDef) and node.name in helpers]
    wall_start = next(index for index, node in enumerate(nodes)
                      if isinstance(node, ast.For) and any(
                          isinstance(child, ast.Constant) and child.value == "wall-type"
                          for child in ast.walk(node.iter)))
    wall_end = next(index for index, node in enumerate(nodes[wall_start:], wall_start)
                    if isinstance(node, ast.For) and any(
                        isinstance(child, ast.Attribute)
                        and child.attr == "regenerate_wall_representation"
                        for child in ast.walk(node)))
    space_start = next(index for index, node in enumerate(nodes)
                       if isinstance(node, ast.Assign) and any(
                           isinstance(target, ast.Name) and target.id == "space_regions"
                           for target in node.targets))
    space_end = next(index for index, node in enumerate(nodes[space_start:], space_start)
                     if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                     and node.target.id == "threshold")
    space_functions = [node for node in nodes if isinstance(node, ast.FunctionDef)
                       and node.name in {"add_spaces", "add_floor_covering"}]
    compile_nodes = lambda selected: compile(
        ast.Module(body=selected, type_ignores=[]), "<compiled-space-regression>", "exec")
    if len(functions) != len(helpers) or len(space_functions) != 2:
        raise AssertionError("A real compiled wall helper is missing")
    return (compile_nodes(functions + nodes[wall_start:wall_end + 1]),
            compile_nodes(space_functions + nodes[space_start:space_end + 1]))


def fixture(declaration):
    """Generate declarations using the real wall type, join and body emitter."""
    from building_author import space_geometry

    declaration.validate()
    file = ifcopenshell.file(schema="IFC4")
    entities = {}
    for operation in declaration.operations:
        cls = {"project": "IfcProject", "site": "IfcSite", "building": "IfcBuilding",
               "storey": "IfcBuildingStorey"}.get(operation.kind)
        if cls is None:
            continue
        entity = ifc_api.root.create_entity(file, ifc_class=cls, name=operation.key)
        entities[operation.key] = entity
        if operation.kind == "storey":
            entity.Elevation = operation.parameters["elevation"]
        for parent in operation.references.values():
            ifc_api.aggregate.assign_object(file, products=[entity], relating_object=entities[parent])
    length = ifc_api.unit.add_si_unit(file, unit_type="LENGTHUNIT")
    ifc_api.unit.assign_unit(file, units=[length])
    context = ifc_api.context.add_context(file, context_type="Model")
    body = ifc_api.context.add_context(file, context_type="Model", context_identifier="Body",
                                       target_view="MODEL_VIEW", parent=context)
    plan = ifc_api.context.add_context(file, context_type="Plan")
    axis = ifc_api.context.add_context(file, context_type="Plan", context_identifier="Axis",
                                       target_view="GRAPH_VIEW", parent=plan)
    materials = {operation.key: ifc_api.material.add_material(file, name=operation.key)
                 for operation in declaration.operations if operation.kind == "material"}
    namespace = dict(math=math, np=np, uuid=uuid, shapely=shapely,
                     ifcopenshell=ifcopenshell, ifc_api=ifc_api, model=file,
                     BUILD_NAME=declaration.name, entities=entities, materials=materials,
                     layer_sets={}, body_context=body, axis_context=axis,
                     OPERATIONS=[operation.as_dict() for operation in declaration.operations],
                     WALLS=compiler.wall_payload(declaration),
                     SPACES=compiler.space_payload(declaration),
                     COVERINGS=compiler.covering_payload(declaration),
                     space_geometry=space_geometry)
    wall_batch, room_batch = compiled_batches(declaration)
    exec(wall_batch, namespace)
    return namespace, room_batch


def plan_projection(entity, *, openings=False):
    """Independent projection adequate for these vertically prismatic fixtures."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, not openings)
    shape = ifcopenshell.geom.create_shape(settings, entity)
    vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
    triangles = np.asarray(shape.geometry.faces).reshape(-1, 3)
    return shapely.unary_union([
        shapely.Polygon(vertices[triangle, :2]) for triangle in triangles
        if shapely.Polygon(vertices[triangle, :2]).area > 1e-12
    ]).buffer(0)


def legacy_region(declaration, point):
    """The removed rectangular-obstacle algorithm, only to prove the defect."""
    obstacles = [shapely.Polygon(polygons.wall_footprint(
        tuple(item["start"]), tuple(item["end"]), item["thickness"],
        item["offset_from_reference_line"], item["direction_sense"]))
        for item in compiler.wall_payload(declaration)["walls"]]
    union = shapely.unary_union(obstacles)
    free = shapely.box(-10, -10, 20, 20).difference(union)
    return next(region for region in free.geoms if region.contains(shapely.Point(point)))


@unittest.skipIf(ifcopenshell is None, "IfcOpenShell and Shapely are required")
class NativeSpaceBoundaryTest(unittest.TestCase):
    def assertPolygonEqual(self, actual, expected):
        self.assertLess(actual.symmetric_difference(expected).area, 1e-8)
        self.assertLess(actual.hausdorff_distance(expected), 1e-7)

    def assertClosedProfile(self, entity):
        profile = entity.Representation.Representations[0].Items[0].SweptArea
        coordinates = profile.OuterCurve.Points.CoordList
        self.assertEqual(coordinates[0], coordinates[-1])

    def test_real_reentrant_and_l_joins_exclude_the_previous_corner_overlap(self):
        for outline, concave_corners in ((L_SHAPE, 1), (REENTRANT, 2)):
            with self.subTest(outline=outline):
                declaration = declared(outline)
                room(declaration, "room", (1, 2))
                namespace, batch = fixture(declaration)
                native_walls = shapely.unary_union([
                    plan_projection(entity) for entity in namespace["entities"].values()
                    if entity.is_a("IfcWall")])
                old = legacy_region(declaration, (1, 2))
                self.assertAlmostEqual(old.intersection(native_walls).area,
                                       concave_corners * .235 ** 2, places=8)
                exec(batch, namespace)
                actual = namespace["space_regions"]["room"]
                expected = shapely.Polygon(outline).buffer(-.235, join_style="mitre")
                self.assertPolygonEqual(actual, expected)
                self.assertLess(actual.intersection(native_walls).area, 1e-9)
                self.assertPolygonEqual(plan_projection(namespace["entities"]["room"]), expected)
                self.assertPolygonEqual(plan_projection(namespace["entities"]["room.floor"]), expected)
                self.assertClosedProfile(namespace["entities"]["room"])
                self.assertClosedProfile(namespace["entities"]["room.floor"])

    def test_native_t_join_keeps_both_rooms_and_finish_footprints_exact(self):
        declaration = declared(elevation=3.2)
        wall(declaration, "divider", storey="ground", wall_type="partition",
             axis=((4, 0), (4, 6)), height=3)
        room(declaration, "west", (2, 3))
        room(declaration, "east", (6, 3), finish="tile", thickness=.02)
        namespace, batch = fixture(declaration)
        exec(batch, namespace)
        expected = {"west": shapely.box(.235, .235, 3.94, 5.765),
                    "east": shapely.box(4.06, .235, 7.765, 5.765)}
        for key, polygon in expected.items():
            self.assertPolygonEqual(namespace["space_regions"][key], polygon)
            self.assertPolygonEqual(plan_projection(namespace["entities"][f"{key}.floor"]), polygon)
        self.assertEqual(len(namespace["model"].by_type("IfcRelConnectsPathElements")), 6)
        logger = ifcopenshell.validate.json_logger()
        round_trip = ifcopenshell.file.from_string(namespace["model"].to_string())
        ifcopenshell.validate.validate(round_trip, logger)
        self.assertEqual(logger.statements, [])

    def test_below_floor_and_elevated_walls_do_not_consume_floor_space(self):
        declaration = declared()
        wall(declaration, "plinth", storey="ground", wall_type="external",
             axis=((1, 2), (7, 2)), height=.3, base_offset=-.3)
        wall(declaration, "high-wall", storey="ground", wall_type="external",
             axis=((1, 4), (7, 4)), height=.3, base_offset=1.0)
        room(declaration, "room", (2, 3))
        namespace, batch = fixture(declaration)
        exec(batch, namespace)
        self.assertPolygonEqual(namespace["space_regions"]["room"],
                                shapely.box(.235, .235, 7.765, 5.765))

    def test_rotated_translated_reentrant_walls_use_native_world_coordinates(self):
        angle = .37
        def transformed(point):
            x, y = point
            return (12.75 + x * math.cos(angle) - y * math.sin(angle),
                    -8.5 + x * math.sin(angle) + y * math.cos(angle))
        outline = tuple(transformed(point) for point in REENTRANT)
        declaration = declared(outline, elevation=3.2)
        room(declaration, "room", transformed((1, 2)))
        namespace, batch = fixture(declaration)
        exec(batch, namespace)
        expected = shapely.Polygon(outline).buffer(-.235, join_style="mitre")
        actual = namespace["space_regions"]["room"]
        self.assertLess(actual.symmetric_difference(expected).area, 3e-6)
        self.assertLess(actual.hausdorff_distance(expected), 1e-7)
        self.assertPolygonEqual(plan_projection(namespace["entities"]["room.floor"]), actual)

    def test_outdoors_is_not_confused_with_a_large_enclosed_room(self):
        declaration = declared(((0, 0), (200, 0), (200, 200), (0, 200)))
        room(declaration, "hall", (100, 100))
        namespace, batch = fixture(declaration)
        exec(batch, namespace)
        self.assertPolygonEqual(namespace["space_regions"]["hall"],
                                shapely.box(.235, .235, 199.765, 199.765))

    def test_two_declared_rooms_cannot_silently_share_one_enclosure(self):
        declaration = declared()
        room(declaration, "first", (2, 3))
        room(declaration, "second", (6, 3))
        namespace, batch = fixture(declaration)
        with self.assertRaisesRegex(RuntimeError, "first.*second.*same enclosed region"):
            exec(batch, namespace)

    def test_missing_native_wall_body_has_no_rectangle_fallback(self):
        declaration = declared()
        room(declaration, "room", (2, 3))
        namespace, batch = fixture(declaration)
        namespace["entities"]["wall.0"].Representation = None
        with self.assertRaisesRegex(RuntimeError, "wall.0.*native IFC geometry"):
            exec(batch, namespace)

    def test_interior_wall_island_is_rejected_instead_of_filled_over(self):
        declaration = declared()
        wall(declaration, "island", storey="ground", wall_type="partition",
             axis=((3, 3), (5, 3)), height=3)
        room(declaration, "room", (2, 3))
        namespace, batch = fixture(declaration)
        with self.assertRaisesRegex(RuntimeError, "room.*interior-ring profiles.*not supported"):
            exec(batch, namespace)
        self.assertEqual(namespace["model"].by_type("IfcCovering"), [])

    def test_each_space_uses_its_own_finished_floor_elevation(self):
        declaration = declared(elevation=3.2)
        wall(declaration, "low-divider", storey="ground", wall_type="partition",
             axis=((4, 0), (4, 6)), height=.5)
        room(declaration, "lower", (2, 3))
        room(declaration, "upper", (2, 3), base=1.0)
        namespace, batch = fixture(declaration)
        exec(batch, namespace)
        self.assertPolygonEqual(namespace["space_regions"]["lower"],
                                shapely.box(.235, .235, 3.94, 5.765))
        self.assertPolygonEqual(namespace["space_regions"]["upper"],
                                shapely.box(.235, .235, 7.765, 5.765))

    def test_opening_void_does_not_merge_rooms_and_patch_remains_single_owned_finish(self):
        declaration = declared()
        wall(declaration, "divider", storey="ground", wall_type="partition",
             axis=((4, 0), (4, 6)), height=3)
        room(declaration, "west", (2, 3), finish="tile", thickness=.02)
        room(declaration, "east", (6, 3))
        panel_door_type(declaration, "door.type")
        door(declaration, "door", wall="divider", door_type="door.type", along=3,
             overall_width=1, overall_height=2.1, threshold_space="west")
        namespace, batch = fixture(declaration)
        model = namespace["model"]
        host = namespace["entities"]["divider"]
        opening = ifc_api.root.create_entity(model, ifc_class="IfcOpeningElement")
        # A full-height void makes accidental opening subtraction observable
        # even if a resolver projects all triangles instead of taking a section.
        body = ifc_api.geometry.add_wall_representation(
            model, context=namespace["body_context"], length=1, height=3.1,
            thickness=.5, offset=-.25)
        ifc_api.geometry.assign_representation(model, product=opening, representation=body)
        matrix = ifcopenshell.util.placement.get_local_placement(host.ObjectPlacement)
        matrix = matrix.copy()
        matrix[:3, 3] += matrix[:3, 0] * 2.5
        ifc_api.geometry.edit_object_placement(model, product=opening, matrix=matrix)
        ifc_api.feature.add_feature(model, feature=opening, element=host)
        self.assertAlmostEqual(plan_projection(host).area - plan_projection(host, openings=True).area,
                               .12, places=8)
        exec(batch, namespace)
        west = namespace["space_regions"]["west"]
        east = namespace["space_regions"]["east"]
        self.assertPolygonEqual(west, shapely.box(.235, .235, 3.94, 5.765))
        self.assertPolygonEqual(east, shapely.box(4.06, .235, 7.765, 5.765))
        patch = namespace["entities"]["door.threshold-flooring"]
        self.assertPolygonEqual(plan_projection(patch), shapely.box(3.94, 2.5, 4.06, 3.5))
        self.assertEqual(patch.ContainedInStructure[0].RelatingStructure,
                         namespace["entities"]["west"])
        self.assertEqual(ifcopenshell.util.element.get_material(patch), namespace["materials"]["tile"])
        self.assertEqual(len(model.by_type("IfcCovering")), 3)
        self.assertLess(west.intersection(plan_projection(patch)).area, 1e-9)
        self.assertLess(east.intersection(plan_projection(patch)).area, 1e-9)

    def test_virtual_boundary_keeps_its_single_explicitly_owned_patch(self):
        declaration = declared()
        room(declaration, "west", (2, 3))
        room(declaration, "east", (6, 3), finish="tile", thickness=.02)
        virtual_element(declaration, "virtual", storey="ground",
                        axis=((4, .235), (4, 5.765)), threshold_space="east")
        namespace, batch = fixture(declaration)
        exec(batch, namespace)
        half = compiler.VIRTUAL_ELEMENT_WIDTH / 2
        self.assertPolygonEqual(namespace["space_regions"]["west"],
                                shapely.box(.235, .235, 4 - half, 5.765))
        self.assertPolygonEqual(namespace["space_regions"]["east"],
                                shapely.box(4 + half, .235, 7.765, 5.765))
        patch = namespace["entities"]["virtual.threshold-flooring"]
        self.assertClosedProfile(patch)
        self.assertPolygonEqual(plan_projection(patch),
                                shapely.box(4 - half, .235, 4 + half, 5.765))
        self.assertEqual(patch.ContainedInStructure[0].RelatingStructure,
                         namespace["entities"]["east"])
        self.assertEqual(ifcopenshell.util.element.get_material(patch), namespace["materials"]["tile"])
        self.assertEqual(len(namespace["model"].by_type("IfcCovering")), 3)

    def test_emitter_accepts_numerical_contact_without_moving_threshold_geometry(self):
        declaration = declared()
        room(declaration, "room", (2, 3))
        panel_door_type(declaration, "door.type")
        door(declaration, "door", wall="wall.0", door_type="door.type", along=3,
             overall_width=1, overall_height=2.1, threshold_space="room")
        namespace, batch = fixture(declaration)
        threshold = namespace["COVERINGS"]["thresholds"][0]
        # Introduce a gap below the precision of the geometry without
        # enlarging either footprint.
        threshold["boundary"] = [[x, y - 3.3e-8] for x, y in threshold["boundary"]]
        expected = tuple(tuple(point) for point in threshold["boundary"])
        exec(batch, namespace)
        patch = namespace["entities"]["door.threshold-flooring"]
        profile = patch.Representation.Representations[0].Items[0].SweptArea
        self.assertEqual(profile.OuterCurve.Points.CoordList, expected + (expected[0],))
        self.assertEqual(patch.ContainedInStructure[0].RelatingStructure,
                         namespace["entities"]["room"])
        self.assertPolygonEqual(namespace["space_regions"]["room"],
                                shapely.box(.235, .235, 7.765, 5.765))


@unittest.skipIf(ifcopenshell is None, "IfcOpenShell and Shapely are required")
class ThresholdAdjacencyTest(unittest.TestCase):
    def test_shared_edge_contact_accepts_zero_and_subprecision_gaps(self):
        from building_author.space_geometry import threshold_is_adjacent

        for offset in (0, 1, 100, 10000):
            for gap in (0, 3.3e-8):
                with self.subTest(offset=offset, gap=gap):
                    room = shapely.box(offset, offset, offset + 2, offset + 2)
                    patch = shapely.box(offset + 2 + gap, offset + .5,
                                        offset + 2.12 + gap, offset + 1.5)
                    self.assertTrue(threshold_is_adjacent(room, patch))

    def test_nearly_parallel_edge_contact_accepts_native_rounding_slope(self):
        from building_author.space_geometry import threshold_is_adjacent

        room = shapely.box(0, 0, 2, 2)
        patch = shapely.Polygon(((2 + 1e-8, .5), (2.12, .5),
                                 (2.12, 1.5), (2 + 3.3e-8, 1.5)))
        self.assertTrue(threshold_is_adjacent(room, patch))

    def test_gap_larger_than_plan_precision_is_not_adjacent(self):
        from building_author.space_geometry import threshold_is_adjacent

        for offset in (0, 1, 100, 10000):
            with self.subTest(offset=offset):
                room = shapely.box(offset, offset, offset + 2, offset + 2)
                patch = shapely.box(offset + 2 + 2e-7, offset + .5,
                                    offset + 2.12 + 2e-7, offset + 1.5)
                self.assertFalse(threshold_is_adjacent(room, patch))

    def test_point_only_contact_is_rejected_at_local_and_large_coordinates(self):
        from building_author.space_geometry import threshold_is_adjacent

        for offset in (0, 1, 100, 10000):
            with self.subTest(offset=offset):
                room = shapely.box(offset, offset, offset + 2, offset + 2)
                patch = shapely.box(offset + 2, offset + 2, offset + 3, offset + 3)
                self.assertEqual(room.intersection(patch).geom_type, "Point")
                self.assertFalse(threshold_is_adjacent(room, patch))


if __name__ == "__main__":
    unittest.main()
