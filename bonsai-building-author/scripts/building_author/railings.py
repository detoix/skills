"""Railings, fences, and matching gates built from measured product systems.

Same split as `roof_windows.py` and `tiles.py`: each profile is its own named
procedure, built in the path's own local frame - X along the run from 0 to
its length, Y across it, Z up from the run's own base - and placed in the
world exactly as a roof window's frame is placed on its roof face.
`railing()` takes a `profile=` key against this module's `PROFILES`, the same
way `roof_window()` takes one against `roof_windows.PROFILES`, rather than raw
dimensions a caller has to already know how to set safely: a steel guardrail
and a timber guardrail are different assemblies with different proportions,
not the same posts-and-rail box in a different material.

## Where the numbers come from

No measured asset for a railing ships with this project, unlike the tile and
window frame recipes. Every dimension below is instead read off a real,
citable source instead of invented:

- IBC 1015.4 / IRC R312.1.3, the 4-inch (101.6 mm) sphere rule: no opening in
  a guard's infill - including the gap against the deck - may pass a 4-inch
  sphere. Both the steel and timber profile's infill spacing is solved
  against this directly.
- Steel: a 316L round tube post system runs 48-50 mm diameter; contemporary
  cable-infill systems space their posts at roughly 4 ft (1.2 m).
- Timber: the IRC caps a nominal 4x4 post (actual 88.9 mm) at 6 ft (1.83 m,
  rounded to 1.8 m) of span, and guard rail construction guidance calls for
  at least a 2x6 (actual 38 x 140 mm) top rail.
- Glass: frameless balustrade systems run 10-15 mm (up to 21.52 mm) glass in
  an aluminium base shoe channel, with published cover widths of 70-100 mm
  and channel envelopes up to 130 x 60 mm.
- Welded mesh fence: Betafence Nylofor 2D panels are 2500 mm wide, with
  200 x 50 mm rectangular mesh, twin 6 mm horizontal wires, and 5 mm
  vertical wires. The dedicated D-Lox system uses 60 x 40 mm posts, mounts
  panels on the front, and normally spaces posts at 2520 mm centres.
  https://www.betafence.com/en/nylofor-2d
  https://www.betafence.com/en/d-lox
- Horizontal slat fence: Dlimity Horizon 020 publishes 100 x 30 mm
  horizontal aluminium slats at 20 mm clear spacing and 80 x 50 mm posts.
  Its current technical sheet caps aluminium bays at 1800 mm between axes;
  the marketing page's looser 2000 mm statement is not used for geometry.
  https://www.dlimity.net/en-gb/horizon-aluminio-020
  https://www.dlimity.net/descargas
- Matching gates: Robusta-Nylofor publishes single- and double-swing gates,
  their free passages, installed widths, post sizes, and 60 x 40 or 60 x 60
  leaf frames. Dlimity publishes matching single- and double-swing Horizon
  gates, made-to-measure widths, a 20 mm ground clearance, and a standard
  height table.
  https://www.betafence.com/en/robusta-nylofor-gates
  https://www.dlimity.net/en-gb/puertas-peatonales
  https://www.dlimity.net/en-gb/puertas-doble-batiente

## What is deliberately simplified

- A round tube post or cable is built as a square-section box - this module
  only builds boxes. A round profile is a real follow-up, not a claim this
  one already makes.
- The steel and timber profiles both use horizontal infill bars. Vertical
  balusters are just as sphere-rule compliant and are the more traditional
  timber look; horizontal infill was chosen so both profiles share one
  algorithm, `_post_and_rail_guard()`, differing only in their cited
  proportions - not because a horizontal timber guard is the only real
  design.
- The glass profile collapses what a real installation joins from several
  panes (finite sheet sizes) into one continuous panel, and its glazing's
  embedment into the shoe (20 mm) is ordinary practice with no specific
  citation, unlike every other number here.
- None of this is a certified guard: the sphere rule is honoured by
  proportion, not verified against an actual sphere, and no load calculation
  backs any member size in this module.
- Nylofor's round wires are square-section solids here because this module
  only builds boxes. Its front-mounted panel is held 4 mm clear of the post
  face in place of unmodelled D-Lox clips. The published 30 mm top-barb
  module is retained nominally. Post caps and foundations are omitted.
- The D-Lox manual recommends 20-50 mm under a panel, while the Robusta gate
  installation table distinguishes nominal height, wing height, and installed
  post height. This authoring API keeps ``height`` as one overall visual
  envelope, like every other railing profile, rather than silently making the
  resulting IFC body taller than the declared height. Ground fixings and that
  installation allowance remain deliberately simplified.
- Horizon 020's slat field is vertically centred inside a published catalogue
  height. Fasteners and post caps are omitted.
- Betafence publishes two possible leaf-frame sections without mapping one to
  each gate size, so the gate procedure consistently chooses the published
  60 x 40 mm option. Dlimity does not publish its gate-frame section; its
  matching gate uses that representative 60 x 40 mm envelope and borrows the
  verified fence's 80 x 50 mm post section. Its slats, gaps, height series,
  and ground clearance are published gate/family data. This is a visual
  product procedure, not a structural gate design.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from . import procedures
from .procedures import Point, ProceduralMesh, Vertex
from .values import AuthoringError

RailingMesh = ProceduralMesh

#: Held between two faces that should never be exactly coincident, the same
#: clearance roof_windows.py holds every shell apart by - so a post's own cap face
#: never lands exactly on the rail's underside and the two do not z-fight.
CLEARANCE = 0.004


def _box(
    verts: list[Vertex],
    faces: list[tuple[int, ...]],
    uvs: list[list[Point]],
    slots: list[str],
    role: str,
    min_x: float,
    max_x: float,
    half_y: float,
    low: float,
    high: float,
    centre_y: float = 0.0,
) -> None:
    """Append a closed box spanning `min_x..max_x` around ``centre_y``."""

    if max_x <= min_x or half_y <= 0.0 or high <= low:
        raise AuthoringError(
            "a railing box needs positive width, depth, and height"
        )

    base = len(verts)
    corners = [
        (min_x, centre_y - half_y),
        (max_x, centre_y - half_y),
        (max_x, centre_y + half_y),
        (min_x, centre_y + half_y),
    ]
    for x, y in corners:
        verts.append((x, y, low))
    for x, y in corners:
        verts.append((x, y, high))
    quad_uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    faces.append((base + 3, base + 2, base + 1, base))
    faces.append((base + 4, base + 5, base + 6, base + 7))
    uvs.extend([quad_uv, quad_uv])
    slots.extend([role, role])
    for index in range(4):
        following = (index + 1) % 4
        faces.append(
            (base + index, base + following, base + 4 + following, base + 4 + index)
        )
        uvs.append(quad_uv)
        slots.append(role)


def _evenly_spaced_infill(
    verts: list[Vertex],
    faces: list[tuple[int, ...]],
    uvs: list[list[Point]],
    slots: list[str],
    role: str,
    length: float,
    low: float,
    high: float,
    bar_depth: float,
    clear_gap: float,
    half_x_reach: float,
    half_y: float,
) -> None:
    """Horizontal infill bars between `low` and `high`, gaps against both
    ends included, so no gap - against the deck, against the rail, or
    between two bars - exceeds `clear_gap`.

    Spaced the same "fit the module, never stretch it" way `guardrail_mesh`'s
    posts are: the target pitch is rounded *up* to a whole number of bays,
    which only ever tightens the actual gap below the target, never widens
    it past the sphere rule it is solving against.
    """

    span = high - low
    if span <= bar_depth:
        raise AuthoringError(
            "a railing's infill has no room between the deck and its rail"
        )
    target_pitch = bar_depth + clear_gap
    count = max(1, math.ceil(span / target_pitch))
    pitch = span / count
    for index in range(count):
        centre = low + pitch * (index + 0.5)
        _box(
            verts, faces, uvs, slots, role,
            -half_x_reach, length + half_x_reach, half_y,
            centre - bar_depth / 2.0, centre + bar_depth / 2.0,
        )


@dataclass(frozen=True, slots=True)
class GuardrailProportions:
    """One guardrail design's cited proportions - everything
    `_post_and_rail_guard` needs beyond the run's own `length` and `height`.

    Bundling these is what keeps `steel_guardrail_mesh` and
    `timber_guardrail_mesh` a single citation each, in one place, rather than
    the same seven-argument call restated twice with only the values
    differing.
    """

    post_spacing: float
    post_size: float
    rail_width: float
    rail_depth: float
    infill_width: float
    infill_depth: float
    infill_clear_gap: float


def _post_and_rail_guard(
    length: float, height: float, proportions: GuardrailProportions
) -> RailingMesh:
    """Posts, horizontal infill, and a top rail - the shared shape behind
    both `steel_guardrail_mesh` and `timber_guardrail_mesh`. Only their
    proportions differ; the algorithm placing them does not.
    """

    if length <= 0 or height <= 0:
        raise AuthoringError("a railing's length and height must be positive")
    if proportions.rail_depth <= CLEARANCE:
        raise AuthoringError(f"a railing's rail_depth must exceed {CLEARANCE} m")
    if height <= proportions.rail_depth:
        raise AuthoringError("a railing's height must exceed its own rail_depth")

    verts: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []
    slots: list[str] = []

    post_count = max(2, round(length / proportions.post_spacing) + 1)
    post_top = height - CLEARANCE
    for index in range(post_count):
        centre = length * index / (post_count - 1)
        _box(
            verts, faces, uvs, slots, "post",
            centre - proportions.post_size / 2.0, centre + proportions.post_size / 2.0,
            proportions.post_size / 2.0, 0.0, post_top,
        )

    _evenly_spaced_infill(
        verts, faces, uvs, slots, "infill",
        length, 0.0, height - proportions.rail_depth,
        proportions.infill_depth, proportions.infill_clear_gap,
        proportions.infill_width / 2.0, proportions.infill_width / 2.0,
    )

    _box(
        verts, faces, uvs, slots, "rail",
        -proportions.rail_width / 2.0, length + proportions.rail_width / 2.0,
        proportions.rail_width / 2.0, height - proportions.rail_depth, height,
    )

    return procedures.validate_mesh("post_and_rail_guard", (verts, faces, uvs, slots))


#: 48-50 mm 316L round tube, approximated as a square box (see module
#: docstring). Reused for the top rail too: no separate cap-rail size is
#: cited for a tube-and-cable system, and a continuous tube section for both
#: is exactly how one reads in practice. Infill is a slim flat bar/cable
#: proxy, at the widest clear gap IBC 1015.4 / IRC R312.1.3 allow (101.6 mm)
#: minus a safety margin. Post spacing follows contemporary cable-infill
#: practice, roughly 4 ft between posts.
STEEL_TUBE = 0.05
STEEL_POST_SPACING = 1.2
STEEL_INFILL_DEPTH = 0.006
STEEL_INFILL_CLEAR_GAP = 0.100
STEEL_PROPORTIONS = GuardrailProportions(
    post_spacing=STEEL_POST_SPACING,
    post_size=STEEL_TUBE,
    rail_width=STEEL_TUBE,
    rail_depth=STEEL_TUBE,
    infill_width=STEEL_TUBE,
    infill_depth=STEEL_INFILL_DEPTH,
    infill_clear_gap=STEEL_INFILL_CLEAR_GAP,
)


def steel_guardrail_mesh(length: float, height: float) -> RailingMesh:
    """A steel tube-and-cable guard: slim posts, horizontal cable infill.

    Posts and rail are both built at the same 48-50 mm tube section; infill
    is thin horizontal bars standing in for cables, spaced against the IBC/
    IRC 4-inch sphere rule.
    """

    return _post_and_rail_guard(length, height, STEEL_PROPORTIONS)


#: Nominal 4x4 post, actual dimension (3.5 in), at the IRC's own cap on a
#: 4x4's span. "At least a 2x6" top rail, laid flat: actual width x actual
#: thickness. Infill is a nominal "1x" slat, actual thickness, flush with
#: the post's own width, its clear gap held under the same 101.6 mm
#: sphere-rule maximum the steel profile uses.
TIMBER_POST = 0.089
TIMBER_POST_SPACING = 1.8
TIMBER_RAIL_WIDTH = 0.140
TIMBER_RAIL_DEPTH = 0.038
TIMBER_INFILL_DEPTH = 0.019
TIMBER_INFILL_CLEAR_GAP = 0.095
TIMBER_PROPORTIONS = GuardrailProportions(
    post_spacing=TIMBER_POST_SPACING,
    post_size=TIMBER_POST,
    rail_width=TIMBER_RAIL_WIDTH,
    rail_depth=TIMBER_RAIL_DEPTH,
    infill_width=TIMBER_POST,
    infill_depth=TIMBER_INFILL_DEPTH,
    infill_clear_gap=TIMBER_INFILL_CLEAR_GAP,
)


def timber_guardrail_mesh(length: float, height: float) -> RailingMesh:
    """A timber guard: 4x4 posts at their IRC-capped spacing, a flat 2x6 cap
    rail, and horizontal 1x infill slats against the same sphere rule the
    steel profile solves.
    """

    return _post_and_rail_guard(length, height, TIMBER_PROPORTIONS)


#: Within the cited 10-15 mm (up to 21.52 mm) range for frameless balustrade
#: glazing.
GLASS_THICKNESS = 0.012
#: The base shoe's own cross-path cover width (cited range 70-100 mm) and
#: vertical channel height (cited "130 x 60 mm max" envelope).
GLASS_SHOE_WIDTH = 0.08
GLASS_SHOE_HEIGHT = 0.06
#: How far the glazing seats down into the shoe channel - ordinary practice,
#: not a cited figure like the rest of this profile.
GLASS_EMBED = 0.02


def glass_balustrade_mesh(length: float, height: float) -> RailingMesh:
    """A frameless glass balustrade: one continuous pane in an aluminium
    base shoe, no posts and no cap rail.

    Real installations join several finite panes; this collapses them into
    one continuous panel the width of the run (see module docstring).
    """

    if length <= 0 or height <= 0:
        raise AuthoringError("a railing's length and height must be positive")
    if height <= GLASS_SHOE_HEIGHT - GLASS_EMBED:
        raise AuthoringError(
            "a glass balustrade's height must clear its own base shoe"
        )

    verts: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []
    slots: list[str] = []

    _box(
        verts, faces, uvs, slots, "shoe",
        0.0, length, GLASS_SHOE_WIDTH / 2.0, 0.0, GLASS_SHOE_HEIGHT,
    )
    _box(
        verts, faces, uvs, slots, "glazing",
        0.0, length, GLASS_THICKNESS / 2.0,
        GLASS_SHOE_HEIGHT - GLASS_EMBED, height,
    )

    return procedures.validate_mesh("glass_balustrade_mesh", (verts, faces, uvs, slots))


def _catalog_height(label: str, height: float, allowed: frozenset[float]) -> None:
    """Require a manufacturer-published height without trusting float equality."""

    if any(math.isclose(height, item, abs_tol=1e-9) for item in allowed):
        return
    known = ", ".join(f"{item:.2f}" for item in sorted(allowed))
    raise AuthoringError(f"{label} height must be one of {known} m")


def _bay_ends(
    length: float,
    maximum_span: float,
    minimum_final_span: float,
) -> list[float]:
    """Lay out full bays unless that would leave an unusable final sliver.

    Redistribute all bays evenly when the remainder is too narrow to fit
    between its post faces. Otherwise repeat full modules and cut the last
    panel to length.
    """

    if not all(math.isfinite(value) for value in (
        length, maximum_span, minimum_final_span
    )):
        raise AuthoringError("fence bay dimensions must be finite")
    if length <= 0.0 or maximum_span <= 0.0 or minimum_final_span <= 0.0:
        raise AuthoringError("fence bay dimensions must be positive")
    if minimum_final_span >= maximum_span:
        raise AuthoringError(
            "a fence's minimum final span must be smaller than its maximum span"
        )
    full = int(math.floor(length / maximum_span + 1e-12))
    remainder = length - full * maximum_span
    if full == 0:
        return [0.0, length]
    if remainder <= 1e-9:
        ends = [index * maximum_span for index in range(full + 1)]
        ends[-1] = length
        return ends
    if remainder >= minimum_final_span:
        return [index * maximum_span for index in range(full + 1)] + [length]
    count = full + 1
    return [length * index / count for index in range(count + 1)]


def _post_centres(
    ends: list[float], *, start_post: bool, end_post: bool
) -> list[float]:
    centres = list(ends)
    if not start_post:
        centres = centres[1:]
    if not end_post and centres:
        centres = centres[:-1]
    return centres


def _module_positions(
    low: float,
    high: float,
    pitch: float,
    minimum_separation: float,
) -> list[float]:
    """Positions at both limits, with fixed pitch and no overlapping tail."""

    if not all(math.isfinite(value) for value in (
        low, high, pitch, minimum_separation
    )):
        raise AuthoringError("infill module dimensions must be finite")
    if high <= low or pitch <= 0.0 or minimum_separation <= 0.0:
        raise AuthoringError("an infill field must have positive extent")
    found = [low]
    index = 1
    while low + index * pitch < high - 1e-9:
        found.append(low + index * pitch)
        index += 1
    if high - found[-1] >= minimum_separation - 1e-9:
        found.append(high)
    else:
        found[-1] = high
    return found


# Betafence Nylofor 2D / D-Lox dimensions, in metres. See the module
# docstring for the manufacturer pages and deliberately simplified parts.
NYLOFOR_2D_PANEL_WIDTH = 2.5
NYLOFOR_2D_POST_CENTRES = 2.52
NYLOFOR_2D_POST_WIDTH = 0.06
NYLOFOR_2D_POST_DEPTH = 0.04
NYLOFOR_2D_MESH_WIDTH = 0.05
NYLOFOR_2D_MESH_HEIGHT = 0.20
NYLOFOR_2D_HORIZONTAL_WIRE = 0.006
NYLOFOR_2D_VERTICAL_WIRE = 0.005
NYLOFOR_2D_BARB = 0.03
NYLOFOR_2D_PANEL_EDGE_GAP = 0.01
NYLOFOR_2D_HEIGHTS = frozenset(
    {0.63, 0.83, 1.03, 1.23, 1.43, 1.63, 1.83, 2.03, 2.43}
)


def _append_nylofor_field(
    verts: list[Vertex],
    faces: list[tuple[int, ...]],
    uvs: list[list[Point]],
    slots: list[str],
    *,
    min_x: float,
    max_x: float,
    low: float,
    high: float,
    centre_y: float,
    vertical_high: float | None = None,
) -> None:
    """Append one 200 x 50 mm twin-wire field in its assembly plane."""

    if max_x - min_x <= NYLOFOR_2D_VERTICAL_WIRE:
        raise AuthoringError("a Nylofor infill field is too narrow for one wire")
    if high - low <= NYLOFOR_2D_HORIZONTAL_WIRE:
        raise AuthoringError("a Nylofor infill field is too short for one wire")

    vertical_top = high if vertical_high is None else vertical_high
    for x in _module_positions(
        min_x + NYLOFOR_2D_VERTICAL_WIRE / 2.0,
        max_x - NYLOFOR_2D_VERTICAL_WIRE / 2.0,
        NYLOFOR_2D_MESH_WIDTH,
        NYLOFOR_2D_VERTICAL_WIRE,
    ):
        _box(
            verts, faces, uvs, slots, "infill",
            x - NYLOFOR_2D_VERTICAL_WIRE / 2.0,
            x + NYLOFOR_2D_VERTICAL_WIRE / 2.0,
            NYLOFOR_2D_VERTICAL_WIRE / 2.0,
            low,
            vertical_top,
            centre_y=centre_y,
        )

    horizontal_offset = (
        NYLOFOR_2D_VERTICAL_WIRE + NYLOFOR_2D_HORIZONTAL_WIRE
    ) / 2.0
    centres = _module_positions(
        low + NYLOFOR_2D_HORIZONTAL_WIRE / 2.0,
        high - NYLOFOR_2D_HORIZONTAL_WIRE / 2.0,
        NYLOFOR_2D_MESH_HEIGHT,
        NYLOFOR_2D_HORIZONTAL_WIRE,
    )
    for z in centres:
        for side in (-1.0, 1.0):
            _box(
                verts, faces, uvs, slots, "infill",
                min_x,
                max_x,
                NYLOFOR_2D_HORIZONTAL_WIRE / 2.0,
                z - NYLOFOR_2D_HORIZONTAL_WIRE / 2.0,
                z + NYLOFOR_2D_HORIZONTAL_WIRE / 2.0,
                centre_y=centre_y + side * horizontal_offset,
            )


def _validate_nylofor_2d_fence(length: float, height: float) -> None:
    if length <= NYLOFOR_2D_POST_WIDTH:
        raise AuthoringError(
            "a Nylofor 2D fence must be longer than its 60 mm post"
        )
    _catalog_height("a Nylofor 2D fence", height, NYLOFOR_2D_HEIGHTS)


def nylofor_2d_fence_mesh(
    length: float,
    height: float,
    *,
    start_post: bool = True,
    end_post: bool = True,
) -> RailingMesh:
    """Front-mounted transparent Nylofor 2D panels on D-Lox posts."""

    _validate_nylofor_2d_fence(length, height)

    verts: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []
    slots: list[str] = []
    ends = _bay_ends(
        length,
        NYLOFOR_2D_POST_CENTRES,
        NYLOFOR_2D_POST_WIDTH + 2.0 * NYLOFOR_2D_PANEL_EDGE_GAP,
    )

    for centre in _post_centres(
        ends, start_post=start_post, end_post=end_post
    ):
        _box(
            verts, faces, uvs, slots, "post",
            centre - NYLOFOR_2D_POST_WIDTH / 2.0,
            centre + NYLOFOR_2D_POST_WIDTH / 2.0,
            NYLOFOR_2D_POST_DEPTH / 2.0,
            0.0,
            height,
        )

    wire_stack = (
        NYLOFOR_2D_VERTICAL_WIRE + 2.0 * NYLOFOR_2D_HORIZONTAL_WIRE
    )
    panel_y = -(
        NYLOFOR_2D_POST_DEPTH / 2.0 + CLEARANCE + wire_stack / 2.0
    )
    for start, end in zip(ends, ends[1:]):
        _append_nylofor_field(
            verts,
            faces,
            uvs,
            slots,
            min_x=start + NYLOFOR_2D_PANEL_EDGE_GAP,
            max_x=end - NYLOFOR_2D_PANEL_EDGE_GAP,
            low=0.0,
            high=height - NYLOFOR_2D_BARB,
            vertical_high=height,
            centre_y=panel_y,
        )

    return procedures.validate_mesh(
        "nylofor_2d_fence_mesh", (verts, faces, uvs, slots)
    )


# Dlimity Horizon 020 dimensions, in metres. The technical sheet linked from
# the manufacturer's downloads page governs over the conflicting 2.0 m
# marketing-page value.
HORIZON_020_MAX_SPAN = 1.8
HORIZON_020_POST_WIDTH = 0.08
HORIZON_020_POST_DEPTH = 0.05
HORIZON_020_SLAT_HEIGHT = 0.10
HORIZON_020_SLAT_DEPTH = 0.03
HORIZON_020_SLAT_GAP = 0.02
HORIZON_020_HEIGHTS = frozenset(
    {0.12, 0.24, 0.36, 0.48, 0.60, 0.72, 0.84, 0.96, 1.08, 1.20,
     1.32, 1.44, 1.56, 1.68, 1.80, 1.92}
)


def _append_horizontal_slats(
    verts: list[Vertex],
    faces: list[tuple[int, ...]],
    uvs: list[list[Point]],
    slots: list[str],
    *,
    min_x: float,
    max_x: float,
    low: float,
    high: float,
) -> None:
    if max_x <= min_x or high - low < HORIZON_020_SLAT_HEIGHT:
        raise AuthoringError("a Horizon 020 infill field has no usable space")
    pitch = HORIZON_020_SLAT_HEIGHT + HORIZON_020_SLAT_GAP
    count = math.floor(
        (high - low + HORIZON_020_SLAT_GAP) / pitch + 1e-9
    )
    field_height = (
        count * HORIZON_020_SLAT_HEIGHT
        + (count - 1) * HORIZON_020_SLAT_GAP
    )
    field_low = low + (high - low - field_height) / 2.0
    for index in range(count):
        slat_low = field_low + index * pitch
        _box(
            verts, faces, uvs, slots, "infill",
            min_x,
            max_x,
            HORIZON_020_SLAT_DEPTH / 2.0,
            slat_low,
            slat_low + HORIZON_020_SLAT_HEIGHT,
        )


def _validate_horizon_020_fence(length: float, height: float) -> None:
    if length <= HORIZON_020_POST_WIDTH:
        raise AuthoringError(
            "a Horizon 020 fence must be longer than its 80 mm post"
        )
    _catalog_height("a Horizon 020 fence", height, HORIZON_020_HEIGHTS)


def horizon_020_fence_mesh(
    length: float,
    height: float,
    *,
    start_post: bool = True,
    end_post: bool = True,
) -> RailingMesh:
    """Mostly opaque horizontal-slat fence based on Dlimity Horizon 020."""

    _validate_horizon_020_fence(length, height)

    verts: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []
    slots: list[str] = []
    ends = _bay_ends(
        length,
        HORIZON_020_MAX_SPAN,
        HORIZON_020_POST_WIDTH + 2.0 * CLEARANCE,
    )

    for centre in _post_centres(
        ends, start_post=start_post, end_post=end_post
    ):
        _box(
            verts, faces, uvs, slots, "post",
            centre - HORIZON_020_POST_WIDTH / 2.0,
            centre + HORIZON_020_POST_WIDTH / 2.0,
            HORIZON_020_POST_DEPTH / 2.0,
            0.0,
            height,
        )

    for start, end in zip(ends, ends[1:]):
        # Four millimetres of each slat enters the solid post proxy. This is
        # deliberate concealed channel engagement, not an accidental visible
        # clash; fastener/channel detail remains below this visual procedure's
        # level of detail.
        _append_horizontal_slats(
            verts,
            faces,
            uvs,
            slots,
            min_x=start + HORIZON_020_POST_WIDTH / 2.0 - CLEARANCE,
            max_x=end - HORIZON_020_POST_WIDTH / 2.0 + CLEARANCE,
            low=0.0,
            high=height,
        )

    return procedures.validate_mesh(
        "horizon_020_fence_mesh", (verts, faces, uvs, slots)
    )


GATE_FRAME_WIDTH = 0.06
GATE_FRAME_DEPTH = 0.04
GATE_HINGE_GAP = 0.02
GATE_CENTRE_GAP = 0.02
NYLOFOR_GATE_HEIGHTS = frozenset(
    # Betafence's live F/2D/2DS table and its linked 2025 F/2D/2D Super
    # flyer conflict. Accept the union of both explicitly published series.
    {1.03, 1.23, 1.43, 1.53, 1.63, 1.73, 1.83, 2.03, 2.43}
)
HORIZON_020_GATE_HEIGHTS = frozenset(
    {1.20, 1.32, 1.44, 1.56, 1.68, 1.80, 1.92, 2.04, 2.16}
)


@dataclass(frozen=True, slots=True)
class GateDimensions:
    """Resolved physical envelope around a clear gate passage."""

    passage_width: float
    post_width: float
    post_depth: float
    frame_width: float = GATE_FRAME_WIDTH
    frame_depth: float = GATE_FRAME_DEPTH
    bottom_clearance: float = 0.02

    @property
    def installed_width(self) -> float:
        return self.passage_width + 2.0 * self.post_width

    @property
    def post_centres(self) -> float:
        return self.passage_width + self.post_width


def _validate_gate_inputs(
    passage_width: float, height: float, leaves: int
) -> None:
    if isinstance(leaves, bool) or leaves not in {1, 2}:
        raise AuthoringError("a swing gate must have one or two leaves")
    if not math.isfinite(passage_width) or passage_width <= 0.0:
        raise AuthoringError("a gate's clear passage must be positive and finite")
    if not math.isfinite(height) or height <= 0.0:
        raise AuthoringError("a gate's height must be positive and finite")


def nylofor_2d_gate_dimensions(
    passage_width: float, height: float, leaves: int
) -> GateDimensions:
    _validate_gate_inputs(passage_width, height, leaves)
    _catalog_height("a Robusta-Nylofor gate", height, NYLOFOR_GATE_HEIGHTS)
    if leaves == 1 and math.isclose(passage_width, 0.985, abs_tol=1e-9):
        return GateDimensions(passage_width, 0.08, 0.08, bottom_clearance=0.05)
    driveway_posts = {3.010: 0.08, 4.090: 0.10}
    if leaves == 2:
        for passage, post in driveway_posts.items():
            if math.isclose(passage_width, passage, abs_tol=1e-9):
                if passage == 3.010 and math.isclose(
                    height, 2.43, abs_tol=1e-9
                ):
                    post = 0.10
                return GateDimensions(
                    passage_width, post, post, bottom_clearance=0.05
                )
    if leaves == 1:
        raise AuthoringError(
            "a Nylofor pedestrian gate needs the published 0.985 m free passage"
        )
    raise AuthoringError(
        "a Nylofor driveway gate free passage must be 3.010 or 4.090 m"
    )


def horizon_020_gate_dimensions(
    passage_width: float, height: float, leaves: int
) -> GateDimensions:
    _validate_gate_inputs(passage_width, height, leaves)
    _catalog_height("a Horizon 020 gate", height, HORIZON_020_GATE_HEIGHTS)
    minimum = 2.0 * (GATE_FRAME_WIDTH + GATE_HINGE_GAP)
    if leaves == 2:
        minimum *= 2.0
    if passage_width <= minimum:
        raise AuthoringError(
            f"a Horizon 020 {leaves}-leaf gate needs more than "
            f"{minimum:.3f} m of clear passage"
        )
    return GateDimensions(
        passage_width,
        HORIZON_020_POST_WIDTH,
        HORIZON_020_POST_DEPTH,
    )


def _leaf_ranges(width: float, leaves: int) -> list[tuple[float, float]]:
    if leaves == 1:
        return [(GATE_HINGE_GAP, width - GATE_HINGE_GAP)]
    if leaves == 2:
        half_gap = GATE_CENTRE_GAP / 2.0
        return [
            (GATE_HINGE_GAP, width / 2.0 - half_gap),
            (width / 2.0 + half_gap, width - GATE_HINGE_GAP),
        ]
    raise AuthoringError("a swing gate must have one or two leaves")


def _swing_gate_mesh(
    dimensions: GateDimensions,
    height: float,
    leaves: int,
    *,
    infill: str,
) -> RailingMesh:
    verts: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []
    slots: list[str] = []
    width = dimensions.passage_width

    _box(
        verts, faces, uvs, slots, "post",
        -dimensions.post_width,
        0.0,
        dimensions.post_depth / 2.0,
        0.0,
        height,
    )
    _box(
        verts, faces, uvs, slots, "post",
        width,
        width + dimensions.post_width,
        dimensions.post_depth / 2.0,
        0.0,
        height,
    )

    for leaf_start, leaf_end in _leaf_ranges(width, leaves):
        if leaf_end - leaf_start <= 2.0 * dimensions.frame_width:
            raise AuthoringError("a gate leaf is too narrow for its own frame")
        bottom = dimensions.bottom_clearance
        if height - bottom <= 2.0 * dimensions.frame_width:
            raise AuthoringError("a gate is too short for its own frame")

        _box(
            verts, faces, uvs, slots, "framing",
            leaf_start,
            leaf_start + dimensions.frame_width,
            dimensions.frame_depth / 2.0,
            bottom,
            height,
        )
        _box(
            verts, faces, uvs, slots, "framing",
            leaf_end - dimensions.frame_width,
            leaf_end,
            dimensions.frame_depth / 2.0,
            bottom,
            height,
        )
        for low, high in (
            (bottom, bottom + dimensions.frame_width),
            (height - dimensions.frame_width, height),
        ):
            _box(
                verts, faces, uvs, slots, "framing",
                leaf_start + dimensions.frame_width - CLEARANCE,
                leaf_end - dimensions.frame_width + CLEARANCE,
                dimensions.frame_depth / 2.0,
                low,
                high,
            )

        field = {
            "min_x": leaf_start + dimensions.frame_width - CLEARANCE,
            "max_x": leaf_end - dimensions.frame_width + CLEARANCE,
            "low": bottom + dimensions.frame_width - CLEARANCE,
            "high": height - dimensions.frame_width + CLEARANCE,
        }
        if infill == "nylofor":
            _append_nylofor_field(
                verts, faces, uvs, slots, centre_y=0.0, **field
            )
        elif infill == "horizon":
            _append_horizontal_slats(verts, faces, uvs, slots, **field)
        else:
            raise AuthoringError(f"unknown gate infill {infill!r}")

    return procedures.validate_mesh(
        f"{infill}_swing_gate_mesh", (verts, faces, uvs, slots)
    )


def nylofor_2d_gate_mesh(
    passage_width: float, height: float, leaves: int
) -> RailingMesh:
    """One real Robusta-Nylofor single- or double-swing gate."""

    return _swing_gate_mesh(
        nylofor_2d_gate_dimensions(passage_width, height, leaves),
        height,
        leaves,
        infill="nylofor",
    )


def horizon_020_gate_mesh(
    passage_width: float, height: float, leaves: int
) -> RailingMesh:
    """One made-to-measure Dlimity Horizon 020 swing gate."""

    return _swing_gate_mesh(
        horizon_020_gate_dimensions(passage_width, height, leaves),
        height,
        leaves,
        infill="horizon",
    )


@dataclass(frozen=True, slots=True)
class RailingProfile:
    """A railing design: how it is built, named the way it is chosen."""

    key: str
    build: Callable[..., RailingMesh]
    validator: Callable[[float, float], None] | None = None
    endpoint_posts: bool = False

    def check(self, length: float, height: float) -> None:
        if self.validator is None:
            self.build(length, height)
        else:
            self.validator(length, height)

    def geometry(
        self,
        length: float,
        height: float,
        *,
        start_post: bool = True,
        end_post: bool = True,
    ) -> RailingMesh:
        if self.endpoint_posts:
            return self.build(
                length,
                height,
                start_post=start_post,
                end_post=end_post,
            )
        if not start_post or not end_post:
            raise AuthoringError(
                f"{self.key} does not support suppressing endpoint posts"
            )
        return self.build(length, height)


@dataclass(frozen=True, slots=True)
class GateProfile:
    """A fence system's matching one- or two-leaf swing gate."""

    key: str
    dimensions_for: Callable[[float, float, int], GateDimensions]
    build: Callable[[float, float, int], RailingMesh]

    def dimensions(
        self, passage_width: float, height: float, leaves: int
    ) -> GateDimensions:
        return self.dimensions_for(passage_width, height, leaves)

    def geometry(
        self, passage_width: float, height: float, leaves: int
    ) -> RailingMesh:
        return self.build(passage_width, height, leaves)


STEEL_GUARDRAIL = RailingProfile(key="guardrail.steel", build=steel_guardrail_mesh)
TIMBER_GUARDRAIL = RailingProfile(key="guardrail.timber", build=timber_guardrail_mesh)
GLASS_BALUSTRADE = RailingProfile(key="balustrade.glass", build=glass_balustrade_mesh)
NYLOFOR_2D_FENCE = RailingProfile(
    key="fence.welded-mesh",
    build=nylofor_2d_fence_mesh,
    validator=_validate_nylofor_2d_fence,
    endpoint_posts=True,
)
HORIZON_020_FENCE = RailingProfile(
    key="fence.horizontal-slat",
    build=horizon_020_fence_mesh,
    validator=_validate_horizon_020_fence,
    endpoint_posts=True,
)

PROFILES: dict[str, RailingProfile] = {
    STEEL_GUARDRAIL.key: STEEL_GUARDRAIL,
    TIMBER_GUARDRAIL.key: TIMBER_GUARDRAIL,
    GLASS_BALUSTRADE.key: GLASS_BALUSTRADE,
    NYLOFOR_2D_FENCE.key: NYLOFOR_2D_FENCE,
    HORIZON_020_FENCE.key: HORIZON_020_FENCE,
}


def profile(key: str) -> RailingProfile:
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise AuthoringError(f"unknown railing profile {key!r}; known: {known}")
    return PROFILES[key]


NYLOFOR_2D_GATE = GateProfile(
    key=NYLOFOR_2D_FENCE.key,
    dimensions_for=nylofor_2d_gate_dimensions,
    build=nylofor_2d_gate_mesh,
)
HORIZON_020_GATE = GateProfile(
    key=HORIZON_020_FENCE.key,
    dimensions_for=horizon_020_gate_dimensions,
    build=horizon_020_gate_mesh,
)

GATE_PROFILES: dict[str, GateProfile] = {
    NYLOFOR_2D_GATE.key: NYLOFOR_2D_GATE,
    HORIZON_020_GATE.key: HORIZON_020_GATE,
}


def gate_profile(key: str) -> GateProfile:
    if key not in GATE_PROFILES:
        known = ", ".join(sorted(GATE_PROFILES))
        raise AuthoringError(f"unknown gate profile {key!r}; known: {known}")
    return GATE_PROFILES[key]
