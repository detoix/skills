"""End-to-end regression checks for reusable composed gable glazing."""

from __future__ import annotations

import ast
import sys
import unittest
from collections import Counter
from itertools import permutations
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from building_author import (  # noqa: E402
    Building,
    building,
    composed_window,
    composed_window_type,
    layer,
    material,
    project,
    site,
    storey,
    wall,
    wall_type,
    window_divider,
    window_piece,
    window_rectangle,
    window_triangle,
)
from building_author import compiler, composed_windows  # noqa: E402
from building_author.values import AuthoringError  # noqa: E402


FACADE_WIDTH = 5.70
WINDOW_WIDTH = 4.42
WINDOW_CENTRE = WINDOW_WIDTH / 2.0
TRANSOM_HEIGHT = 2.30
GABLE_SPRING = 2.75
WINDOW_APEX = 4.30
WALL_THICKNESS = 0.47
PROFILE_DEPTH = 0.08
FLUSH_OFFSET = -(WALL_THICKNESS / 2.0 - PROFILE_DEPTH / 2.0)


def glazing_pieces():
    """Compose two lower lights and two rectangle-plus-triangle upper panes."""

    return [
        window_rectangle(
            0.0,
            0.0,
            WINDOW_CENTRE,
            TRANSOM_HEIGHT,
            profile_edges=("bottom", "top", "left"),
            pane="lower.left",
        ),
        window_rectangle(
            WINDOW_CENTRE,
            0.0,
            WINDOW_CENTRE,
            TRANSOM_HEIGHT,
            profile_edges=("bottom", "top", "right"),
            pane="lower.right",
        ),
        window_rectangle(
            0.0,
            TRANSOM_HEIGHT,
            WINDOW_CENTRE,
            GABLE_SPRING - TRANSOM_HEIGHT,
            profile_edges=("left",),
            pane="upper.left",
        ),
        window_rectangle(
            WINDOW_CENTRE,
            TRANSOM_HEIGHT,
            WINDOW_CENTRE,
            GABLE_SPRING - TRANSOM_HEIGHT,
            profile_edges=("right",),
            pane="upper.right",
        ),
        window_triangle(
            (0.0, GABLE_SPRING),
            (WINDOW_CENTRE, GABLE_SPRING),
            (WINDOW_CENTRE, WINDOW_APEX),
            profile_edges=("skew",),
            pane="upper.left",
        ),
        window_triangle(
            (WINDOW_CENTRE, GABLE_SPRING),
            (WINDOW_WIDTH, GABLE_SPRING),
            (WINDOW_CENTRE, WINDOW_APEX),
            profile_edges=("skew",),
            pane="upper.right",
        ),
    ]


def composed_gable_model() -> Building:
    """A minimal layered wall carrying one cross-level composed window."""

    model = Building("composed-gable-glazing")
    project(model, "project", name="Composed Gable Glazing")
    site(model, "site", project="project", name="Test Site")
    building(model, "building", site="site", name="Test Building")
    storey(model, "ground", building="building", elevation=0.0)
    storey(
        model,
        "upper-datum",
        building="building",
        elevation=TRANSOM_HEIGHT,
    )
    material(
        model,
        "wall.finish",
        ifc_name="Wall finish",
        category="plaster",
        base_color=(0.9, 0.9, 0.9),
        roughness=0.8,
    )
    material(
        model,
        "frame",
        ifc_name="Frame",
        category="metal",
        base_color=(0.08, 0.08, 0.08),
        roughness=0.3,
        metallic=0.8,
    )
    material(
        model,
        "glass",
        ifc_name="Glass",
        category="glass",
        base_color=(0.8, 0.8, 0.8),
        roughness=0.5,
        alpha=0.5,
    )
    wall_type(
        model,
        "wall.470",
        layers=[
            layer(
                "wall.finish",
                WALL_THICKNESS,
                priority=90,
                category="Wall",
            )
        ],
    )
    wall(
        model,
        "gable-wall",
        storey="ground",
        wall_type="wall.470",
        axis=((0.0, 0.0), (FACADE_WIDTH, 0.0)),
        height=5.40,
        direction_sense="NEGATIVE",
        offset_from_reference_line=WALL_THICKNESS,
    )
    composed_window_type(
        model,
        "window-type",
        profile_width=0.08,
        profile_depth=PROFILE_DEPTH,
        glazing_thickness=0.024,
        offset=FLUSH_OFFSET,
    )
    composed_window(
        model,
        "gable-window",
        wall="gable-wall",
        window_type="window-type",
        along=FACADE_WIDTH / 2.0,
        sill_height=0.0,
        pieces=glazing_pieces(),
        dividers=[
            window_divider(
                (WINDOW_CENTRE, 0.0),
                (WINDOW_CENTRE, WINDOW_APEX),
            )
        ],
        framing_material="frame",
        glazing_material="glass",
        is_external=True,
    )
    return model


class ComposedGableGlazingTest(unittest.TestCase):
    def setUp(self):
        self.model = composed_gable_model()
        self.window = next(
            item for item in self.model.operations if item.kind == "composed-window"
        )
        self.pieces = self.window.parameters["pieces"]

    def test_model_validates_and_both_batches_compile(self):
        self.model.validate()
        ast.parse(self.model.ifc_source())
        ast.parse(self.model.blender_source())

    def test_one_window_crosses_the_upper_datum_without_being_split(self):
        windows = [
            item for item in self.model.operations if item.kind == "composed-window"
        ]
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].references["wall"], "gable-wall")
        self.assertEqual(windows[0].parameters["sill_height"], 0.0)
        self.assertGreater(WINDOW_APEX, TRANSOM_HEIGHT)

    def test_payload_preserves_the_complete_window_size(self):
        payload = compiler.composed_window_payload(self.model)
        self.assertEqual(len(payload), 1)
        self.assertAlmostEqual(payload[0]["overall_width"], WINDOW_WIDTH)
        self.assertAlmostEqual(payload[0]["overall_height"], WINDOW_APEX)
        self.assertEqual(
            composed_windows.bounds(self.pieces),
            (0.0, 0.0, WINDOW_WIDTH, WINDOW_APEX),
        )

    def test_lower_rectangles_leave_the_centre_to_one_divider(self):
        lower_left, lower_right = self.pieces[:2]
        # Rectangle edge order is bottom, right, top, left.
        self.assertEqual(lower_left["profile_edges"], (0, 2, 3))
        self.assertEqual(lower_right["profile_edges"], (0, 1, 2))
        self.assertEqual(
            self.window.parameters["dividers"],
            [
                {
                    "start": (WINDOW_CENTRE, 0.0),
                    "end": (WINDOW_CENTRE, WINDOW_APEX),
                }
            ],
        )

    def test_upper_rectangles_omit_top_and_bottom_profiles(self):
        upper_left, upper_right = self.pieces[2:4]
        self.assertEqual(upper_left["profile_edges"], (3,))
        self.assertEqual(upper_right["profile_edges"], (1,))
        for piece in (upper_left, upper_right):
            self.assertNotIn(0, piece["profile_edges"])
            self.assertNotIn(2, piece["profile_edges"])

    def test_triangles_carry_only_the_sloping_profiles(self):
        left_triangle, right_triangle = self.pieces[4:]
        self.assertEqual(left_triangle["profile_edges"], (2,))
        self.assertEqual(right_triangle["profile_edges"], (1,))

    def test_each_triangle_unions_with_its_rectangle_as_one_pane(self):
        self.assertEqual(
            Counter(piece["pane"] for piece in self.pieces),
            Counter(
                {
                    "lower.left": 1,
                    "lower.right": 1,
                    "upper.left": 2,
                    "upper.right": 2,
                }
            ),
        )

    def test_composed_section_is_flush_with_the_outer_wall_face(self):
        window_type = next(
            item
            for item in self.model.operations
            if item.kind == "composed-window-type"
        )
        self.assertAlmostEqual(window_type.parameters["profile_width"], 0.08)
        self.assertAlmostEqual(window_type.parameters["profile_depth"], 0.08)
        self.assertAlmostEqual(window_type.parameters["glazing_thickness"], 0.024)
        self.assertAlmostEqual(window_type.parameters["offset"], -0.195)


class ComposedWindowTriangulationTest(unittest.TestCase):
    """The public garden glazing's five frame holes must stay closed."""

    OUTLINE = [(0, 0), (4.42, 0), (4.42, 2.842), (2.21, 4.39), (0, 2.842)]

    def dividers(self, endpoint=2.40):
        return [
            window_divider((0, 2.40), (4.42, 2.40)),
            window_divider((2.21, 0), (2.21, 4.39)),
            window_divider((3.315, 0), (3.315, endpoint)),
        ]

    def mesh(self, dividers):
        return composed_windows.composed_window_mesh(
            [window_piece(self.OUTLINE)],
            dividers,
            profile_width=0.07,
            profile_depth=0.11,
            glazing_thickness=0.024,
        )

    def assert_closed(self, mesh):
        vertices, faces, _, roles = mesh
        edges = Counter()
        directions = Counter()
        for face, role in zip(faces, roles):
            for first, second in zip(face, face[1:] + face[:1]):
                edge = (role, *sorted((first, second)))
                edges[edge] += 1
                directions[edge] += 1 if first < second else -1
        self.assertTrue(vertices)
        self.assertEqual(set(edges.values()), {2})
        self.assertEqual(set(directions.values()), {0})

    def assert_cap_coverage(self, mesh, role, depth, expected):
        vertices, faces, _, roles = mesh
        caps = [
            Polygon([(vertices[index][0], vertices[index][2]) for index in face])
            for face, face_role in zip(faces, roles)
            if face_role == role
            and all(abs(vertices[index][1] + depth / 2) < 1e-12 for index in face)
        ]
        coverage = unary_union(caps)
        self.assertAlmostEqual(coverage.symmetric_difference(expected).area, 0, places=9)
        self.assertAlmostEqual(sum(face.area for face in caps), coverage.area, places=9)

    def test_exact_transom_and_band_edge_endpoints_cover_all_five_frame_holes(self):
        outline = Polygon(self.OUTLINE)
        for endpoint in (2.40, 2.435, 2.43501):
            with self.subTest(endpoint=endpoint):
                dividers = self.dividers(endpoint)
                mesh = self.mesh(dividers)
                expected_frame = unary_union(
                    [outline.boundary.buffer(0.07, join_style=2)]
                    + [
                        LineString((divider["start"], divider["end"])).buffer(
                            0.035, cap_style=2
                        )
                        for divider in dividers
                    ]
                ).intersection(outline)
                self.assertEqual(len(expected_frame.interiors), 5)
                self.assert_closed(mesh)
                self.assert_cap_coverage(mesh, "framing", 0.11, expected_frame)
                self.assert_cap_coverage(mesh, "glazing", 0.024, outline)

    def test_exact_garden_dimensions_validate_and_compile_without_endpoint_workaround(self):
        model = composed_gable_model()
        window = next(item for item in model.operations if item.kind == "composed-window")
        window.parameters.update(pieces=[window_piece(self.OUTLINE)], dividers=self.dividers())
        section = next(
            item for item in model.operations if item.kind == "composed-window-type"
        )
        section.parameters.update(profile_width=0.07, profile_depth=0.11)
        model.validate()
        ast.parse(model.ifc_source())
        ast.parse(model.blender_source())
        payload = compiler.composed_window_payload(model)[0]
        self.assertEqual((payload["overall_width"], payload["overall_height"]), (4.42, 4.39))
        self.assertEqual(payload["dividers"][-1]["end"], (3.315, 2.40))

    def test_divider_order_is_deterministic_at_each_transom_endpoint(self):
        for endpoint in (2.40, 2.435, 2.43501):
            dividers = self.dividers(endpoint)
            expected = self.mesh(dividers)
            for order in permutations(dividers):
                with self.subTest(endpoint=endpoint, order=order):
                    self.assertEqual(self.mesh(order), expected)
        self.assertEqual(self.mesh(self.dividers(2.40)), self.mesh(self.dividers(2.435)))

    def test_piece_order_is_deterministic(self):
        arguments = dict(profile_width=0.08, profile_depth=0.08, glazing_thickness=0.024)
        dividers = [window_divider((WINDOW_CENTRE, 0), (WINDOW_CENTRE, WINDOW_APEX))]
        self.assertEqual(
            composed_windows.composed_window_mesh(glazing_pieces(), dividers, **arguments),
            composed_windows.composed_window_mesh(
                list(reversed(glazing_pieces())), dividers, **arguments
            ),
        )

    def test_concave_prism_preserves_multiple_holes(self):
        polygon = Polygon(
            [(0, 0), (7, 0), (7, 3), (5, 3), (5, 5), (0, 5)],
            holes=[
                [(0.1, 0.1), (3.0, 0.1), (3.0, 4.9), (0.1, 4.9)],
                [(3.1, 0.1), (6.9, 0.1), (6.9, 2.9), (3.1, 2.9)],
            ],
        )
        mesh = ([], [], [], [])
        composed_windows._append_area_prism(*mesh, polygon, -0.055, 0.055, "framing")
        self.assert_closed(mesh)
        self.assert_cap_coverage(mesh, "framing", 0.11, polygon)

    def test_missing_constrained_triangulation_has_an_actionable_error(self):
        with patch.object(composed_windows.shapely, "constrained_delaunay_triangles", None):
            with self.assertRaisesRegex(
                AuthoringError, r"Shapely >= 2\.1.*GEOS >= 3\.10; upgrade Shapely"
            ):
                self.mesh(self.dividers())

    def test_old_geos_has_an_actionable_error(self):
        with patch.object(composed_windows.shapely, "geos_version", (3, 9, 0)):
            with self.assertRaisesRegex(
                AuthoringError, r"GEOS >= 3\.10; upgrade Shapely"
            ):
                self.mesh(self.dividers())


if __name__ == "__main__":
    unittest.main()
