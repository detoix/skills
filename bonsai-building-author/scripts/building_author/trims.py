"""Roof trims: the edge classifier, and the verge trim it selects.

Two concerns, kept apart the way `tiles.py` keeps a tile's mesh apart from
the layout that places it:

- `edge_kind()` classifies one edge of a roof solid from its two adjacent
  faces. It is the whole of the "which edges get what" question, stated once
  as a function of geometry rather than spread across the places that build
  trims.
- A `VergeProfile` carries the **section** - a plain upright rectangle - and
  where that rectangle sits against the roof's own arris. Nothing here builds
  a mesh; the IFC phase sweeps it.

## Which edges get a trim

Classify each roof edge from its adjacent faces.

| adjacent faces | edge | trim |
| --- | --- | --- |
| two upward, convex, level | ridge | cap |
| two upward, convex, raking | hip | cap |
| two upward, concave | valley | lined - see `references/trims.md` |
| one upward, level | eave | gutter |
| one upward, raking | verge | **this module** |

It needs no gable list of its own: `roof_edge(defines_slope=False)` is
already what makes the solid produce those edges.

## Convexity is the local fold at the shared edge

The signed fold is `(n_a x n_b) . edge_a`, where `edge_a` follows face A's
outward winding. A bmesh edge's storage order is arbitrary; its face loop
supplies this direction. Swapping the faces reverses both the cross product
and the wound direction, preserving the answer. Whole-face centres cannot
describe this local fold on concave roof polygons. Coplanar seams carry no
trim.

## The section is an upright rectangle

A verge trim is a board standing on edge along the rake, its outer face flush
with the roof's own gable plane and its top standing proud of the covering as
a raised lip - what a tiled roof's `obróbka blacharska` looks like from the
ground, and what the trim in the reference photograph is.

So the section is `IfcRectangleProfileDef` - `XDim` and `YDim` as readable
numbers - rather than a folded sheet outline. **Its plane is vertical**: one
axis world up, the other the horizontal across the run. The rake is then the
extrusion direction, skew to that plane, which makes this an *oblique*
extrusion.

That obliquity is the whole point. An extrusion is a pure translation sweep,
so every edge of the profile stays parallel to itself for the length of the
run: the board leans with the rake while its vertical edges stay truly
vertical. Sweeping a section perpendicular to the rake instead - which is
what a `FixedReference` sweep does, and what this module did first - rotates
the board about the run and stands its edges normal to the roof plane, which
is visibly wrong against any gable.

`upstand` is how far the top sits above the arris. It is the **one** thing a
trim takes from the covering, and `roof_payload` derives it through
`upstand_over()` rather than defaulting it, because the lip has to read as a
lip over whatever relief the tile under it has. What that cannot do is move
the board: the section's zero is the arris, so the trim is flush to the
roof's own edge whichever way the lip goes.

## What is deliberately simplified

- A run is **one length**, so the end laps a real 2 m trim would need are not
  modelled - the same call `gutters.py` makes for unions and expansion
  joints. The supply figures live in `references/trims.md`, where a fact
  nothing computes with belongs.
- The board is solid. Real sheet trim is folded from coil over a timber
  barge, and the fold, the drip and the timber behind it are all one
  rectangle here.

Two runs meeting at a gable apex is **not** on that list. They butt flush by
construction, for the reason `references/trims.md` derives.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, NamedTuple

from .values import AuthoringError


class VergeRun(NamedTuple):
    """One placed verge run: where the board goes and which way it leans.

    Named rather than a bare tuple for the reason `gutters.Sole` is. Two of
    these fields are horizontal unit vectors in the same frame, and `across`
    and `along` are exactly the pair a reader would expect to be
    interchangeable - they are perpendicular, both unit, both horizontal, and
    swapping them yields a board lying flat along the rake instead of standing
    on it. Positionally that swap is invisible; by name it cannot be written.

    `up` is deliberately absent: it is world vertical for every run there will
    ever be, so returning it would suggest it varies. The template writes the
    constant into the placement directly.
    """

    #: The lower end of the roof's own arris, where the section's zero sits.
    origin: Any
    #: Horizontal, pointing inboard across the run.
    across: Any
    #: Horizontal, along the run in plan. `across x up`, so the frame is
    #: right-handed and no face or vert order can flip it.
    along: Any
    #: The run direction expressed in that frame - what the oblique
    #: `ExtrudedDirection` needs.
    rake: tuple[float, float, float]
    #: True length up the rake, which is the extrusion's own `Depth`.
    length: float

#: An edge between two upward faces that folds away from both, running level.
RIDGE = "ridge"

#: The same fold, running up a slope.
HIP = "hip"

#: An edge between two upward faces that folds *into* them.
VALLEY = "valley"

#: A level edge where the roof surface stops.
EAVE = "eave"

#: A raking edge where the roof surface stops - what a gable raises, and the
#: only edge this module trims.
VERGE = "verge"

#: How far from level an edge may run and still count as level. An eave and a
#: ridge are both modelled dead level, so this is a numeric tolerance on
#: skeleton output rather than a shallow pitch anyone declared.
LEVEL_EPS = 1e-6

#: How far a face normal must tip up before the face counts as roof surface.
#: A gable's plane is vertical and a rafter cut faces outward, so both fall
#: below this and neither is a surface a trim sits on.
UPWARD_EPS = 1e-6

#: Sine of the smallest resolved fold between unit face normals. The tolerance
#: accommodates Blender's float32 normal noise on coplanar subdivisions.
FOLD_EPS = 1e-6

#: How far a verge trim's top stands above the covering it closes.
#:
#: Not a tolerance. `CLEARANCE` and `SILL_RISE` exist to stop two faces
#: landing on one plane; this is a **visible lip**, and it has to read as one
#: from the ground. A clay tile reaches 0.089 m above the roof face, so the
#: catalogue's own 0.100 m fixing left 0.011 m of daylight and the two merged
#: into each other at any distance.
COVER_LIP = 0.040


def upstand_over(envelope: float, lip: float = COVER_LIP) -> float:
    """How high to fix a verge trim over a covering of the given envelope.

    Derived rather than defaulted, because the answer changes with what the
    roof is covered with and a constant cannot be right for two coverings of
    different relief.

    This is the **only** number a trim takes from the covering. The board is
    flush to the roof's own gable edge whichever way this goes, so getting it
    wrong moves the lip, not the trim - which is what separates it from the
    seating this module tried first, where the same coupling floated the whole
    board off the roof and left its edge bare.
    """

    if envelope < 0:
        raise AuthoringError("a covering's envelope cannot be negative")
    if lip <= 0:
        raise AuthoringError("a verge trim's lip over its covering must be positive")
    return envelope + lip


def _upward(normal: tuple[float, float, float]) -> bool:
    return normal[2] > UPWARD_EPS


def _level(direction: tuple[float, float, float]) -> bool:
    return abs(direction[2]) <= LEVEL_EPS


def edge_kind(
    normal_a: tuple[float, float, float],
    normal_b: tuple[float, float, float],
    direction: tuple[float, float, float],
) -> str | None:
    """Classify one edge of a roof solid from the two faces meeting on it.

    Returns one of the constants above, or ``None`` when neither face is roof
    surface or the faces are coplanar. Both normals are outward and unit.
    ``direction`` is a unit vector following face A's winding along the shared
    edge; it must reverse when A and B are exchanged. Use
    ``edge_kind_from_bmesh`` to resolve arbitrary Blender storage order.
    """

    up_a, up_b = _upward(normal_a), _upward(normal_b)
    if not up_a and not up_b:
        return None
    if up_a != up_b:
        return EAVE if _level(direction) else VERGE
    cross = (
        normal_a[1] * normal_b[2] - normal_a[2] * normal_b[1],
        normal_a[2] * normal_b[0] - normal_a[0] * normal_b[2],
        normal_a[0] * normal_b[1] - normal_a[1] * normal_b[0],
    )
    fold = sum(component * along for component, along in zip(cross, direction))
    if abs(fold) <= FOLD_EPS:
        return None
    if fold < 0:
        return VALLEY
    return RIDGE if _level(direction) else HIP


def face_edge_direction(edge, face) -> tuple[float, float, float]:
    """The unit shared-edge direction in one BMesh face's outward winding.

    This adapter only reads the face loop; it needs no Blender imports. A
    degenerate edge returns zero and is ignored by ``edge_kind_from_bmesh``.
    """

    loop = next(loop for loop in edge.link_loops if loop.face == face)
    start, end = loop.vert.co, loop.link_loop_next.vert.co
    delta = tuple(end[axis] - start[axis] for axis in range(3))
    length = math.sqrt(sum(component * component for component in delta))
    if length <= LEVEL_EPS:
        return (0.0, 0.0, 0.0)
    return tuple(component / length for component in delta)


def edge_kind_from_bmesh(edge) -> str | None:
    """Classify a manifold BMesh edge with current outward face normals."""

    if len(edge.link_faces) != 2:
        return None
    face_a, face_b = edge.link_faces
    direction = face_edge_direction(edge, face_a)
    if direction == (0.0, 0.0, 0.0):
        return None
    return edge_kind(tuple(face_a.normal), tuple(face_b.normal), direction)


@dataclass(frozen=True, slots=True)
class VergeProfile:
    """One verge trim design: an upright board along a rake.

    The same split a gutter uses - the profile carries the shape, the
    occurrence carries only what a script wants to vary.

    ``height`` and ``thickness`` are the rectangle, and both are catalogued:
    a `wiatrownica` is sold as "170 x 80", the face down the gable by the leg
    in over the covering.

    ``upstand`` is **not** catalogued - it is where the trim is fixed rather
    than what it is - so it is stated on the profile. It has to clear the
    covering's own relief or the tiles stand proud of the board that is meant
    to close them: a clay tile laid on its 6 degree tilt reaches 0.089 m above
    the roof plane, which is what the 0.100 m default is sized against. This
    is the one number here that cares what the roof is covered with.

    All three are measured in the vertical plane the section is stated in, so
    ``height`` is a true vertical dimension and stays one however steep the
    rake is. That is the property the whole placement exists to preserve.
    """

    key: str
    height: float
    thickness: float
    upstand: float

    def resolved(
        self,
        height: float | None = None,
        thickness: float | None = None,
        upstand: float | None = None,
    ) -> dict[str, float]:
        """The three numbers the IFC phase sweeps, checked here.

        Returned as a mapping rather than a tuple: all three are lengths in
        metres of the same order of magnitude, so a positional triple can be
        permuted and still look plausible in every test written against a
        square-ish section. `gutters.Sole` exists for the same reason.
        """

        values = {
            "height": self.height if height is None else height,
            "thickness": self.thickness if thickness is None else thickness,
            "upstand": self.upstand if upstand is None else upstand,
        }
        for label in ("height", "thickness"):
            if values[label] <= 0:
                raise AuthoringError(
                    f"a verge trim's {label} must be positive, "
                    f"got {values[label]}"
                )
        if values["upstand"] < 0:
            raise AuthoringError(
                f"a verge trim's upstand cannot be negative, "
                f"got {values['upstand']}"
            )
        if values["upstand"] >= values["height"]:
            raise AuthoringError(
                f"a verge trim standing {values['upstand']} m above the arris "
                f"cannot be {values['height']} m tall; the whole board would "
                "be above the roof edge with nothing lapping it"
            )
        return values

    def centre(self, **overrides: float | None) -> tuple[float, float]:
        """Where the rectangle's centre sits, in the section frame.

        The frame is ``(across, up)``: across runs **inboard** from the roof's
        gable plane, so the outer face sits at zero and the board is entirely
        at positive across; up is world vertical, with zero on the arris.

        `IfcRectangleProfileDef` is centred on its own placement, so this is
        what its 2D position carries. Stating it here rather than in the
        template is what lets it be tested without a Blender session.
        """

        values = self.resolved(**overrides)
        return (
            values["thickness"] / 2.0,
            values["upstand"] - values["height"] / 2.0,
        )


#: The ordinary Polish domestic `wiatrownica`, catalogued as **170 x 80 mm**
#: and sold in 2 m lengths: 170 mm down the gable face, 80 mm in over the
#: covering. Those two are the supplier's; `upstand` is not - see below.
VERGE = VergeProfile(
    key="verge.standard",
    height=0.170,
    thickness=0.080,
    upstand=0.100,
)

#: A deeper board, near the top of the made-to-measure range (A 100-300 mm
#: down the face, B 50-200 mm across), for a thicker roof buildup or a tile
#: standing further proud.
VERGE_DEEP = VergeProfile(
    key="verge.deep",
    height=0.250,
    thickness=0.120,
    upstand=0.130,
)

PROFILES: dict[str, VergeProfile] = {
    VERGE.key: VERGE,
    VERGE_DEEP.key: VERGE_DEEP,
}


def profile(key: str) -> VergeProfile:
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise AuthoringError(f"unknown verge trim profile {key!r}; known: {known}")
    return PROFILES[key]
