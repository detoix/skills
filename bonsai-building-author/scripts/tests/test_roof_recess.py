import copy
import json
import unittest

from building_author.roof_recess import roof_wall_recess


VERTICES = [(0,0,0),(2,0,0),(2,2,0),(0,2,0),
            (0,0,1),(2,0,1),(2,2,1),(0,2,1)]
FACES = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),
         (2,3,7,6),(3,0,4,7)]


class RoofRecessTest(unittest.TestCase):
    def test_only_competing_side_recedes_without_changing_source(self):
        original = copy.deepcopy(VERTICES)
        wall = ([(0,0,.2),(2,0,.2),(2,0,.8),(0,0,.8)], [(0,1,2,3)])
        deltas, report = roof_wall_recess(VERTICES, FACES, [wall])
        self.assertEqual(VERTICES, original)
        for point, delta in zip(VERTICES, deltas):
            self.assertAlmostEqual(delta[0], 0)
            self.assertAlmostEqual(delta[2], 0)
            self.assertAlmostEqual(delta[1], .001 if point[1] == 0 else 0)
        self.assertEqual(report['competing_faces'], 1)

    def test_hidden_contact_and_distant_wall_are_noops(self):
        for wall in [
            ([(0,0,.2),(2,0,.2),(2,0,.8),(0,0,.8)], [(3,2,1,0)]),
            ([(3,0,.2),(4,0,.2),(4,0,.8),(3,0,.8)], [(0,1,2,3)]),
        ]:
            deltas, report = roof_wall_recess(VERTICES, FACES, [wall])
            self.assertEqual(report['competing_faces'], 0)
            self.assertTrue(all(all(c == 0 for c in d) for d in deltas))

    def test_deterministic_and_bounded(self):
        args = (VERTICES, FACES, [(VERTICES, FACES)])
        self.assertEqual(roof_wall_recess(*args), roof_wall_recess(*args))
        _, report = roof_wall_recess(*args)
        json.dumps(report)
        self.assertLess(report['max_displacement_m'], .002)
        with self.assertRaises(ValueError):
            roof_wall_recess(*args, recess=.1)

    def test_disconnected_coplanar_piece_does_not_move(self):
        vertices = VERTICES + [(x+5,y,z) for x,y,z in VERTICES]
        faces = FACES + [tuple(i+8 for i in face) for face in FACES]
        wall = ([(0,0,.2),(2,0,.2),(2,0,.8),(0,0,.8)], [(0,1,2,3)])
        deltas, _ = roof_wall_recess(vertices, faces, [wall])
        self.assertTrue(all(all(c == 0 for c in d) for d in deltas[8:]))

    def test_sloped_translated_roof_preserves_adjacent_planes(self):
        vertices = [(x+20,y-8,z+.5*y+4) for x,y,z in VERTICES]
        wall = ([(20,-8,4.2),(22,-8,4.2),(22,-8,4.8),(20,-8,4.8)], [(0,1,2,3)])
        deltas, _ = roof_wall_recess(vertices, FACES, [wall])
        for point, delta in zip(vertices,deltas):
            self.assertAlmostEqual(delta[0],0)
            self.assertAlmostEqual(delta[2]-.5*delta[1],0)
            self.assertAlmostEqual(delta[1],.001 if point[1]==-8 else 0)

    def test_split_material_vertices_remain_coincident(self):
        vertices = [VERTICES[i] for face in FACES for i in face]
        faces = [tuple(range(i,i+4)) for i in range(0,len(vertices),4)]
        wall = ([(0,0,.2),(2,0,.2),(2,0,.8),(0,0,.8)], [(0,1,2,3)])
        deltas, _ = roof_wall_recess(vertices,faces,[wall])
        moved = {}
        for point,delta in zip(vertices,deltas):
            if point in moved:
                self.assertEqual(moved[point],delta)
            moved[point]=delta


if __name__ == '__main__':
    unittest.main()
