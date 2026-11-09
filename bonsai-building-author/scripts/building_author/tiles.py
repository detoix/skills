"""Roof tiles: one procedure per tile type, plus the layout that places them.

Two separate concerns, deliberately kept apart:

- Each tile type has its own mesh procedure, including the tilt for lapped tiles.
- `centres()` is the layout. It returns positions and nothing else, and asks
  a profile only for `width` and `exposure`. It never calls a tile procedure
  and never needs to know what a tile looks like.

Everything is pure Python, so both halves are covered by `scripts/tests/`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from . import caps, polygons, procedures
from .gutters import sheet_ring
from .procedures import Point, ProceduralMesh, Vertex
from .values import AuthoringError

TileMesh = ProceduralMesh

_FIT_EPS = 1e-6


# --------------------------------------------------------------------------
# Tile procedures. One per tile type, each standalone and readable.
#
# All of them use the same local axes, because that is the contract the
# placement code relies on: X across the eave, Y up the slope, Z normal to
# the roof plane. The head (uphill, +Y) sits on the plane and the tail
# (downhill, -Y) rides up by one thickness per exposure, so identical tiles
# laid flat on the plane still lap over each other.
# --------------------------------------------------------------------------


#: Six degrees gives about 42 mm of rise per 400 mm course for the lap.
TILE_TILT = math.radians(6.0)


def clay_tile_mesh() -> TileMesh:
    """Build a flat clay tile with the lap tilt.

    The tile is narrower than its layout module to leave a joint between tiles.
    """

    width, length, thickness = 0.2928, 0.47, 0.04
    half_width, half_length = width / 2.0, length / 2.0
    rise = length * math.tan(TILE_TILT)

    verts: list[Vertex] = [
        (-half_width, -half_length, rise),
        (half_width, -half_length, rise),
        (half_width, half_length, 0.0),
        (-half_width, half_length, 0.0),
        (-half_width, -half_length, rise + thickness),
        (half_width, -half_length, rise + thickness),
        (half_width, half_length, thickness),
        (-half_width, half_length, thickness),
    ]
    faces: list[tuple[int, ...]] = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    uvs = [
        [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)],
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
    ]
    slots = ["tile"] * len(faces)
    return procedures.validate_mesh("clay_tile_mesh",
                                    (verts, faces, uvs, slots))


#: Each Bezier entry is (point, right handle, left handle) in section
#: coordinates across the tile and above its datum.
CELTIC_SPLINE = (
    ((-0.141552, 0.00839), (-0.061824, 0.05314), None),
    ((-0.012792, -0.00195), (0.008292, -0.0017), (-0.058788, -0.00251)),
    ((0.121788, -0.00046), (0.132504, -0.00911), (0.048444, 0.0587)),
    ((0.160332, 0.00612), None, (0.149592, 0.00152)),
)

#: Samples per cubic segment.
CELTIC_RESOLUTION = 10

#: Pantile sheet thickness in metres.
CELTIC_GAUGE = 0.020

#: Pantile length in metres, giving an 80 mm lap at 400 mm exposure.
CELTIC_LENGTH = 0.48


def _cubic(
    a: Point, b: Point, c: Point, d: Point, steps: int
) -> list[Point]:
    """Sample one cubic Bezier segment, dropping its first point.

    Dropped because consecutive segments share an end: keeping both would
    repeat a point, which `procedures.validate_mesh` would pass and the
    crop's EXACT boolean would then reject as a zero-area face.
    """

    result: list[Point] = []
    for step in range(1, steps + 1):
        t = step / steps
        u = 1.0 - t
        result.append(
            tuple(
                u * u * u * a[i]
                + 3.0 * u * u * t * b[i]
                + 3.0 * u * t * t * c[i]
                + t * t * t * d[i]
                for i in range(2)
            )
        )
    return result


def celtic_section() -> list[Point]:
    """The pantile's centreline, sampled off `CELTIC_SPLINE`."""

    points: list[Point] = [CELTIC_SPLINE[0][0]]
    for index in range(len(CELTIC_SPLINE) - 1):
        here, ahead = CELTIC_SPLINE[index], CELTIC_SPLINE[index + 1]
        points += _cubic(here[0], here[1], ahead[2], ahead[0],
                         CELTIC_RESOLUTION)
    return points


def celtic_tile_mesh() -> TileMesh:
    """Sweep the pantile's Bezier section as a sheet.

    The cap skirt uses the height difference between the roll and the pan,
    computed from the same section.
    """

    ring = sheet_ring(celtic_section(), CELTIC_GAUGE)
    outline = ring[:-1] if ring[0] == ring[-1] else list(ring)
    count = len(outline)
    half_length = CELTIC_LENGTH / 2.0
    rise = CELTIC_LENGTH * math.tan(TILE_TILT)

    # Same axes and the same lap as every other tile: the head sits on the
    # plane and the tail rides up by the course's own rise.
    verts: list[Vertex] = [(x, -half_length, rise + z) for x, z in outline]
    verts += [(x, half_length, z) for x, z in outline]
    # Wound like the tray's, not like a cap's: a section stated in (across,
    # normal) and swept along Y is the opposite handedness to one stated in
    # (across, up) and swept along Z, so the winding that faces a cap outward
    # faces this inward. `test_every_procedure_faces_outward` caught it.
    faces: list[tuple[int, ...]] = [
        (i, i + count, (i + 1) % count + count, (i + 1) % count)
        for i in range(count)
    ]
    faces.append(tuple(range(count)))
    faces.append(tuple(range(count * 2 - 1, count - 1, -1)))

    uvs: list[list[Point]] = [
        [
            (i / count, 0.0),
            ((i + 1) / count, 0.0),
            ((i + 1) / count, 1.0),
            (i / count, 1.0),
        ]
        for i in range(count)
    ]
    low = min(x for x, _ in outline)
    span = (max(x for x, _ in outline) - low) or 1.0
    deep = min(z for _, z in outline)
    tall = (max(z for _, z in outline) - deep) or 1.0
    for cap_face in (faces[-2], faces[-1]):
        uvs.append(
            [
                (
                    (outline[corner % count][0] - low) / span,
                    (outline[corner % count][1] - deep) / tall,
                )
                for corner in cap_face
            ]
        )
    slots = ["tile"] * len(faces)
    return procedures.validate_mesh("celtic_tile_mesh",
                                    (verts, faces, uvs, slots))


#: How far the pantile's own surface swings across its width - the top of its
#: roll to the bottom of its pan. Read off the sampled curve rather than
#: stated, so it cannot drift away from the profile it describes.
CELTIC_RELIEF = (
    max(z for _, z in celtic_section()) - min(z for _, z in celtic_section())
)


#: How tall a standing seam stands above its own tray. 38 mm is the ordinary
#: double-lock height; 25 mm is the shallow single-lock end of the range.
SEAM_HEIGHT = 0.038

#: The sheet a tray is rolled from - the same 0.7 mm coil `gutters.py` uses,
#: because it is the same coil.
SEAM_GAUGE = 0.0007


def standing_seam_mesh() -> TileMesh:
    """One tray of a standing seam roof: a flat pan with one upstand.

    Not a tile at all, which is the point of it being here rather than being
    a tile with a funny shape. A tray is a continuous folded sheet running
    eave to ridge, so it has no headlap, no tilt, and no bond - and it still
    lays out on the same 0.3 x 0.4 grid as every other covering, because the
    module is how units are **spread** rather than how big they are.

    **One** upstand, at the right edge. A real seam is two neighbouring
    upstands folded together into a single fold, so modelling an upstand on
    each side puts two of them in the same place on every joint - coincident
    faces down the whole roof. One per tray, at one edge, is the same
    silhouette without that.

    The section is a folded sheet, so it is stated as a centreline and rung by
    `gutters.sheet_ring()`, exactly as a gutter and a cap are.
    """

    # A pan is the **full** module wide, where a tile is deliberately
    # narrower than its own. That shortfall is the joint between neighbouring
    # tiles. Adjacent pans meet at the
    # seam with nothing showing between them, because a real seam is both
    # panels' upstands folded together into one fold.
    #
    # The course length is exact for the same kind of reason: a tray butts
    # where a tile laps.
    half_width, half_length = 0.15, 0.20
    centreline: list[Point] = [
        (-half_width, 0.0),
        (half_width, 0.0),
        (half_width, SEAM_HEIGHT),
    ]
    ring = sheet_ring(centreline, SEAM_GAUGE)
    outline = ring[:-1] if ring[0] == ring[-1] else list(ring)
    count = len(outline)

    # **No tilt.** Every other covering here rides up by `TILE_TILT` so its
    # lap has somewhere to sit; a tray has no lap to sit, and tilting it puts
    # a step across the roof at every course. A standing seam runs eave to
    # ridge unbroken, so a horizontal line every 400 mm is the one thing it
    # must not show - which is exactly what a rise draws.
    #
    # It costs the seam nothing because the panels butt rather than overlap -
    # but butting still leaves each course's top coplanar with the next
    # course's, and each tray's underside in the face plane the crop prism is
    # built from. `course_clearance` (see Layout) separates those two
    # coincidences without drawing a line.
    verts: list[Vertex] = [(x, -half_length, z) for x, z in outline]
    verts += [(x, half_length, z) for x, z in outline]
    # Wound the opposite way to a cap's sweep. A cap states its section in
    # (across, up) and sweeps along Z; a tray states its in (across, normal)
    # and sweeps along Y, which is the other handedness - so the winding that
    # faces a cap outward faces a tray inward. An inside-out field survives
    # every procedure check and is then deleted whole by the crop's INTERSECT,
    # with nothing reported. `test_every_procedure_faces_outward` is the guard.
    faces: list[tuple[int, ...]] = [
        (i, i + count, (i + 1) % count + count, (i + 1) % count)
        for i in range(count)
    ]
    faces.append(tuple(range(count)))
    faces.append(tuple(range(count * 2 - 1, count - 1, -1)))
    uvs: list[list[Point]] = [
        [
            (i / count, 0.0),
            ((i + 1) / count, 0.0),
            ((i + 1) / count, 1.0),
            (i / count, 1.0),
        ]
        for i in range(count)
    ]
    for cap_face in (faces[-2], faces[-1]):
        uvs.append(
            [
                (
                    (outline[corner % count][0] + half_width) / (half_width * 2),
                    outline[corner % count][1] / SEAM_HEIGHT,
                )
                for corner in cap_face
            ]
        )
    slots = ["tile"] * len(faces)
    return procedures.validate_mesh("standing_seam_mesh",
                                    (verts, faces, uvs, slots))


# --------------------------------------------------------------------------
# Profiles: the handful of numbers layout needs, plus which procedure builds
# the mesh. Nothing here describes the shape.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TileProfile:
    """The grid a tile occupies, and the procedure that builds its mesh.

    ``width`` and ``length`` define the grid spacing. The mesh procedure
    controls tile dimensions, overlap and tilt.
    """

    key: str
    width: float
    length: float
    build: Callable[[], TileMesh]
    stagger: float = 0.5
    cap: str = caps.SEGMENTAL.key
    relief: float = 0.0
    laps: bool = True

    def geometry(self) -> TileMesh:
        self.validate()
        return self.build()

    def envelope(self) -> float:
        """How far the laid tile's outer surface stands off the roof plane.

        Read off the built mesh rather than declared, so it stays true for any
        procedure written next to these: a tile's head sits on the plane and
        its tail rides up by the lap tilt, so this is the rise plus the
        thickness - 0.089 m for the clay tile, not its 0.04 m thickness.

        What `trims.upstand_over()` needs, to put a verge trim's top a visible
        lip above the covering it closes rather than a hair's breadth above
        it. This is the **only** thing a trim asks about the covering: it is
        flush to the roof's own edge either way, so the envelope sets how high
        the lip sits and nothing else.
        """

        verts, _, _, _ = self.geometry()
        return max(z for _, _, z in verts)

    def validate(self) -> None:
        check_stagger(self.stagger)
        caps.profile(self.cap)
        if self.relief < 0:
            raise AuthoringError("tile relief cannot be negative")
        for label, value in (("width", self.width), ("length", self.length)):
            if value <= 0:
                raise AuthoringError(f"tile {label} must be greater than zero")


def check_stagger(value: float) -> float:
    """A bond fraction: at least zero, and strictly below one."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthoringError("tile stagger must be numeric")
    result = float(value)
    if not 0.0 <= result < 1.0:
        raise AuthoringError(
            f"tile stagger must be at least zero and below one, got {result!r}"
        )
    return result


#: A 470 mm tile on a 400 mm course gives 70 mm of headlap.
CLAY_TILE = TileProfile(
    key="tile.clay",
    width=0.3,
    length=0.4,
    build=clay_tile_mesh,
    # A flat **interlocking** tile, not the small double-lap plain tile the
    # word "flat" also covers - 0.2928 x 0.47 m single-lapped on a 0.3 x 0.4
    # module. That is the covering that takes a segmental ridge; the plain
    # tile is the one that takes a half-round.
    cap=caps.SEGMENTAL.key,
    # It presents an unbroken plane, so a cap's skirt lands on it the whole
    # way across and has nothing to close over.
    relief=0.0,
)

#: Its relief is `CELTIC_RELIEF`, computed off the sampled curve rather than
#: stated - 0.030 m from the top of its roll to the bottom of its pan. A cap
#: crossing that at an angle has to close over the drop rather than follow it,
#: which is what earns the pantile its own cap rather than the flat tile's.
#: The hand-built version this replaced declared 0.049, and every pantile
#: cap's lip sat wrong for it.
CELTIC_TILE = TileProfile(
    key="tile.celtic",
    width=0.3,
    length=0.4,
    build=celtic_tile_mesh,
    cap=caps.HALF_ROUND.key,
    relief=CELTIC_RELIEF,
)

#: On the same 0.3 x 0.4 grid as every other covering. A real bay is 0.5 m
#: and a real tray runs eave to ridge in one piece, but the module is how
#: units are **spread**, not how big they are - so the grid stays shared and
#: the mesh is tuned on its own, the way `width` and `length` have always been
#: the step rather than the size.
STANDING_SEAM = TileProfile(
    key="tile.standing_seam",
    width=0.3,
    length=0.4,
    build=standing_seam_mesh,
    stagger=0.0,
    laps=False,
    cap=caps.SEAM.key,
    relief=SEAM_HEIGHT,
)

PROFILES: dict[str, TileProfile] = {
    CLAY_TILE.key: CLAY_TILE,
    CELTIC_TILE.key: CELTIC_TILE,
    STANDING_SEAM.key: STANDING_SEAM,
}


def profile(key: str) -> TileProfile:
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise AuthoringError(f"unknown tile profile {key!r}; known: {known}")
    return PROFILES[key]


# --------------------------------------------------------------------------
# Layout. Positions only.
# --------------------------------------------------------------------------

#: How far a non-lapping covering is raised off the roof face, and how much
#: higher each successive course sits on top of that. Both are rendering
#: clearances, not dimensions: at a fifth and a tenth of a millimetre nothing
#: about the covering's look changes.
#:
#: They exist because a tray does not lap (`STANDING_SEAM.laps` is False) and
#: a real standing seam runs eave to ridge unbroken, so its mesh carries no
#: tilt and no lap to separate one course from the next. That leaves two
#: exact coincidences in the field the crop's boolean is handed:
#:
#: - every tray's **underside lies in the roof face's own plane**, which is
#:   the plane the crop prism is built from, and
#: - two butting trays' **tops are coplanar** along the course line they
#:   share, because every tray is placed the same way.
#:
#: The EXACT solver resolves those ties every time - except when it does not,
#: and then it silently drops a triangle rather than reporting anything. The
#: covering arrives with a half-tray hole in it; `mesh.validate()` calls the
#: mesh invalid; and the walkthrough, which culls back faces, shows the pale
#: interior through the hole as a small triangle on the roof. (Seen once on
#: the north slope at the first column of the west end - one tile in
#: thousands, which is exactly how a tie behaves.)
#:
#: The lift and the step remove both coincidences by construction: no tray
#: face shares a plane with another tray's or with the prism's. The tilt is
#: still left out, so the seam stays unbroken; the step is a fiftieth of the
#: sheet's own gauge (`SEAM_GAUGE`), and across a full slope it accumulates
#: only a few millimetres at the ridge - below the covering's own relief, and
#: invisible under the cap and the verge's lip. Lapping profiles need none of
#: this: their authored tilt already separates course from course.
FIELD_LIFT = 0.0002
COURSE_CLEARANCE = 0.0001


def course_clearance(v: float, tile: TileProfile) -> float:
    """How far above the face plane the unit centred at ``v`` is placed.

    ``v`` is a centre's up-slope coordinate, and `centres` lays courses from
    ``length / 2`` at a pitch of ``length``, so the course index is exact:
    every course lands precisely ``COURSE_CLEARANCE`` above the one below and
    no two of them can be coplanar. Returns zero for a lapping profile, whose
    tilt already keeps its courses apart.
    """

    if tile.laps:
        return 0.0
    return FIELD_LIFT + COURSE_CLEARANCE * round(
        (v - tile.length / 2.0) / tile.length
    )


def centres(
    face: list[Point],
    tile: TileProfile,
    stagger: float | None = None,
) -> list[Point]:
    """Lay tile centres over a roof face expressed in its own plane.

    The grid uses the tile's module and is snapped with `floor()`. Each
    course uses the profile's stagger unless an override is supplied. Keep a
    tile when any of its corners falls inside the face.

    The face coordinates are true distances along the eave and up the slope.
    Set ``v = 0`` at the eave so the first course starts half a module above
    it. The retained tiles can overlap the face boundary for trimming.
    """

    tile.validate()
    bond = tile.stagger if stagger is None else check_stagger(stagger)
    if len(face) < 3:
        raise AuthoringError("a roof face needs at least three points")

    min_u, max_u, min_v, max_v = polygons.bounds(face)
    half_width = tile.width / 2.0
    half_length = tile.length / 2.0

    start_u = math.floor(min_u / tile.width) * tile.width
    # Half a module up, so the first course's lower edge sits on the eave
    # rather than its centre. Starting on the centre would bury half the eave
    # course below the roof edge and leave a stunted first band once cropped.
    start_v = (
        math.floor(min_v / tile.length) * tile.length + tile.length / 2.0
    )

    # The keep test is on the tile's corners while the sweep steps its centre,
    # so the sweep is bounded by overlap rather than by the centre: a tile is
    # a candidate while its own extent crosses the face's. Bounding the centre
    # instead leaves a course short of the edge by up to half a module, and
    # since the bond moves that shortfall from course to course, it reads as
    # every second course ending early.
    #
    # Both comparisons are strict, so a tile that would only touch the bound
    # is never laid - it would contribute nothing but a degenerate solid for
    # the crop to resolve. On a face measuring a whole number of modules this
    # makes the sweep identical to a centre-bounded one, which is exactly why
    # the shortfall hides on tidy test geometry.
    #
    # `start_v` is deliberately anchored half a module above the eave and
    # carries no bond, so only `u` needs the near bound.
    result: list[Point] = []
    v = start_v
    while v < max_v + half_length - _FIT_EPS:
        row = round((v - start_v) / tile.length)
        # The bond accumulates up the roof, so a third repeats every three
        # courses rather than flipping between two. A half reduces to the
        # alternating broken bond and a zero to stacked columns, which is what
        # makes those the ordinary cases rather than special ones.
        offset = (row * bond % 1.0) * tile.width
        u = start_u + offset
        # An offset course would otherwise start a fraction of a module late
        # and leave the near rake bare. At most one step: `start_u` is snapped
        # at or below `min_u` and the offset is under one module.
        while u - half_width > min_u + _FIT_EPS:
            u -= tile.width
        while u - half_width < max_u - _FIT_EPS:
            corners = (
                (u + half_width, v + half_length),
                (u - half_width, v + half_length),
                (u + half_width, v - half_length),
                (u - half_width, v - half_length),
            )
            if any(polygons.contains(corner, face) for corner in corners):
                result.append((u, v))
            u += tile.width
        v += tile.length
    return result
