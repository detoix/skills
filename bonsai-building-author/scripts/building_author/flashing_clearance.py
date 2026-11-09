"""Presentation clearance for the exposed faces of generated verge flashings.

The IFC section stays flush and inboard. Only the outer face moves outward in
the rendered derivative, clearing a coplanar competitor surface - a wall face,
or the roof body and covering the board is seated against; the back face,
elevations and object placement stay fixed. Adjacent rake faces share the same
offset so their apex stays closed.
"""

import math

import numpy as np
from shapely.geometry import Polygon

from .roof_recess import PLANE_TOLERANCE, _face


RENDER_CLEARANCE = 0.001


def _face_record(vertices, face, origin):
    # One common origin keeps Newell normals and plane distances stable for
    # georeferenced coordinates. Output displacements remain world vectors.
    points = [tuple(np.asarray(vertices[index], dtype=float) - origin) for index in face]
    record = _face(points, range(len(points)))
    return None if record is None else (*record, points)


def _projection(record, axis):
    """Compare both faces in one projection, even at a dominant-axis tie."""

    if record[2] == axis:
        return record[3]
    return Polygon([tuple(point[i] for i in range(3) if i != axis)
                    for point in record[4]])


def _shares_edge(first, second):
    """Require positive collinear edge overlap, allowing coordinate roundoff."""

    a = list(first.exterior.coords)
    b = list(second.exterior.coords)
    for start, end in zip(a, a[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length <= 1e-7:
            continue
        ux, uy = dx / length, dy / length
        for other_start, other_end in zip(b, b[1:]):
            offsets = [(point[0] - start[0], point[1] - start[1])
                       for point in (other_start, other_end)]
            if any(abs(ux * y - uy * x) > PLANE_TOLERANCE for x, y in offsets):
                continue
            low, high = sorted(ux * x + uy * y for x, y in offsets)
            if min(length, high) - max(0.0, low) > 1e-7:
                return True
    return False


def flashing_render_clearances(flashings, competitor_meshes, *, clearance=RENDER_CLEARANCE):
    """Return ``{key: (world_vertex_deltas, report)}`` without changing inputs.

    Each flashing is ``(world_vertices, faces, outward_horizontal_direction)``.
    Call once for the roof's complete flashing assembly: even when only one
    rake touches a competitor surface, its coplanar apex partner must receive
    the same clearance. A competitor is any coplanar surface the board is
    flush with by construction - a wall face, or the roof body and its
    covering. Competitor planes are computed once for the entire batch.
    """

    if not math.isfinite(clearance) or not 0 < clearance <= 0.005:
        raise ValueError("flashing clearance must be positive and at most 5 mm")
    origin = next((np.asarray(mesh[0][0], dtype=float)
                   for _, mesh in sorted(flashings.items()) if len(mesh[0])), np.zeros(3))
    competitor_records = [
        record
        for vertices, faces in competitor_meshes
        for face in faces
        if (record := _face_record(vertices, face, origin)) is not None
    ]
    records = {}
    for key, (vertices, faces, outward) in sorted(flashings.items()):
        outward = np.array(outward, dtype=float, copy=True)
        length = float(np.linalg.norm(outward))
        if not np.all(np.isfinite(outward)) or length < 1e-9:
            raise ValueError(f"{key} needs a finite outward direction")
        outward /= length
        if abs(float(outward[2])) > 1e-6:
            raise ValueError(f"{key} outward direction must be horizontal")
        for index, face in enumerate(faces):
            record = _face_record(vertices, face, origin)
            if record is not None and float(record[0] @ outward) > 1 - 1e-8:
                records[(key, index)] = record

    selected = set()
    overlaps = {key: 0.0 for key in flashings}
    direct = {key: 0 for key in flashings}
    for identity, (normal, distance, axis, polygon, _) in records.items():
        area = 0.0
        for competitor in competitor_records:
            wn, wd = competitor[:2]
            if (float(normal @ wn) < 1 - 1e-8
                    or abs(distance - wd) > PLANE_TOLERANCE):
                continue
            wp = _projection(competitor, axis)
            # Most competitor triangles are nowhere near this short rake face.
            if not polygon.intersects(wp):
                continue
            overlap = polygon.intersection(wp).area / abs(float(normal[axis]))
            if overlap > 1e-6:
                area += overlap
        if area:
            selected.add(identity)
            overlaps[identity[0]] += area
            direct[identity[0]] += 1

    # Propagate only over shared edges, not over disconnected faces elsewhere
    # on the same plane. This also joins triangulated/material-split faces.
    pending = sorted(selected)
    while pending:
        normal, distance, axis, polygon, _ = records[pending.pop()]
        for identity, other in records.items():
            if identity in selected:
                continue
            other_normal, other_distance = other[:2]
            if (float(normal @ other_normal) > 1 - 1e-8
                    and abs(distance - other_distance) <= PLANE_TOLERANCE
                    and _shares_edge(polygon, _projection(other, axis))):
                selected.add(identity)
                pending.append(identity)

    result = {}
    for key, (vertices, faces, outward) in sorted(flashings.items()):
        outer_points = {
            tuple(round(float(value), 7) for value in vertices[index])
            for identity in selected if identity[0] == key
            for index in faces[identity[1]]
        }
        outward = np.array(outward, dtype=float, copy=True)
        outward /= np.linalg.norm(outward)
        # Preserve elevation exactly, including small normal-rounding errors.
        outward[2] = 0.0
        outward /= np.linalg.norm(outward)
        movement = tuple(float(value) for value in outward * clearance)
        deltas = [
            movement if tuple(round(float(value), 7) for value in vertex) in outer_points
            else (0.0, 0.0, 0.0)
            for vertex in vertices
        ]
        result[key] = (deltas, {
            "clearance_m": float(clearance),
            "touching_faces": direct[key],
            "clearance_faces": sum(1 for identity in selected if identity[0] == key),
            "overlap_area_m2": float(overlaps[key]),
            "moved_vertices": sum(1 for delta in deltas if delta != (0.0, 0.0, 0.0)),
            "max_displacement_m": float(clearance) if outer_points else 0.0,
        })
    return result
