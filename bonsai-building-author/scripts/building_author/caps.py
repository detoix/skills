"""Ridge and hip caps: one procedure per cap type, plus the run that lays them.

The same split `tiles.py` makes, one dimension down:

- Each cap type has **its own procedure** that builds that cap and nothing
  else. Adding a type means writing another procedure next to these.
- `spacing()` is the layout. It returns stations along a run and nothing else,
  and asks a profile only for `module` and `nose`.
- `seating()` is the one thing a cap takes from the covering it closes, the
  way `trims.upstand_over()` is for a verge board.

A cap is **presentation only**. Unlike the tile field it has no `IfcCovering`
of its own: it is merged into the roof covering's Blender mesh, which is
already swapped onto the `IfcCovering(ROOFING)` the IFC phase created. The
file therefore says "this roof is covered in clay tile" and the capping is
part of that covering, which is what it is. See `references/caps.md` for why,
and for what that costs.

## One cap per covering, and which one is not obvious

| covering | cap | its silhouette |
| --- | --- | --- |
| flat interlocking tile | `cap.segmental` | faceted crown breaking to straight flanks |
| profiled tile | `cap.half_round` | an arc, matching the pantile's own roll |
| standing seam | `cap.seam` | folded sheet, no arc at all |

"Plain tile" and "flat tile" are two different coverings that share a word in
English, and confusing them is what put a half-round on `tile.clay` first. The
small double-lap **plain** tile takes a half-round; a **flat interlocking**
tile - which is what `tile.clay` is, 0.2928 x 0.47 m on a single lap - takes a
segmental or angular ridge. `TileProfile.cap` names it, because a ridge
fitting is sold against the covering it caps.

One cap serves a covering's ridges **and** its hips. `trims.edge_kind` tells
those apart and deliberately nothing here does.

## The section is solid, where a gutter's is a shell

A cap is drawn as a centreline and then **closed onto the covering** - one
point under the arris turns the outer curve into a solid section that closes
gaps under the skirt.

The rule that separates the two: you look **into** a gutter and along a cap.
A gutter's wall is a face you see, so `sheet_ring` is right there and stays.

What is left over is a shallow recess at each low point, as deep as the
covering's relief - 30 mm on a pantile, 38 mm on a standing seam - where the
underside bridges from high point to high point. A real roof fills those with
a closure strip cut to the corrugation; see `references/caps.md`.

`thickness` is the material gauge used to check the clearance between
adjacent pieces.

## Where a cap sits is derived, never declared

A cap has to clear the covering under it, and how far that is depends on the
covering's own relief and on how steeply the roof falls away from the arris.
Both are known at build time, so neither is stated:

    seat    = envelope / cosine - foot * tangent
    tangent = how steeply the covering falls away, from the same cosine

`cosine` is the dot product of the run's own `up` - the bisector of the two
roof faces - with either face normal. `seat` puts the **foot** of the skirt
exactly on the covering surface, so the skirt then lies flat along it at the
roof's own pitch for its whole width.

Seating it any other way floats the skirt on a steep roof and buries it on a
shallow one, and no constant can be right for both.

`relief` - how far the covering undulates *across* the run - is the second
thing a cap takes from it, and it is what turns the skirt down at its tip. A
cap crosses a pantile's rolls and a seam's upstands at an angle, so no swept
section can sit into them; a lip as deep as the relief closes the gap instead.
A flat tile has no relief and so grows no lip, without anyone selecting one.

## A piece is not one swept section

Four things happen along a piece, and every one of them exists because a run
has to **end** somewhere:

    z = 0              head, barrel drawn in by `inset`
    z = nose           full section
    z = length - nose  full section, then a step out by `rim`
    z = length         section closed over onto its own skirts

**The dome.** A run ends at an eave and its last piece is the one thing on a
hip that is looked at from directly below. Swept and left open it is a tube
seen straight up; a flat plate across the mouth closes the hole and still
reads as a tube sawn off. It has to close over, following `sqrt(1 - t^2)` so
it leaves the barrel tangent and arrives flat.

The dome scales the **whole section** about the seat line, not only its
height. Dropping the crown alone leaves the tip as wide as the body, so the
piece ends in a full-width strip that reads as a chamfer however smooth the
curve over it is - it has to roll over in plan as well as in section.

**The inset.** A closure would ordinarily mean two objects, a plain piece and
a special end piece, and the field would then have to know which is which. It
does not: the same closure is on every piece, and each head is drawn in by
`inset` so the dome of the piece above sits over it. One mesh, repeated, and
the last piece on a run is simply the one whose dome nobody covers.

**The rim.** The section steps out where the closure begins, so the dome
starts on a hard edge rather than fading into the piece it covers. That edge
is the joint. A capped ridge tile carries a raised section at one end that
laps onto the end of the next, sold that way so the butt joint beneath needs
no pointing; without it a run reads as one extruded tube with no joint
anywhere along it.

`rim` is deliberately not measured against the gauge. It is a step in the
**silhouette** - what makes a run read as units - where a gauge is a step in
the surface. A moulded clay unit has a 16 mm wall and a 12 mm rim, and the rim
is the one seen from the ground.

## The run ends on the arris

A piece is one step of body plus a nose that laps the piece below, so `n` of
them reach `n * step + nose`. `spacing()` solves that against the arris, which
is what lands the last dome **on** the eave. Laying them at the module and
letting the tail fall where it may overhangs by a whole nose - and on a hip
that is the piece nobody can miss.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

from . import procedures
from .procedures import Point, ProceduralMesh, Vertex
from .values import AuthoringError

Section = list[Point]
CapMesh = ProceduralMesh

#: How finely a barrel's half turn is sampled. The same twelve the gutter
#: trough uses, and for the same reason: the chord error stays under the sheet
#: thickness, so the sweep is exact and only the section is faceted.
CAP_SEGMENTS = 12

#: How finely the closing dome is sampled along the run. Six is enough that
#: the silhouette reads as moulded at arm's length; the dome is only one nose
#: long, so this costs far less than `CAP_SEGMENTS` does.
DOME_SEGMENTS = 6

#: How much of itself the section keeps at the very tip. A section of no
#: extent has no direction for its own offset to follow, so it cannot be rung
#: into a sheet - and a tenth reads as closed from any distance.
_DOME_FLOOR = 0.10

_FIT_EPS = 1e-9

#: How close two section points may be before they are the same point.
_POINT_EPS = 1e-9


class Seating(NamedTuple):
    """Where a cap sits on the covering it closes, for one run.

    Named rather than a bare tuple for the reason `gutters.Sole` is: these are
    numbers about the same arris, and a positional tuple lets them be
    transposed in silence - a seat read as a tangent is still a
    plausible-looking cap.
    """

    #: How far the foot of the skirt stands above the roof's own arris.
    seat: float
    #: How steeply the covering falls away from that arris, as a tangent.
    tangent: float
    #: How much the covering undulates **across** the run - a pantile's roll,
    #: a standing seam's upstand, nothing at all on a flat tile.
    #:
    #: A cap is one section swept along a straight arris, so it cannot follow
    #: a corrugation it crosses at an angle. This is what the skirt has to
    #: close over rather than follow, and it is why the three caps have three
    #: skirts rather than one shared one.
    relief: float


class Spacing(NamedTuple):
    """How one run of caps divides up: where each piece starts and how long."""

    #: Distance along the run to each piece's near end, from the run's start.
    stations: list[float]
    #: The fitted module - never longer than the profile's own.
    step: float
    #: How long each piece is built: one step of body plus its own nose, which
    #: is the overlap that hides the joint under the dome.
    piece: float


class CapRun(NamedTuple):
    """One placed cap run: where the caps go and which way they lean.

    The analogue of `trims.VergeRun`, with one deliberate difference. A verge
    returns no `up` because a verge board's up is world vertical for every run
    there will ever be. A cap sits on the **bisector** of its two roof faces,
    which is world vertical only on a ridge, so `up` is carried.

    Every roof here slopes at one agreed pitch - `skeleton.require_supported`
    refuses anything else - so the two faces meeting on any arris are
    symmetric about the vertical plane through it, and that bisector is world
    up with the run's own direction taken out of it. On a roof of mixed
    pitches it would not be, which is why the pitch rule is what makes this
    frame correct rather than merely convenient.
    """

    #: The upper end of the arris, where the first piece starts.
    origin: Any
    #: Across the run, in the bisector's own plane. `up x along`, so the frame
    #: is right-handed and no face or vert order can flip it.
    across: Any
    #: The bisector of the two roof faces.
    up: Any
    #: Along the run, pointing **downhill**, so every dome faces down the
    #: slope. Level on a ridge, where downhill is only a stable ordering.
    along: Any
    #: True length of the arris.
    length: float
    #: The bisector against either face normal - one number that yields both
    #: how high the cap sits and how steeply its skirt falls.
    cosine: float


def seating(
    envelope: float, cosine: float, foot: float, relief: float = 0.0
) -> Seating:
    """Where a cap run sits, from the covering it closes and its own dihedral.

    ``envelope`` is how far the laid covering stands off the roof plane -
    `tiles.TileProfile.envelope()`, the same number `trims.upstand_over()`
    takes. ``cosine`` is the run's bisector against either face normal,
    ``foot`` is the profile's own half width where its skirt begins, and
    ``relief`` is how far that covering undulates across the run.

    The seat is clamped at zero. A negative one means the cap is wider than
    the covering's relief can lift it clear of, and the honest answer there is
    a cap resting on the arris with its skirt a hair above the tiles - not a
    cap sunk into them, and not a refusal, since a steep roof with a thin
    covering is an ordinary building rather than a mistake.
    """

    if envelope < 0:
        raise AuthoringError("a covering's envelope cannot be negative")
    if relief < 0:
        raise AuthoringError("a covering's relief cannot be negative")
    if not 0.0 < cosine <= 1.0:
        raise AuthoringError(
            f"a cap run's bisector cosine must be above zero and at most one, "
            f"got {cosine!r}"
        )
    if foot <= 0:
        raise AuthoringError("a cap's foot half width must be positive")
    tangent = math.sqrt(max(0.0, 1.0 - cosine * cosine)) / cosine
    return Seating(
        max(0.0, envelope / cosine - foot * tangent), tangent, relief
    )


# --------------------------------------------------------------------------
# Cap procedures. One per cap type, each standalone and readable.
#
# All of them use the same local axes, because that is the contract the
# placement code relies on: X across the run, Y along the bisector, Z along
# the run. Z = 0 is the piece's head, drawn in under the dome that covers it;
# Z = length is its foot, closed over.
# --------------------------------------------------------------------------


def _domed(
    name: str,
    centreline: Callable[[float], Section],
    profile: CapProfile,
    seat: Seating,
    length: float,
) -> CapMesh:
    """Sweep one piece: drawn in at the head, full through the body, then
    closed over at the foot by a dome.

    This is the whole shape of the thing, and it is why a cap cannot be an
    extrusion. A run ends at an eave and its last piece is looked at from
    directly below, so a swept section left open is a tube you see straight
    up; a flat plate across it closes the hole and still reads as a tube that
    was sawn off. It has to **close over**, the way the moulded end of a real
    ridge tile does.

    Which would ordinarily mean two objects - a plain piece and a special
    end piece - and the whole field would then have to know which is which.
    It does not, because the same closure is on **every** piece and the head
    of each one is drawn in by `inset` so the dome of the piece above sits
    over it. One mesh, repeated, and the joint is hidden inside the dome:

        z = 0              head, barrel drawn in by `inset`
        z = nose           full section
        z = length - nose  full section, then a step out by `rim`
        z = length         barrel closed down onto its own skirts

    The dome follows a quarter ellipse, `sqrt(1 - t^2)`, so it leaves the
    barrel tangent to it and arrives flat - the two things that make it read
    as moulded rather than as a cone.

    It scales the **whole section** about the seat line, not only its height.
    Dropping the crown alone leaves the tip as wide as the body, so the piece
    ends in a full-width strip that reads as a chamfer however smooth the
    curve over it is: the thing has to roll over in plan as well as in
    section. That is also why the skirts pull in over the dome, where along
    the body they never move - past the last course of tiles there is nothing
    left for them to lie on.

    The last ring keeps a sliver of its size rather than collapsing to a
    point, which would leave the sweep's final band with no area at all.
    """

    if length <= 0:
        raise AuthoringError(f"{name} needs a positive length, got {length}")
    if profile.nose >= length:
        raise AuthoringError(
            f"{name} has a {profile.nose} m nose on a {length} m piece"
        )

    def ring_at(delta: float, scale: float) -> Section:
        # Scaled about the seat line, so the section keeps its footing on the
        # covering while it shrinks.
        drawn = [
            (a * scale, seat.seat + (u - seat.seat) * scale)
            for a, u in centreline(delta)
        ]
        # Closed onto the covering rather than offset into a shell. The
        # centreline runs tip to tip over the crown; one more point under the
        # arris closes it into a solid, sitting on the covering's own surface
        # so the solid never fills the roof it stands on.
        #
        # Clamped under the crown, because that surface is not always below
        # it. `seating` measures the covering by its **envelope** - its
        # highest point - so a shallow cap on a coarse covering can have its
        # crown lower than the surface it is seated over, and an apex there
        # would push the underside out through the top and turn the section
        # inside out. `cap.seam` on a 35 degree roof is exactly that case.
        crest = max(u for _, u in drawn)
        drawn.append(
            (
                0.0,
                min(
                    seat.seat + profile.foot * seat.tangent * scale,
                    crest - profile.thickness,
                ),
            )
        )
        result = _wound(_taut(drawn))
        if len(result) < 3:
            raise AuthoringError(
                f"{name} produced a section of {len(result)} points"
            )
        return result

    # Stations along the run, each with the section drawn there. The two at
    # `length - nose` are the **rim**: the section steps out there, so the
    # closure starts on a hard edge instead of fading into the piece it
    # covers. That edge is the joint, and a run without it reads as one
    # extruded tube - see the module docstring.
    rings: list[tuple[Section, float]] = [
        (ring_at(-profile.inset, 1.0), 0.0),
        (ring_at(0.0, 1.0), profile.nose),
        (ring_at(0.0, 1.0), length - profile.nose),
        (ring_at(profile.rim, 1.0), length - profile.nose),
    ]
    for step in range(1, DOME_SEGMENTS + 1):
        t = step / DOME_SEGMENTS
        scale = max(_DOME_FLOOR, math.sqrt(max(0.0, 1.0 - t * t)))
        rings.append(
            (
                ring_at(profile.rim, scale),
                length - profile.nose + profile.nose * t,
            )
        )

    count = len(rings[0][0])
    for ring, _ in rings:
        if len(ring) != count:
            raise AuthoringError(
                f"{name} built sections of {count} and {len(ring)} points; "
                "every station has to correspond point for point"
            )

    verts: list[Vertex] = [
        (a, u, station) for ring, station in rings for a, u in ring
    ]
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []

    everything = [point for ring, _ in rings for point in ring]
    min_a = min(a for a, _ in everything)
    span_a = max(a for a, _ in everything) - min_a or 1.0
    min_u = min(u for _, u in everything)
    span_u = max(u for _, u in everything) - min_u or 1.0

    def section_uv(point: Point) -> Point:
        return ((point[0] - min_a) / span_a, (point[1] - min_u) / span_u)

    bands = len(rings) - 1
    for segment in range(bands):
        near, far = segment * count, (segment + 1) * count
        for index in range(count):
            following = (index + 1) % count
            faces.append(
                (near + index, near + following, far + following, far + index)
            )
            uvs.append(
                [
                    (index / count, segment / bands),
                    ((index + 1) / count, segment / bands),
                    ((index + 1) / count, (segment + 1) / bands),
                    (index / count, (segment + 1) / bands),
                ]
            )

    last = bands * count
    faces.append(tuple(range(count - 1, -1, -1)))
    uvs.append([section_uv(rings[0][0][corner % count])
                for corner in faces[-1]])
    faces.append(tuple(range(last, last + count)))
    uvs.append([section_uv(rings[-1][0][corner % count])
                for corner in faces[-1]])

    slots = ["cap"] * len(faces)
    return procedures.validate_mesh(name, (verts, faces, uvs, slots))


def _wound(section: Section) -> Section:
    """Return the section wound counter-clockwise, whichever way it arrived.

    The sweep builds its side faces from consecutive section points, so the
    section's own winding decides which way every face ends up pointing. An
    inside-out cap survives the closed-mesh check, the point-count check and
    every dimension test, then renders with inverted lighting.

    Normalising here means a procedure can draw its section in whichever
    direction reads best and never has to think about it.
    """

    area = 0.0
    for index in range(len(section)):
        here, ahead = section[index], section[(index + 1) % len(section)]
        area += here[0] * ahead[1] - ahead[0] * here[1]
    return section if area > 0.0 else section[::-1]


def _taut(section: Section) -> Section:
    """Drop points a section repeats, so no segment has zero length.

    A cap's section is assembled from parts that each know their own job -
    skirt, shoulder, crown - and two of them meet on the same point whenever
    the number between them is zero: a covering with no relief needs no
    shoulder, so the shoulder lands on the foot. `offset_open_polyline` cannot
    take the direction of a zero-length segment and says so, which is the
    right answer to a bad section and the wrong one to a section that is
    merely simpler than usual.

    Doing it here rather than in each procedure is what keeps the next cap
    design from rediscovering it.
    """

    taut: Section = []
    for point in section:
        if not taut or (
            abs(point[0] - taut[-1][0]) > _POINT_EPS
            or abs(point[1] - taut[-1][1]) > _POINT_EPS
        ):
            taut.append(point)
    return taut


def _skirt(profile: CapProfile, seat: Seating) -> tuple[Section, Section]:
    """The two skirts, drawn outward from the foot, as (left, right).

    Every cap shares this because every cap has the same job at its edge: run
    down the covering at the covering's own pitch from the foot to the tip,
    then, if the covering has relief the sweep cannot follow, turn down over
    it by exactly that much.

    The turn-down is the relief itself, so it disappears on a covering that
    has none. A cap crosses a pantile's rolls and a standing seam's upstands
    at an angle and no swept section can sit into them, so a lip as deep as
    the relief closes the shadow gap instead of pretending it is not there;
    a flat tile presents an unbroken plane and gets a straight skirt without
    anyone selecting one.
    """

    tip = profile.width / 2.0
    drop = (tip - profile.foot) * seat.tangent
    lip = seat.relief
    left: Section = [(-profile.foot, seat.seat)]
    right: Section = [(profile.foot, seat.seat)]
    if lip:
        # Out to the tip along the covering, then straight down over it.
        left.insert(0, (-tip, seat.seat - drop - lip))
        left.insert(1, (-tip, seat.seat - drop))
        right.append((tip, seat.seat - drop))
        right.append((tip, seat.seat - drop - lip))
    else:
        left.insert(0, (-tip, seat.seat - drop))
        right.append((tip, seat.seat - drop))
    return left, right


def segmental_cap_mesh(
    profile: CapProfile, seat: Seating, length: float
) -> CapMesh:
    """A segmental cap, for a **flat interlocking tile** field.

    Not round. A flat interlocking tile takes an angular or segmental ridge,
    where the small double-lap plain tile takes the half-round - two coverings
    that share the word "flat" in English and nothing else. `tile.clay` is
    0.2928 x 0.47 m laid single-lap on a 0.3 x 0.4 module, which is an
    interlocking tile, so this is its fitting.

    The silhouette is three straight runs and one shallow arc: a skirt on the
    covering, a straight flank rising off the arris, a defined break, and a
    barely-curved crown between the two breaks. The break is what makes it
    read as angular from the ground however soft the crown is, and the crown's
    own segment is what keeps it from being a bare V.
    """

    left, right = _skirt(profile, seat)
    # Where the flank stops and the crown starts. The crown carries its own
    # shallow segment above the chord between the two breaks, so `segment` is
    # measured from that chord rather than from the arris.
    chord = profile.crown - profile.segment

    def centreline(delta: float) -> Section:
        rise = chord + delta
        points: Section = list(left)
        points.append((-profile.crown_half, seat.seat + rise))
        for step in range(1, CAP_SEGMENTS // 2):
            angle = math.pi * step / (CAP_SEGMENTS // 2)
            points.append(
                (
                    -profile.crown_half * math.cos(angle),
                    seat.seat + rise + profile.segment * math.sin(angle),
                )
            )
        points.append((profile.crown_half, seat.seat + rise))
        return points + right

    return _domed("segmental_cap_mesh", centreline, profile, seat, length)


def half_round_cap_mesh(
    profile: CapProfile, seat: Seating, length: float
) -> CapMesh:
    """A half-round cap, for a **profiled tile** field.

    The round one belongs here, not on the flat tile: a half-round ridge
    matches a pantile's own roll, which is why it is what pantile and plain
    double-lap roofs are finished with and why a flat interlocking tile is
    not.

    Two things separate it from a bare semicircle, and both come from the roll
    it crosses:

    - **A shoulder.** The barrel leaves the foot vertically for the height of
      the roll before it starts to turn, so the arch springs above the
      corrugation rather than out of it. A semicircle springing at the foot
      would have its own tangent running into the first roll it meets.
    - **A lip**, from `_skirt`, closing the shadow gap over the pans.

    Both are the covering's own relief, derived rather than stated.
    """

    left, right = _skirt(profile, seat)
    shoulder = seat.seat + seat.relief

    def centreline(delta: float) -> Section:
        points: Section = list(left)
        points.append((-profile.foot, shoulder))
        for step in range(1, CAP_SEGMENTS):
            angle = math.pi * step / CAP_SEGMENTS
            points.append(
                (
                    -profile.foot * math.cos(angle),
                    shoulder + (profile.crown + delta) * math.sin(angle),
                )
            )
        points.append((profile.foot, shoulder))
        return points + right

    return _domed("half_round_cap_mesh", centreline, profile, seat, length)


def seam_cap_mesh(
    profile: CapProfile, seat: Seating, length: float
) -> CapMesh:
    """A folded angular capping, for a **standing seam** roof.

    Sheet metal is folded, not thrown, so this is straight segments and no
    arc at all: a flat crown, a fold down to each shoulder, then the skirts.
    Its lip turns down over the seams it crosses, which stand proud of the
    tray exactly as a pantile's roll does - the same closure, over a different
    corrugation.

    It carries a 3 mm rim where the clay caps carry 12: a folded sheet laps by
    a fold, not by a moulded collar, so its joint is a much shallower step.
    """

    left, right = _skirt(profile, seat)

    def centreline(delta: float) -> Section:
        crown = seat.seat + profile.crown + delta
        return list(left) + [
            (-profile.crown_half, crown),
            (profile.crown_half, crown),
        ] + right

    return _domed("seam_cap_mesh", centreline, profile, seat, length)


# --------------------------------------------------------------------------
# Profiles: the section a procedure draws, and the module layout steps by.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CapProfile:
    """One cap design: its section, its module, and the procedure that builds it.

    The same split a gutter and a tile both use - the profile carries the
    shape, the run carries only what varies along it.

    ``width`` is the overall width across the arris, ``foot`` the half width
    where the skirt leaves the crown, and ``crown`` how far the top stands
    above that foot. All three are section dimensions, in the plane the
    section is drawn in; nothing here is a world coordinate.

    ``module`` is the layout step. ``nose`` is how far back from the foot the
    barrel starts closing over, and ``inset`` how far the head is drawn in so
    the piece above's dome sits over it - between them, the reason one mesh
    can be repeated along a run and still finish properly at the eave.

    ``rim`` is how far the section steps out where that closure begins. It is
    what makes the joint read: a capped ridge tile carries a raised section at
    one end that laps onto the end of the next, and it is sold that way
    precisely so the butt joint underneath needs no pointing. Without it the
    dome tapers into the piece it covers and a run reads as one long tube.

    ``crown_half`` and ``segment`` are read only by the segmental procedure,
    the way ``TileProfile.stagger`` is read only by layout: a barrel has no
    flat and no break.
    """

    key: str
    width: float
    foot: float
    crown: float
    thickness: float
    module: float
    nose: float
    inset: float
    rim: float
    build: Callable[["CapProfile", Seating, float], CapMesh]
    crown_half: float = 0.0
    segment: float = 0.0

    def geometry(self, seat: Seating, length: float) -> CapMesh:
        self.validate()
        return self.build(self, seat, length)

    def validate(self) -> None:
        for label, value in (
            ("width", self.width),
            ("foot", self.foot),
            ("crown", self.crown),
            ("thickness", self.thickness),
            ("module", self.module),
        ):
            if value <= 0:
                raise AuthoringError(f"cap {label} must be greater than zero")
        for label, value in (("nose", self.nose), ("inset", self.inset),
                             ("rim", self.rim),
                             ("crown_half", self.crown_half),
                             ("segment", self.segment)):
            if value < 0:
                raise AuthoringError(f"cap {label} cannot be negative")
        if not self.nose:
            raise AuthoringError(
                f"cap {self.key!r} has no nose, so its run would end on an "
                "open tube looked straight up from the eave below it"
            )
        if self.nose * 2.0 >= self.module:
            raise AuthoringError(
                f"cap {self.key!r} gives {self.nose} m of its {self.module} m "
                "module to a dome at each end, leaving it no body"
            )
        # Deliberately not measured against the gauge. A rim is a step in the
        # **silhouette** - what makes a run read as units rather than as one
        # tube - where a fold in a sheet is a step in the surface. A moulded
        # clay unit has a 16 mm wall and a 12 mm rim, and the rim is the one
        # you see from the ground.
        if not self.rim:
            raise AuthoringError(
                f"cap {self.key!r} steps out by nothing where its closure "
                "begins, so a run of them reads as one extruded tube with no "
                "joint anywhere along it"
            )
        # The head has to clear the dome that covers it by more than the sheet
        # the dome is made of, or the two lie on each other and z-fight down
        # the whole overlap - the coplanar joint this shape exists to avoid.
        if self.inset <= self.thickness:
            raise AuthoringError(
                f"cap {self.key!r} draws its head in by {self.inset} m under "
                f"a {self.thickness} m sheet, so the dome over it has no "
                "clearance"
            )
        if self.foot * 2.0 >= self.width:
            raise AuthoringError(
                f"cap {self.key!r} has a foot of {self.foot} m against a width "
                f"of {self.width} m, leaving it no skirt to reach the covering"
            )
        if self.crown_half >= self.foot:
            raise AuthoringError(
                f"cap {self.key!r} has a crown flat wider than its own foot"
            )
        if self.segment >= self.crown:
            raise AuthoringError(
                f"cap {self.key!r} puts its whole {self.crown} m crown into a "
                f"{self.segment} m segment, leaving no flank under the break"
            )


#: Segmental, for a **flat interlocking tile** field. 250 x 115 mm on a
#: 300 mm piece, which is the clay ridge length the trade sells; the 60 mm
#: crown flat and its 22 mm segment are what put the break where a flat
#: tile's ridge shows one.
SEGMENTAL = CapProfile(
    key="cap.segmental",
    width=0.250,
    foot=0.104,
    crown=0.115,
    crown_half=0.060,
    segment=0.022,
    thickness=0.016,
    module=0.300,
    nose=0.100,
    inset=0.022,
    rim=0.012,
    build=segmental_cap_mesh,
)

#: Half-round, for a **profiled tile** field - 220 x 110 mm on the same
#: 300 mm piece, straight off the clay ridge catalogue. It is the pantile's
#: fitting because its arc is the pantile's own roll.
HALF_ROUND = CapProfile(
    key="cap.half_round",
    width=0.220,
    foot=0.090,
    crown=0.110,
    thickness=0.016,
    module=0.300,
    nose=0.100,
    inset=0.022,
    rim=0.012,
    build=half_round_cap_mesh,
)

#: Folded angular capping, for a **standing seam** roof. Wider and far
#: shallower than either clay cap, and a 3 mm rim where they carry 12 - a
#: folded sheet laps by a fold, not by a moulded collar. It runs on the same
#: 300 mm module as the others: real coil comes in metres, but the module is
#: how pieces are spread rather than how long they are.
SEAM = CapProfile(
    key="cap.seam",
    # 60 mm of skirt each side of the fold. A folded capping is fixed through
    # its flange so it carries more of one than a moulded clay unit's 20 mm,
    # but not the 110 mm this had - that made the cap read as two wide flat
    # wings with a small ridge between them rather than as a capping.
    width=0.240,
    foot=0.060,
    # Tall enough to clear its own foot. The roof falls `foot * tan(pitch)`
    # from the arris to where this cap's flanks land, so a crown shallower
    # than that sits **below** the arris and the cap is buried at its centre -
    # 34 mm did, on any roof past 30 degrees. 70 mm clears a 45 degree roof,
    # which is the steep end of anything this covering is laid on.
    crown=0.070,
    crown_half=0.030,
    thickness=0.0007,
    module=0.300,
    nose=0.100,
    inset=0.004,
    rim=0.003,
    build=seam_cap_mesh,
)

PROFILES: dict[str, CapProfile] = {
    SEGMENTAL.key: SEGMENTAL,
    HALF_ROUND.key: HALF_ROUND,
    SEAM.key: SEAM,
}


def profile(key: str) -> CapProfile:
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise AuthoringError(f"unknown cap profile {key!r}; known: {known}")
    return PROFILES[key]


# --------------------------------------------------------------------------
# Layout. Stations only.
# --------------------------------------------------------------------------


def spacing(length: float, cap: CapProfile) -> Spacing:
    """Divide one arris into whole cap pieces, ending flush at both ends.

    The module is **fitted** rather than snapped to a grid, because a cap run
    cannot be cropped the way a tile field can and a stub piece at a hip foot
    is visible from the ground. Fitting it means every piece is cut to the
    same slightly-short length, which is the one thing a run of ridge tiles
    genuinely is on site.

    The run is solved so the **last dome lands on the arris**. A piece is a
    step of body plus a nose that laps the piece below, so `n` of them reach
    `n * step + nose`; setting that equal to the arris is what stops the last
    one hanging out past the eave, which on a hip is the piece everybody sees.

    The count is rounded **up**, so the fitted step is never longer than the
    profile's own module. Each nose then overlaps the next piece.
    """

    cap.validate()
    if length <= 0:
        raise AuthoringError(f"a cap run needs a positive length, got {length}")
    if length <= cap.nose:
        raise AuthoringError(
            f"a {length} m cap run is shorter than the {cap.nose} m nose that "
            f"has to close it"
        )
    reach = length - cap.nose
    count = max(1, math.ceil(reach / cap.module - _FIT_EPS))
    step = reach / count
    return Spacing(
        stations=[index * step for index in range(count)],
        step=step,
        piece=step + cap.nose,
    )
