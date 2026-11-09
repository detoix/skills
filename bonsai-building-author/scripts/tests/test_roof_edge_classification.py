"""Local roof folds, including concave faces and BMesh storage permutations."""

import itertools
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from building_author import trims


def unit(vector):
    length = math.sqrt(sum(component * component for component in vector))
    return tuple(component / length for component in vector)


def cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def mesh_edges(coordinates, polygons):
    """Only the BMesh vertex/face/loop fields read by the production adapter."""
    vertices = [SimpleNamespace(co=coordinate) for coordinate in coordinates]
    edges = {}
    for number, polygon in enumerate(polygons):
        origin = coordinates[polygon[0]]
        relative = [tuple(coordinates[index][axis] - origin[axis] for axis in range(3))
                    for index in polygon]
        crosses = [cross(first, second)
                   for first, second in zip(relative, relative[1:] + relative[:1])]
        normal = unit(tuple(sum(vector[axis] for vector in crosses) for axis in range(3)))
        face = SimpleNamespace(name=f"face-{number}", normal=normal)
        for first, second in zip(polygon, polygon[1:] + polygon[:1]):
            key = tuple(sorted((first, second)))
            edge = edges.setdefault(key, SimpleNamespace(
                verts=[vertices[first], vertices[second]], link_faces=[], link_loops=[]
            ))
            edge.link_faces.append(face)
            edge.link_loops.append(SimpleNamespace(
                face=face,
                vert=vertices[first],
                link_loop_next=SimpleNamespace(vert=vertices[second]),
            ))
    return edges


class RoofEdgeClassificationTest(unittest.TestCase):
    PITCH = math.tan(math.radians(35))
    COORDINATES = [
        (0, 0, 0), (17, 0, 0), (17, 4.5, 4.5 * PITCH), (0, 4.5, 4.5 * PITCH),
        (17, 9, 0), (13.35, 9, 0), (13.35, 10.5, 0), (10.5, 10.5, 2.85 * PITCH),
        (7.65, 10.5, 0), (7.65, 9, 0), (0, 9, 0), (10.5, 6.15, 2.85 * PITCH),
    ]
    FACES = [(0, 1, 2, 3), (3, 2, 4, 5, 11, 9, 10), (11, 5, 6, 7), (9, 11, 7, 8)]
    FOLDS = {(2, 3): trims.RIDGE, (7, 11): trims.RIDGE,
             (5, 11): trims.VALLEY, (9, 11): trims.VALLEY}

    def assert_folds(self, edges, expected):
        actual = {key: kind for key, edge in edges.items()
                  if (kind := trims.edge_kind_from_bmesh(edge)) is not None}
        self.assertEqual(actual, expected)
        self.assertEqual(
            {key for key, kind in actual.items() if kind in (trims.RIDGE, trims.HIP)},
            {key for key, kind in expected.items() if kind in (trims.RIDGE, trims.HIP)},
        )

    def test_exact_t_roof_has_two_ridges_and_two_uncapped_valleys(self):
        self.assert_folds(mesh_edges(self.COORDINATES, self.FACES), self.FOLDS)

    def test_face_edge_loop_and_polygon_storage_orders_preserve_each_valley(self):
        for face_order, edge_order, loop_order, polygon_start in itertools.product((False, True), repeat=4):
            with self.subTest(face_order=face_order, edge_order=edge_order,
                              loop_order=loop_order, polygon_start=polygon_start):
                faces = [face[1:] + face[:1] if polygon_start else face for face in self.FACES]
                edges = mesh_edges(self.COORDINATES, faces)
                for edge in edges.values():
                    if face_order:
                        edge.link_faces.reverse()
                    if edge_order:
                        edge.verts.reverse()
                    if loop_order:
                        edge.link_loops.reverse()
                self.assert_folds(edges, self.FOLDS)

    def test_translated_rotated_and_mirrored_t_roofs_preserve_local_folds(self):
        for angle, mirror, offset in (
            (0, False, (12345, -24680, 125)),
            (37, False, (120, -450, 10)),
            (90, False, (-20, 30, -5)),
            (0, True, (17, 0, 0)),
            (137, True, (80, 160, 25)),
        ):
            with self.subTest(angle=angle, mirror=mirror, offset=offset):
                radians = math.radians(angle)
                cosine, sine = math.cos(radians), math.sin(radians)
                coordinates = []
                for x, y, z in self.COORDINATES:
                    x = -x if mirror else x
                    coordinates.append((x * cosine - y * sine + offset[0],
                                        x * sine + y * cosine + offset[1], z + offset[2]))
                # Reflection reverses handedness; reverse loops to retain
                # outward normals, just as a correctly wound mirrored mesh.
                faces = [tuple(reversed(face)) if mirror else face for face in self.FACES]
                edges = mesh_edges(coordinates, faces)
                self.assert_folds(edges, self.FOLDS)
                for edge in edges.values():
                    edge.link_faces.reverse()
                    edge.verts.reverse()
                self.assert_folds(edges, self.FOLDS)

    def test_triangulating_the_concave_face_adds_no_cap_runs(self):
        faces = [self.FACES[0], (3, 2, 11), (3, 11, 9), (3, 9, 10),
                 (2, 4, 5), (2, 5, 11), *self.FACES[2:]]
        edges = mesh_edges(self.COORDINATES, faces)
        self.assert_folds(edges, self.FOLDS)
        for seam in ((3, 11), (3, 9), (2, 5), (2, 11)):
            self.assertIsNone(trims.edge_kind_from_bmesh(edges[seam]))

    def test_real_hipped_roof_still_caps_all_four_hips(self):
        coordinates = [(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0), (2, 2, 2 * self.PITCH)]
        faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
        edges = mesh_edges(coordinates, faces)
        expected = {(index, 4): trims.HIP for index in range(4)}
        self.assert_folds(edges, expected)
        for edge in edges.values():
            edge.link_faces.reverse()
            edge.verts.reverse()
        self.assert_folds(edges, expected)

    def test_float32_normal_noise_does_not_cap_coplanar_seams(self):
        pitch = math.radians(35)
        first = (0, math.sin(pitch), math.cos(pitch))
        for perturbation in (-2e-7, 0, 2e-7):
            second = (0, math.sin(pitch + perturbation), math.cos(pitch + perturbation))
            self.assertIsNone(trims.edge_kind(first, second, (1, 0, 0)))
            self.assertIsNone(trims.edge_kind(second, first, (-1, 0, 0)))

    def test_local_interior_points_into_both_faces(self):
        edges = mesh_edges(self.COORDINATES, self.FACES)
        for key in ((5, 11), (9, 11)):
            edge = edges[key]
            first, second = edge.link_faces
            for face, neighbour in ((first, second), (second, first)):
                interior = cross(face.normal, trims.face_edge_direction(edge, face))
                # Moving into either valley face rises above the neighbour's
                # plane, independently confirming a concave local fold.
                self.assertGreater(sum(a * b for a, b in zip(interior, neighbour.normal)), 0)

    def test_boundary_and_nonmanifold_edges_have_no_cap_classification(self):
        edges = mesh_edges(self.COORDINATES, self.FACES)
        self.assertIsNone(trims.edge_kind_from_bmesh(edges[(0, 1)]))
        edge = edges[(5, 11)]
        edge.link_faces.append(SimpleNamespace(normal=(0, 0, 1)))
        self.assertIsNone(trims.edge_kind_from_bmesh(edge))


if __name__ == "__main__":
    unittest.main()
