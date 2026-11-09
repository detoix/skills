"""Measured European fence runs and their matching swing gates."""

from __future__ import annotations

import math

from . import railings, values
from .author import Building, _fence_railing
from .values import AuthoringError

# The public fence and gate helpers deliberately expose the same two product
# families. Derive the keys from the registry so a renamed or removed profile
# cannot leave declaration validation and geometry compilation disagreeing.
FENCE_PROFILES = frozenset(railings.GATE_PROFILES)


def gate_fence_connections(
    path: tuple[tuple[float, float], tuple[float, float]],
    *,
    height: float,
    profile: str,
    leaves: int,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return the fence-centreline endpoints at a gate's support posts.

    The longitudinal coordinate is each gate post's centre. Horizon fence and
    gate posts share a section plane, so their transverse coordinate is the
    gate path itself. D-Lox panels mount on the front of a shallower 60 x 40
    mm fence post; at its deeper Robusta gate post, the returned fence line is
    offset so the two front faces align instead of interpenetrating.

    Draw adjacent fence paths in the same direction as the gate path, finish
    the left run at the first point with ``end_post=False``, and start the
    right run at the second with ``start_post=False``.
    """

    if profile not in FENCE_PROFILES:
        known = ", ".join(sorted(FENCE_PROFILES))
        raise AuthoringError(f"unknown gate profile {profile!r}; known: {known}")
    start, end = values.axis(path, "gate clear-passage path")
    resolved_height = values.positive("gate height", height)
    passage_width = math.hypot(end[0] - start[0], end[1] - start[1])
    dimensions = railings.gate_profile(profile).dimensions(
        passage_width, resolved_height, leaves
    )
    along = (
        (end[0] - start[0]) / passage_width,
        (end[1] - start[1]) / passage_width,
    )
    # Local -Y, the face on which D-Lox mounts its panel.
    front = (along[1], -along[0])
    fence_post_depth = {
        "fence.welded-mesh": railings.NYLOFOR_2D_POST_DEPTH,
        "fence.horizontal-slat": railings.HORIZON_020_POST_DEPTH,
    }[profile]
    front_offset = max(
        0.0, (dimensions.post_depth - fence_post_depth) / 2.0
    )

    def connection(point, longitudinal_sign):
        return (
            point[0]
            + longitudinal_sign * along[0] * dimensions.post_width / 2.0
            + front[0] * front_offset,
            point[1]
            + longitudinal_sign * along[1] * dimensions.post_width / 2.0
            + front[1] * front_offset,
        )

    return connection(start, -1.0), connection(end, 1.0)


def fence(
    model: Building,
    key: str,
    *,
    storey: str,
    path: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    profile: str = "fence.welded-mesh",
    base_offset: float = 0.0,
    material: str | None = None,
    start_post: bool = True,
    end_post: bool = True,
    name: str | None = None,
) -> str:
    """Declare one straight external boundary fence.

    ``profile`` selects either the transparent Betafence Nylofor 2D-derived
    welded mesh or the mostly opaque Dlimity Horizon 020-derived horizontal
    slats. Their dimensions are fixed in :mod:`building_author.railings` from
    the cited manufacturer data; a building script chooses only its run,
    height, elevation, and material.

    IFC4 has no ``FENCE`` value in ``IfcRailingTypeEnum``, so this composes
    the established railing primitive as ``IfcRailing(USERDEFINED)`` with
    ``ObjectType=Fence``. IFC4.3 adds the native ``FENCE`` enumerator.
    """

    if profile not in FENCE_PROFILES:
        known = ", ".join(sorted(FENCE_PROFILES))
        raise AuthoringError(f"unknown fence profile {profile!r}; known: {known}")

    start, end = values.axis(path, "fence path")
    resolved_height = values.positive("fence height", height)

    return _fence_railing(
        model,
        key,
        storey=storey,
        path=(start, end),
        height=resolved_height,
        profile=profile,
        start_post=start_post,
        end_post=end_post,
        base_offset=base_offset,
        material=material,
        name=name,
    )


def _gate(
    model: Building,
    key: str,
    *,
    storey: str,
    path: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    profile: str,
    leaves: int,
    operation_type: str,
    direction_sense: str,
    base_offset: float,
    material: str | None,
    name: str | None,
) -> str:
    """Declare a free-standing ``IfcDoor(GATE)`` across a clear passage."""

    if profile not in FENCE_PROFILES:
        known = ", ".join(sorted(FENCE_PROFILES))
        raise AuthoringError(f"unknown gate profile {profile!r}; known: {known}")
    start, end = values.axis(path, "gate clear-passage path")
    resolved_height = values.positive("gate height", height)
    passage_width = math.hypot(end[0] - start[0], end[1] - start[1])
    dimensions = railings.gate_profile(profile).dimensions(
        passage_width, resolved_height, leaves
    )
    references = {"storey": storey}
    if material is not None:
        references["material"] = material
    return model.add_ifc(
        "gate",
        key,
        references=references,
        name=name or key,
        path=(start, end),
        passage_width=passage_width,
        installed_width=dimensions.installed_width,
        post_centres=dimensions.post_centres,
        height=resolved_height,
        profile=profile,
        leaves=leaves,
        operation_type=values.enumeration(
            "gate operation_type", operation_type, values.DOOR_OPERATIONS
        ),
        direction_sense=values.enumeration(
            "gate direction_sense", direction_sense, values.DIRECTION_SENSE
        ),
        base_offset=values.number("gate base_offset", base_offset),
    )


def driveway_gate(
    model: Building,
    key: str,
    *,
    storey: str,
    path: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    profile: str = "fence.welded-mesh",
    direction_sense: str = "POSITIVE",
    base_offset: float = 0.0,
    material: str | None = None,
    name: str | None = None,
) -> str:
    """Declare a matching two-leaf driveway swing gate.

    ``path`` spans the clear vehicle passage, not the posts. The chosen real
    product profile owns the support-post and installed overall dimensions.
    IFC receives ``DOUBLE_DOOR_SINGLE_SWING`` on a free-standing
    ``IfcDoor(GATE)``; no wall opening or fill relationship is invented.
    """

    return _gate(
        model,
        key,
        storey=storey,
        path=path,
        height=height,
        profile=profile,
        leaves=2,
        operation_type="DOUBLE_DOOR_SINGLE_SWING",
        direction_sense=direction_sense,
        base_offset=base_offset,
        material=material,
        name=name,
    )


def pedestrian_gate(
    model: Building,
    key: str,
    *,
    storey: str,
    path: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    profile: str = "fence.welded-mesh",
    operation_type: str = "SINGLE_SWING_LEFT",
    direction_sense: str = "POSITIVE",
    base_offset: float = 0.0,
    material: str | None = None,
    name: str | None = None,
) -> str:
    """Declare a matching one-leaf pedestrian gate (wicket / Polish furtka)."""

    if operation_type not in {"SINGLE_SWING_LEFT", "SINGLE_SWING_RIGHT"}:
        raise AuthoringError(
            "a pedestrian gate operation_type must be SINGLE_SWING_LEFT "
            "or SINGLE_SWING_RIGHT"
        )
    return _gate(
        model,
        key,
        storey=storey,
        path=path,
        height=height,
        profile=profile,
        leaves=1,
        operation_type=operation_type,
        direction_sense=direction_sense,
        base_offset=base_offset,
        material=material,
        name=name,
    )
