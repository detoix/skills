"""Derive `IfcRelConnectsPathElements` from declared wall axes.

Walls are connected because their reference lines touch, not because the
script says so. That is how a wall grid is drawn, and it means a corner cannot
disagree with the geometry that produced it.

`ifcopenshell.api.geometry.connect_wall` can infer the same relationships by
intersecting body geometry at runtime. This module derives them from the
declared coordinates instead: the declaration is exact, the derivation is
testable without Blender, and the result is deterministic.

The connection types are IFC's own: `ATSTART` and `ATEND` for an axis end,
`ATPATH` for a wall whose path is met somewhere along its length.

Reference lines are drawn in plan, so touching in plan is necessary but not
sufficient: walls also have to share the height at which they touch. A plinth
run under its own wall shares that wall's axis exactly, and stacking is not a
junction.
"""

from __future__ import annotations

from typing import Any

# Declared coordinates are meant to coincide exactly; this only absorbs the
# float error of writing 0.1 + 0.2. It is deliberately far below any dimension
# a building script would express.
TOLERANCE = 1e-6


def _same_point(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= TOLERANCE and abs(a[1] - b[1]) <= TOLERANCE


def _parameter_on_axis(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float | None:
    """Where `point` falls along the axis, or None if it is not on it.

    Returns the normalised distance from `start`, so 0.0 and 1.0 are the ends.
    """

    axis_x, axis_y = end[0] - start[0], end[1] - start[1]
    length_squared = axis_x * axis_x + axis_y * axis_y
    if length_squared == 0.0:
        return None
    offset_x, offset_y = point[0] - start[0], point[1] - start[1]
    # Distance from the infinite line, as a cross product over the length.
    if abs(offset_x * axis_y - offset_y * axis_x) > TOLERANCE * length_squared**0.5:
        return None
    return (offset_x * axis_x + offset_y * axis_y) / length_squared


def _shares_height(wall: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether the two walls exist at a common height.

    Touching exactly - a plinth's top at the base of the wall above it - is
    stacking, not a junction, so the overlap has to be real.
    """

    lowest_top = min(
        wall["base_z"] + wall["height"], other["base_z"] + other["height"]
    )
    highest_base = max(wall["base_z"], other["base_z"])
    return lowest_top - highest_base > TOLERANCE


def _end_name(
    point: tuple[float, float],
    wall: dict[str, Any],
) -> str | None:
    """`ATSTART` or `ATEND` if the point is one of the axis ends."""

    if _same_point(point, wall["start"]):
        return "ATSTART"
    if _same_point(point, wall["end"]):
        return "ATEND"
    return None


def connections(walls: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Every junction between the given walls, once per pair.

    Each wall is a mapping with `key`, `start`, `end`, `base_z`, and `height`.
    A junction exists where an axis end meets another axis, either at its end
    (a corner) or along its length (a T), at a height both walls occupy. Two
    walls that merely cross without sharing an end are not connected: IFC has
    no connection type for that, and neither has a building. Neither are two
    walls stacked on one axis.
    """

    resolved: list[dict[str, str]] = []
    for index, wall in enumerate(walls):
        for other in walls[index + 1 :]:
            connection = _pair(wall, other)
            if connection is not None:
                resolved.append(connection)
    return resolved


def _pair(
    wall: dict[str, Any],
    other: dict[str, Any],
) -> dict[str, str] | None:
    """Classify how two walls meet, if they meet at all."""

    if not _shares_height(wall, other):
        return None

    for point_name in ("start", "end"):
        point = wall[point_name]
        far_end = _end_name(point, other)
        if far_end is not None:
            # A corner: both walls end here.
            near_end = "ATSTART" if point_name == "start" else "ATEND"
            return _relation(wall, near_end, other, far_end)

    # A T: one wall ends somewhere along the other's path. The wall that ends
    # is the relating element, matching what `connect_wall` produces.
    for near, far in ((wall, other), (other, wall)):
        for point_name in ("start", "end"):
            parameter = _parameter_on_axis(
                near[point_name], far["start"], far["end"]
            )
            if parameter is not None and TOLERANCE < parameter < 1.0 - TOLERANCE:
                near_end = "ATSTART" if point_name == "start" else "ATEND"
                return _relation(near, near_end, far, "ATPATH")
    return None


def _relation(
    relating: dict[str, Any],
    relating_connection: str,
    related: dict[str, Any],
    related_connection: str,
) -> dict[str, str]:
    return {
        "relating": relating["key"],
        "relating_connection": relating_connection,
        "related": related["key"],
        "related_connection": related_connection,
    }
