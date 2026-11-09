"""Roof windows: one procedure per window type, plus what hosting needs.

Same split as `tiles`: each window type has **its own procedure** that builds
that window and nothing else, written out in code rather than loaded from a
model file. Adding a window type means writing another procedure next to
these.

A roof window is two things at once. In IFC it is an `IfcWindow` with
predefined type `SKYLIGHT`, filling an `IfcOpeningElement` that voids the
roof. In the presentation it is a frame that has to cover the tiles the
opening cuts through. The flashing margin controls that overlap in metres.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import procedures
from .procedures import Point, ProceduralMesh, Vertex
from .values import AuthoringError

WindowMesh = ProceduralMesh


def _ring(verts, faces, uvs, slots, role, half_x, half_y, inner_x, inner_y,
          low, high):
    """Append a closed rectangular ring solid, and return the vertex count."""

    base = len(verts)
    outer = [
        (-half_x, -half_y),
        (half_x, -half_y),
        (half_x, half_y),
        (-half_x, half_y),
    ]
    inner = [
        (-inner_x, -inner_y),
        (inner_x, -inner_y),
        (inner_x, inner_y),
        (-inner_x, inner_y),
    ]
    for x, y in outer:
        verts.append((x, y, low))
    for x, y in outer:
        verts.append((x, y, high))
    for x, y in inner:
        verts.append((x, y, low))
    for x, y in inner:
        verts.append((x, y, high))

    o_low, o_high, i_low, i_high = base, base + 4, base + 8, base + 12
    quad_uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for index in range(4):
        following = (index + 1) % 4
        # outer skirt, inner reveal, top face, underside
        faces.append((o_low + index, o_low + following,
                      o_high + following, o_high + index))
        faces.append((i_low + following, i_low + index,
                      i_high + index, i_high + following))
        faces.append((o_high + index, o_high + following,
                      i_high + following, i_high + index))
        faces.append((i_low + index, i_low + following,
                      o_low + following, o_low + index))
        uvs.extend([quad_uv, quad_uv, quad_uv, quad_uv])
        slots.extend([role] * 4)


def _box(verts, faces, uvs, slots, role, half_x, half_y, low, high):
    """Append a closed box, used for the pane."""

    base = len(verts)
    corners = [
        (-half_x, -half_y),
        (half_x, -half_y),
        (half_x, half_y),
        (-half_x, half_y),
    ]
    for x, y in corners:
        verts.append((x, y, low))
    for x, y in corners:
        verts.append((x, y, high))
    faces.append((base + 3, base + 2, base + 1, base))
    faces.append((base + 4, base + 5, base + 6, base + 7))
    quad_uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    uvs.extend([quad_uv, quad_uv])
    slots.extend([role] * 2)
    for index in range(4):
        following = (index + 1) % 4
        faces.append((base + index, base + following,
                      base + 4 + following, base + 4 + index))
        uvs.append(quad_uv)
        slots.append(role)


#: Keep adjacent shells apart to prevent z-fighting.
CLEARANCE = 0.004

#: Flashing overlap beyond the skylight opening, in metres.
FLASHING = 0.07
UPSTAND = 0.09
SASH_BAND = 0.045
SASH_DEPTH = 0.055
GLAZING = 0.006


def standard_roof_window_mesh(width: float, height: float) -> WindowMesh:
    """A flashed roof window: outer frame, sash, and glazing.

    Local axes match the roof face frame it is placed with: X across the eave,
    Y up the slope, Z normal to the roof plane, origin at the centre of the
    opening on the roof plane.

    Three separate closed shells, mirroring how a real roof window is built:
    the **outer frame** is fixed and flashed to the roof, reaching `FLASHING`
    beyond the opening so it laps the tiles the opening cut; the **sash** sits
    inside the daylight and is what would open; the **glazing** sits inside the
    sash. Every shell is inset by `CLEARANCE` from the next, so no two faces
    are ever coplanar.
    """

    if width <= 0 or height <= 0:
        raise AuthoringError("roof window width and height must be positive")
    daylight_x = width / 2.0
    daylight_y = height / 2.0
    if min(daylight_x, daylight_y) <= CLEARANCE + SASH_BAND + CLEARANCE:
        raise AuthoringError(
            f"roof window {width} x {height} is too small for its frame; "
            f"each side needs more than "
            f"{2 * (CLEARANCE + SASH_BAND + CLEARANCE):.3f} m"
        )

    verts: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []
    slots: list[str] = []

    # Outer frame: laps the cut tiles, and its inner edge is the daylight.
    _ring(
        verts, faces, uvs, slots, "frame",
        daylight_x + FLASHING, daylight_y + FLASHING,
        daylight_x, daylight_y,
        -0.02, UPSTAND,
    )

    # Sash: clear of the frame's reveal, and stopping below its top face.
    sash_outer_x = daylight_x - CLEARANCE
    sash_outer_y = daylight_y - CLEARANCE
    sash_inner_x = sash_outer_x - SASH_BAND
    sash_inner_y = sash_outer_y - SASH_BAND
    sash_top = UPSTAND - CLEARANCE * 2.5
    _ring(
        verts, faces, uvs, slots, "frame",
        sash_outer_x, sash_outer_y,
        sash_inner_x, sash_inner_y,
        sash_top - SASH_DEPTH, sash_top,
    )

    # Glazing: inside the sash, and floating between its faces.
    glass_centre = sash_top - SASH_DEPTH / 2.0
    _box(
        verts, faces, uvs, slots, "glazing",
        sash_inner_x - CLEARANCE, sash_inner_y - CLEARANCE,
        glass_centre - GLAZING / 2.0, glass_centre + GLAZING / 2.0,
    )
    return procedures.validate_mesh(
        "standard_roof_window_mesh", (verts, faces, uvs, slots)
    )


@dataclass(frozen=True, slots=True)
class WindowProfile:
    """A roof window type: how it is built, and how far it laps the tiles."""

    key: str
    build: Callable[[float, float], WindowMesh]
    flashing: float = FLASHING

    def geometry(self, width: float, height: float) -> WindowMesh:
        return self.build(width, height)


STANDARD_WINDOW = WindowProfile(
    key="window.standard",
    build=standard_roof_window_mesh,
    flashing=FLASHING,
)

PROFILES: dict[str, WindowProfile] = {STANDARD_WINDOW.key: STANDARD_WINDOW}


def profile(key: str) -> WindowProfile:
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise AuthoringError(f"unknown window profile {key!r}; known: {known}")
    return PROFILES[key]
