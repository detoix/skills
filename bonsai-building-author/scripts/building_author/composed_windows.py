"""Composable wall glazing from simple panes and selectively framed edges.

The stock IfcOpenShell window generator owns ordinary rectangular window
types.  It cannot build a sloping head or omit one side of a lining, so this
module serves the distinct case where a window is composed from rectangles
and triangles.  The declaration remains parametric in the building script;
the generated IFC body carries separate ``Framing`` and ``Glazing`` shape
aspects, but deliberately does not claim a ``BBIM_Window`` payload that the
stock Bonsai window tool could not regenerate.

Local coordinates match every other wall opening: X runs along the wall, Y
runs through it, and Z runs up.  A piece boundary is walked anticlockwise in
the XZ plane.  Profiles are optional per edge and lie *inside* that boundary,
so the boundary stays the opening's readable overall outline.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

import shapely
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from . import procedures, values
from .procedures import Point, ProceduralMesh, Vertex
from .values import AuthoringError

_EPS = 1e-9


def _signed_area(boundary: Sequence[tuple[float, float]]) -> float:
    points = list(boundary)
    return sum(
        x1 * z2 - x2 * z1
        for (x1, z1), (x2, z2) in zip(points, points[1:] + points[:1])
    ) / 2.0


def _canonical_ring(
    boundary: Sequence[tuple[float, float]], *, anticlockwise: bool
) -> list[tuple[float, float]]:
    """Remove redundant corners and give a ring one stable walk and start.

    GEOS is free to choose a polygon ring's first corner, and a union may keep
    or discard collinear input corners depending on input order.  Neither is a
    geometric difference, but both would otherwise change the compiled IFC
    coordinate list and the procedure's vertex numbering.
    """

    points = [
        (
            0.0 if abs(float(x)) <= _EPS else round(float(x), 12),
            0.0 if abs(float(z)) <= _EPS else round(float(z), 12),
        )
        for x, z in boundary
    ]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()

    compact: list[tuple[float, float]] = []
    for point in points:
        if not compact or point != compact[-1]:
            compact.append(point)
    if len(compact) > 1 and compact[0] == compact[-1]:
        compact.pop()

    changed = True
    while changed and len(compact) > 3:
        changed = False
        retained = []
        count = len(compact)
        for index, current in enumerate(compact):
            previous = compact[index - 1]
            following = compact[(index + 1) % count]
            first = (current[0] - previous[0], current[1] - previous[1])
            second = (following[0] - current[0], following[1] - current[1])
            cross = first[0] * second[1] - first[1] * second[0]
            scale = max(
                1.0,
                (first[0] ** 2 + first[1] ** 2) ** 0.5
                * (second[0] ** 2 + second[1] ** 2) ** 0.5,
            )
            # Only remove a corner that continues in the same direction.  A
            # zero-area spike doubles back and is invalid rather than redundant.
            forward = first[0] * second[0] + first[1] * second[1]
            if abs(cross) <= _EPS * scale and forward >= 0.0:
                changed = True
                continue
            retained.append(current)
        compact = retained

    if len(compact) < 3 or abs(_signed_area(compact)) <= _EPS:
        raise AuthoringError("composed window geometry collapsed to no area")
    if (_signed_area(compact) > 0.0) != anticlockwise:
        compact.reverse()
    start = min(range(len(compact)), key=lambda index: compact[index])
    return compact[start:] + compact[:start]


def _canonical_polygon(polygon: Polygon) -> Polygon:
    """Return an equivalent polygon with deterministic, correctly wound rings."""

    polygon = orient(polygon, sign=1.0)
    exterior = _canonical_ring(polygon.exterior.coords, anticlockwise=True)
    holes = sorted(
        (
            _canonical_ring(ring.coords, anticlockwise=False)
            for ring in polygon.interiors
        ),
        key=lambda ring: tuple(ring),
    )
    return Polygon(exterior, holes)


def _named_profile_indices(
    label: str,
    profile_edges: Iterable[str] | None,
    names: Sequence[str],
) -> tuple[int, ...]:
    """Resolve optional human-readable edge names in boundary order."""

    if profile_edges is None:
        selected = set(names)
    else:
        if isinstance(profile_edges, (str, bytes)):
            raise AuthoringError(f"{label} profile_edges must be an iterable of names")
        try:
            supplied = tuple(profile_edges)
        except TypeError as exc:
            raise AuthoringError(
                f"{label} profile_edges must be an iterable of names"
            ) from exc
        if any(not isinstance(name, str) for name in supplied):
            raise AuthoringError(f"{label} profile edge names must be strings")
        selected = set(supplied)
    unknown = sorted(selected - set(names))
    if unknown:
        raise AuthoringError(
            f"unknown {label} profile edge(s): {', '.join(unknown)}"
        )
    return tuple(index for index, name in enumerate(names) if name in selected)


def _pane(value: str | None) -> str | None:
    return None if value is None else values.identifier("window pane", value)


def window_piece(
    boundary: Sequence[tuple[float, float]],
    *,
    profile_edges: Iterable[int] | None = None,
    pane: str | None = None,
) -> dict:
    """One polygonal piece of a composed window.

    ``profile_edges`` names boundary-edge indices.  Leaving it ``None`` keeps
    the ordinary default of a profile on every side; an empty iterable makes
    a frameless piece.  Use :func:`window_rectangle` and
    :func:`window_triangle` when named sides read more clearly than indices.
    Pieces sharing ``pane`` are unioned into one glazing shell, which is how a
    rectangle plus a triangle becomes one trapezoid without a seam.
    """

    points = values.boundary(boundary)
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= _EPS:
        raise AuthoringError("a composed window piece must be a simple polygon")
    if _signed_area(points) <= _EPS:
        raise AuthoringError(
            "a composed window piece boundary must be anticlockwise"
        )

    if profile_edges is None:
        edges = tuple(range(len(points)))
    else:
        edges = set()
        for edge in profile_edges:
            if isinstance(edge, bool) or not isinstance(edge, int):
                raise AuthoringError(
                    "composed window profile edge indices must be whole numbers"
                )
            if not 0 <= edge < len(points):
                raise AuthoringError(
                    f"composed window profile edge {edge} is outside "
                    f"0..{len(points) - 1}"
                )
            edges.add(edge)
        edges = tuple(sorted(edges))

    return {
        "boundary": tuple(points),
        "profile_edges": edges,
        "pane": _pane(pane),
    }


def window_rectangle(
    x: float,
    z: float,
    width: float,
    height: float,
    *,
    profile_edges: Iterable[str] | None = None,
    pane: str | None = None,
) -> dict:
    """A rectangular glazing piece with profiles optional on named sides.

    The named sides are ``bottom``, ``right``, ``top`` and ``left``.  All are
    present by default.  For example, ``profile_edges=("left",)`` declares a
    lower gable rectangle whose top is continued by a triangular piece and
    whose other boundaries are owned by a shared transom and divider.
    """

    x = values.number("window rectangle x", x)
    z = values.number("window rectangle z", z)
    width = values.positive("window rectangle width", width)
    height = values.positive("window rectangle height", height)
    names = ("bottom", "right", "top", "left")
    indices = _named_profile_indices("window rectangle", profile_edges, names)
    return window_piece(
        ((x, z), (x + width, z), (x + width, z + height), (x, z + height)),
        profile_edges=indices,
        pane=pane,
    )


def window_triangle(
    base_start: tuple[float, float],
    base_end: tuple[float, float],
    apex: tuple[float, float],
    *,
    profile_edges: Iterable[str] | None = None,
    pane: str | None = None,
) -> dict:
    """A triangular glazing piece with profiles selected by edge character.

    ``base_start`` to ``base_end`` is edge ``base``.  Each remaining edge is
    classified as ``vertical`` or ``skew`` from its coordinates, so the same
    ``profile_edges=("skew",)`` declaration works for the left and right
    halves of a gable.  All edge classes are present by default.
    """

    start = values.point2("window triangle base start", base_start)
    end = values.point2("window triangle base end", base_end)
    top = values.point2("window triangle apex", apex)
    points = (start, end, top)
    if _signed_area(points) <= _EPS:
        raise AuthoringError(
            "window triangle base_start, base_end and apex must be anticlockwise"
        )

    labels = ["base"]
    for first, second in ((end, top), (top, start)):
        dx, dz = second[0] - first[0], second[1] - first[1]
        labels.append("vertical" if abs(dx) <= _EPS else "skew")
    names = ("base", "vertical", "skew")
    if profile_edges is None:
        supplied = None
    else:
        if isinstance(profile_edges, (str, bytes)):
            raise AuthoringError(
                "window triangle profile_edges must be an iterable of names"
            )
        try:
            supplied = tuple(profile_edges)
        except TypeError as exc:
            raise AuthoringError(
                "window triangle profile_edges must be an iterable of names"
            ) from exc
    indices = _named_profile_indices("window triangle", supplied, names)
    if supplied is not None:
        selected = set(supplied)
        absent = sorted(selected - set(labels))
        if absent:
            raise AuthoringError(
                "window triangle has no " + ", ".join(absent) + " profile edge"
            )
        indices = tuple(
            index for index, edge_label in enumerate(labels) if edge_label in selected
        )
    return window_piece(points, profile_edges=indices, pane=pane)


def window_divider(
    start: tuple[float, float],
    end: tuple[float, float],
) -> dict:
    """One explicit mullion or transom in a composed window's XZ plane."""

    first, second = values.axis((start, end), label="window divider")
    if second < first:
        first, second = second, first
    return {"start": first, "end": second}


def _validated_pieces(pieces: Sequence[dict]) -> list[dict]:
    if not isinstance(pieces, (list, tuple)) or not pieces:
        raise AuthoringError("a composed window needs at least one piece")
    resolved = []
    for index, piece in enumerate(pieces):
        if not isinstance(piece, dict) or "boundary" not in piece:
            raise AuthoringError(
                f"composed window piece {index} must be a window_piece declaration"
            )
        resolved.append(
            window_piece(
                piece["boundary"],
                profile_edges=piece.get("profile_edges"),
                pane=piece.get("pane"),
            )
        )
    return resolved


def _validated_dividers(dividers: Sequence[dict]) -> list[dict]:
    if not isinstance(dividers, (list, tuple)):
        raise AuthoringError("composed window dividers must be a sequence")
    resolved = []
    for index, item in enumerate(dividers):
        if not isinstance(item, dict) or not {"start", "end"} <= set(item):
            raise AuthoringError(
                f"composed window divider {index} must be a window_divider declaration"
            )
        resolved.append(window_divider(item["start"], item["end"]))
    return resolved


def _one_polygon(geometry, label: str) -> Polygon:
    if geometry.geom_type != "Polygon" or geometry.is_empty:
        raise AuthoringError(f"{label} must form one connected polygon")
    if geometry.interiors:
        raise AuthoringError(f"{label} must not enclose a hole")
    return geometry


def _composition_polygon(pieces: Sequence[dict]) -> Polygon:
    """Validate overlap and edge-connectivity, then return the exact union."""

    polygons = [Polygon(piece["boundary"]) for piece in pieces]
    neighbours = {index: set() for index in range(len(polygons))}
    point_contacts = []
    for first_index, first in enumerate(polygons):
        for second_index in range(first_index + 1, len(polygons)):
            intersection = first.intersection(polygons[second_index])
            if intersection.area > _EPS:
                raise AuthoringError(
                    "composed window pieces "
                    f"{first_index} and {second_index} overlap"
                )
            if intersection.length > _EPS:
                neighbours[first_index].add(second_index)
                neighbours[second_index].add(first_index)
            elif not intersection.is_empty:
                point_contacts.append((first_index, second_index))

    reached = {0}
    pending = [0]
    while pending:
        current = pending.pop()
        for neighbour in sorted(neighbours[current]):
            if neighbour not in reached:
                reached.add(neighbour)
                pending.append(neighbour)
    if len(reached) != len(polygons):
        if point_contacts:
            pairs = ", ".join(f"{a}/{b}" for a, b in point_contacts)
            raise AuthoringError(
                "composed window pieces must share an edge, not only a point "
                f"(point contact: {pairs})"
            )
        raise AuthoringError(
            "a composed window's pieces must form one edge-connected composition"
        )

    return _one_polygon(
        unary_union(polygons), "a composed window's pieces"
    )


def _canonical_boundary(polygon: Polygon) -> list[tuple[float, float]]:
    return _canonical_ring(polygon.exterior.coords, anticlockwise=True)


def opening_outline(
    pieces: Sequence[dict],
    *,
    clearance: float = 0.0,
) -> list[tuple[float, float]]:
    """Union piece boundaries into the one opening the window fills."""

    resolved = _validated_pieces(pieces)
    polygon = _composition_polygon(resolved)
    clearance = values.non_negative("composed window opening clearance", clearance)
    if clearance:
        polygon = _one_polygon(
            polygon.buffer(clearance, join_style=2),
            "a composed window's buffered opening",
        )
    return _canonical_boundary(polygon)


def bounds(pieces: Sequence[dict]) -> tuple[float, float, float, float]:
    polygon = Polygon(opening_outline(pieces))
    return tuple(float(value) for value in polygon.bounds)


def _polygon_parts(geometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        candidates = [geometry]
    elif geometry.geom_type == "MultiPolygon":
        candidates = list(geometry.geoms)
    else:
        raise AuthoringError(f"composed window geometry became {geometry.geom_type}")
    canonical = [_canonical_polygon(polygon) for polygon in candidates]
    return sorted(
        canonical,
        key=lambda polygon: (
            tuple(round(float(value), 12) for value in polygon.bounds),
            tuple(polygon.exterior.coords),
            tuple(tuple(ring.coords) for ring in polygon.interiors),
        ),
    )


def _append_area_prism(
    verts: list[Vertex],
    faces: list[tuple[int, ...]],
    uvs: list[list[Point]],
    slots: list[str],
    geometry,
    y_min: float,
    y_max: float,
    role: str,
) -> None:
    """Append a closed prism for a Polygon or MultiPolygon, holes included."""

    triangulate = getattr(shapely, "constrained_delaunay_triangles", None)
    if not callable(triangulate) or getattr(shapely, "geos_version", ()) < (3, 10, 0):
        raise AuthoringError(
            "composed window triangulation requires Shapely >= 2.1 with "
            "GEOS >= 3.10; upgrade Shapely in the Python environment "
            "compiling or executing this building"
        )

    for polygon in _polygon_parts(geometry):
        min_x, min_z, max_x, max_z = polygon.bounds
        span_x = max(max_x - min_x, _EPS)
        span_z = max(max_z - min_z, _EPS)
        vertex_indices: dict[tuple[float, float, float], int] = {}

        def vertex(x: float, y: float, z: float) -> int:
            key = (round(float(x), 12), round(float(y), 12), round(float(z), 12))
            if key not in vertex_indices:
                vertex_indices[key] = len(verts)
                verts.append((float(x), float(y), float(z)))
            return vertex_indices[key]

        def face_uv(points: Sequence[tuple[float, float]]) -> list[Point]:
            return [
                ((x - min_x) / span_x, (z - min_z) / span_z)
                for x, z in points
            ]

        # Every exterior and hole edge must survive triangulation. Filtering
        # unconstrained Delaunay triangles can leave gaps beside T-junctions,
        # where the transom separates panes with different subdivisions.
        triangles = [
            _canonical_ring(triangle.exterior.coords, anticlockwise=True)
            for triangle in triangulate(polygon).geoms
            if triangle.area > _EPS
        ]
        triangles.sort(key=tuple)
        if any(not polygon.covers(Polygon(item)) for item in triangles) or abs(
            sum(abs(_signed_area(item)) for item in triangles) - polygon.area
        ) > max(_EPS, polygon.area * 1e-9):
            raise AuthoringError("composed window prism could not be triangulated")
        for points in triangles:
            # Anticlockwise in XZ faces -Y, which is outward at y_min.
            faces.append(tuple(vertex(x, y_min, z) for x, z in points))
            uvs.append(face_uv(points))
            slots.append(role)
            reversed_points = list(reversed(points))
            faces.append(tuple(vertex(x, y_max, z) for x, z in reversed_points))
            uvs.append(face_uv(reversed_points))
            slots.append(role)

        rings = [polygon.exterior, *polygon.interiors]
        for ring in rings:
            points = [(float(x), float(z)) for x, z in list(ring.coords)[:-1]]
            for first, second in zip(points, points[1:] + points[:1]):
                x1, z1 = first
                x2, z2 = second
                faces.append(
                    (
                        vertex(x1, y_min, z1),
                        vertex(x1, y_max, z1),
                        vertex(x2, y_max, z2),
                        vertex(x2, y_min, z2),
                    )
                )
                length = max(((x2 - x1) ** 2 + (z2 - z1) ** 2) ** 0.5, _EPS)
                uvs.append([(0.0, 0.0), (0.0, 1.0), (length, 1.0), (length, 0.0)])
                slots.append(role)


def _profile_region(line: LineString, window: Polygon, width: float):
    """One declared member, full-width but never doubled at a shared edge.

    On the outer outline the full section lies inside the opening.  On an
    internal piece edge it is centred on the joint.  Unioning these regions
    deduplicates the same member when both neighbouring pieces declare it.
    """

    regions = []
    outer = line.intersection(window.boundary)
    internal = line.difference(window.boundary)
    for part, distance in ((outer, width), (internal, width / 2.0)):
        if part.is_empty:
            continue
        region = part.buffer(distance, cap_style=2, join_style=2).intersection(window)
        if not region.is_empty and region.area > _EPS:
            regions.append(region)
    return unary_union(regions) if regions else Polygon()


def _validate_closed_mesh(mesh: ProceduralMesh) -> ProceduralMesh:
    """Require two oppositely directed faces at every edge of every role."""

    verts, faces, _, slots = mesh
    counts = Counter()
    balance = Counter()
    volumes = defaultdict(float)
    for face, role in zip(faces, slots):
        for first, second in zip(face, face[1:] + face[:1]):
            low, high = sorted((first, second))
            key = (role, low, high)
            counts[key] += 1
            balance[key] += 1 if first == low else -1
        origin = verts[face[0]]
        for index in range(1, len(face) - 1):
            second, third = verts[face[index]], verts[face[index + 1]]
            volumes[role] += (
                origin[0] * (second[1] * third[2] - second[2] * third[1])
                - origin[1] * (second[0] * third[2] - second[2] * third[0])
                + origin[2] * (second[0] * third[1] - second[1] * third[0])
            ) / 6.0
    broken = [key for key, count in counts.items() if count != 2 or balance[key] != 0]
    if broken:
        role, first, second = broken[0]
        raise AuthoringError(
            f"composed window {role} mesh is open at edge {first}-{second}"
        )
    inward = sorted(role for role, volume in volumes.items() if volume <= 0.0)
    if inward:
        raise AuthoringError(
            "composed window mesh has inward-facing " + ", ".join(inward) + " faces"
        )
    return mesh


def composed_window_mesh(
    pieces: Sequence[dict],
    dividers: Sequence[dict],
    *,
    profile_width: float,
    profile_depth: float,
    glazing_thickness: float,
) -> ProceduralMesh:
    """Build profiles and panes for one composed wall window."""

    pieces = _validated_pieces(pieces)
    dividers = _validated_dividers(dividers)
    profile_width = values.positive("composed window profile width", profile_width)
    profile_depth = values.positive("composed window profile depth", profile_depth)
    glazing_thickness = values.positive(
        "composed window glazing thickness", glazing_thickness
    )
    if glazing_thickness >= profile_depth:
        raise AuthoringError(
            "composed window glazing thickness must be less than profile depth"
        )

    window_polygon = Polygon(opening_outline(pieces))
    panes: dict[tuple, list[Polygon]] = defaultdict(list)
    for index, piece in enumerate(pieces):
        key = (
            ("named", piece["pane"])
            if piece["pane"] is not None
            else ("piece", tuple(_canonical_boundary(Polygon(piece["boundary"]))))
        )
        panes[key].append(Polygon(piece["boundary"]))

    verts: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[list[Point]] = []
    slots: list[str] = []

    for key in sorted(panes):
        geometry = _one_polygon(
            unary_union(panes[key]), f"composed window pane {key[1]!r}"
        )
        _append_area_prism(
            verts,
            faces,
            uvs,
            slots,
            geometry,
            -glazing_thickness / 2.0,
            glazing_thickness / 2.0,
            "glazing",
        )

    profile_regions = []
    for piece in pieces:
        boundary = piece["boundary"]
        for edge in piece["profile_edges"]:
            first = boundary[edge]
            second = boundary[(edge + 1) % len(boundary)]
            region = _profile_region(
                LineString((first, second)), window_polygon, profile_width
            )
            if not region.is_empty:
                profile_regions.append(region)
    for divider in dividers:
        line = LineString((divider["start"], divider["end"]))
        if not window_polygon.buffer(_EPS).covers(line):
            raise AuthoringError("a composed window divider must lie inside its opening")
        region = _profile_region(line, window_polygon, profile_width)
        if not region.is_empty:
            profile_regions.append(region)

    if profile_regions:
        _append_area_prism(
            verts,
            faces,
            uvs,
            slots,
            unary_union(profile_regions),
            -profile_depth / 2.0,
            profile_depth / 2.0,
            "framing",
        )

    return _validate_closed_mesh(
        procedures.validate_mesh(
            "composed_window_mesh", (verts, faces, uvs, slots)
        )
    )
