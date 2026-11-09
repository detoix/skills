"""Small, render-only roof-body recesses at competing wall surfaces.

No IFC declarations or representations are changed. The presentation phase
uses these displacements in a non-applied modifier on the imported roof mesh.
The millimetre is a visualization tolerance, not a construction dimension.
"""
from collections import defaultdict

import numpy as np
from shapely.geometry import Polygon

RENDER_RECESS = 0.001
PLANE_TOLERANCE = 1e-5


def _face(vertices, indices):
    points = np.asarray([vertices[i] for i in indices], dtype=float)
    normal = np.sum(np.cross(points, np.roll(points, -1, axis=0)), axis=0)
    length = np.linalg.norm(normal)
    if length < 1e-10:
        return None
    normal /= length
    distance = float(points[0] @ normal)
    axis = int(np.argmax(np.abs(normal)))
    polygon = Polygon(np.delete(points, axis, axis=1))
    if not polygon.is_valid or polygon.area < 1e-8:
        return None
    return normal, distance, axis, polygon


def roof_wall_recess(vertices, faces, wall_meshes, *, recess=RENDER_RECESS):
    """Return world-space vertex deltas and diagnostics, without mutation.

Only same-facing, coplanar roof/wall surfaces with positive overlapping area
select a roof plane. A hidden back-to-front contact selects nothing. Adjacent
planes constrain their shared vertices, so this is a plane inset rather than
object scaling or averaged-normal shrinkage. Roofs away from walls are no-ops.
"""
    if not 0 < recess <= 0.005:
        raise ValueError("render recess must be positive and at most 5 mm")
    records = [_face(vertices, face) for face in faces]
    wall_records = [
        record
        for wall_vertices, wall_faces in wall_meshes
        for face in wall_faces
        if (record := _face(wall_vertices, face)) is not None
    ]
    selected = set()
    overlap_area = 0.0
    for index, record in enumerate(records):
        if record is None:
            continue
        normal, distance, axis, polygon = record
        for other in wall_records:
            wn, wd, wa, wp = other
            if (axis != wa or float(normal @ wn) < 1 - 1e-8
                    or abs(distance - wd) > PLANE_TOLERANCE):
                continue
            area = polygon.intersection(wp).area / abs(normal[axis])
            if area > 1e-6:
                selected.add(index)
                overlap_area += area

    # A face can be triangulated or split by material. Treat its entire plane
    # consistently so shared edges do not crack when one triangle is covered.
    pending = list(sorted(selected))
    while pending:
        parent = records[pending.pop()]
        for index, record in enumerate(records):
            if index in selected or record is None:
                continue
            if (float(record[0] @ parent[0]) > 1 - 1e-8
                    and abs(record[1] - parent[1]) < PLANE_TOLERANCE
                    and record[3].boundary.intersection(parent[3].boundary).length > 1e-7):
                selected.add(index)
                pending.append(index)

    # IFC shape aspects may duplicate vertices at a material boundary. Gather
    # incident planes by position, not by those unrelated vertex indices.
    incidence = defaultdict(set)
    point_keys = [tuple(round(float(c), 7) for c in v) for v in vertices]
    for index, face in enumerate(faces):
        if records[index] is not None:
            for vertex in face:
                incidence[point_keys[vertex]].add(index)
    moves = {}
    for point, indices in incidence.items():
        if not selected.intersection(indices):
            moves[point] = np.zeros(3)
            continue
        constraints = {}
        for index in sorted(indices):
            normal = records[index][0]
            key = tuple(np.round(normal, 7))
            constraints[key] = -recess if index in selected else 0.0
        matrix = np.asarray(list(constraints))
        target = np.asarray(list(constraints.values()))
        delta, *_ = np.linalg.lstsq(matrix, target, rcond=None)
        if np.max(np.abs(matrix @ delta - target)) > recess * 0.05:
            raise ValueError("roof recess has incompatible planes at " + str(point))
        if np.linalg.norm(delta) > 4 * recess:
            raise ValueError("roof recess exceeds bounded corner allowance at " + str(point))
        moves[point] = delta
    deltas = [tuple(float(c) for c in moves.get(point, np.zeros(3))) for point in point_keys]
    return deltas, {
        "recess_m": recess,
        "competing_faces": len(selected),
        "overlap_area_m2": overlap_area,
        "moved_vertices": sum(1 for d in deltas if np.linalg.norm(d) > 1e-9),
        "max_displacement_m": max((float(np.linalg.norm(d)) for d in deltas), default=0.0),
    }
