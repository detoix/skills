"""Render-only outer-face clearance and unchanged flashing seating/apex."""

import ast
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from building_author.flashing_clearance import flashing_render_clearances


FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def rake(y0=0.0, y1=2.0, z0=0.0, z1=1.0):
    bottom = [(0, y0, z0), (.08, y0, z0), (.08, y1, z1), (0, y1, z1)]
    return bottom + [(x, y, z + .17) for x, y, z in bottom], FACES, (-1, 0, 0)


WALL = ([(0, 0, .02), (0, 0, .15), (0, 1, .65), (0, 1, .52)], [(0, 1, 2, 3)])


class FlashingClearanceTest(unittest.TestCase):
    def test_only_outer_face_moves_outward_and_source_back_and_elevations_stay_fixed(self):
        source = {"roof.verge.0": rake()}
        original = copy.deepcopy(source)
        deltas, report = flashing_render_clearances(source, [WALL])["roof.verge.0"]
        self.assertEqual(source, original)
        for vertex, delta in zip(source["roof.verge.0"][0], deltas):
            self.assertEqual(delta, (-.001, 0, 0) if vertex[0] == 0 else (0, 0, 0))
        self.assertEqual(report["moved_vertices"], 4)
        self.assertAlmostEqual(report["overlap_area_m2"], .13)
        json.dumps(report)

    def test_touching_rakes_keep_apex_closed_without_moving_a_disconnected_rake(self):
        source = {"a": rake(), "b": rake(2, 4, 1, 0), "c": rake(10, 12, 0, 1)}
        result = flashing_render_clearances(source, [WALL])
        apex_sections = []
        for key in ("a", "b"):
            deltas, report = result[key]
            self.assertEqual(report["moved_vertices"], 4)
            apex_sections.append({
                tuple(np.asarray(vertex) + delta)
                for vertex, delta in zip(source[key][0], deltas) if vertex[1] == 2
            })
        self.assertEqual(apex_sections[0], apex_sections[1])
        self.assertEqual(result["b"][1]["touching_faces"], 0)
        self.assertEqual(result["c"][1]["moved_vertices"], 0)

    def test_yaw_rotation_translation_and_split_vertices_preserve_world_clearance(self):
        angle = .63
        rotation = np.array(((math.cos(angle), -math.sin(angle), 0),
                             (math.sin(angle), math.cos(angle), 0), (0, 0, 1)))
        offset = np.array((17.0, -9.0, 3.4))
        vertices, faces, outward = rake()
        # Model material-boundary duplication from IFC shape aspects.
        duplicated = [tuple(rotation @ vertices[i] + offset) for face in faces for i in face]
        split_faces = [tuple(range(i, i + 4)) for i in range(0, len(duplicated), 4)]
        world_outward = rotation @ outward
        original_direction = world_outward.copy()
        transformed_wall = ([tuple(rotation @ point + offset) for point in WALL[0]], WALL[1])
        source = {"trim": (duplicated, split_faces, world_outward)}
        deltas, _ = flashing_render_clearances(source, [transformed_wall])["trim"]
        np.testing.assert_array_equal(world_outward, original_direction)
        previous = {}
        for vertex, delta in zip(duplicated, deltas):
            local_x = float((rotation.T @ (np.asarray(vertex) - offset))[0])
            expected = world_outward * .001 if abs(local_x) < 1e-8 else np.zeros(3)
            np.testing.assert_allclose(delta, expected, atol=1e-12)
            self.assertEqual(delta[2], 0)
            if vertex in previous:
                self.assertEqual(delta, previous[vertex])
            previous[vertex] = delta

    def test_axis_ties_at_45_and_135_degrees_preserve_contact_and_apex(self):
        for degrees in (15, 30, 36.1, 45, 60, 135, 180, 225, 315):
            for offset in ((0, 0, 0), (17, -9, 3.4), (10000, -20000, 250)):
                with self.subTest(degrees=degrees, offset=offset):
                    angle = math.radians(degrees)
                    rotation = np.array(((math.cos(angle), -math.sin(angle), 0),
                                         (math.sin(angle), math.cos(angle), 0), (0, 0, 1)))
                    source = {}
                    originals = {"a": rake(), "b": rake(2, 4, 1, 0)}
                    for key, (vertices, faces, outward) in originals.items():
                        source[key] = ([tuple(rotation @ vertex + offset) for vertex in vertices],
                                       faces, tuple(rotation @ outward))
                    wall = ([tuple(rotation @ vertex + offset) for vertex in WALL[0]], WALL[1])
                    result = flashing_render_clearances(source, [wall])
                    self.assertEqual(result["a"][1]["touching_faces"], 1)
                    self.assertAlmostEqual(result["a"][1]["overlap_area_m2"], .13)
                    self.assertEqual(result["b"][1]["touching_faces"], 0)
                    sections = []
                    for key in ("a", "b"):
                        deltas, report = result[key]
                        self.assertEqual(report["moved_vertices"], 4)
                        sections.append(sorted(
                            tuple(np.asarray(vertex) + delta)
                            for original, vertex, delta in zip(originals[key][0], source[key][0], deltas)
                            if original[1] == 2
                        ))
                    np.testing.assert_allclose(sections[0], sections[1], atol=1e-12)

    def test_roundoff_at_a_shared_edge_propagates_but_a_point_contact_does_not(self):
        vertices, faces, outward = rake(2, 4, 1, 0)
        shifted = ([(x, y + 1e-8, z) for x, y, z in vertices], faces, outward)
        # This third rake touches only the upper outer corner of the apex.
        point_contact = rake(2, 4, 1.17, 2.17)
        result = flashing_render_clearances({"a": rake(), "b": shifted,
                                           "point": point_contact}, [WALL])
        self.assertEqual(result["b"][1]["moved_vertices"], 4)
        self.assertEqual(result["point"][1]["moved_vertices"], 0)

    def test_missing_overlap_opposite_facing_contact_and_inner_face_are_noops(self):
        walls = [
            [],
            [([(x, y + 10, z) for x, y, z in WALL[0]], WALL[1])],
            [(WALL[0], [(3, 2, 1, 0)])],
            [([(.08, y, z) for _, y, z in WALL[0]], [(3, 2, 1, 0)])],
        ]
        for candidates in walls:
            with self.subTest(walls=candidates):
                deltas, report = flashing_render_clearances({"trim": rake()}, candidates)["trim"]
                self.assertTrue(all(delta == (0, 0, 0) for delta in deltas))
                self.assertEqual(report["moved_vertices"], 0)

    def test_repeated_source_evaluation_is_deterministic_and_clearance_is_bounded(self):
        source = {"trim": rake()}
        self.assertEqual(flashing_render_clearances(source, [WALL]),
                         flashing_render_clearances(source, [WALL]))
        for amount in (0, -.001, .006, float("nan")):
            with self.assertRaises(ValueError):
                flashing_render_clearances(source, [WALL], clearance=amount)


class NamedItems(list):
    def get(self, name):
        return next((item for item in self if item.name == name), None)

    def new(self, name, *unused):
        item = SimpleNamespace(name=name, data=[SimpleNamespace(vector=None) for _ in range(8)])
        self.append(item)
        return item


class RenderDisplacementRerunTest(unittest.TestCase):
    def test_actual_modifier_writer_replaces_offset_and_cleans_a_later_noop(self):
        path = Path(__file__).resolve().parents[1] / "building_author/templates/presentation_phase.py"
        function = next(node for node in ast.parse(path.read_text()).body
                        if isinstance(node, ast.FunctionDef) and node.name == "apply_render_displacements")
        namespace = {
            "json": json, "Vector": np.asarray,
            "bpy": SimpleNamespace(data=SimpleNamespace(
                node_groups=SimpleNamespace(get=lambda name: SimpleNamespace(name=name)))),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
        class Object(dict):
            pass
        obj = Object()
        obj.modifiers = NamedItems()
        vertices = copy.deepcopy(rake()[0])
        original_vertices = copy.deepcopy(vertices)
        obj.data = SimpleNamespace(users=1, attributes=NamedItems(), vertices=vertices)
        obj.matrix_world = SimpleNamespace(to_3x3=lambda: SimpleNamespace(inverted=lambda: np.eye(3)))
        placement = obj.matrix_world
        kwargs = dict(modifier_name="clearance", attribute_name="clearance_delta",
                      group_name="clearance_graph", report_key="clearance_report")
        apply = namespace["apply_render_displacements"]
        deltas, report = flashing_render_clearances({"trim": rake()}, [WALL])["trim"]
        for _ in range(2):
            apply(obj, deltas, report, **kwargs)
            self.assertEqual(len(obj.modifiers), 1)
            self.assertEqual(len(obj.data.attributes), 1)
            np.testing.assert_allclose([item.vector for item in obj.data.attributes[0].data], deltas)
            self.assertEqual(obj.data.vertices, original_vertices)
            self.assertIs(obj.matrix_world, placement)
        noop, noop_report = flashing_render_clearances({"trim": rake()}, [])["trim"]
        apply(obj, noop, noop_report, **kwargs)
        self.assertEqual(len(obj.modifiers), 0)
        self.assertEqual(len(obj.data.attributes), 0)
        self.assertNotIn("clearance_report", obj)


class PresentationFlashingCompetitorsTest(unittest.TestCase):
    def test_the_board_competes_with_the_roof_body_and_its_covering(self):
        """The flush gable-plane partner is the roof the board is seated on."""

        path = Path(__file__).resolve().parents[1] / "building_author/templates/presentation_phase.py"
        tree = ast.parse(path.read_text())
        call = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "flashing_render_clearances")
        self.assertEqual(ast.unparse(call.args[1]), "wall_meshes + roof_meshes")
        assignment = next(node for node in ast.walk(tree)
                          if isinstance(node, ast.Assign)
                          and getattr(node.targets[0], "id", None) == "roof_meshes")
        text = ast.unparse(assignment.value)
        self.assertIn("roof['key']", text)
        self.assertIn(".covering", text)


if __name__ == "__main__":
    unittest.main()
