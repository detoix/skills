"""Gutters and downspouts: the rainwater system a roof never builds itself.

Same split as `railings.py`, `sills.py` and `tiles.py` - the shape is a
procedure, written out in code rather than loaded from a model file. What
differs is where that shape lands. A guardrail is posts, infill and a rail:
three parts in one product, which is why `railings.py` returns a mesh and
`assign_role_split_body` splits it. A gutter is **one folded sheet swept
along a straight run**, and IFC has words for exactly that - a profile and
an extrusion - so this module returns *profiles*, not meshes, and the IFC
phase sweeps them.

That is the doctrine, not a departure from it: a swept solid carries its own
section as readable numbers, so a consumer reads a 125 mm half-round gutter
back off the file. The same gutter written as a face set is a coordinate
list nobody can query, which is the "dead geometry" the skill already
refuses elsewhere.

## The frame

Every section is stated in the run's own **section frame**:

    u   up, from the gutter's top edge downward (so the trough is negative u)
    v   across the run, positive toward the building

`v = 0` is the **back** of the gutter - the face that meets the fascia - and
the body projects outboard, into negative `v`. The datum is the back rather
than the centre because the fascia is what a gutter is actually hung on, and
because a run placed on its own eave line then needs no lateral offset: half
a centred section would otherwise sit inboard of that line, buried in the
roof it hangs off.

`u = 0` is the gutter's own top edge, and `hang()` says how far below the
roof's drip edge that lands: its own rise plus a clearance, so the covering
oversails into the trough. Nothing about the roof's *thickness* enters into
it - the whole section is outboard of the roof's face, so its height cannot
clash. Turning the frame into the profile coordinates an
`IfcExtrudedAreaSolid` wants is the IFC phase's job - see
`references/gutters.md` for the one axis flip involved.

## Where the numbers come from

- EN 612 is the European standard for eaves gutters and rainwater pipes of
  sheet metal; its half-round sizes are named by nominal width, of which
  125 mm is the common domestic size and the default here.
- Sheet thicknesses follow the same standard's ordinary range: 0.6 mm for
  steel and 0.7 mm for zinc/titanium-zinc.
- Round downpipe runs 50, 65, 68 and 80 mm in the UK and 80 to 150 mm in
  Polish steel systems; 100 mm is what pairs with a 125 mm half-round gutter.
  Square downpipe is catalogued at 65 x 65 and 80 x 80 mm.
- Elbows deflect 67.5 degrees in Bryza and Gamrat PVC, 72 in KJG steel.

## What is deliberately simplified

- Sections are polylines. A rolled bead is a short straight return, not the
  true rolled edge, and the half-round trough is sampled into segments
  rather than carried as an arc. The sweep is exact; only the section is
  faceted.
- Gutters are **level**. Real installations fall toward an outlet, but fall
  tilts each run by its own angle, and two runs falling toward different
  outlets would no longer share a mitre plane - see `references/gutters.md`.
- No brackets, no unions, no expansion joints. A run is one length of
  gutter; the fixings that hold it up are not modelled.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

from .values import AuthoringError

#: A point in the section frame: (u up, v across).
Section = list[tuple[float, float]]


class Sole(NamedTuple):
    """A section's lowest point, in its own frame.

    Named rather than a bare pair, because a **half-round's sole sits at
    `(-nominal/2, -nominal/2)`** - up and across are the same number, so
    transposing them changes nothing at all on the default profile and every
    test written against it still passes. On a box gutter, whose sole is at
    `(-0.8 * nominal, -nominal/2)`, the same swap throws a downspout 37.5 mm
    sideways out of its own trough. That happened; this is the fix that stops
    it recurring, rather than the one that patched the instance.
    """

    up: float
    across: float


#: How finely the half-round trough is sampled. Twelve segments over a half
#: turn holds the chord error under a tenth of a millimetre at 125 mm, which
#: is below the sheet thickness itself - past that the extra points cost file
#: size and buy nothing visible.
TROUGH_SEGMENTS = 12

#: EN 612 sheet thicknesses: steel and zinc respectively. A gutter type may
#: state its own; these are what the profiles default to.
STEEL_SHEET = 0.0006
ZINC_SHEET = 0.0007

#: How far a run is extruded past its own end before the mitre plane cuts it
#: back, as a multiple of the section's own half width. The plane has to have
#: material to cut: stopping the extrusion exactly at the corner leaves the
#: cut coplanar with the end face and the boolean nothing to resolve.
MITRE_OVERRUN = 1.2

#: How far a run's own highest point is held below the roof's drip edge, so
#: the covering oversails into the trough instead of ending flush with its
#: back upstand. The same deliberate non-coincidence `SILL_RISE` and
#: `OPENING_REACH` exist for: two faces at exactly one height are what nothing
#: resolves consistently.
EAVE_CLEARANCE = 0.010

#: How far a downspout is held clear of the soffit it swans back under, on
#: top of its own half width. A pipe that turns inboard while still level with
#: the roof's overhang runs straight through it.
SOFFIT_CLEARANCE = 0.020

#: How a downspout finishes at the bottom.
#:
#: ``straight`` stops the pipe where its own fall ends, cut square - what a
#: downspout does when it discharges into a gully directly below it.
#:
#: ``shoe`` adds a kicked final segment, throwing the water clear of the wall
#: onto a splash block or into an open gully set away from the plinth. Its
#: mouth is inclined without being cut: a swept solid ends perpendicular to
#: its own directrix, so a kicked segment arrives with its mouth already on
#: the slant.
TERMINATIONS = frozenset({"straight", "shoe"})

#: How far a shoe reaches along its own kick. 0.15 m is the ordinary domestic
#: length; at SHOE_ANGLE it throws the water about 0.139 m clear of the pipe.
SHOE_LENGTH = 0.15

#: The angle a shoe kicks at, **from vertical** - the deflection, which is how
#: Polish catalogues name an elbow and the opposite of how UK ones do. A
#: `kolano 67,5 stopni` and a "112.5 degree offset bend" are the same fitting:
#: 67.5 + 112.5 = 180. Bryza and Gamrat PVC run 67.5; KJG and Bryza steel run
#: 72. Not exposed per declaration - one angle is what makes every shoe on a
#: building match, and a script that wants a different system changes it here.
SHOE_ANGLE = 67.5


def _normalize(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    if length == 0.0:
        raise AuthoringError("cannot take the direction of a zero-length vector")
    return (x / length, y / length)


def _intersect(
    origin_a: tuple[float, float],
    direction_a: tuple[float, float],
    origin_b: tuple[float, float],
    direction_b: tuple[float, float],
) -> tuple[float, float] | None:
    """Where two lines cross, or None when they are parallel.

    The same solve `polygons._intersect` does for a roof's overhang corners,
    kept here rather than imported because that module works in plan and this
    one in a section frame - sharing a helper across the two would mean one
    of them reading in the other's coordinates.
    """

    determinant = (
        direction_a[0] * direction_b[1] - direction_a[1] * direction_b[0]
    )
    if abs(determinant) < 1e-12:
        return None
    delta = (origin_b[0] - origin_a[0], origin_b[1] - origin_a[1])
    t = (delta[0] * direction_b[1] - delta[1] * direction_b[0]) / determinant
    return (origin_a[0] + direction_a[0] * t, origin_a[1] + direction_a[1] * t)


def offset_open_polyline(points: Section, distance: float) -> Section:
    """Offset an open polyline sideways, mitreing every interior fold.

    Each segment is pushed along its own normal, then consecutive offset
    lines are intersected, so a fold keeps its thickness through the corner
    instead of pinching. The two ends have only one segment each, so they
    take the plain offset. Parallel neighbours - a fold of no angle - cannot
    be intersected and fall back the same way.

    Offsetting each *vertex* along its own normal instead is the tempting
    shortcut and it is wrong at every fold: a 90 degree fold offset that way
    comes out `distance * (1 - 1/sqrt(2))` thin on the inside. This is the
    same mitred offset a roof's overhang polygon already uses, done on an
    open run rather than a closed one.
    """

    if len(points) < 2:
        raise AuthoringError("a gutter section needs at least two points")

    lines = []
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        direction = _normalize(end[0] - start[0], end[1] - start[1])
        normal = (direction[1], -direction[0])
        lines.append(
            (
                (
                    start[0] + normal[0] * distance,
                    start[1] + normal[1] * distance,
                ),
                direction,
            )
        )

    result: Section = [lines[0][0]]
    for index in range(1, len(lines)):
        previous_origin, previous_direction = lines[index - 1]
        origin, direction = lines[index]
        corner = _intersect(previous_origin, previous_direction, origin, direction)
        result.append(corner if corner is not None else origin)
    last_origin, last_direction = lines[-1]
    span = math.hypot(
        points[-1][0] - points[-2][0], points[-1][1] - points[-2][1]
    )
    result.append(
        (
            last_origin[0] + last_direction[0] * span,
            last_origin[1] + last_direction[1] * span,
        )
    )
    return result


def sheet_ring(centreline: Section, thickness: float) -> Section:
    """A folded sheet's closed outline: the centreline offset both ways.

    Returned closed - the first point repeated last - because that is what
    `IfcArbitraryClosedProfileDef` wants of its `IfcPolyline`, and leaving a
    consumer to close it is how a profile ends up with one missing face.

    `IfcCenterLineProfileDef` says exactly this in the schema - a centreline
    plus a `Thickness` - and would be the better statement of intent. It is
    not used because IfcOpenShell 0.8.5 ignores that `Thickness` and closes
    the bare centreline into a filled polygon instead, so a 0.6 mm gutter
    arrives as a solid lump of metal. Building the ring here is what makes
    the sheet a sheet in every consumer, not only in ones that implement the
    offset. See `references/gutters.md`.
    """

    if thickness <= 0:
        raise AuthoringError("a gutter section's thickness must be positive")
    outward = offset_open_polyline(centreline, thickness / 2.0)
    inward = offset_open_polyline(centreline, -thickness / 2.0)
    ring = outward + list(reversed(inward))
    ring.append(ring[0])
    return ring


def _backed(section: Section, half: float) -> Section:
    """Move a section drawn about its own centre onto its back datum.

    Sections read most naturally centred - a half round is a semicircle about
    zero - but a gutter hangs off a fascia, not off its own centreline. Every
    profile is therefore drawn centred and shifted here once, so `v = 0` is
    the back face and the whole body sits at negative `v`.
    """

    return [(u, v - half) for u, v in section]


def half_round_section(nominal: float) -> Section:
    """A half-round eaves gutter, EN 612's ordinary domestic section.

    A semicircular trough of `nominal / 2` radius hung under the eave, with
    a rolled bead returning at the front edge and an upstand at the back
    where it meets the fascia. Both returns are straight (see the module
    docstring) and both point upward, which is what stops the section being
    a bare half circle a consumer would read as a pipe cut in half.
    """

    radius = nominal / 2.0
    bead = nominal * 0.10
    upstand = nominal * 0.16
    section: Section = [(bead, -radius), (0.0, -radius)]
    for step in range(1, TROUGH_SEGMENTS):
        angle = math.pi * step / TROUGH_SEGMENTS
        section.append((-radius * math.sin(angle), -radius * math.cos(angle)))
    section.extend([(0.0, radius), (upstand, radius)])
    return _backed(section, radius)


def box_section(nominal: float) -> Section:
    """A square/box eaves gutter: a rectangular trough, same returns.

    Depth is 0.8 of the width, the ordinary proportion for a box gutter -
    deeper than that and it stops shedding into the outlet, shallower and it
    carries less than the half-round it replaces.
    """

    half = nominal / 2.0
    depth = nominal * 0.8
    bead = nominal * 0.10
    upstand = nominal * 0.16
    return _backed(
        [
            (bead, -half),
            (0.0, -half),
            (-depth, -half),
            (-depth, half),
            (0.0, half),
            (upstand, half),
        ],
        half,
    )


def concealed_section(nominal: float) -> Section:
    """A concealed (parapet or valley) gutter, lined rather than hung.

    The trough sits inside the roof
    line rather than under it, so both edges rise into upstands - one against
    the roof covering, one against the parapet - and there is no front bead
    to shed off, because there is no front.
    """

    half = nominal / 2.0
    depth = nominal * 0.6
    upstand = nominal * 0.35
    return _backed(
        [
            (upstand, -half),
            (0.0, -half),
            (-depth, -half),
            (-depth, half),
            (0.0, half),
            (upstand, half),
        ],
        half,
    )


@dataclass(frozen=True, slots=True)
class GutterProfile:
    """One gutter design: how its section is built, named the way it is chosen."""

    key: str
    build: Callable[[float], Section]
    default_thickness: float

    def section(self, nominal: float) -> Section:
        if nominal <= 0:
            raise AuthoringError("a gutter's nominal size must be positive")
        return self.build(nominal)

    def ring(self, nominal: float, thickness: float) -> Section:
        return sheet_ring(self.section(nominal), thickness)

    def plate(self, nominal: float) -> Section:
        """The trough's cross section as a **filled** outline, for a stop-end.

        A stop-end is a flat plate soldered across the end of a run, so its
        profile is the section closed into a polygon - not `ring()`, which is
        the sheet's own outline and would extrude into an annulus: a thin
        hollow slice of the gutter, flush against the run's own end face,
        closing nothing and invisible against the metal it was cut from.
        """

        section = self.section(nominal)
        return section + [section[0]]

    def projection(self, nominal: float) -> float:
        """How far the section reaches out from its own back datum.

        What a mitre has to overrun by - read off the built section rather
        than assumed to be `nominal`, because a bead or an upstand can sit
        outside the nominal width.
        """

        return max(abs(v) for _, v in self.section(nominal))

    def rise(self, nominal: float) -> float:
        """How far the section reaches **above** its own datum.

        The back upstand, ordinarily. What a run has to be held below the
        drip edge by, so its highest point tucks under the covering rather
        than standing proud of it.
        """

        return max(u for u, _ in self.section(nominal))

    def sole(self, nominal: float) -> Sole:
        """The section's lowest point: where an outlet is cut and a downspout
        hangs from.

        Read off the section rather than assumed to be its middle, because a
        box gutter's sole is a flat run and a half round's is a single point.
        This is the whole of what a downspout needs from its gutter - which is
        why a downspout never has to ask about a roof.
        """

        section = self.section(nominal)
        lowest = min(u for u, _ in section)
        at = [v for u, v in section if abs(u - lowest) < 1e-12]
        return Sole(up=lowest, across=sum(at) / len(at))


HALF_ROUND = GutterProfile(
    key="gutter.half_round",
    build=half_round_section,
    default_thickness=ZINC_SHEET,
)
BOX = GutterProfile(
    key="gutter.box",
    build=box_section,
    default_thickness=STEEL_SHEET,
)
CONCEALED = GutterProfile(
    key="gutter.concealed",
    build=concealed_section,
    default_thickness=STEEL_SHEET,
)

PROFILES: dict[str, GutterProfile] = {
    HALF_ROUND.key: HALF_ROUND,
    BOX.key: BOX,
    CONCEALED.key: CONCEALED,
}


def profile(key: str) -> GutterProfile:
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise AuthoringError(f"unknown gutter profile {key!r}; known: {known}")
    return PROFILES[key]


def hang(profile: GutterProfile, nominal: float) -> float:
    """How far below the **drip edge** a run's own datum sits.

    A gutter hangs on the fascia, which is the roof's own outer face, and its
    top tucks just under the covering so what leaves the drip edge lands in
    the trough. The whole run is outboard of that face - `v = 0` is its back -
    so nothing about its height can clash with the roof, whatever the roof's
    thickness is.

    Dropping it by the roof's *own* vertical eave thickness instead, which
    this did first, puts the run on the soffit line: 0.39 m below the drip
    edge on a 0.30 m roof at 40 degrees, hung off the bottom of the fascia
    rather than the top of it. That was an over-correction for a plan clash
    the back datum had already fixed, and it is why this function exists
    rather than the arithmetic living at the call site.
    """

    return profile.rise(nominal) + EAVE_CLEARANCE


def sole_below_eave(profile: GutterProfile, nominal: float) -> float:
    """How far below the drip edge a run's sole sits - what a downspout falls
    from, and the one number a script needs to state a pipe's own `length`.

    Exposed so a building script never restates `hang()`: a script that
    recomputes it carries a second copy of a detail that belongs to this
    module, and goes silently stale the day the detail changes.
    """

    return hang(profile, nominal) - profile.sole(nominal).up


@dataclass(frozen=True, slots=True)
class PipeProfile:
    """One downspout cross section, named the way it is chosen.

    The same split a gutter uses: the **profile** carries the shape, the
    occurrence carries only its size and gauge. `nominal_size` is the
    outside dimension across - a diameter for a round pipe, a width for a
    rectangular one - which is how both are catalogued.

    `aspect` is depth over width, so a square pipe is 1.0 and a rectangular
    one states its own ratio rather than making every caller pass a second
    dimension that a round pipe has no use for.
    """

    key: str
    shape: str
    default_size: float
    default_thickness: float
    aspect: float = 1.0

    def dimensions(self, nominal: float, thickness: float) -> dict[str, float]:
        """The numbers the IFC phase sweeps, resolved and checked here.

        A wall thicker than half the pipe leaves no bore, which the schema
        will not say and the kernel will not catch - `IfcSweptDiskSolid`
        requires `Radius` to exceed `InnerRadius`, and a hollow rectangle
        with no cavity is simply a solid bar nobody notices.
        """

        if nominal <= 0:
            raise AuthoringError("a downspout's nominal size must be positive")
        if thickness <= 0:
            raise AuthoringError("a downspout's sheet thickness must be positive")
        if self.shape == "round":
            radius = nominal / 2.0
            if thickness >= radius:
                raise AuthoringError(
                    f"a {nominal} m downspout cannot have {thickness} m walls; "
                    "they would meet in the middle"
                )
            return {
                "shape": "round",
                "radius": radius,
                "inner_radius": radius - thickness,
            }
        depth = nominal * self.aspect
        if thickness * 2.0 >= min(nominal, depth):
            raise AuthoringError(
                f"a {nominal} x {depth} m downspout cannot have {thickness} m "
                "walls; they would meet in the middle"
            )
        return {
            "shape": "rectangular",
            "x": nominal,
            "y": depth,
            "wall": thickness,
            # A folded or extruded rectangular pipe is never sharp-cornered.
            # The fillet is held under half the wall so the profile stays
            # valid at the thinnest gauge this accepts.
            "fillet": min(thickness * 2.0, nominal / 8.0),
        }


#: Round is the ordinary domestic pipe: 50, 65, 68 and 80 mm in the UK, 80 to
#: 150 mm in Polish steel systems. 100 mm is what pairs with the 125 mm
#: half-round gutter this module defaults to.
PIPE_ROUND = PipeProfile(
    key="downspout.round",
    shape="round",
    default_size=0.100,
    default_thickness=0.0015,
)
#: Square downpipe, catalogued at 65 x 65 and 80 x 80 mm.
PIPE_RECTANGULAR = PipeProfile(
    key="downspout.rectangular",
    shape="rectangular",
    default_size=0.080,
    default_thickness=0.0015,
    aspect=1.0,
)

PIPE_PROFILES: dict[str, PipeProfile] = {
    PIPE_ROUND.key: PIPE_ROUND,
    PIPE_RECTANGULAR.key: PIPE_RECTANGULAR,
}


def pipe_profile(key: str) -> PipeProfile:
    if key not in PIPE_PROFILES:
        known = ", ".join(sorted(PIPE_PROFILES))
        raise AuthoringError(f"unknown downspout profile {key!r}; known: {known}")
    return PIPE_PROFILES[key]


def downspout_path(
    length: float,
    standoff: float,
    drop: float,
    termination: str,
    shoe_length: float = SHOE_LENGTH,
) -> list[tuple[float, float, float]]:
    """A downspout's directrix, in its own frame: X along the run it hangs
    from, Y toward the building, Z up from the gutter's sole.

    The path has three segments: fall
    `drop` clear of the gutter, swan back `standoff` over the same distance
    down, then fall the rest of the way. A ``shoe`` adds a fourth, kicked the
    other way - **outboard**, away from the building - so the water leaves
    the pipe pointing away from the wall rather than at its own plinth.

    ``length`` is the whole vertical fall from the gutter's sole to the end
    of that straight run, not the leftover segment after the swan neck. It is
    the number that can be measured on site, which is the number a script
    should be stating; the segment is arithmetic and belongs here. A shoe
    hangs below it, as a real one does.
    """

    if termination not in TERMINATIONS:
        raise AuthoringError(
            f"a downspout termination must be one of "
            f"{', '.join(sorted(TERMINATIONS))}; got {termination!r}"
        )
    if length <= drop + standoff:
        raise AuthoringError(
            f"a downspout of {length} m cannot fall {drop} m clear and swan "
            f"back {standoff} m; its own neck would use the whole run"
        )

    path = [
        (0.0, 0.0, 0.0),
        (0.0, 0.0, -drop),
        (0.0, standoff, -drop - standoff),
        (0.0, standoff, -length),
    ]
    if termination == "shoe":
        kick = shoe_length * math.sin(math.radians(SHOE_ANGLE))
        fall = shoe_length * math.cos(math.radians(SHOE_ANGLE))
        path.append((0.0, standoff - kick, -length - fall))
    return path


def mitre_normal(
    incoming: tuple[float, float], outgoing: tuple[float, float]
) -> tuple[float, float] | None:
    """The plan normal of the mitre plane where two runs meet, or None.

    `incoming` arrives at the corner and `outgoing` leaves it, both unit
    directions in plan. The mitre plane bisects the turn, so its normal is
    the **sum** of the two directions - not their difference, which is the
    joint line itself. The incoming run keeps the negative side, the
    outgoing run the positive side.

    Two runs meeting straight on give back the incoming direction unchanged,
    which is a plain butt joint at the corner and still correct. Two runs
    doubling back on themselves have no bisector at all and give back None,
    for the caller to refuse by name.

    This is the whole of the corner-window trick, stated once: because the
    plane bisects, each run cuts at the same angle to its own axis from its
    own section, and the two cuts land on one plane without either run ever
    being handed the other's numbers.
    """

    total = (incoming[0] + outgoing[0], incoming[1] + outgoing[1])
    if math.hypot(*total) < 1e-9:
        return None
    return _normalize(*total)
