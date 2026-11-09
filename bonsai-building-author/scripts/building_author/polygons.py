"""Planar polygon helpers shared by roof declarations.

Pure Python and free of Blender, IFC, and numpy, so every function here runs
in `scripts/tests/` without a runtime. Roof overhang is solved here rather
than in the skeleton: offsetting each edge by its own overhang and mitring
the neighbours produces a plain polygon that any straight skeleton accepts
unchanged.
"""

from __future__ import annotations

from .values import AuthoringError

Point = tuple[float, float]

_PARALLEL_EPS = 1e-9


def signed_area(points: list[Point]) -> float:
    """Return twice the signed area; positive when counter-clockwise."""

    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return total


def is_counter_clockwise(points: list[Point]) -> bool:
    return signed_area(points) > 0


def contains(point: Point, polygon: list[Point]) -> bool:
    """Even-odd point-in-polygon test."""

    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        xi, yi = polygon[index]
        xj, yj = polygon[index - 1]
        if (yi > y) != (yj > y):
            crossing = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < crossing:
                inside = not inside
    return inside


def _intersect(
    origin_a: Point,
    direction_a: Point,
    origin_b: Point,
    direction_b: Point,
) -> Point | None:
    """Intersect two lines given as origin plus direction."""

    denominator = (
        direction_a[0] * direction_b[1] - direction_a[1] * direction_b[0]
    )
    if abs(denominator) < _PARALLEL_EPS:
        return None
    delta_x = origin_b[0] - origin_a[0]
    delta_y = origin_b[1] - origin_a[1]
    t = (delta_x * direction_b[1] - delta_y * direction_b[0]) / denominator
    return (
        origin_a[0] + direction_a[0] * t,
        origin_a[1] + direction_a[1] * t,
    )


def _normalize(x: float, y: float) -> Point:
    length = (x * x + y * y) ** 0.5
    if length == 0.0:
        return (1.0, 0.0)
    return (x / length, y / length)


def offset_polygon(
    edges: list[tuple[Point, Point, float]],
) -> list[Point]:
    """Offset each edge outward by its own overhang and mitre the corners.

    ``edges`` are ``(start, end, overhang)`` in boundary order. Each edge is
    pushed along its outward normal by its own overhang, then consecutive
    offset lines are intersected, so neighbouring edges carrying different
    overhangs still meet in a single corner. Parallel neighbours cannot be
    intersected and fall back to the plain offset point.
    """

    if len(edges) < 3:
        raise AuthoringError("a roof boundary needs at least three edges")

    base = [start for start, _, _ in edges]
    outward_sign = 1.0 if is_counter_clockwise(base) else -1.0

    lines = []
    for start, end, overhang in edges:
        direction = _normalize(end[0] - start[0], end[1] - start[1])
        normal = (
            direction[1] * outward_sign,
            -direction[0] * outward_sign,
        )
        lines.append(
            (
                (
                    start[0] + normal[0] * overhang,
                    start[1] + normal[1] * overhang,
                ),
                direction,
                normal,
                overhang,
            )
        )

    result: list[Point] = []
    for index in range(len(edges)):
        previous_origin, previous_direction, _, _ = lines[index - 1]
        origin, direction, normal, overhang = lines[index]
        corner = _intersect(
            previous_origin, previous_direction, origin, direction
        )
        if corner is None:
            start = edges[index][0]
            corner = (
                start[0] + normal[0] * overhang,
                start[1] + normal[1] * overhang,
            )
        result.append(corner)
    return result


def wall_footprint(
    start: Point,
    end: Point,
    thickness: float,
    offset: float,
    direction_sense: str = "POSITIVE",
) -> list[Point]:
    """The oriented rectangle a layered wall occupies in plan.

    Mirrors the same `IfcMaterialLayerSetUsage` placement `wall_payload`
    resolves: `offset` is the perpendicular distance from the reference line
    to the layer set's base, and `direction_sense` says which side of that
    base the layers stack towards - `POSITIVE` towards the left of the wall
    walked from `start` to `end`, `NEGATIVE` towards the right. Used to gather
    obstacle rectangles for space detection; a virtual element uses the same
    shape at a fixed, small thickness in place of a declared layer set.
    """

    direction = _normalize(end[0] - start[0], end[1] - start[1])
    left = (-direction[1], direction[0])
    near, far = (offset, offset + thickness)
    if direction_sense == "NEGATIVE":
        near, far = (offset - thickness, offset)
    return [
        (start[0] + left[0] * near, start[1] + left[1] * near),
        (end[0] + left[0] * near, end[1] + left[1] * near),
        (end[0] + left[0] * far, end[1] + left[1] * far),
        (start[0] + left[0] * far, start[1] + left[1] * far),
    ]


def wall_interval_footprint(
    start: Point,
    end: Point,
    thickness: float,
    offset: float,
    along: float,
    width: float,
    direction_sense: str = "POSITIVE",
) -> list[Point]:
    """Return an exact-width slice through a wall's plan footprint.

    Unlike an opening cutter, this rectangle has no robustness reach beyond
    either wall face. It is the physical finish area under a floor-level
    opening, measured by the same reference-line ``along`` as that opening.
    """

    direction = _normalize(end[0] - start[0], end[1] - start[1])
    interval_start = (
        start[0] + direction[0] * (along - width / 2.0),
        start[1] + direction[1] * (along - width / 2.0),
    )
    interval_end = (
        start[0] + direction[0] * (along + width / 2.0),
        start[1] + direction[1] * (along + width / 2.0),
    )
    return wall_footprint(
        interval_start,
        interval_end,
        thickness,
        offset,
        direction_sense,
    )


def bounds(points: list[Point]) -> tuple[float, float, float, float]:
    """Return ``(min_u, max_u, min_v, max_v)`` for a set of planar points."""

    us = [u for u, _ in points]
    vs = [v for _, v in points]
    return min(us), max(us), min(vs), max(vs)
