"""Compile building declarations into IFC and Blender MCP execution batches.

The executed source lives in `templates/` as real Python files, so it is
syntax-checked, linted, and diffable like any other module. Compiling only
substitutes `"@@NAME@@"` placeholders for literals; nothing else is generated.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .author import Building, Operation

_TEMPLATES = Path(__file__).parent / "templates"


class CompileError(RuntimeError):
    """Raised when a template cannot be compiled into executable source."""


def roof_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve every roof into the form both phases execute against.

    Edge overrides are merged over the roof defaults and the overhang polygon
    is solved here, in pure Python, so the runtime only has to run a skeleton
    over a plain polygon. Both phases consume this same payload, which is why
    they agree on face geometry without passing state between them.
    """

    from . import polygons, skeleton, tiles, trims

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }

    payload = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "roof":
            continue
        parameters = operation.parameters
        edges = model.roof_edges(operation.key)
        storey_key = operation.references["storey"]
        overhang_boundary = polygons.offset_polygon(
            [(edge["start"], edge["end"], edge["overhang"]) for edge in edges]
        )
        # `upstand` left unstated is solved from the covering that is actually
        # laid, so the lip reads as a lip whatever the relief of the tile
        # under it. A stated one still wins, and the profile's own is the
        # fallback for a roof carrying no covering at all.
        trim_profile = (
            trims.profile(parameters["verge_trim"])
            if parameters.get("verge_trim")
            else None
        )
        trim_overrides = dict(parameters.get("verge_trim_overrides") or {})
        if (
            trim_profile is not None
            and trim_overrides.get("upstand") is None
            and parameters.get("covering")
        ):
            trim_overrides["upstand"] = trims.upstand_over(
                tiles.profile(parameters["covering"]).envelope()
            )
        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "storey": storey_key,
                # Resolved once here so both phases place the roof identically
                # without passing state between them.
                "base_z": elevations[storey_key] + parameters["base_offset"],
                "materials": {
                    "Top": operation.references["top_material"],
                    "Ceiling": operation.references["ceiling_material"],
                    "Side": operation.references["side_material"],
                },
                "boundary": [list(point) for point in parameters["boundary"]],
                "overhang_boundary": [
                    list(point) for point in overhang_boundary
                ],
                "angle": skeleton.require_supported(operation.key, edges),
                "thickness": parameters["thickness"],
                "base_offset": parameters["base_offset"],
                "rafter_edge_angle": parameters["rafter_edge_angle"],
                "gable_indices": [
                    edge["index"]
                    for edge in edges
                    if not edge["defines_slope"]
                ],
                "predefined_type": _roof_predefined_type(parameters, edges),
                "covering": parameters.get("covering"),
                "covering_material": parameters.get("covering_material"),
                "covering_stagger": parameters.get("covering_stagger"),
                # Only the choice travels. Which edges are verges is a fact
                # about the solid, so it is classified where the solid exists
                # rather than guessed from the boundary here - the same reason
                # a roof window resolves its face at runtime.
                "verge_trim": parameters.get("verge_trim"),
                "verge_trim_material": parameters.get("verge_trim_material"),
                # The section, already resolved to the numbers the template
                # sweeps and the 2D centre it places them at, so the template
                # branches on nothing and the arithmetic stays testable
                # without a Blender session.
                "verge_trim_section": (
                    None
                    if trim_profile is None
                    else trim_profile.resolved(**trim_overrides)
                ),
                "verge_trim_centre": (
                    None
                    if trim_profile is None
                    else list(trim_profile.centre(**trim_overrides))
                ),
                "roof_windows": [
                    {
                        "key": window.key,
                        "name": window.parameters["name"],
                        "material": window.references.get("material"),
                        "materials": {
                            role: window.references[key]
                            for role, key in (("frame", "material"),
                                              ("glazing", "glazing"))
                            if key in window.references
                        },
                        "edge": window.parameters["edge"],
                        "along": window.parameters["along"],
                        "up_slope": window.parameters["up_slope"],
                        "width": window.parameters["width"],
                        "height": window.parameters["height"],
                        "profile": window.parameters["profile"],
                    }
                    for window in model.operations
                    if window.phase == "ifc"
                    and window.kind == "roof-window"
                    and window.references.get("roof") == operation.key
                ],
            }
        )
    return payload


def wall_payload(model: Building) -> dict[str, Any]:
    """Resolve walls, their layer sets, and the junctions between them.

    Thickness is summed from the layer set here rather than declared, and the
    default offset that centres a wall on its reference line is solved here
    too, so the template places layers without doing arithmetic.
    """

    from . import junctions, polygons

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }
    thicknesses = {
        operation.key: sum(
            entry["thickness"] for entry in operation.parameters["layers"]
        )
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "wall-type"
    }

    walls = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "wall":
            continue
        parameters = operation.parameters
        start, end = parameters["axis"]
        storey_key = operation.references["storey"]
        thickness = thicknesses[operation.references["wall_type"]]
        offset = parameters["offset_from_reference_line"]
        if offset is None:
            # Centre the layer set on the reference line: the base sits half a
            # thickness to one side, and the layers stack back across it.
            offset = -thickness / 2.0
            if parameters["direction_sense"] == "NEGATIVE":
                offset = thickness / 2.0
        footprint = polygons.wall_footprint(
            start,
            end,
            thickness,
            offset,
            parameters["direction_sense"],
        )
        walls.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "storey": storey_key,
                "wall_type": operation.references["wall_type"],
                "start": list(start),
                "end": list(end),
                "height": parameters["height"],
                "thickness": thickness,
                "direction_sense": parameters["direction_sense"],
                "offset_from_reference_line": offset,
                "base_z": elevations[storey_key] + parameters["base_offset"],
                "footprint": [list(point) for point in footprint],
            }
        )

    walls_by_storey: dict[str, list[dict[str, Any]]] = {}
    for wall in walls:
        walls_by_storey.setdefault(wall["storey"], []).append(wall)

    return {
        "walls": walls,
        "junctions": [
            connection
            for storey_walls in walls_by_storey.values()
            for connection in junctions.connections(
                [
                    {
                        "key": wall["key"],
                        "start": tuple(wall["start"]),
                        "end": tuple(wall["end"]),
                        "base_z": wall["base_z"],
                        "height": wall["height"],
                    }
                    for wall in storey_walls
                ]
            )
        ],
    }


def walls_with_openings_payload(model: Building) -> list[str]:
    """Resolve which walls carry at least one window or door.

    `ifcopenshell.api.feature.add_feature` - what the IFC phase calls for
    every opening - only ever writes the `IfcRelVoidsElement` relationship.
    It does not touch a wall's Blender mesh, and nothing else in the IFC
    phase forces that mesh back in sync with the voids it now carries: the
    IFC phase's own `regenerate_wall_representation` pass runs once, before
    any opening exists, and only ever resolves corners - see walls.md. A
    wall can therefore reach the live scene still looking unopened even
    though its IFC data is correct throughout.

    The presentation phase recalculates every wall named here
    (`bim.recalculate_wall`, the same operator Bonsai's own UI uses) as its
    first step, before any material or tile work reads the scene - so a
    wall carrying several openings cannot silently keep a stale, uncut mesh
    the way it could otherwise.
    """

    seen: dict[str, None] = {}
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind not in (
            "window",
            "door",
            "composed-window",
        ):
            continue
        seen.setdefault(operation.references["wall"], None)
    return list(seen)


def extend_to_structure_payload(model: Building) -> list[dict[str, str]]:
    """Resolve wall-to-structure roles and the declared terminating surface."""

    return [
        {
            "key": operation.key,
            "relating_element": operation.references["relating_element"],
            "related_element": operation.references["related_element"],
            "termination": operation.parameters["termination"],
        }
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "extend-to-structure"
    ]


def slab_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve slabs and their layer sets, exactly as `wall_payload` does.

    A slab has no corners to resolve against neighbours, so this is the
    simpler half of `wall_payload`: sum the declared layers into a depth and
    place the boundary at the storey's elevation plus `base_offset`.
    """

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }
    thicknesses = {
        operation.key: sum(
            entry["thickness"] for entry in operation.parameters["layers"]
        )
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "slab-type"
    }

    payload = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "slab":
            continue
        parameters = operation.parameters
        storey_key = operation.references["storey"]
        base_z = elevations[storey_key] + parameters["base_offset"]
        slab_type = operation.references.get("slab_type")

        # A tiered slab stacks its own declared heights from `base_z`, so each
        # tier's elevation is resolved here rather than left as an offset the
        # template would have to accumulate. A layered slab has one profile
        # and one depth, which is its layer sum.
        tiers = []
        if parameters["tiers"] is not None:
            cursor = base_z
            for boundary, height in parameters["tiers"]:
                tiers.append(
                    {
                        "boundary": [list(point) for point in boundary],
                        "height": height,
                        "base_z": cursor,
                    }
                )
                cursor += height

        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "storey": storey_key,
                "slab_type": slab_type,
                "predefined_type": parameters["predefined_type"],
                "material": operation.references.get("material"),
                "boundary": (
                    None
                    if parameters["boundary"] is None
                    else [list(point) for point in parameters["boundary"]]
                ),
                "tiers": tiers,
                "thickness": (
                    sum(tier["height"] for tier in tiers)
                    if tiers
                    else thicknesses[slab_type]
                ),
                "base_z": base_z,
            }
        )
    return payload


def railing_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve railings onto their path, exactly as `wall_payload` resolves a
    wall's reference line - a straight run placed at the storey's elevation
    plus `base_offset`. A railing has no layer set and no corners to resolve,
    so this is the plain half of `wall_payload`: no thickness sum, no
    junctions.
    """

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }

    payload = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "railing":
            continue
        parameters = operation.parameters
        start, end = parameters["path"]
        storey_key = operation.references["storey"]
        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "storey": storey_key,
                "start": list(start),
                "end": list(end),
                "base_z": elevations[storey_key] + parameters["base_offset"],
                "height": parameters["height"],
                "profile": parameters["profile"],
                "predefined_type": parameters["predefined_type"],
                "object_type": parameters["object_type"],
                "start_post": parameters["start_post"],
                "end_post": parameters["end_post"],
                "materials": {
                    role: operation.references[reference]
                    for role, reference in (
                        ("Post", "post_material"),
                        ("Rail", "rail_material"),
                        ("Infill", "infill_material"),
                        ("Shoe", "shoe_material"),
                        ("Glazing", "glazing_material"),
                    )
                    if reference in operation.references
                },
            }
        )
    return payload


def gate_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve free-standing gates onto their clear-passage reference line.

    Local X follows the declared path and local +Y defines the operation
    side. ``NEGATIVE`` turns the same closed body around and anchors it at the
    opposite end, so it still occupies the same passage while IFC interprets
    left/right operation in the reversed local frame.
    """

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }
    payload: list[dict[str, Any]] = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "gate":
            continue
        parameters = operation.parameters
        start, end = parameters["path"]
        base_angle = math.atan2(end[1] - start[1], end[0] - start[0])
        flipped = parameters["direction_sense"] == "NEGATIVE"
        position = end if flipped else start
        material = operation.references.get("material")
        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "storey": operation.references["storey"],
                "start": list(start),
                "end": list(end),
                "position": [position[0], position[1], elevations[
                    operation.references["storey"]
                ] + parameters["base_offset"]],
                "angle": base_angle + (math.pi if flipped else 0.0),
                "height": parameters["height"],
                "passage_width": parameters["passage_width"],
                "installed_width": parameters["installed_width"],
                "post_centres": parameters["post_centres"],
                "profile": parameters["profile"],
                "leaves": parameters["leaves"],
                "operation_type": parameters["operation_type"],
                "direction_sense": parameters["direction_sense"],
                "materials": (
                    {}
                    if material is None
                    else {
                        "Post": material,
                        "Framing": material,
                        "Infill": material,
                    }
                ),
            }
        )
    return payload


def _resolved_drop(spout: Operation, sole_above_soffit: float) -> float:
    """How far a downspout falls before it swans back, stated or derived.

    Left unstated, it is the distance to the roof's own soffit plus the pipe's
    own half width and a clearance: enough to be clear of the overhang before
    turning inboard under it. The distance is a fact about the gutter's roof,
    handed to the pipe rather than asked of it - a downspout still references
    nothing but its gutter, and still cannot clash with a roof it never
    consulted.

    A stated `drop` is used verbatim. A caller who wants the pipe tucked
    tighter than the derived figure is describing a real detail; refusing it
    here would be this module overruling a declaration it cannot see the
    reason for.
    """

    from . import gutters

    stated = spout.parameters["drop"]
    if stated is not None:
        return stated
    section = gutters.pipe_profile(spout.parameters["profile"]).dimensions(
        spout.parameters["nominal_size"], spout.parameters["sheet_thickness"]
    )
    half = section["radius"] if section["shape"] == "round" else section["y"] / 2.0
    return sole_above_soffit + half + gutters.SOFFIT_CLEARANCE


def gutter_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve every gutter onto its roof's overhang line, and mitre it.

    The run is one edge of the polygon `roof_payload` already solves, so a
    gutter carries no coordinates of its own. What is solved here is the
    **end condition** at each of its two ends: a mitre where the neighbouring
    edge also carries a gutter, a stop-end where it does not.

    Each end's mitre is expressed in that run's **own local frame** - X along
    itself, Y across, Z up - never in world coordinates. That is what keeps
    the corner-window property: the plane bisects the turn, so both runs cut
    at the same angle to their own axis and land on one plane without either
    being handed the other's numbers. Handing each run the shared world plane
    would produce identical geometry and quietly destroy that property, since
    the two would then depend on a value neither could derive alone.
    """

    from . import gutters, polygons, skeleton

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }
    roofs = {
        operation.key: operation
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "roof"
    }

    declared = [
        operation
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "gutter"
    ]
    by_roof_edge = {
        (operation.references["roof"], operation.parameters["edge"]): operation
        for operation in declared
    }

    payload = []
    for operation in declared:
        parameters = operation.parameters
        roof_key = operation.references["roof"]
        roof_operation = roofs[roof_key]
        edges = model.roof_edges(roof_key)
        overhang = polygons.offset_polygon(
            [(edge["start"], edge["end"], edge["overhang"]) for edge in edges]
        )
        count = len(overhang)
        index = parameters["edge"]
        start = overhang[index]
        end = overhang[(index + 1) % count]
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        length = math.hypot(end[0] - start[0], end[1] - start[1])

        def direction_of(edge_index: int) -> tuple[float, float]:
            a = overhang[edge_index % count]
            b = overhang[(edge_index + 1) % count]
            span = math.hypot(b[0] - a[0], b[1] - a[1])
            return ((b[0] - a[0]) / span, (b[1] - a[1]) / span)

        def local(vector: tuple[float, float]) -> tuple[float, float]:
            """A world plan direction, turned into this run's own frame."""

            cos, sin = math.cos(-angle), math.sin(-angle)
            return (
                vector[0] * cos - vector[1] * sin,
                vector[0] * sin + vector[1] * cos,
            )

        own = (1.0, 0.0)
        ends = {}
        for name, neighbour_index, incoming, outgoing in (
            ("start", index - 1, None, own),
            ("end", index + 1, own, None),
        ):
            neighbour = by_roof_edge.get((roof_key, neighbour_index % count))
            if neighbour is None:
                ends[name] = {"kind": "stop_end"}
                continue
            other = local(direction_of(neighbour_index))
            normal = gutters.mitre_normal(
                incoming if incoming is not None else other,
                outgoing if outgoing is not None else other,
            )
            if normal is None:
                raise CompileError(
                    f"{operation.key} meets {neighbour.key} head on at its "
                    f"{name}; two runs doubling back have no mitre plane"
                )
            # The incoming run keeps the negative side and the outgoing run
            # the positive side, so the run whose start this is cuts with the
            # normal reversed. One rule, applied from each run's own end.
            sign = 1.0 if name == "end" else -1.0
            ends[name] = {
                "kind": "mitre",
                "normal": [normal[0] * sign, normal[1] * sign],
                "against": neighbour.key,
            }

        # `base_offset` positions the eave, which is the roof's *top* surface -
        # the drip edge. A run hangs just under it, by its own back upstand
        # plus a clearance, so the covering oversails into the trough.
        #
        # It does not hang by the roof's own thickness. The whole section is
        # outboard of the roof's outer face (`v = 0` is its back), so nothing
        # about its height can clash with the roof; dropping it a further
        # `thickness / cos(pitch)` only moves it from the top of the fascia to
        # the bottom of it. See `gutters.hang`.
        design = gutters.profile(parameters["profile"])
        nominal = parameters["nominal_size"]
        storey_key = roof_operation.references["storey"]

        # How far a run's own sole sits above the roof's soffit at this eave.
        # A downspout swans back **under** that overhang, so it has to fall
        # past it before it turns inboard - and the distance is a fact about
        # this gutter's roof, which is why the pipe is handed it rather than
        # asked for it. The roof's single agreed pitch is used, as
        # `skeleton.require_supported` already refuses a roof whose
        # slope-defining edges disagree.
        pitch = math.radians(skeleton.require_supported(roof_key, edges))
        soffit_below_eave = roof_operation.parameters["thickness"] / math.cos(pitch)
        sole_above_soffit = soffit_below_eave - gutters.sole_below_eave(
            design, nominal
        )

        spouts = [
            spout
            for spout in model.operations
            if spout.phase == "ifc"
            and spout.kind == "downspout"
            and spout.references.get("gutter") == operation.key
        ]
        drops = {
            spout.key: _resolved_drop(spout, sole_above_soffit)
            for spout in spouts
        }
        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "roof": roof_key,
                "storey": storey_key,
                "edge": index,
                "start": list(start),
                "angle": angle,
                "length": length,
                "base_z": elevations[storey_key]
                + roof_operation.parameters["base_offset"]
                - gutters.hang(design, nominal),
                "profile": parameters["profile"],
                "nominal_size": nominal,
                "thickness": parameters["thickness"],
                "material": operation.references.get("material"),
                "ends": ends,
                # Where a downspout hangs from, in the run's own frame: the
                # section's lowest point. Resolved here rather than in the
                # template so it can be tested.
                #
                # Named, not a pair. As a pair this was unpacked in the
                # opposite order at the far end, and a half-round hid it
                # completely: its sole is at `(-nominal/2, -nominal/2)`, so up
                # and across are the same number and transposing them changes
                # nothing at all. A box gutter's sole is at
                # `(-0.8 * nominal, -nominal/2)`, and there the same swap threw
                # every pipe 37.5 mm sideways, out of its own trough.
                #
                # `across` is negative because the body hangs outboard of its
                # own back datum. `section_profile` flips that axis for the
                # profile plane; an object placement must not flip it again.
                "drop_point": design.sole(nominal)._asdict(),
                "sole_above_soffit": sole_above_soffit,
                "downspouts": [
                    {
                        "key": spout.key,
                        "name": spout.parameters["name"],
                        "along": spout.parameters["along"],
                        "drop": drops[spout.key],
                        # The path is resolved here, not in the template: it
                        # is arithmetic over declared numbers, and solving it
                        # in pure Python is what lets it be tested without a
                        # Blender session.
                        "path": [
                            list(point)
                            for point in gutters.downspout_path(
                                spout.parameters["length"],
                                spout.parameters["standoff"],
                                drops[spout.key],
                                spout.parameters["termination"],
                                spout.parameters["shoe_length"],
                            )
                        ],
                        "termination": spout.parameters["termination"],
                        # Round or rectangular, already resolved to the numbers
                        # each one sweeps, so the template branches on a shape
                        # rather than recomputing a section.
                        "pipe": gutters.pipe_profile(
                            spout.parameters["profile"]
                        ).dimensions(
                            spout.parameters["nominal_size"],
                            spout.parameters["sheet_thickness"],
                        ),
                        "profile": spout.parameters["profile"],
                        "nominal_size": spout.parameters["nominal_size"],
                        "sheet_thickness": spout.parameters["sheet_thickness"],
                        "bend_radius": spout.parameters["bend_radius"],
                        "material": spout.references.get("material"),
                    }
                    for spout in spouts
                ],
            }
        )
    return payload


#: The plan thickness given to a virtual element's obstacle rectangle when
#: gathering space boundaries. It carries no material and is never built as a
#: body, so this is a topology tolerance, not a declared dimension - thin
#: enough to be geometrically negligible, thick enough for the boolean union
#: to treat it as a real edge rather than a zero-area sliver.
VIRTUAL_ELEMENT_WIDTH = 0.002


def space_payload(model: Building) -> list[dict[str, Any]]:
    """Group native wall references and virtual boundaries with their spaces.

    A physical wall's footprint only exists after IfcOpenShell resolves its
    joins. Pass its key and vertical extent, never an axis-derived rectangle:
    the IFC runtime reads that regenerated body. Only a virtual element has
    no body, so its thin numerical boundary is resolved here.
    """

    from . import polygons

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }

    walls_by_storey: dict[str, list[dict[str, Any]]] = {}
    for wall in wall_payload(model)["walls"]:
        walls_by_storey.setdefault(wall["storey"], []).append(
            {name: wall[name] for name in ("key", "base_z", "height")}
        )
    virtual_by_storey: dict[str, list[list[list[float]]]] = {}
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "virtual-element":
            continue
        start, end = operation.parameters["axis"]
        storey_key = operation.references["storey"]
        virtual_by_storey.setdefault(storey_key, []).append(
            [
                list(point)
                for point in polygons.wall_footprint(
                    start, end, VIRTUAL_ELEMENT_WIDTH, -VIRTUAL_ELEMENT_WIDTH / 2.0
                )
            ]
        )

    spaces_by_storey: dict[str, list[dict[str, Any]]] = {}
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "space":
            continue
        parameters = operation.parameters
        storey_key = operation.references["storey"]
        spaces_by_storey.setdefault(storey_key, []).append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "at": list(parameters["at"]),
                "height": parameters["height"],
                "predefined_type": parameters["predefined_type"],
                "base_z": elevations[storey_key] + parameters["base_offset"],
            }
        )

    return [
        {
            "storey": storey_key,
            "walls": walls_by_storey.get(storey_key, []),
            "virtual_obstacles": virtual_by_storey.get(storey_key, []),
            "spaces": spaces,
        }
        for storey_key, spaces in spaces_by_storey.items()
    ]


def covering_payload(model: Building) -> dict[str, list[dict[str, Any]]]:
    """Resolve room finishes and separate threshold-patch occurrences.

    Main covering boundaries remain unresolved because they are exactly the
    room regions the IFC template encloses with Shapely. Threshold boundaries
    are plain rectangles, however, and are resolved here from the opening's
    width and its host wall's exact footprint. Both kinds inherit their
    elevation from the owning space; the patch's small `THRESHOLD_RISE` is a
    contact clearance over the plinth it spans, not an independent offset.
    """

    from . import polygons

    elevations = {
        operation.key: operation.parameters["elevation"]
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "storey"
    }
    spaces = {
        operation.key: operation
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "space"
    }
    main = []
    by_space: dict[str, dict[str, Any]] = {}
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "covering":
            continue
        space_key = operation.references["space"]
        space_operation = spaces[space_key]
        storey_key = space_operation.references["storey"]
        thickness = operation.parameters["thickness"]
        item = {
            "key": operation.key,
            "name": operation.parameters["name"],
            "space": space_key,
            "storey": storey_key,
            "material": operation.references["material"],
            "thickness": thickness,
            "base_z": (
                elevations[storey_key]
                + space_operation.parameters["base_offset"]
                - thickness
            ),
            "predefined_type": operation.parameters["predefined_type"],
        }
        main.append(item)
        by_space[space_key] = item

    walls = {wall["key"]: wall for wall in wall_payload(model)["walls"]}
    thresholds = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind not in {
            "window",
            "door",
            "virtual-element",
        }:
            continue
        space_key = operation.references.get("threshold_space")
        if space_key is None:
            continue
        inherited = by_space[space_key]
        if operation.kind == "virtual-element":
            start, end = operation.parameters["axis"]
            boundary = polygons.wall_footprint(
                start,
                end,
                VIRTUAL_ELEMENT_WIDTH,
                -VIRTUAL_ELEMENT_WIDTH / 2.0,
            )
        else:
            wall = walls[operation.references["wall"]]
            boundary = polygons.wall_interval_footprint(
                tuple(wall["start"]),
                tuple(wall["end"]),
                wall["thickness"],
                wall["offset_from_reference_line"],
                operation.parameters["along"],
                operation.parameters["overall_width"],
                wall["direction_sense"],
            )
        thresholds.append(
            {
                "key": f"{operation.key}.threshold-flooring",
                "name": f"{operation.parameters['name']} Threshold Flooring",
                "source": operation.key,
                "space": space_key,
                "storey": inherited["storey"],
                "material": inherited["material"],
                "thickness": inherited["thickness"],
                "base_z": inherited["base_z"] + THRESHOLD_RISE,
                "predefined_type": inherited["predefined_type"],
                "boundary": [list(point) for point in boundary],
            }
        )

    return {"main": main, "thresholds": thresholds}


#: How far an opening solid reaches past the wall it voids. A cutter that
#: stops exactly on the wall face leaves two coplanar surfaces for the boolean
#: to resolve, which is where slivers come from.
OPENING_REACH = 0.05

#: Elevation clearance around a composed polygonal opening.  Unlike the stock
#: rectangular generator, the composed body's profiles sit exactly on an
#: arbitrary outline; the small oversize prevents coincident wall/profile
#: faces without changing the window's nominal OverallWidth/OverallHeight.
COMPOSED_OPENING_CLEARANCE = 0.004

#: How far a sill's own top face is raised above the window's nominal sill
#: line. The wall's own opening void has its bottom face exactly there too -
#: both driven by the same `sill_height` - so left alone the sill and the
#: wall's cut reveal are two independent, coincident, overlapping faces at
#: the same height, which is exactly the z-fighting `OPENING_REACH` exists
#: to avoid on the wall's own cut. Solved the same way: a small deliberate
#: overlap into the wall, rather than an exact match neither renderer nor
#: boolean can resolve consistently.
SILL_RISE = 0.004

#: How far a threshold patch's finished face is raised above the floor it
#: joins. A room's floor lies inside its walls, meeting the slab as a hidden
#: back-to-front contact; a threshold patch spans the host wall's own
#: footprint, where a plinth tops out at that same floor datum - so a patch
#: landing exactly on it is a coplanar, same-facing pair and shimmers. The
#: rise clears it, and hides the plinth's top edge under the patch. One
#: millimetre is enough to break the coincidence and reads as nothing.
THRESHOLD_RISE = 0.001


def opening_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve every window and door onto the wall that hosts it.

    The whole placement is solved here, in pure Python, so both phases agree
    on where an opening sits without passing state. An opening is declared
    against its host wall's reference line, so this is where that reference
    becomes a world position and a rotation: an origin at the opening's lower
    left corner, with the lining centred in the wall's thickness.

    `direction_sense` is resolved here too. IFC carries which stile a door is
    hung on in `OperationType` and which way it swings in the **placement**,
    so `NEGATIVE` turns the element half a turn about its own height and moves
    its origin to the opposite corner - which is the same flip Bonsai's
    `bim.toggle_door_swing` performs.
    """

    walls = {wall["key"]: wall for wall in wall_payload(model)["walls"]}
    types = {
        operation.key: operation.parameters
        for operation in model.operations
        if operation.phase == "ifc"
        and operation.kind in ("window-type", "door-type")
    }

    payload = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind not in ("window", "door"):
            continue
        parameters = operation.parameters
        wall = walls[operation.references["wall"]]
        type_key = operation.references[f"{operation.kind}_type"]
        type_parameters = types[type_key]
        lining = type_parameters["lining"]

        width = parameters["overall_width"]
        height = parameters["overall_height"]
        base = (
            parameters["sill_height"]
            if operation.kind == "window"
            else parameters["base_offset"]
        )

        # The layer set stacks from the reference line by its offset, so the
        # wall's own centre is half a thickness further along that stack.
        sense = 1.0 if wall["direction_sense"] == "POSITIVE" else -1.0
        wall_centre = wall["offset_from_reference_line"] + sense * wall["thickness"] / 2.0
        wall_angle = math.atan2(
            wall["end"][1] - wall["start"][1],
            wall["end"][0] - wall["start"][0],
        )

        # IfcOpenShell builds an opening from its lower left corner with the
        # lining running into +Y, so centring the lining is a half-depth back.
        # Turned about its own height, the same body reaches the other way, so
        # its origin moves to the far corner to still fill the same opening.
        flipped = parameters["direction_sense"] == "NEGATIVE"
        half_depth = lining["LiningDepth"] / 2.0
        if flipped:
            local = (parameters["along"] + width / 2.0, wall_centre + half_depth)
        else:
            local = (parameters["along"] - width / 2.0, wall_centre - half_depth)

        # A door meets the floor, so its cutter drops below the wall base
        # rather than stopping flush with it and leaving a coplanar face.
        drop = OPENING_REACH if operation.kind == "door" and base == 0.0 else 0.0
        payload.append(
            {
                "key": operation.key,
                "kind": operation.kind,
                "name": parameters["name"],
                "wall": wall["key"],
                "storey": wall["storey"],
                "type": type_key,
                # IFC states a division as a ratio of the window, which is what
                # the type's property set keeps. IfcOpenShell's generator wants
                # the distance that ratio works out to at this size, and so
                # does the pset Bonsai's own window tool reads.
                "lining": _generator_lining(lining, width, height),
                "along": parameters["along"],
                "overall_width": width,
                "overall_height": height,
                "base": base,
                "direction_sense": parameters["direction_sense"],
                "is_external": parameters["is_external"],
                "materials": {
                    role: operation.references[reference]
                    for role, reference in (
                        ("Lining", "lining_material"),
                        ("Framing", "framing_material"),
                        ("Glazing", "glazing_material"),
                    )
                    if reference in operation.references
                },
                "angle": wall_angle + (math.pi if flipped else 0.0),
                "position": _placed(wall, wall_angle, local, base),
                # The cutter spans the whole wall and a reach beyond each face.
                # It is a box about its own centre, so it never flips.
                "opening_angle": wall_angle,
                "opening_position": _placed(
                    wall,
                    wall_angle,
                    (parameters["along"], wall_centre),
                    base - drop + (height + drop) / 2.0,
                ),
                # Named rather than a positional triple: the three spans are
                # all lengths in metres and nothing but the name distinguishes
                # the one that runs through the wall from the one that runs up
                # it, so an unpacking in the wrong order reads as valid code
                # and cuts a letterbox.
                "opening_size": {
                    "width": width,
                    "through": wall["thickness"] + 2.0 * OPENING_REACH,
                    "height": height + drop,
                },
            }
        )
    return payload


def composed_window_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve script-parametric glazing onto its host wall.

    Piece coordinates remain untouched so the IFC body preserves the source
    composition. Placement translates their bounding box so ``along`` names
    its centre and ``sill_height`` its lowest point. No host/storey height is
    consulted: spatial containment is not a geometric clipping boundary.
    """

    from . import composed_windows

    walls = {wall["key"]: wall for wall in wall_payload(model)["walls"]}
    types = {
        operation.key: operation.parameters
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "composed-window-type"
    }
    payload = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "composed-window":
            continue
        parameters = operation.parameters
        wall = walls[operation.references["wall"]]
        type_key = operation.references["composed_window_type"]
        section = types[type_key]
        min_x, min_z, max_x, max_z = composed_windows.bounds(parameters["pieces"])
        width = max_x - min_x
        height = max_z - min_z

        sense = 1.0 if wall["direction_sense"] == "POSITIVE" else -1.0
        wall_centre = (
            wall["offset_from_reference_line"]
            + sense * wall["thickness"] / 2.0
        )
        wall_angle = math.atan2(
            wall["end"][1] - wall["start"][1],
            wall["end"][0] - wall["start"][0],
        )
        x_origin = parameters["along"] - width / 2.0 - min_x
        z_origin = parameters["sill_height"] - min_z
        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "type": type_key,
                "wall": wall["key"],
                "storey": wall["storey"],
                "overall_width": width,
                "overall_height": height,
                "pieces": parameters["pieces"],
                "dividers": parameters["dividers"],
                "profile_width": section["profile_width"],
                "profile_depth": section["profile_depth"],
                "glazing_thickness": section["glazing_thickness"],
                "materials": {
                    role: operation.references[reference]
                    for role, reference in (
                        ("Framing", "framing_material"),
                        ("Glazing", "glazing_material"),
                    )
                    if reference in operation.references
                },
                "position": _placed(
                    wall,
                    wall_angle,
                    (x_origin, wall_centre + section["offset"]),
                    z_origin,
                ),
                "angle": wall_angle,
                "opening_outline": composed_windows.opening_outline(
                    parameters["pieces"], clearance=COMPOSED_OPENING_CLEARANCE
                ),
                "opening_position": _placed(
                    wall,
                    wall_angle,
                    (x_origin, wall_centre),
                    z_origin,
                ),
                "opening_through": wall["thickness"] + 2.0 * OPENING_REACH,
                "is_external": parameters["is_external"],
            }
        )
    return payload


def sill_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve every window sill onto the wall its window is hosted on.

    A sill sits at the opening's own sill line and spans the wall's full
    thickness, not the window's own, usually narrower, lining depth - it
    sheds water off the wall, not off the frame - so this is solved from the
    wall directly, the same way `opening_payload` solves the opening's own
    cutter, rather than reused from the window's lining placement.
    """

    walls = {wall["key"]: wall for wall in wall_payload(model)["walls"]}
    windows = {
        operation.key: operation
        for operation in model.operations
        if operation.phase == "ifc" and operation.kind == "window"
    }

    payload = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "window-sill":
            continue
        parameters = operation.parameters
        window = windows[operation.references["window"]]
        wall = walls[window.references["wall"]]
        window_parameters = window.parameters

        sense = 1.0 if wall["direction_sense"] == "POSITIVE" else -1.0
        wall_centre = wall["offset_from_reference_line"] + sense * wall["thickness"] / 2.0
        wall_angle = math.atan2(
            wall["end"][1] - wall["start"][1], wall["end"][0] - wall["start"][0]
        )
        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "window": window.key,
                "storey": wall["storey"],
                "material": operation.references.get("material"),
                "width": window_parameters["overall_width"]
                + 2.0 * parameters["horn"],
                "depth": wall["thickness"] + 2.0 * parameters["projection"],
                "thickness": parameters["thickness"],
                "corner": parameters["corner"],
                "corner_reach": parameters["corner_reach"],
                "angle": wall_angle,
                "position": _placed(
                    wall,
                    wall_angle,
                    (window_parameters["along"], wall_centre),
                    window_parameters["sill_height"] + SILL_RISE,
                ),
            }
        )
    return payload


def corner_opening_payload(model: Building) -> list[dict[str, Any]]:
    """Resolve common cutter geometry for two host-specific corner openings.

    Sized from each wall's own declared thickness, not estimated: through
    `wall_a` it is `wall_a`'s own full thickness, and along it, the extent
    is `wall_b`'s own thickness - the most either wall's mitre with the
    other could ever occupy, regardless of the mitre's actual shape.
    `_shared_endpoint` is what finds the corner itself and `wall_a`'s own
    `along` value there, from the two walls' own declared axes; neither
    wall's declaration is touched to do it.
    """

    walls = {wall["key"]: wall for wall in wall_payload(model)["walls"]}

    payload = []
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind != "corner-opening":
            continue
        parameters = operation.parameters
        wall_a = walls[operation.references["wall.0"]]
        wall_b = walls[operation.references["wall.1"]]
        corner, along_a = _shared_endpoint(wall_a, wall_b, operation.key)

        sense = 1.0 if wall_a["direction_sense"] == "POSITIVE" else -1.0
        wall_centre = wall_a["offset_from_reference_line"] + sense * wall_a["thickness"] / 2.0
        wall_angle = math.atan2(
            wall_a["end"][1] - wall_a["start"][1],
            wall_a["end"][0] - wall_a["start"][0],
        )
        reach = parameters["reach"]
        payload.append(
            {
                "key": operation.key,
                "name": parameters["name"],
                "storey": wall_a["storey"],
                "wall_a": wall_a["key"],
                "wall_b": wall_b["key"],
                "angle": wall_angle,
                "position": _placed(
                    wall_a, wall_angle, (along_a, wall_centre), parameters["base"]
                ),
                "size": {
                    "along": wall_b["thickness"] + 2.0 * reach,
                    "through": wall_a["thickness"] + 2.0 * reach,
                    "height": parameters["height"],
                },
            }
        )
    return payload


def _shared_endpoint(wall_a, wall_b, key):
    """The point `wall_a` and `wall_b` share, and `wall_a`'s own `along`
    value there - 0 at its start, its own length at its end."""

    length = math.hypot(
        wall_a["end"][0] - wall_a["start"][0], wall_a["end"][1] - wall_a["start"][1]
    )
    candidates = [(wall_a["start"], 0.0), (wall_a["end"], length)]
    others = [wall_b["start"], wall_b["end"]]
    for point, along in candidates:
        for other in others:
            if math.hypot(point[0] - other[0], point[1] - other[1]) < 1e-6:
                return point, along
    raise CompileError(
        f"{key} names two walls that do not share an endpoint: "
        f"{wall_a['key']} and {wall_b['key']}"
    )


def _placed(wall, wall_angle, local, height):
    """Carry a point from the wall's own frame out into world coordinates."""

    return [
        wall["start"][0]
        + math.cos(wall_angle) * local[0]
        - math.sin(wall_angle) * local[1],
        wall["start"][1]
        + math.sin(wall_angle) * local[0]
        + math.cos(wall_angle) * local[1],
        wall["base_z"] + height,
    ]


def _generator_lining(lining, width, height):
    """Turn IFC's division ratios into the distances the generator consumes.

    A division this partitioning does not have has no ratio, and lands as zero
    - which is what the generator and Bonsai's window props both expect from
    an absent mullion or transom.
    """

    resolved = dict(lining)
    for attribute, extent in (
        ("FirstMullionOffset", width),
        ("SecondMullionOffset", width),
        ("FirstTransomOffset", height),
        ("SecondTransomOffset", height),
    ):
        if attribute in resolved:
            ratio = resolved[attribute]
            resolved[attribute] = 0.0 if ratio is None else ratio * extent
    return resolved


def _roof_predefined_type(parameters: dict, edges: list[dict]) -> str:
    """Classify the roof for `IfcRoof.PredefinedType`.

    Derived from what was actually declared rather than asked for separately,
    so the IFC classification cannot drift from the geometry.
    """

    if parameters["angle"] == 0.0:
        return "FLAT_ROOF"
    sloping = [edge for edge in edges if edge["defines_slope"]]
    gables = len(edges) - len(sloping)
    if gables == 0:
        return "HIP_ROOF"
    if len(sloping) == 1:
        return "SHED_ROOF"
    if gables == 2 and len(edges) == 4:
        return "GABLE_ROOF"
    return "HIPPED_GABLE_ROOF"


def compile_ifc(model: Building) -> str:
    """Compile the IFC phase into one Bonsai MCP execution batch."""

    operations = [
        operation.as_dict()
        for operation in model.operations
        if operation.phase == "ifc"
    ]
    return _render(
        "ifc_phase.py",
        {
            "BUILD_NAME": model.name,
            "OPERATIONS": json.dumps(operations),
            "TURFS": json.dumps([op.as_dict() for op in model.operations
                                 if op.phase == "ifc" and op.kind == "turf"]),
            "ROOFS": json.dumps(roof_payload(model)),
            "WALLS": json.dumps(wall_payload(model)),
            "SLABS": json.dumps(slab_payload(model)),
            "SPACES": json.dumps(space_payload(model)),
            "COVERINGS": json.dumps(covering_payload(model)),
            "RAILINGS": json.dumps(railing_payload(model)),
            "GATES": json.dumps(gate_payload(model)),
            "GUTTERS": json.dumps(gutter_payload(model)),
            "EXTEND_TO_STRUCTURE": json.dumps(extend_to_structure_payload(model)),
            "OPENINGS": json.dumps(opening_payload(model)),
            "COMPOSED_WINDOWS": json.dumps(composed_window_payload(model)),
            "SILLS": json.dumps(sill_payload(model)),
            "CORNER_OPENINGS": json.dumps(corner_opening_payload(model)),
            "PACKAGE_ROOT": str(_TEMPLATES.parent.parent),
        },
    )


def compile_blender(model: Building) -> str:
    """Compile presentation operations for post-reload Blender execution."""

    presentation = [
        operation.as_dict()
        for operation in model.operations
        if operation.phase == "presentation"
    ]
    # Only elements made of one material are painted this way, because the
    # presentation phase does it by clearing the object's slots. An element
    # whose parts carry their own materials - a roof or window, through its
    # shape aspects and constituents - already arrives correctly split, and
    # clearing its slots would collapse it back onto a single material.
    single_material_kinds = {"extrusion"}
    material_targets: dict[str, list[str]] = {}
    for operation in model.operations:
        if operation.phase != "ifc" or operation.kind not in single_material_kinds:
            continue
        material_key = operation.references.get("material")
        if material_key:
            material_targets.setdefault(material_key, []).append(operation.key)

    return _render(
        "presentation_phase.py",
        {
            "OPERATIONS": json.dumps(presentation),
            "MATERIAL_TARGETS": json.dumps(material_targets),
            "TURFS": json.dumps([op.as_dict() for op in model.operations
                                 if op.phase == "ifc" and op.kind == "turf"]),
            "ROOFS": json.dumps(roof_payload(model)),
            "WALLS_WITH_OPENINGS": json.dumps(walls_with_openings_payload(model)),
            "PACKAGE_ROOT": str(_TEMPLATES.parent.parent),
            "BLEND_PATH": str(model.blend_path),
        },
    )


def _render(template_name: str, values: dict[str, Any]) -> str:
    """Replace each `"@@NAME@@"` string literal with the repr of its value."""

    source = (_TEMPLATES / template_name).read_text(encoding="utf-8")
    for name, value in values.items():
        placeholder = f'"@@{name}@@"'
        if placeholder not in source:
            raise CompileError(
                f"{template_name} has no placeholder for {name}"
            )
        source = source.replace(placeholder, repr(value))
    if "@@" in source:
        raise CompileError(
            f"{template_name} still holds an unsubstituted placeholder"
        )
    return source
