"""Concise building-as-code declarations compiled for Bonsai MCP."""

from __future__ import annotations

import json
import math
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import (
    caps,
    composed_windows,
    gutters,
    railings,
    roof_windows,
    tiles,
    trims,
    values,
)
from .values import AuthoringError

_IFC_KINDS = {
    "project",
    "site",
    "building",
    "storey",
    "material",
    "wall-type",
    "wall",
    "extend-to-structure",
    "extrusion",
    "slab-type",
    "slab",
    "virtual-element",
    "space",
    "turf",
    "covering",
    "railing",
    "gate",
    "roof",
    "roof-edge",
    "roof-window",
    "gutter",
    "downspout",
    "window-type",
    "window",
    "composed-window-type",
    "composed-window",
    "window-sill",
    "door-type",
    "door",
    "corner-opening",
}
_PRESENTATION_KINDS = {"pbr-material", "roof-tiles", "roof-window-frame"}

# Authoring intent rather than an IFC enumeration: IFC says that a wall
# extends to the structure above, but does not prescribe which of that
# structure's two bounding surfaces terminates the wall.
EXTEND_TO_STRUCTURE_TERMINATIONS = frozenset({"UNDERSIDE", "TOP_SURFACE"})


@dataclass(frozen=True, slots=True)
class Operation:
    """One IFC-semantic or Blender-presentation instruction."""

    phase: str
    kind: str
    key: str
    references: Mapping[str, str]
    parameters: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "references": dict(self.references),
            "parameters": dict(self.parameters),
        }


class Building:
    """A complete executable building script."""

    def __init__(self, name: str, *, output_dir: str | Path | None = None) -> None:
        self.name = values.identifier("building script name", name)
        root = (
            Path(output_dir)
            if output_dir is not None
            else Path(tempfile.gettempdir()) / "bonsai-building-author"
        )
        self.output_dir = root.expanduser().resolve()
        self.ifc_path = self.output_dir / f"{self.name}.ifc"
        self.blend_path = self.output_dir / f"{self.name}.blend"
        self._operations: list[Operation] = []

    @property
    def operations(self) -> tuple[Operation, ...]:
        return tuple(self._operations)

    def add_ifc(
        self,
        kind: str,
        key: str,
        *,
        references: Mapping[str, str] | None = None,
        **parameters: Any,
    ) -> str:
        """Append one core IFC declaration."""

        if kind not in _IFC_KINDS:
            raise AuthoringError(f"unsupported core IFC operation: {kind}")
        self._append("ifc", kind, key, references, parameters)
        return key

    def add_presentation(
        self,
        kind: str,
        key: str,
        *,
        target: str,
        references: Mapping[str, str] | None = None,
        **parameters: Any,
    ) -> str:
        """Append one Blender-only presentation operation."""

        if kind not in _PRESENTATION_KINDS:
            raise AuthoringError(
                f"unsupported core presentation operation: {kind}"
            )
        operation_references = dict(references or {})
        operation_references["target"] = target
        self._append(
            "presentation",
            kind,
            key,
            operation_references,
            parameters,
        )
        return key

    def validate(self) -> None:
        """Validate the complete source before any MCP edit call."""

        errors: list[str] = []
        keys_by_phase: dict[str, set[str]] = {"ifc": set(), "presentation": set()}

        for operation in self._operations:
            phase_keys = keys_by_phase[operation.phase]
            if operation.key in phase_keys:
                errors.append(
                    f"duplicate {operation.phase} operation key: {operation.key}"
                )
            phase_keys.add(operation.key)

        ifc_keys = keys_by_phase["ifc"]
        for operation in self._operations:
            for role, reference in operation.references.items():
                if reference not in ifc_keys:
                    errors.append(
                        f"{operation.key} has unresolved {role} reference: "
                        f"{reference}"
                    )

        project_count = sum(
            operation.phase == "ifc" and operation.kind == "project"
            for operation in self._operations
        )
        if project_count != 1:
            errors.append(
                f"script must declare exactly one project; found {project_count}"
            )

        try:
            json.dumps([operation.as_dict() for operation in self._operations])
        except (TypeError, ValueError) as exc:
            errors.append(f"operation parameters are not serializable: {exc}")

        operations = {op.key: op for op in self._operations if op.phase == "ifc"}
        for op in operations.values():
            if op.kind == "turf":
                parent = operations.get(op.references["site"])
                if parent is not None and parent.kind != "site":
                    errors.append(f"{op.key} site must reference an IfcSite declaration")

        errors.extend(self._roof_errors())
        errors.extend(self._opening_errors())
        errors.extend(self._composed_window_errors())
        errors.extend(self._extend_to_structure_errors())
        errors.extend(self._corner_opening_errors())
        errors.extend(self._slab_errors())
        errors.extend(self._covering_errors())
        errors.extend(self._gutter_errors())
        errors.extend(self._railing_errors())
        errors.extend(self._gate_errors())

        if errors:
            raise AuthoringError("\n".join(errors))

    def _railing_errors(self) -> list[str]:
        """Check a railing's spatial and material roles before compilation."""

        operations = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc"
        }
        errors: list[str] = []
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "railing":
                continue
            storey_key = operation.references["storey"]
            storey_operation = operations.get(storey_key)
            if storey_operation is not None and storey_operation.kind != "storey":
                errors.append(
                    f"{operation.key} storey must be a storey: "
                    f"{storey_key} is {storey_operation.kind}"
                )
            for role, material_key in operation.references.items():
                if not role.endswith("_material"):
                    continue
                material_operation = operations.get(material_key)
                if (
                    material_operation is not None
                    and material_operation.kind != "material"
                ):
                    errors.append(
                        f"{operation.key} {role} must be a material: "
                        f"{material_key} is {material_operation.kind}"
                    )
        return errors

    def _gate_errors(self) -> list[str]:
        """Check a free-standing gate's storey and material identities."""

        operations = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc"
        }
        errors: list[str] = []
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "gate":
                continue
            storey_key = operation.references["storey"]
            storey_operation = operations.get(storey_key)
            if storey_operation is not None and storey_operation.kind != "storey":
                errors.append(
                    f"{operation.key} storey must be a storey: "
                    f"{storey_key} is {storey_operation.kind}"
                )
            material_key = operation.references.get("material")
            material_operation = operations.get(material_key)
            if (
                material_operation is not None
                and material_operation.kind != "material"
            ):
                errors.append(
                    f"{operation.key} material must be a material: "
                    f"{material_key} is {material_operation.kind}"
                )
        return errors

    def _extend_to_structure_errors(self) -> list[str]:
        """Check the IFC roles used to extend a wall to an element above."""

        operations = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc"
        }
        errors: list[str] = []
        claimed_walls: dict[str, str] = {}
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "extend-to-structure":
                continue
            relating_key = operation.references["relating_element"]
            related_key = operation.references["related_element"]
            relating = operations.get(relating_key)
            related = operations.get(related_key)
            if relating_key == related_key:
                errors.append(f"{operation.key} cannot connect an element to itself")
            if relating is not None and relating.kind not in {"roof", "slab"}:
                errors.append(
                    f"{operation.key} relating_element must be a roof or slab: "
                    f"{relating_key} is {relating.kind}"
                )
            if related is not None and related.kind != "wall":
                errors.append(
                    f"{operation.key} related_element must be a wall: "
                    f"{related_key} is {related.kind}"
                )
            previous = claimed_walls.get(related_key)
            if previous is not None:
                errors.append(
                    f"{operation.key} and {previous} both extend "
                    f"{related_key}; a wall may name only one structure above"
                )
            claimed_walls[related_key] = operation.key
        return errors

    def _composed_window_errors(self) -> list[str]:
        """Validate composed-window roles and geometry without storey clipping.

        A storey is the element's spatial home, not an envelope for its body.
        In particular, a gable window may begin on one storey and continue
        above it, so there is deliberately no comparison with either the host
        wall height or a storey-to-storey height here.
        """

        operations = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc"
        }
        errors: list[str] = []
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "composed-window":
                continue
            wall_key = operation.references.get("wall")
            type_key = operation.references.get("composed_window_type")
            wall = operations.get(wall_key)
            window_type = operations.get(type_key)
            if wall is not None and wall.kind != "wall":
                errors.append(
                    f"{operation.key} wall must be a wall: {wall_key} is {wall.kind}"
                )
            if window_type is not None and window_type.kind != "composed-window-type":
                errors.append(
                    f"{operation.key} composed_window_type must be a "
                    f"composed-window-type: {type_key} is {window_type.kind}"
                )
            try:
                composed_windows.opening_outline(operation.parameters["pieces"])
                if window_type is not None and window_type.kind == "composed-window-type":
                    composed_windows.composed_window_mesh(
                        operation.parameters["pieces"],
                        operation.parameters["dividers"],
                        profile_width=window_type.parameters["profile_width"],
                        profile_depth=window_type.parameters["profile_depth"],
                        glazing_thickness=window_type.parameters["glazing_thickness"],
                    )
            except AuthoringError as exc:
                errors.append(f"{operation.key}: {exc}")
        return errors

    def _corner_opening_errors(self) -> list[str]:
        """Check the two roles a corner opening names are both real walls.

        Whether they actually share an endpoint is a geometric fact, not a
        reference to resolve, so that is `compiler.corner_opening_payload`'s
        to catch - the same split `_extend_to_structure_errors` already
        draws between "does this role name the right kind of element" and
        "does the geometry actually agree".
        """

        operations = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc"
        }
        errors: list[str] = []
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "corner-opening":
                continue
            wall_a_key = operation.references["wall.0"]
            wall_b_key = operation.references["wall.1"]
            if wall_a_key == wall_b_key:
                errors.append(f"{operation.key} cannot name the same wall twice")
            for role, wall_key in (("wall.0", wall_a_key), ("wall.1", wall_b_key)):
                wall = operations.get(wall_key)
                if wall is not None and wall.kind != "wall":
                    errors.append(
                        f"{operation.key} {role} must be a wall: "
                        f"{wall_key} is {wall.kind}"
                    )
        return errors

    def _opening_errors(self) -> list[str]:
        """Check every opening against the size its own type can be built at.

        A division is a ratio on the type, so whether it leaves a usable panel
        is only knowable once an occurrence states its size. Catching it here
        names the window; letting it through surfaces as an index error inside
        IfcOpenShell's shape builder with nothing to trace it back to.
        """

        types = {
            operation.key: operation.parameters
            for operation in self._operations
            if operation.phase == "ifc" and operation.kind == "window-type"
        }
        errors: list[str] = []
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "window":
                continue
            type_parameters = types.get(operation.references.get("window_type"))
            if type_parameters is None:
                continue  # an unresolved reference is already reported above
            lining = type_parameters["lining"]
            width = operation.parameters["overall_width"]
            height = operation.parameters["overall_height"]
            if type_parameters.get("assembly"):
                from .window_assemblies import validate_lift_slide_assembly

                try:
                    validate_lift_slide_assembly(
                        {k: v for k, v in type_parameters["assembly"].items() if k != "kind"},
                        width, height,
                    )
                except AuthoringError as exc:
                    errors.append(f"{operation.key}: {exc}")
                continue
            _, mullions, transoms = values.WINDOW_PARTS[
                type_parameters["partitioning_type"]
            ]
            for count, extent, thickness_key, offsets, axis in (
                (
                    mullions,
                    width,
                    "MullionThickness",
                    ("FirstMullionOffset", "SecondMullionOffset"),
                    "wide",
                ),
                (
                    transoms,
                    height,
                    "TransomThickness",
                    ("FirstTransomOffset", "SecondTransomOffset"),
                    "tall",
                ),
            ):
                if not count:
                    continue
                cuts = [lining[offsets[index]] * extent for index in range(count)]
                spans = [
                    following - preceding
                    for preceding, following in zip(
                        [0.0] + cuts, cuts + [extent]
                    )
                ]
                # An upper bound on what the lining or a mullion eats from each
                # side. Anything narrower than this cannot leave a panel.
                consumed = 2.0 * (
                    max(lining["LiningThickness"], lining[thickness_key])
                    + lining["LiningToPanelOffsetX"]
                )
                if min(spans) <= consumed:
                    errors.append(
                        f"{operation.key} is {extent:.3f} m {axis} and divided "
                        f"into panels of {min(spans):.3f} m, which its "
                        f"{consumed:.3f} m of framing leaves nothing of"
                    )
        return errors

    def _roof_errors(self) -> list[str]:
        """Check every roof against the skeleton the runtime actually has."""

        from . import skeleton

        errors: list[str] = []
        operations = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc"
        }
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "roof":
                continue
            for role in ("top_material", "ceiling_material", "side_material"):
                material_key = operation.references[role]
                material = operations.get(material_key)
                if material is not None and material.kind != "material":
                    errors.append(
                        f"{operation.key} {role} must be a material: "
                        f"{material_key} is {material.kind}"
                    )
            corners = len(operation.parameters["boundary"])
            for index in self._override_indices(operation.key):
                if not 0 <= index < corners:
                    errors.append(
                        f"{operation.key} has an edge override for index "
                        f"{index}, but its boundary has {corners} edges"
                    )
            try:
                skeleton.require_supported(
                    operation.key, self.roof_edges(operation.key)
                )
            except AuthoringError as exc:
                errors.append(str(exc))
        return errors

    def _slab_errors(self) -> list[str]:
        """Check each slab declared exactly one of its two ways.

        The unresolved-reference check already names a missing `slab_type` or
        `material`; what it cannot see is a slab that named both, or neither,
        or that paired a layer set with tiers those layers cannot describe.
        """

        errors: list[str] = []
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "slab":
                continue
            typed = "slab_type" in operation.references
            tiered = operation.parameters["tiers"] is not None
            material = "material" in operation.references
            if typed and tiered:
                errors.append(
                    f"{operation.key} declares both a slab_type and tiers; a "
                    "layer set is one profile sliced through its thickness, "
                    "which is what tiers are not"
                )
            if not typed and not tiered:
                errors.append(
                    f"{operation.key} declares neither a slab_type nor tiers"
                )
            if tiered and not material:
                errors.append(
                    f"{operation.key} is tiered but names no material; tiers "
                    "carry no layer set to take one from"
                )
            if typed and material:
                errors.append(
                    f"{operation.key} names both a slab_type and a material; "
                    "a layered slab takes its materials from its layers"
                )
        return errors

    def _covering_errors(self) -> list[str]:
        """Validate room flooring and the separate patches through openings.

        A room covering has exactly one source of plan geometry: its space.
        An opening only selects which adjacent room owns its threshold patch;
        it never restates the finish. The geometric adjacency check remains in
        the IFC template because that is where the resolved room regions exist.
        """

        operations = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc"
        }
        errors: list[str] = []
        coverings_by_space: dict[str, list[str]] = {}

        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "covering":
                continue
            space_key = operation.references["space"]
            material_key = operation.references["material"]
            coverings_by_space.setdefault(space_key, []).append(operation.key)
            space_operation = operations.get(space_key)
            material_operation = operations.get(material_key)
            if space_operation is not None and space_operation.kind != "space":
                errors.append(
                    f"{operation.key} space must be a space: "
                    f"{space_key} is {space_operation.kind}"
                )
            if (
                material_operation is not None
                and material_operation.kind != "material"
            ):
                errors.append(
                    f"{operation.key} material must be a material: "
                    f"{material_key} is {material_operation.kind}"
                )

        for space_key, covering_keys in coverings_by_space.items():
            if len(covering_keys) > 1:
                errors.append(
                    f"space {space_key} has more than one main flooring "
                    f"covering: {', '.join(covering_keys)}"
                )

        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind not in {
                "window",
                "door",
                "virtual-element",
            }:
                continue
            space_key = operation.references.get("threshold_space")
            if space_key is None:
                continue
            opening_type = operations.get(operation.references.get("window_type"))
            if opening_type is not None and opening_type.parameters.get("assembly"):
                errors.append(
                    f"{operation.key}: lift-slide windows do not support threshold_space; "
                    "the full-wall flooring patch would overlap the track. "
                    "Resolve interior/exterior finishes against the actual assembly footprint."
                )
                continue
            generated_key = f"{operation.key}.threshold-flooring"
            if generated_key in operations:
                errors.append(
                    f"{operation.key} generates threshold key {generated_key}, "
                    "but that IFC key is already declared"
                )
            space_operation = operations.get(space_key)
            if space_operation is not None and space_operation.kind != "space":
                errors.append(
                    f"{operation.key} threshold_space must be a space: "
                    f"{space_key} is {space_operation.kind}"
                )
                continue
            if space_operation is None:
                continue  # unresolved-reference validation already reports it
            if len(coverings_by_space.get(space_key, [])) != 1:
                errors.append(
                    f"{operation.key} threshold_space {space_key} must have "
                    "exactly one main flooring covering"
                )

            if operation.kind == "virtual-element":
                source_storey = operation.references["storey"]
                floor_offset = space_operation.parameters["base_offset"]
            else:
                wall_operation = operations.get(operation.references["wall"])
                if wall_operation is None or wall_operation.kind != "wall":
                    continue
                source_storey = wall_operation.references["storey"]
                opening_offset = (
                    operation.parameters["sill_height"]
                    if operation.kind == "window"
                    else operation.parameters["base_offset"]
                )
                floor_offset = (
                    wall_operation.parameters["base_offset"] + opening_offset
                )

            space_storey = space_operation.references["storey"]
            if source_storey != space_storey:
                errors.append(
                    f"{operation.key} threshold_space {space_key} is on "
                    f"{space_storey}, not opening storey {source_storey}"
                )
            if abs(floor_offset - space_operation.parameters["base_offset"]) > 1e-9:
                errors.append(
                    f"{operation.key} names threshold_space {space_key} but "
                    "is not floor-level at that space's datum"
                )

        return errors

    def _gutter_errors(self) -> list[str]:
        """Check gutters against their roof, and downspouts against their run.

        A downspout's `along` is checked against the run it drops from, which
        needs the overhang polygon the compiler solves - so the run length is
        solved here too rather than deferred, on the same principle every
        other check follows: refuse by name before execution, never emit
        something that only fails inside a shape builder.
        """

        from . import polygons

        errors: list[str] = []
        roofs = {
            operation.key: operation
            for operation in self._operations
            if operation.phase == "ifc" and operation.kind == "roof"
        }

        run_lengths: dict[str, float] = {}
        claimed: dict[tuple[str, int], str] = {}
        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "gutter":
                continue
            roof_key = operation.references["roof"]
            if roof_key not in roofs:
                # The unresolved-reference check already names this one.
                continue
            corners = len(roofs[roof_key].parameters["boundary"])
            index = operation.parameters["edge"]
            if not 0 <= index < corners:
                errors.append(
                    f"{operation.key} hangs on edge {index}, but "
                    f"{roof_key}'s boundary has {corners} edges"
                )
                continue
            previous = claimed.get((roof_key, index))
            if previous is not None:
                errors.append(
                    f"{operation.key} and {previous} both hang on "
                    f"{roof_key} edge {index}"
                )
            claimed[(roof_key, index)] = operation.key
            overhang = polygons.offset_polygon(
                [
                    (edge["start"], edge["end"], edge["overhang"])
                    for edge in self.roof_edges(roof_key)
                ]
            )
            start = overhang[index]
            end = overhang[(index + 1) % len(overhang)]
            run_lengths[operation.key] = math.hypot(
                end[0] - start[0], end[1] - start[1]
            )

        for operation in self._operations:
            if operation.phase != "ifc" or operation.kind != "downspout":
                continue
            gutter_key = operation.references["gutter"]
            length = run_lengths.get(gutter_key)
            if length is None:
                continue
            along = operation.parameters["along"]
            if not 0.0 <= along <= length:
                errors.append(
                    f"{operation.key} drops {along} m along {gutter_key}, "
                    f"which is {length:.3f} m long"
                )
            # Every segment of the path has to fall or stay level. `drop` and
            # `length` are non-negative by declaration and `standoff` moves
            # horizontally, so the only way to climb is a swan neck asked to
            # rise - which happens when the run has no drop to swan within.
            # An unstated drop is derived to clear the soffit and is never
            # zero, so only a stated one can be wrong this way.
            if operation.parameters["standoff"] > 0.0 and (
                operation.parameters["drop"] == 0.0
            ):
                errors.append(
                    f"{operation.key} steps back "
                    f"{operation.parameters['standoff']} m but drops nothing "
                    "first, so its swan neck would run level or climb; water "
                    "cannot flow down it"
                )
        return errors

    def roof_edges(self, key: str) -> list[dict[str, Any]]:
        """Materialise a roof's edges, applying overrides over its defaults.

        Both `validate()` and the compiler need the same resolved edge list,
        so it is derived here once rather than duplicated.
        """

        roof_operation = next(
            operation
            for operation in self._operations
            if operation.phase == "ifc"
            and operation.kind == "roof"
            and operation.key == key
        )
        parameters = roof_operation.parameters
        overrides = {
            operation.parameters["index"]: operation.parameters
            for operation in self._operations
            if operation.phase == "ifc"
            and operation.kind == "roof-edge"
            and operation.references.get("roof") == key
        }

        edges = []
        boundary = parameters["boundary"]
        for index in range(len(boundary)):
            override = overrides.get(index, {})
            edges.append(
                {
                    "index": index,
                    "start": boundary[index],
                    "end": boundary[(index + 1) % len(boundary)],
                    "defines_slope": override.get("defines_slope", True),
                    "angle": override.get("angle", parameters["angle"]),
                    "overhang": override.get(
                        "overhang", parameters["overhang"]
                    ),
                }
            )
        return edges

    def _override_indices(self, key: str) -> list[int]:
        """Every edge index a `roof_edge()` call targeted on this roof."""

        return [
            operation.parameters["index"]
            for operation in self._operations
            if operation.phase == "ifc"
            and operation.kind == "roof-edge"
            and operation.references.get("roof") == key
        ]

    def ifc_source(self) -> str:
        """Compile the IFC phase into one Bonsai MCP execution batch."""

        self.validate()
        from .compiler import compile_ifc

        return compile_ifc(self)

    def blender_source(self) -> str:
        """Compile presentation operations for post-reload Blender execution."""

        self.validate()
        from .compiler import compile_blender

        return compile_blender(self)

    def _append(
        self,
        phase: str,
        kind: str,
        key: str,
        references: Mapping[str, str] | None,
        parameters: Mapping[str, Any],
    ) -> None:
        normalized_references = {
            values.identifier("reference role", role): values.identifier(
                f"{role} reference", reference
            )
            for role, reference in (references or {}).items()
        }
        self._operations.append(
            Operation(
                phase=phase,
                kind=kind,
                key=values.identifier("operation key", key),
                references=normalized_references,
                parameters=dict(parameters),
            )
        )


def project(
    model: Building,
    key: str,
    *,
    name: str | None = None,
    units: str = "m",
) -> str:
    """Declare the IFC project root."""

    if units != "m":
        raise AuthoringError("the executable prototype currently supports metres")
    return model.add_ifc("project", key, name=name or key, units=units)


def site(
    model: Building,
    key: str,
    *,
    project: str,
    name: str | None = None,
) -> str:
    """Declare a site in a project."""

    return model.add_ifc(
        "site",
        key,
        references={"project": project},
        name=name or key,
    )


def building(
    model: Building,
    key: str,
    *,
    site: str,
    name: str | None = None,
) -> str:
    """Declare a building on a site."""

    return model.add_ifc(
        "building",
        key,
        references={"site": site},
        name=name or key,
    )


def storey(
    model: Building,
    key: str,
    *,
    building: str,
    elevation: float,
    name: str | None = None,
) -> str:
    """Declare a building storey."""

    return model.add_ifc(
        "storey",
        key,
        references={"building": building},
        name=name or key,
        elevation=values.number("storey elevation", elevation),
    )


def material(
    model: Building,
    key: str,
    *,
    ifc_name: str,
    category: str,
    base_color: tuple[float, float, float],
    roughness: float,
    metallic: float = 0.0,
    alpha: float = 1.0,
    ior: float = 1.5,
    double_sided: bool = True,
    material_recipe: str | None = None,
) -> str:
    """Declare one IFC material and its Blender PBR presentation.

    ``base_color`` is linear RGB; opacity is carried by ``alpha`` alone,
    which drives both the IFC surface style's Transparency and the
    Principled BSDF's Alpha input. An ``alpha`` below one also switches
    the Blender material to alpha blending. ``double_sided=False`` enables
    deterministic backface culling and a single-sided glTF material for closed
    solids. ``material_recipe`` optionally points to the sole
    repository-relative, renderer-neutral recipe an agent must translate into
    the requested target after compilation. The compiler deliberately keeps a
    simplified scalar fallback and ships no target port.
    """

    color = values.rgb(base_color)
    roughness = values.unit_interval("roughness", roughness)
    metallic = values.unit_interval("metallic", metallic)
    alpha = values.unit_interval("alpha", alpha)
    ior = values.positive("ior", ior)
    if not isinstance(double_sided, bool):
        raise AuthoringError("double_sided must be a boolean")
    if material_recipe is not None:
        if not isinstance(material_recipe, str) or not material_recipe:
            raise AuthoringError("material_recipe must be a non-empty path")
        if (
            "\\" in material_recipe
            or ":" in material_recipe
            or material_recipe.startswith("/")
            or any(
                part in {"", ".", ".."}
                for part in material_recipe.split("/")
            )
            or not material_recipe.startswith("references/material-recipes/")
            or not material_recipe.endswith(".material.md")
        ):
            raise AuthoringError(
                "material_recipe must name a repository-relative "
                "references/material-recipes/*.material.md file"
            )
        recipe_path = Path(__file__).resolve().parents[2] / material_recipe
        if not recipe_path.is_file():
            raise AuthoringError(f"material_recipe does not exist: {material_recipe}")
    model.add_ifc(
        "material",
        key,
        ifc_name=ifc_name,
        category=category,
        base_color=color,
        alpha=alpha,
    )
    presentation = {
        "ifc_name": ifc_name,
        "base_color": color,
        "roughness": roughness,
        "metallic": metallic,
        "alpha": alpha,
        "ior": ior,
        "double_sided": double_sided,
    }
    if material_recipe is not None:
        presentation["material_recipe"] = material_recipe
    model.add_presentation(
        "pbr-material",
        f"{key}.pbr",
        target=key,
        **presentation,
    )
    return key


def layer(
    material: str,
    thickness: float,
    *,
    priority: int,
    category: str | None = None,
    name: str | None = None,
    is_ventilated: bool | None = None,
) -> dict[str, Any]:
    """One `IfcMaterialLayer` of a wall type's layer set.

    `priority` is IFC's normalised [0, 100] integer, and it is what resolves a
    corner: the higher-priority layer runs through, the lower one stops
    against it. It is required rather than defaulted because a layer set
    without priorities produces corners that merely look plausible.

    `category` carries IFC's recommended keywords - "LoadBearing",
    "Insulation", "Inner finish", "Outer finish" - but is not restricted to
    them, because IFC lets a model view definition add its own.
    """

    return {
        "material": values.identifier("layer material", material),
        "thickness": values.positive("layer thickness", thickness),
        "priority": values.priority("layer priority", priority),
        "category": category,
        "name": name,
        "is_ventilated": is_ventilated,
    }


def wall_type(
    model: Building,
    key: str,
    *,
    layers: list[dict[str, Any]],
    predefined_type: str = "NOTDEFINED",
    name: str | None = None,
) -> str:
    """Declare an `IfcWallType` and the `IfcMaterialLayerSet` it carries.

    Every wall references a type. IFC puts the layer set on the type and the
    usage on the occurrence, so thickness is the sum of the layers and is
    never stated twice.
    """

    if not isinstance(layers, (list, tuple)) or not layers:
        raise AuthoringError(f"{key} must declare at least one layer")
    resolved = [dict(entry) for entry in layers]
    references = {
        f"layer.{index}.material": entry["material"]
        for index, entry in enumerate(resolved)
    }
    return model.add_ifc(
        "wall-type",
        key,
        references=references,
        name=name or key,
        layers=resolved,
        predefined_type=values.enumeration(
            "wall predefined_type", predefined_type, values.WALL_TYPES
        ),
    )


def wall(
    model: Building,
    key: str,
    *,
    storey: str,
    wall_type: str,
    axis: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    direction_sense: str = "POSITIVE",
    offset_from_reference_line: float | None = None,
    base_offset: float = 0.0,
    name: str | None = None,
) -> str:
    """Declare a straight IFC wall along its reference line.

    `axis` is the reference line, which becomes the wall's `Axis`
    representation. The layer set is then placed against it exactly as
    `IfcMaterialLayerSetUsage` defines: `offset_from_reference_line` shifts the
    layer set base off the reference line, and `direction_sense` says which way
    the layers stack from there, in declaration order.

    Left at its default, `offset_from_reference_line` centres the wall on its
    reference line. Naming a value instead is how a reference line becomes a
    face rather than a centre, which is what a structural grid usually wants.
    """

    start, end = values.axis(axis)
    return model.add_ifc(
        "wall",
        key,
        references={"storey": storey, "wall_type": wall_type},
        name=name or key,
        axis=(start, end),
        height=values.positive("wall height", height),
        direction_sense=values.enumeration(
            "wall direction_sense", direction_sense, values.DIRECTION_SENSE
        ),
        offset_from_reference_line=(
            None
            if offset_from_reference_line is None
            else values.number(
                "wall offset_from_reference_line", offset_from_reference_line
            )
        ),
        base_offset=values.number("wall base_offset", base_offset),
    )


def extend_to_structure(
    model: Building,
    key: str,
    *,
    relating_element: str,
    related_element: str,
    termination: str = "UNDERSIDE",
) -> str:
    """Extend a wall to one bounding surface of the element above it.

    The names follow ``IfcRelConnectsElements``: the structure above is the
    ``RelatingElement`` and the wall being extended is the ``RelatedElement``.
    ``UNDERSIDE`` is the ordinary partition condition. ``TOP_SURFACE`` lets a
    gable wall occupy the roof's structural depth and stop immediately below
    its separate covering.

    Compilation records ``Pset_WallCommon.ExtendToStructure`` on the wall,
    creates the relationship, and lets Bonsai produce the resolved IFC
    boolean geometry.
    """

    return model.add_ifc(
        "extend-to-structure",
        key,
        references={
            "relating_element": relating_element,
            "related_element": related_element,
        },
        termination=values.enumeration(
            "extend-to-structure termination",
            termination,
            EXTEND_TO_STRUCTURE_TERMINATIONS,
        ),
    )


def slab_type(
    model: Building,
    key: str,
    *,
    layers: list[dict[str, Any]],
    predefined_type: str = "NOTDEFINED",
    name: str | None = None,
) -> str:
    """Declare an `IfcSlabType` and the `IfcMaterialLayerSet` it carries.

    Every slab references a type, exactly as a wall does: the layer set lives
    on the type, so a slab's depth is the sum of its layers rather than a
    second, disagreeable number on the occurrence.
    """

    if not isinstance(layers, (list, tuple)) or not layers:
        raise AuthoringError(f"{key} must declare at least one layer")
    resolved = [dict(entry) for entry in layers]
    references = {
        f"layer.{index}.material": entry["material"]
        for index, entry in enumerate(resolved)
    }
    return model.add_ifc(
        "slab-type",
        key,
        references=references,
        name=name or key,
        layers=resolved,
        predefined_type=values.enumeration(
            "slab predefined_type", predefined_type, values.SLAB_TYPES
        ),
    )


def slab(
    model: Building,
    key: str,
    *,
    storey: str,
    slab_type: str | None = None,
    boundary: list[tuple[float, float]] | None = None,
    tiers: list[tuple[list[tuple[float, float]], float]] | None = None,
    material: str | None = None,
    predefined_type: str | None = None,
    base_offset: float = 0.0,
    name: str | None = None,
) -> str:
    """Declare a horizontal IFC slab, either layered or tiered.

    **Layered** - `slab_type` plus one `boundary`. The type carries an
    `IfcMaterialLayerSet` and every layer shares the boundary, because that
    is what a layer set means: one profile, sliced through its thickness.
    This is the ordinary floor, and what a ground slab or a balcony wants.

    **Tiered** - `material` plus `tiers`, each a `(boundary, height)` pair,
    stacked bottom-up from `base_offset`. Every footprint is stated; nothing
    is offset, inferred, or mirrored. A terrace whose deck steps down to a
    garden is two tiers, and three steps are three.

    The two are mutually exclusive, and the reason is not style. Tiers have
    **different profiles**, so they cannot be a layer set - and layers of one
    material would be that material written once per tier, carrying nothing
    but a thickness that belongs with the boundary it applies to. So a tiered
    slab takes a single `material` and associates it directly, the way an
    `extrusion()` does.

    Either way this is one `IfcSlab`. A tiered one carries several
    `IfcExtrudedAreaSolid`s in a single body rather than several elements.

    `base_offset` is where the stack starts, so a slab whose top should sit
    flush with its storey declares it as the negative of the total - the
    layer sum, or the tier sum.
    """

    references = {"storey": storey}
    if slab_type is not None:
        references["slab_type"] = slab_type
    if material is not None:
        references["material"] = material

    if tiers is None:
        if boundary is None:
            raise AuthoringError(f"{key} needs a boundary, or tiers")
        resolved_tiers = None
        resolved_boundary = values.boundary(boundary)
    else:
        if boundary is not None:
            raise AuthoringError(
                f"{key} declares both a boundary and tiers; a tiered slab "
                "states every footprint in its tiers"
            )
        if not isinstance(tiers, (list, tuple)) or not tiers:
            raise AuthoringError(f"{key} needs at least one tier")
        resolved_boundary = None
        resolved_tiers = [
            [
                values.boundary(pair[0]),
                values.positive(f"{key} tier {index} height", pair[1]),
            ]
            for index, pair in enumerate(_tier_pairs(key, tiers))
        ]

    return model.add_ifc(
        "slab",
        key,
        references=references,
        name=name or key,
        boundary=resolved_boundary,
        tiers=resolved_tiers,
        predefined_type=(
            None
            if predefined_type is None
            else values.enumeration(
                "slab predefined_type", predefined_type, values.SLAB_TYPES
            )
        ),
        base_offset=values.number("slab base_offset", base_offset),
    )


def _tier_pairs(key: str, tiers) -> list[tuple[Any, float]]:
    """Check each tier is a `(boundary, height)` pair before reading it."""

    pairs = []
    for index, pair in enumerate(tiers):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise AuthoringError(
                f"{key} tier {index} must be a (boundary, height) pair"
            )
        pairs.append(pair)
    return pairs


def roof(
    model: Building,
    key: str,
    *,
    storey: str,
    boundary: list[tuple[float, float]],
    angle: float,
    thickness: float,
    top_material: str,
    ceiling_material: str,
    side_material: str,
    base_offset: float = 0.0,
    overhang: float = 0.0,
    rafter_edge_angle: float = 90.0,
    covering: str | None = None,
    covering_material: str | None = None,
    covering_stagger: float | None = None,
    covering_cap: str | None = None,
    verge_trim: str | None = None,
    verge_trim_material: str | None = None,
    verge_trim_height: float | None = None,
    verge_trim_thickness: float | None = None,
    verge_trim_upstand: float | None = None,
    name: str | None = None,
) -> str:
    """Declare a roof from its base boundary, as a roof tool would.

    The boundary is a closed footprint given as corners. Every edge slopes at
    ``angle`` and projects ``overhang`` outward unless `roof_edge()` overrides
    it. ``base_offset`` lifts the footprint above its storey, ``thickness`` is
    the roof buildup measured perpendicular to the slope, and
    ``rafter_edge_angle`` is the angle the eave is cut at.

    Passing ``covering`` also declares the tile field as a presentation
    operation: tiles are laid out per roof face, merged into one mesh, and
    cropped to the face by boolean.

    ``covering_stagger`` is the bond - the fraction of a tile width each
    course is offset from the one below. It defaults to the tile profile's
    own, which is a half; zero stacks the courses in the same columns.

    ``covering_cap`` overrides which ridge and hip cap the covering wears. It
    defaults to the tile profile's own, because a ridge tile is catalogued to
    the tile it caps. **Which** edges are capped is never stated, the same way
    a verge's are not: a cap goes wherever two roof faces fold away from each
    other, which the solid already says, so a shed roof grows none and a
    hipped one grows them on every hip without anyone listing them. Caps are
    presentation only and are merged into the covering's own mesh - see
    [references/caps.md](../../references/caps.md).

    ``verge_trim`` runs an upright board along the roof's raking free edges.
    **Which** edges those are is derived, not stated: a verge is where a
    sloping face meets something that is not roof surface, which is exactly
    what a gable raises, so `roof_edge(defines_slope=False)` has already said
    it. A roof with no gable takes a trim profile and grows no trims, the same
    way an eave with no neighbouring gutter stop-ends without being told to.

    ``verge_trim_height`` and ``verge_trim_thickness`` override the profile's
    catalogued section. ``verge_trim_upstand`` is how far the board's top
    stands above the roof's arris, and is best left unstated: the compiler
    derives it from the covering, so the lip reads as a lip over whatever
    relief the tile under it has. See
    [references/trims.md](../../references/trims.md).

    ``top_material``, ``ceiling_material``, and ``side_material`` are the
    three material roles of the roof body itself. They become Top, Ceiling,
    and Side shape aspects and material constituents on the one ``IfcRoof``.
    """

    corners = values.boundary(boundary)
    # Left as None rather than defaulted here: the profile owns its own
    # section, an unset override has to stay distinguishable from one stated
    # at the profile's own value, and an unset `upstand` is what lets
    # `roof_payload` derive it from the covering.
    #
    # Checked through `values` like every other number on this call, so a
    # string arrives as a named AuthoringError rather than as a TypeError
    # raised by a comparison three modules away.
    trim_overrides = {
        "height": None
        if verge_trim_height is None
        else values.positive("roof verge_trim_height", verge_trim_height),
        "thickness": None
        if verge_trim_thickness is None
        else values.positive("roof verge_trim_thickness", verge_trim_thickness),
        "upstand": None
        if verge_trim_upstand is None
        else values.non_negative("roof verge_trim_upstand", verge_trim_upstand),
    }
    # Looked up and resolved once, here, so a mis-named profile, a negative
    # dimension, or a board standing entirely above the arris all fail at
    # declaration rather than inside Blender.
    trim_profile = trims.profile(verge_trim) if verge_trim else None
    if trim_profile is not None:
        trim_profile.resolved(**trim_overrides)
    references = {
        "storey": storey,
        "top_material": top_material,
        "ceiling_material": ceiling_material,
        "side_material": side_material,
    }
    model.add_ifc(
        "roof",
        key,
        references=references,
        name=name or key,
        boundary=corners,
        angle=values.pitch("roof angle", angle),
        thickness=values.positive("roof thickness", thickness),
        base_offset=values.number("roof base offset", base_offset),
        overhang=values.non_negative("roof overhang", overhang),
        rafter_edge_angle=values.pitch(
            "roof rafter edge angle", rafter_edge_angle
        )
        if rafter_edge_angle < 90.0
        else 90.0,
        # The covering is an IfcCovering(ROOFING), so the choice belongs on
        # the IFC declaration, not only on the presentation operation.
        covering=tiles.profile(covering).key if covering else None,
        covering_material=covering_material,
        covering_stagger=(
            None
            if covering_stagger is None
            else tiles.check_stagger(covering_stagger)
        ),
        verge_trim=trim_profile.key if trim_profile else None,
        verge_trim_material=verge_trim_material,
        verge_trim_overrides=trim_overrides,
    )
    if covering is not None:
        tile = tiles.profile(covering)
        tile.validate()
        covering_references = {}
        if covering_material is not None:
            covering_references["material"] = covering_material
        # Resolved here so a mis-named cap fails at declaration rather than
        # inside Blender, the same way the verge profile does above.
        cap = caps.profile(covering_cap or tile.cap)
        cap.validate()
        # Only the profile key travels: the tile factory is the single source
        # of the tile's shape, and the runtime looks it up by name.
        model.add_presentation(
            "roof-tiles",
            f"{key}.tiles",
            target=key,
            references=covering_references,
            profile=tile.key,
            stagger=covering_stagger,
            cap=cap.key,
        )
    elif covering_cap is not None:
        raise AuthoringError(
            f"{key} declares covering_cap={covering_cap!r} but no covering; a "
            "cap closes a covering, so there is nothing for it to cap"
        )
    return key


def roof_edge(
    model: Building,
    roof: str,
    index: int,
    *,
    defines_slope: bool = True,
    angle: float | None = None,
    overhang: float | None = None,
) -> str:
    """Override one edge of a roof boundary.

    ``defines_slope=False`` makes the edge a gable: no plane rises from it and
    the ridge runs out to meet it. ``angle`` and ``overhang`` override the
    roof's defaults for this edge alone. Differing pitches between edges that
    still define slope need a weighted skeleton, which `validate()` rejects
    until one is available.
    """

    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise AuthoringError("a roof edge index must be a non-negative integer")
    parameters: dict[str, Any] = {
        "index": index,
        "defines_slope": bool(defines_slope),
    }
    if angle is not None:
        parameters["angle"] = values.pitch("roof edge angle", angle)
    if overhang is not None:
        parameters["overhang"] = values.non_negative(
            "roof edge overhang", overhang
        )
    return model.add_ifc(
        "roof-edge",
        f"{roof}.edge.{index}",
        references={"roof": roof},
        **parameters,
    )


def roof_window(
    model: Building,
    key: str,
    *,
    roof: str,
    edge: int,
    along: float,
    up_slope: float,
    width: float,
    height: float,
    profile: str = "window.standard",
    material: str | None = None,
    glazing: str | None = None,
    name: str | None = None,
) -> str:
    """Declare a roof window hosted on one face of a roof.

    The window sits on the face that rises from boundary ``edge``, ``along``
    metres from that edge's start and ``up_slope`` metres up the slope from
    the eave. Positioning against a declared edge rather than a face index
    keeps the placement stable: faces are straight-skeleton output and their
    numbering shifts whenever the boundary changes, whereas edges are
    declared.

    In IFC this becomes an `IfcWindow` with predefined type ``SKYLIGHT``
    filling an `IfcOpeningElement` that voids the roof. In the presentation it
    also cuts the tile covering and places a flashed frame over the cut.
    """

    if not isinstance(edge, int) or isinstance(edge, bool) or edge < 0:
        raise AuthoringError("a roof window edge must be a non-negative integer")
    window = roof_windows.profile(profile)
    references = {"roof": roof}
    # One material per role the procedure declares, so a frame is never
    # painted with the pane's material.
    if material is not None:
        references["material"] = material
    if glazing is not None:
        references["glazing"] = glazing
    model.add_ifc(
        "roof-window",
        key,
        references=references,
        name=name or key,
        edge=edge,
        along=values.number("roof window along", along),
        up_slope=values.positive("roof window up slope", up_slope),
        width=values.positive("roof window width", width),
        height=values.positive("roof window height", height),
        profile=window.key,
    )
    frame_references = {}
    if material is not None:
        frame_references["material"] = material
    if glazing is not None:
        frame_references["glazing"] = glazing
    model.add_presentation(
        "roof-window-frame",
        f"{key}.frame",
        target=key,
        references=frame_references,
        profile=window.key,
    )
    return key


def gutter(
    model: Building,
    key: str,
    *,
    roof: str,
    edge: int,
    profile: str = "gutter.half_round",
    nominal_size: float = 0.125,
    thickness: float | None = None,
    material: str | None = None,
    name: str | None = None,
) -> str:
    """Declare an eaves gutter along one edge of a roof's overhang.

    The run follows boundary ``edge``'s own overhang line - the mitred
    polygon `roof()` already solves - so a gutter states no coordinates of
    its own and moves with the roof it hangs on. Positioning against a
    declared edge rather than a skeleton face is the same choice
    `roof_window()` makes, for the same reason.

    Where two gutters meet at a roof corner they **mitre**, and neither is
    told the other's numbers: the mitre plane bisects the turn, so each run
    cuts at the same angle to its own axis from its own section and the two
    cuts land on one plane. An edge whose neighbour carries no gutter gets a
    stop-end instead. Both are derived, so neither is declared.

    ``nominal_size`` is EN 612's naming - the gutter's width across, 125 mm
    being the ordinary domestic half-round. ``thickness`` is the sheet, and
    defaults to the profile's own cited gauge.

    In IFC this becomes an `IfcPipeSegment` with predefined type ``GUTTER``,
    its body a real swept solid of the declared section, assigned to the
    building's ``RAINWATER`` distribution system.
    """

    if not isinstance(edge, int) or isinstance(edge, bool) or edge < 0:
        raise AuthoringError("a gutter edge must be a non-negative integer")
    resolved = gutters.profile(profile)
    references = {"roof": roof}
    if material is not None:
        references["material"] = material
    return model.add_ifc(
        "gutter",
        key,
        references=references,
        name=name or key,
        edge=edge,
        profile=resolved.key,
        nominal_size=values.positive("gutter nominal_size", nominal_size),
        thickness=values.positive(
            "gutter thickness",
            resolved.default_thickness if thickness is None else thickness,
        ),
    )


def downspout(
    model: Building,
    key: str,
    *,
    gutter: str,
    along: float,
    length: float,
    profile: str = "downspout.round",
    nominal_size: float | None = None,
    termination: str = "straight",
    shoe_length: float = gutters.SHOE_LENGTH,
    standoff: float = 0.05,
    drop: float | None = None,
    sheet_thickness: float | None = None,
    bend_radius: float = 0.0,
    material: str | None = None,
    name: str | None = None,
) -> str:
    """Declare a downspout dropping from one point along a gutter.

    A downspout references **one** thing: the gutter it hangs from. It starts
    at that gutter's own sole and falls. It knows nothing of the roof, and
    nothing of any wall - which is what makes it reliable rather than merely
    correct today: it cannot clash with a roof it never consulted, because
    the gutter it hangs from does not, and it inherits that by construction.

    ``along`` measures from the run's own start, the same vocabulary a
    window's ``along`` uses. The pipe drops ``drop`` clear of the gutter,
    swans back ``standoff`` over the same distance down, then falls the rest
    of the way.

    ``length`` is the **whole** vertical fall, from the gutter's sole to the
    end of that straight run - not the segment left over after the swan neck.
    It is the dimension that can be measured on site, so it is the one a
    script states; turning it into a segment is arithmetic, and arithmetic
    belongs in the compiler rather than in every call.

    ``termination`` finishes the pipe. ``straight`` stops it square, for a
    gully directly below. ``shoe`` adds a kicked segment throwing the water
    clear of the wall, its mouth inclined without being cut - a swept disk
    ends perpendicular to its own directrix, so a 45 degree kick arrives
    with a 45 degree mouth already on it. ``shoe_length`` is that kick.

    ``standoff`` is stated, not derived. How far back the pipe should reach
    depends on what it is fixed to, and neither this declaration nor its
    gutter knows that; deriving it from the roof's overhang would be a guess
    dressed as a default. This is `corner_reach`'s lesson again - derive what
    is derivable locally, declare what needs knowledge from outside.

    ``drop`` is the other way round, and left unstated it is derived: the pipe
    swans back **under** the roof's overhang, so it has to fall clear of the
    soffit before it turns inboard, and how far that is belongs to the gutter's
    own roof. The pipe is handed the figure rather than asked for it, so it
    still references nothing but its gutter. State it only to describe a real
    detail tighter than the derived one.

    ``profile`` names the cross section against `gutters.PIPE_PROFILES`, the
    same way a gutter names its own: ``downspout.round`` or
    ``downspout.rectangular``. ``nominal_size`` is the outside dimension
    across - a diameter for a round pipe, a width for a rectangular one -
    and defaults to the profile's own catalogued size.

    ``sheet_thickness`` is the **pipe's** own gauge, not any building
    thickness, and likewise defaults to the profile's.

    ``bend_radius`` left at zero mitres each bend at half angle, which is
    what a folded sheet elbow looks like; a positive radius sweeps a real
    filleted bend instead.

    A downspout must be able to drain: every segment of its path has to fall
    or stay level, and `validate()` refuses one that would climb, by name,
    rather than emitting a pipe that cannot carry water.

    In IFC this becomes an `IfcPipeSegment` with predefined type
    ``RIGIDSEGMENT``. A round pipe's body is one `IfcSweptDiskSolid`, bored
    by its own ``InnerRadius`` with no boolean; a rectangular one is an
    `IfcRectangleHollowProfileDef` swept along the same path. One element,
    not an assembly: the outlet that pierces the gutter sole is where the
    pipe already starts, so modelling it separately adds a product to every
    downspout in the building and says nothing the pipe does not.
    """

    references = {"gutter": gutter}
    if material is not None:
        references["material"] = material
    section = gutters.pipe_profile(profile)
    size = values.positive(
        "downspout nominal_size",
        section.default_size if nominal_size is None else nominal_size,
    )
    sheet = values.positive(
        "downspout sheet_thickness",
        section.default_thickness if sheet_thickness is None else sheet_thickness,
    )
    # Resolved here so a pipe whose walls would meet in the middle is refused
    # where it was declared, not inside a shape builder that names only the
    # product.
    section.dimensions(size, sheet)
    resolved_length = values.positive("downspout length", length)
    resolved_standoff = values.non_negative("downspout standoff", standoff)
    resolved_drop = (
        None if drop is None else values.non_negative("downspout drop", drop)
    )
    resolved_termination = values.enumeration(
        "downspout termination", termination, gutters.TERMINATIONS
    )
    resolved_shoe = values.positive("downspout shoe_length", shoe_length)
    # A stated drop is checked here, where it was declared. An unstated one is
    # the gutter's roof to resolve, so its path is only buildable at compile
    # time and `_gutter_errors` checks it there against the same rule.
    if resolved_drop is not None:
        gutters.downspout_path(
            resolved_length,
            resolved_standoff,
            resolved_drop,
            resolved_termination,
            resolved_shoe,
        )
    return model.add_ifc(
        "downspout",
        key,
        references=references,
        name=name or key,
        along=values.number("downspout along", along),
        length=resolved_length,
        profile=section.key,
        nominal_size=size,
        termination=resolved_termination,
        shoe_length=resolved_shoe,
        standoff=resolved_standoff,
        drop=resolved_drop,
        sheet_thickness=sheet,
        bend_radius=values.non_negative("downspout bend_radius", bend_radius),
    )


def window_lining(
    *,
    depth: float,
    thickness: float,
    offset: float = 0.0,
    to_panel_offset_x: float = 0.025,
    to_panel_offset_y: float = 0.025,
    mullion_thickness: float = 0.0,
    first_mullion_offset: float | None = None,
    second_mullion_offset: float | None = None,
    transom_thickness: float = 0.0,
    first_transom_offset: float | None = None,
    second_transom_offset: float | None = None,
) -> dict[str, Any]:
    """The `IfcWindowLiningProperties` a window type carries.

    The lining is the frame fixed into the wall: ``depth`` is how far it
    reaches through the wall and ``thickness`` how wide its band reads in
    elevation. ``mullion_thickness`` divides a vertically partitioned window
    and ``transom_thickness`` a horizontally partitioned one; a partitioning
    that has neither leaves both at zero.

    The four offsets are where those divisions sit, and IFC measures them as
    `IfcNormalisedRatioMeasure` - a fraction of the window, not a distance.
    That is what lets one type serve every size it is built at, so they are
    ratios here too, and the compiler turns them into the distances
    IfcOpenShell's generator wants. Left at ``None`` they divide the window
    evenly, which is what a mullion or transom does unless told otherwise.

    ``offset`` is `LiningOffset`, which shifts the lining through the wall
    from the centred position the compiler resolves. The two
    ``to_panel_offset`` values are the reveal between lining and panel, across
    the opening and through it.

    Keys are IFC attribute names because these travel unchanged into
    `IfcWindowLiningProperties` and, once resolved, into the generator.
    """

    def division(label, value):
        return None if value is None else values.ratio(label, value)

    return {
        "LiningDepth": values.positive("window lining depth", depth),
        "LiningThickness": values.positive("window lining thickness", thickness),
        "LiningOffset": values.number("window lining offset", offset),
        "LiningToPanelOffsetX": values.non_negative(
            "window lining to panel offset x", to_panel_offset_x
        ),
        "LiningToPanelOffsetY": values.non_negative(
            "window lining to panel offset y", to_panel_offset_y
        ),
        "MullionThickness": values.non_negative(
            "window mullion thickness", mullion_thickness
        ),
        "FirstMullionOffset": division(
            "window first mullion offset", first_mullion_offset
        ),
        "SecondMullionOffset": division(
            "window second mullion offset", second_mullion_offset
        ),
        "TransomThickness": values.non_negative(
            "window transom thickness", transom_thickness
        ),
        "FirstTransomOffset": division(
            "window first transom offset", first_transom_offset
        ),
        "SecondTransomOffset": division(
            "window second transom offset", second_transom_offset
        ),
    }


def window_panel(
    *,
    frame_depth: float,
    frame_thickness: float,
    operation_type: str = "NOTDEFINED",
    position: str = "NOTDEFINED",
) -> dict[str, Any]:
    """One `IfcWindowPanelProperties` of a window type: a sash.

    ``frame_depth`` and ``frame_thickness`` are the sash's own section, which
    is what makes it read as a separate part inside the lining rather than as
    a hole. ``operation_type`` says how it opens - IFC's own vocabulary, so a
    fixed light is `FIXEDCASEMENT` rather than an absent handle.
    """

    return {
        "FrameDepth": values.positive("window panel frame depth", frame_depth),
        "FrameThickness": values.positive(
            "window panel frame thickness", frame_thickness
        ),
        "OperationType": values.enumeration(
            "window panel operation_type",
            operation_type,
            values.WINDOW_PANEL_OPERATIONS,
        ),
        "PanelPosition": values.enumeration(
            "window panel position", position, values.WINDOW_PANEL_POSITIONS
        ),
    }


def door_lining(
    *,
    depth: float,
    thickness: float,
    offset: float = 0.0,
    to_panel_offset_x: float = 0.0,
    to_panel_offset_y: float = 0.0,
    casing_thickness: float | None = None,
    casing_depth: float | None = None,
    threshold_thickness: float = 0.0,
    threshold_depth: float | None = None,
    threshold_offset: float = 0.0,
    transom_thickness: float = 0.0,
    transom_offset: float = 0.0,
) -> dict[str, Any]:
    """The `IfcDoorLiningProperties` a door type carries.

    ``casing_thickness`` is the architrave lapping the wall around the lining,
    which is how a door frame covers the reveal the opening cut. A
    ``threshold`` is the sill under the leaf, and a ``transom`` the rail that
    divides a leaf from the light above it - an internal door usually has
    neither.

    The casing and threshold depths are `IfcPositiveLengthMeasure`, so a door
    that has none leaves them unset rather than zero: zero is not a length the
    schema allows, and writing it would make the property set invalid while
    still reading as "no casing".
    """

    def optional(label, value):
        return None if value is None else values.positive(label, value)

    return {
        "LiningDepth": values.positive("door lining depth", depth),
        "LiningThickness": values.positive("door lining thickness", thickness),
        "LiningOffset": values.number("door lining offset", offset),
        "LiningToPanelOffsetX": values.non_negative(
            "door lining to panel offset x", to_panel_offset_x
        ),
        "LiningToPanelOffsetY": values.non_negative(
            "door lining to panel offset y", to_panel_offset_y
        ),
        "CasingThickness": optional("door casing thickness", casing_thickness),
        "CasingDepth": optional("door casing depth", casing_depth),
        "ThresholdThickness": values.non_negative(
            "door threshold thickness", threshold_thickness
        ),
        "ThresholdDepth": optional("door threshold depth", threshold_depth),
        "ThresholdOffset": values.non_negative(
            "door threshold offset", threshold_offset
        ),
        "TransomThickness": values.non_negative(
            "door transom thickness", transom_thickness
        ),
        "TransomOffset": values.non_negative("door transom offset", transom_offset),
    }


def door_panel(
    *,
    depth: float,
    width_ratio: float = 1.0,
    frame_depth: float = 0.0,
    frame_thickness: float = 0.0,
    operation_type: str = "SWINGING",
    position: str = "NOTDEFINED",
) -> dict[str, Any]:
    """The `IfcDoorPanelProperties` a door type carries: the leaf.

    ``depth`` is the leaf's thickness. ``width_ratio`` is IFC's `PanelWidth`,
    a normalised ratio of the opening rather than a length, so one type serves
    every width the door is built at. ``frame_depth`` and ``frame_thickness``
    describe a glazed leaf's own framing and stay zero on a solid one.
    """

    return {
        "PanelDepth": values.positive("door panel depth", depth),
        "PanelWidth": values.unit_interval("door panel width ratio", width_ratio),
        "FrameDepth": values.non_negative("door panel frame depth", frame_depth),
        "FrameThickness": values.non_negative(
            "door panel frame thickness", frame_thickness
        ),
        "PanelOperation": values.enumeration(
            "door panel operation_type", operation_type, values.DOOR_PANEL_OPERATIONS
        ),
        "PanelPosition": values.enumeration(
            "door panel position", position, values.DOOR_PANEL_POSITIONS
        ),
    }


def window_type(
    model: Building,
    key: str,
    *,
    partitioning_type: str,
    lining: dict[str, Any],
    panels: list[dict[str, Any]],
    predefined_type: str = "WINDOW",
    name: str | None = None,
    assembly: dict[str, Any] | None = None,
) -> str:
    """Declare an `IfcWindowType` and the lining and panel properties it carries.

    Every window references a type. IFC puts the lining and panel geometry on
    the type as `IfcWindowLiningProperties` and `IfcWindowPanelProperties`,
    and leaves only the overall size on the occurrence - so a section is
    stated once and two windows of one type cannot drift apart.

    ``partitioning_type`` fixes how many panels the type must declare, which
    is why the panel count is checked here rather than discovered as a shape
    error later.

    ``assembly`` optionally selects the supported LIFT_SLIDE section layout.
    Its native IFC Body takes precedence over the scalar properties, which
    must still describe the same frame and panels. Use the opening pack's
    ``lift_slide_window_type()`` to derive that matching declaration. Omitting
    it retains the stock generator and Bonsai's native window parameters.
    """

    partitioning_type = values.enumeration(
        "window partitioning_type", partitioning_type, values.WINDOW_PARTITIONING
    )
    if not isinstance(panels, (list, tuple)) or not panels:
        raise AuthoringError(f"{key} must declare at least one panel")
    expected, mullions, transoms = values.WINDOW_PARTS[partitioning_type]
    if len(panels) != expected:
        raise AuthoringError(
            f"{key} is {partitioning_type}, which has {expected} panels; "
            f"{len(panels)} were declared"
        )

    resolved = dict(lining)
    extra = {}
    if assembly is not None:
        from .window_assemblies import validate_lift_slide_assembly

        if not isinstance(assembly, dict) or assembly.get("kind") != "LIFT_SLIDE":
            raise AuthoringError(f"{key} assembly kind must be LIFT_SLIDE")
        section = validate_lift_slide_assembly(
            {k: v for k, v in assembly.items() if k != "kind"}
        )
        if partitioning_type != "DOUBLE_PANEL_VERTICAL" or predefined_type != "WINDOW":
            raise AuthoringError(f"{key} lift-slide assembly requires WINDOW / DOUBLE_PANEL_VERTICAL")
        required_lining = {
            "LiningDepth": section["frame_depth"],
            "LiningThickness": section["jamb_width"],
            "LiningToPanelOffsetX": section["jamb_width"] + section["sealing_clearance"],
            # The two tracks cannot be represented by one common Y offset.
            "LiningToPanelOffsetY": None,
            "MullionThickness": 0.0, "TransomThickness": 0.0,
            "FirstMullionOffset": None, "SecondMullionOffset": None,
            "FirstTransomOffset": None, "SecondTransomOffset": None,
        }
        for attribute, expected_value in required_lining.items():
            actual = resolved.get(attribute)
            matches = (actual is None if expected_value is None else
                       isinstance(actual, (int, float)) and abs(actual - expected_value) < 1e-9)
            if not matches:
                raise AuthoringError(f"{key} {attribute} must match its lift-slide assembly ({expected_value})")
        for panel, side in zip(panels, ("LEFT", "RIGHT")):
            required_panel = {
                "FrameDepth": section["sash_depth"],
                "FrameThickness": section["sash_face_width"],
                "PanelPosition": side,
                "OperationType": "SLIDINGHORIZONTAL" if side == section["sliding_side"] else "FIXEDCASEMENT",
            }
            if any(panel.get(k) != v for k, v in required_panel.items()):
                raise AuthoringError(f"{key} {side} panel properties must match its lift-slide assembly")
        extra["assembly"] = {"kind": "LIFT_SLIDE", **section}
        # Partitioning describes the two lights, not a physical centre mullion.
        mullions = transoms = 0
    for count, thickness_name, offsets in (
        (mullions, "MullionThickness", ("FirstMullionOffset", "SecondMullionOffset")),
        (transoms, "TransomThickness", ("FirstTransomOffset", "SecondTransomOffset")),
    ):
        if count and not resolved[thickness_name]:
            raise AuthoringError(
                f"{key} is {partitioning_type}, which is divided by "
                f"{count} {thickness_name[:-9].lower()}(s); "
                f"{thickness_name} must be greater than zero"
            )
        for index, attribute in enumerate(offsets):
            if index >= count:
                # A division this partitioning does not have carries no offset.
                resolved[attribute] = None
            elif resolved[attribute] is None:
                # Divide evenly: one mullion halves the window, two make thirds.
                resolved[attribute] = (index + 1) / (count + 1)
    ordered = [
        resolved[attribute]
        for attribute in ("FirstMullionOffset", "SecondMullionOffset")
        if resolved[attribute] is not None
    ]
    if len(ordered) == 2 and ordered[0] >= ordered[1]:
        raise AuthoringError(
            f"{key} puts its second mullion at or before its first"
        )
    ordered = [
        resolved[attribute]
        for attribute in ("FirstTransomOffset", "SecondTransomOffset")
        if resolved[attribute] is not None
    ]
    if len(ordered) == 2 and ordered[0] >= ordered[1]:
        raise AuthoringError(
            f"{key} puts its second transom at or before its first"
        )

    return model.add_ifc(
        "window-type",
        key,
        name=name or key,
        predefined_type=values.enumeration(
            "window predefined_type", predefined_type, values.WINDOW_TYPES
        ),
        partitioning_type=partitioning_type,
        lining=resolved,
        panels=[dict(panel) for panel in panels],
        **extra,
    )


def composed_window_type(
    model: Building,
    key: str,
    *,
    profile_width: float,
    profile_depth: float,
    glazing_thickness: float,
    offset: float = 0.0,
    name: str | None = None,
) -> str:
    """Declare the shared section of a script-parametric composed window.

    ``profile_width`` is the visible band around a selected edge or divider;
    ``profile_depth`` is its reach through the wall. ``offset`` moves the
    section centre through the wall from the host wall centre. The glazing is
    centred within that depth and must be thinner than it.

    Unlike :func:`window_type`, this type intentionally does not pretend to
    use one of IfcOpenShell's rectangular partition schemas. It becomes an
    ``IfcWindowType`` with ``USERDEFINED`` partitioning, while the building
    script remains the authoritative composition.
    """

    width = values.positive("composed window profile width", profile_width)
    depth = values.positive("composed window profile depth", profile_depth)
    glazing = values.positive(
        "composed window glazing thickness", glazing_thickness
    )
    if glazing >= depth:
        raise AuthoringError(
            "composed window glazing thickness must be less than profile depth"
        )
    return model.add_ifc(
        "composed-window-type",
        key,
        name=name or key,
        profile_width=width,
        profile_depth=depth,
        glazing_thickness=glazing,
        offset=values.number("composed window offset", offset),
    )


def door_type(
    model: Building,
    key: str,
    *,
    operation_type: str,
    lining: dict[str, Any],
    panel: dict[str, Any],
    predefined_type: str = "DOOR",
    name: str | None = None,
) -> str:
    """Declare an `IfcDoorType` and the lining and panel properties it carries.

    ``operation_type` is `IfcDoorType.OperationType`: which way the leaf is
    hung and how it moves. It is the type's, not the occurrence's, because it
    is what distinguishes one door product from another.
    """

    return model.add_ifc(
        "door-type",
        key,
        name=name or key,
        predefined_type=values.enumeration(
            "door predefined_type", predefined_type, values.DOOR_TYPES
        ),
        operation_type=values.enumeration(
            "door operation_type", operation_type, values.DOOR_OPERATIONS
        ),
        lining=dict(lining),
        panel=dict(panel),
    )


def _opening_references(
    lining_material: str | None,
    framing_material: str | None,
    glazing_material: str | None,
) -> dict[str, str]:
    """Map declared materials onto the roles the geometry actually names.

    `Lining`, `Framing` and `Glazing` are the shape aspects IfcOpenShell's
    generators emit, so they are the constituent names IFC gets. There is no
    fourth: a door's lever is part of the framing the generator built, and a
    window has none.
    """

    found = {}
    for role, material in (
        ("lining_material", lining_material),
        ("framing_material", framing_material),
        ("glazing_material", glazing_material),
    ):
        if material is not None:
            found[role] = material
    return found


def window(
    model: Building,
    key: str,
    *,
    wall: str,
    window_type: str,
    along: float,
    sill_height: float,
    overall_width: float,
    overall_height: float,
    direction_sense: str = "POSITIVE",
    lining_material: str | None = None,
    framing_material: str | None = None,
    glazing_material: str | None = None,
    threshold_space: str | None = None,
    is_external: bool = True,
    name: str | None = None,
) -> str:
    """Declare a window hosted in a wall.

    ``along`` is the distance from the host wall's reference line start to the
    **centre** of the opening, and ``sill_height`` its height above that
    wall's base. Positioning against the declared reference line rather than
    world coordinates is what keeps a window on its wall when the wall moves.

    ``direction_sense`` is which way the window's own frame runs across the
    wall, in the same `IfcDirectionSenseEnum` a wall states its layers in.
    A window is not symmetric through the wall - its sash stands proud on one
    face and its reveal is deeper on the other - so this is which way round it
    sits. ``lining_offset`` on the type then moves the lining through the wall
    from the centred position; IFC has no way to name a layer, so a window set
    against one layer of a buildup is that offset, measured.

    In IFC this becomes an `IfcWindow` filling an `IfcOpeningElement` that
    voids the wall, typed by `IfcWindowType`. The body is IfcOpenShell's
    parametric lining and panels, whose `Lining`, `Framing` and `Glazing`
    shape aspects become the material constituents.

    A floor-level window may name ``threshold_space`` to generate a separate
    flooring patch through the wall. The patch inherits that room's main
    covering; the window never carries finish material of its own.
    """

    references = {"wall": wall, "window_type": window_type}
    if threshold_space is not None:
        references["threshold_space"] = threshold_space
    references.update(
        _opening_references(lining_material, framing_material, glazing_material)
    )
    return model.add_ifc(
        "window",
        key,
        references=references,
        name=name or key,
        along=values.number("window along", along),
        sill_height=values.non_negative("window sill height", sill_height),
        overall_width=values.positive("window overall width", overall_width),
        overall_height=values.positive("window overall height", overall_height),
        direction_sense=values.enumeration(
            "window direction_sense", direction_sense, values.DIRECTION_SENSE
        ),
        is_external=bool(is_external),
    )


def composed_window(
    model: Building,
    key: str,
    *,
    wall: str,
    window_type: str,
    along: float,
    sill_height: float,
    pieces: list[dict[str, Any]],
    dividers: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    framing_material: str | None = None,
    glazing_material: str | None = None,
    is_external: bool = True,
    name: str | None = None,
) -> str:
    """Compose one wall-hosted window from polygonal glazing pieces.

    Rectangles and triangles may share a ``pane`` name to become one pane of
    glass. Every piece independently selects which boundary edges receive a
    profile, and ``dividers`` add explicit mullions or transoms. ``along`` is
    the centre of the composition's bounding box and ``sill_height`` locates
    its lowest point above the host wall base.

    The host wall's storey supplies placement and IFC containment only. It
    never clips the window: a single composition may therefore cross a
    storey boundary or rise into a gable.
    """

    if not isinstance(pieces, (list, tuple)):
        raise AuthoringError("composed window pieces must be a sequence")
    resolved_pieces = composed_windows._validated_pieces(pieces)
    resolved_dividers = composed_windows._validated_dividers(dividers)
    # Resolve the union now so disconnected or holed compositions fail at the
    # declaration that caused them, not later inside Blender.
    composed_windows.opening_outline(resolved_pieces)

    references = {"wall": wall, "composed_window_type": window_type}
    if framing_material is not None:
        references["framing_material"] = framing_material
    if glazing_material is not None:
        references["glazing_material"] = glazing_material
    return model.add_ifc(
        "composed-window",
        key,
        references=references,
        name=name or key,
        along=values.number("composed window along", along),
        sill_height=values.non_negative(
            "composed window sill height", sill_height
        ),
        pieces=resolved_pieces,
        dividers=resolved_dividers,
        is_external=bool(is_external),
    )


def door(
    model: Building,
    key: str,
    *,
    wall: str,
    door_type: str,
    along: float,
    overall_width: float,
    overall_height: float,
    base_offset: float = 0.0,
    direction_sense: str = "POSITIVE",
    lining_material: str | None = None,
    framing_material: str | None = None,
    glazing_material: str | None = None,
    threshold_space: str | None = None,
    is_external: bool = False,
    name: str | None = None,
) -> str:
    """Declare a door hosted in a wall.

    ``along`` is the distance from the host wall's reference line start to the
    **centre** of the opening. A door sits on the wall's base, so it has no
    sill height; ``base_offset`` raises it for the rare case that it does, and
    is otherwise zero.

    A door has four states, and IFC splits them across two places. Which stile
    it is hung on is `IfcDoorType.OperationType` - `SINGLE_SWING_LEFT` against
    `SINGLE_SWING_RIGHT` - and which way it swings is the **object
    placement**, because the schema carries no attribute for it and reads the
    operation in the element's own frame. ``direction_sense`` is that
    placement, in the same `IfcDirectionSenseEnum` a wall states its layers
    in: `NEGATIVE` turns the door about its own height to face the other side
    of the wall, and the hung side named by the type is then read from there.
    The two together are the four states.

    In IFC this becomes an `IfcDoor` filling an `IfcOpeningElement` that voids
    the wall, typed by `IfcDoorType`. Its lever is part of the body
    IfcOpenShell generates, mirrored onto both faces of the leaf, so a door
    declares no hardware of its own.

    ``threshold_space`` selects the one adjacent room that owns the separate
    flooring patch through a floor-level doorway. Its material, thickness and
    elevation come from that room's main ``covering()`` declaration.
    """

    references = {"wall": wall, "door_type": door_type}
    if threshold_space is not None:
        references["threshold_space"] = threshold_space
    references.update(
        _opening_references(lining_material, framing_material, glazing_material)
    )
    return model.add_ifc(
        "door",
        key,
        references=references,
        name=name or key,
        along=values.number("door along", along),
        base_offset=values.non_negative("door base offset", base_offset),
        overall_width=values.positive("door overall width", overall_width),
        overall_height=values.positive("door overall height", overall_height),
        direction_sense=values.enumeration(
            "door direction_sense", direction_sense, values.DIRECTION_SENSE
        ),
        is_external=bool(is_external),
    )


def window_sill(
    model: Building,
    key: str,
    *,
    window: str,
    horn: float = 0.05,
    projection: float = 0.04,
    thickness: float = 0.03,
    corner: str | None = None,
    corner_reach: float = 0.0,
    material: str | None = None,
    name: str | None = None,
) -> str:
    """Declare a projecting sill under a window's opening.

    `horn` is how far the slab reaches beyond the opening on each side, and
    `projection` how far it reaches beyond the wall's own face on each side -
    the two things that make a sill read as a sill rather than as the
    opening's own reveal. It sits at the window's sill line and spans the
    wall's full thickness rather than the window's own, usually narrower,
    lining depth: a sill sheds water off the wall, not off the frame.

    A corner window's two sills each stop `horn` short of the corner they
    share, which leaves a real unfilled square exactly where they should
    meet. `corner` names which end of this sill (`"start"` or `"end"`, the
    same vocabulary `along` measures from) faces that corner, and
    `corner_reach` how far it is mitred there - positive or negative,
    since which physical side of the wall is which is `sills.py`'s own local
    frame, not something either declaration is told. Declared on the sill
    around the corner with the reach that closes its own half the same way,
    the two sills' mitres - each a trapezoid, the near corner pushed out and
    the far one shrunk back by its own depth - meet exactly on the diagonal
    between them; see `sills.standard_sill_mesh` for why that is always true
    regardless of either sill's own reach.

    IFC has no entity for a sill. The closest fit is `IfcBuildingElementPart`
    - a functional part of a larger element, `PredefinedType` `USERDEFINED`
    since none of the enumeration's few values name one - aggregated onto the
    window it serves with `IfcRelAggregates` rather than stood beside it as
    its own occurrence. That is also why it takes no `along` or `sill_height`
    of its own: both already live on the window, and an aggregate's placement
    is solved relative to its parent's, not restated against the wall.
    """

    if corner is not None and corner not in ("start", "end"):
        raise AuthoringError(
            f"window sill corner must be 'start', 'end', or left unset; "
            f"got {corner!r}"
        )
    if corner_reach != 0.0 and corner is None:
        raise AuthoringError("window sill corner_reach needs a corner to mitre")

    references = {"window": window}
    if material is not None:
        references["material"] = material
    return model.add_ifc(
        "window-sill",
        key,
        references=references,
        name=name or key,
        horn=values.non_negative("window sill horn", horn),
        projection=values.non_negative("window sill projection", projection),
        thickness=values.positive("window sill thickness", thickness),
        corner=corner,
        corner_reach=values.number("window sill corner_reach", corner_reach),
    )


def corner_opening(
    model: Building,
    key: str,
    *,
    walls: tuple[str, str],
    base: float,
    height: float,
    reach: float = 0.05,
    name: str | None = None,
) -> str:
    """Declare one corner cut, emitted as an opening for each of two walls.

    A wall corner window's own openings each void only their own host, so
    each one only ever removes material up to its own wall's endpoint - the
    solid the two walls still mitre between themselves there, `junctions.py`
    resolving it the ordinary way any two coincident endpoints do, is never
    touched by either. Reaching one opening past its own wall's endpoint to
    try to clear it anyway means guessing how far the mitre actually
    extended; wrong by too little leaves a sliver, wrong by too much cuts
    into wall that was never meant to move.

    IFC4's `IfcOpeningElement.VoidsElements` inverse names one relationship,
    so each wall receives its own opening occurrence. Both share the same
    cutter geometry, sized from the walls' declared thickness rather than
    estimated. That size is exact regardless of how the mitre actually
    shaped itself, because it is bounded by what either wall could
    ever contain there - its own thickness through itself, the other wall's
    thickness along it - not by the mitre's own geometry.

    `base` and `height` are the same vertical span the two windows meeting
    at that corner already state, measured the same way `sill_height` is:
    from the wall's own base. Neither wall is touched; both keep the axis,
    length and corner mitre they were declared with.
    """

    if len(walls) != 2:
        raise AuthoringError("a corner opening names exactly two walls")
    return model.add_ifc(
        "corner-opening",
        key,
        references={"wall.0": walls[0], "wall.1": walls[1]},
        name=name or key,
        base=values.number("corner opening base", base),
        height=values.positive("corner opening height", height),
        reach=values.non_negative("corner opening reach", reach),
    )


def virtual_element(
    model: Building,
    key: str,
    *,
    storey: str,
    axis: tuple[tuple[float, float], tuple[float, float]],
    threshold_space: str | None = None,
    name: str | None = None,
) -> str:
    """Declare an `IfcVirtualElement` along a reference line.

    IFC's own answer to a boundary with no physical presence - a corridor
    that merely opens into a room, an imaginary lot line - is not a wall with
    no material, it is its own entity: no layers, no body, no quantities.
    Declared the same way a wall's reference line is, so it joins a wall's
    axis wherever the two share an endpoint and can close a space loop
    exactly like one, without the model mistaking it for something built.

    When the whole virtual run is a floor-level opening, ``threshold_space``
    selects the adjacent room whose main covering its separate patch inherits.
    """

    start, end = values.axis(axis)
    references = {"storey": storey}
    if threshold_space is not None:
        references["threshold_space"] = threshold_space
    return model.add_ifc(
        "virtual-element",
        key,
        references=references,
        name=name or key,
        axis=(start, end),
    )


def space(
    model: Building,
    key: str,
    *,
    storey: str,
    at: tuple[float, float],
    height: float,
    predefined_type: str = "SPACE",
    base_offset: float = 0.0,
    name: str | None = None,
) -> str:
    """Declare an `IfcSpace` by an interior point, not a boundary.

    A room's true shape depends on how its walls resolve their corners, which
    only exists once IfcOpenShell has regenerated them - the same reason a
    wall's own corners are derived rather than declared. `at` names a point
    inside the intended room instead: compilation encloses every wall and
    `virtual_element()` on `storey` into regions and assigns this space the
    one region containing `at`, the way Bonsai's own space tool resolves a
    point into a room. A space that moves its walls keeps its key and its
    point; only the resolved shape changes.
    """

    return model.add_ifc(
        "space",
        key,
        references={"storey": storey},
        name=name or key,
        at=values.point2("space at", at),
        height=values.positive("space height", height),
        predefined_type=values.enumeration(
            "space predefined_type", predefined_type, values.SPACE_TYPES
        ),
        base_offset=values.number("space base_offset", base_offset),
    )


def covering(
    model: Building,
    key: str,
    *,
    space: str,
    material: str,
    thickness: float,
    name: str | None = None,
) -> str:
    """Declare one room's `IfcCovering` floor finish.

    The covering has no authorable plan boundary or elevation. Compilation
    gives it the resolved footprint of ``space`` exactly and places its top at
    that space's base datum. A floor-level opening that names this space with
    ``threshold_space`` receives a second, opening-sized covering occurrence
    carrying the same material and thickness.
    """

    return model.add_ifc(
        "covering",
        key,
        references={"space": space, "material": material},
        name=name or key,
        thickness=values.positive("covering thickness", thickness),
        predefined_type="FLOORING",
    )


def _declare_railing(
    model: Building,
    key: str,
    *,
    storey: str,
    path: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    profile: str = "guardrail.steel",
    predefined_type: str = "GUARDRAIL",
    object_type: str | None = None,
    start_post: bool = True,
    end_post: bool = True,
    base_offset: float = 0.0,
    post_material: str | None = None,
    rail_material: str | None = None,
    infill_material: str | None = None,
    shoe_material: str | None = None,
    glazing_material: str | None = None,
    name: str | None = None,
    fence_declaration: bool,
) -> str:
    """Record the common IFC railing shape used by guards and fences.

    `path` is a reference line exactly as a wall's `axis` is - a straight run,
    not a face - so a guarded perimeter with a corner is two declarations, the
    same way a wall with a corner is two walls. Neither mitres the other's
    end; each run's own posts, infill, or panel stop where it does.

    `profile` names a real, cited design against `railings.PROFILES` - a
    steel tube-and-cable guard, a timber post-and-rail guard, or a frameless
    glass balustrade - the same way `roof_window()` names a window design
    against `roof_windows.PROFILES`. A profile owns its own proportions; nothing
    here overrides them; only `height` and which run to guard are a script's
    to set. External boundary fences use the narrower `fences.fence()` helper,
    which supplies IFC4's required user-defined classification.

    In IFC this becomes one `IfcRailing`, its body built from whichever parts
    the chosen profile names - `Post`, `Rail` and `Infill` for a guardrail;
    `Shoe` and `Glazing` for a balustrade; or `Post` and `Infill` for a fence -
    each its own shape aspect, the same way a window's lining and glazing are,
    so the one product can carry every material its design actually has.
    """

    start, end = values.axis(path, "railing path")
    resolved = railings.profile(profile)
    if not isinstance(start_post, bool) or not isinstance(end_post, bool):
        raise AuthoringError("railing endpoint-post flags must be booleans")
    references = {"storey": storey}
    for role, material_key in (
        ("post_material", post_material),
        ("rail_material", rail_material),
        ("infill_material", infill_material),
        ("shoe_material", shoe_material),
        ("glazing_material", glazing_material),
    ):
        if material_key is not None:
            references[role] = material_key
    resolved_predefined_type = values.enumeration(
        "railing predefined_type", predefined_type, values.RAILING_TYPES
    )
    if resolved_predefined_type == "USERDEFINED":
        if not isinstance(object_type, str) or not object_type.strip():
            raise AuthoringError(
                "a USERDEFINED railing needs a non-empty object_type"
            )
        resolved_object_type = object_type.strip()
    elif object_type is not None:
        raise AuthoringError(
            "railing object_type is only valid with predefined_type USERDEFINED"
        )
    else:
        resolved_object_type = None

    is_fence_profile = resolved.key.startswith("fence.")
    is_fence_classification = (
        resolved_predefined_type == "USERDEFINED"
        and resolved_object_type is not None
        and resolved_object_type.casefold() == "fence"
    )
    if not fence_declaration and is_fence_profile:
        raise AuthoringError(
            f"{resolved.key} must be declared through fence(), not as a guardrail"
        )
    if not fence_declaration and is_fence_classification:
        raise AuthoringError(
            "ObjectType Fence needs a fence profile from fence()"
        )
    if fence_declaration and not (
        is_fence_profile and is_fence_classification
    ):
        raise AuthoringError(
            "internal fence declarations need a fence profile and classification"
        )
    if not is_fence_profile and (not start_post or not end_post):
        raise AuthoringError(
            "endpoint posts may only be suppressed on a fence profile"
        )

    resolved_height = values.positive("railing height", height)
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    # Fence profiles validate only their dimensions here; their potentially
    # dense wire body is built once, in the IFC phase. Small guard profiles
    # still exercise their complete procedure before an operation is stored.
    resolved.check(length, resolved_height)

    return model.add_ifc(
        "railing",
        key,
        references=references,
        name=name or key,
        path=(start, end),
        height=resolved_height,
        profile=resolved.key,
        predefined_type=resolved_predefined_type,
        object_type=resolved_object_type,
        start_post=start_post,
        end_post=end_post,
        base_offset=values.number("railing base_offset", base_offset),
    )


def railing(
    model: Building,
    key: str,
    *,
    storey: str,
    path: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    profile: str = "guardrail.steel",
    predefined_type: str = "GUARDRAIL",
    object_type: str | None = None,
    start_post: bool = True,
    end_post: bool = True,
    base_offset: float = 0.0,
    post_material: str | None = None,
    rail_material: str | None = None,
    infill_material: str | None = None,
    shoe_material: str | None = None,
    glazing_material: str | None = None,
    name: str | None = None,
) -> str:
    """Declare a guarding `IfcRailing` along one straight run.

    ``profile`` accepts the guardrail and balustrade designs in
    :mod:`building_author.railings`. Boundary fence profiles are intentionally
    rejected here; use :func:`building_author.fence`, which owns their IFC4
    ``USERDEFINED`` / ``Fence`` classification and shared-post rules.
    """

    return _declare_railing(
        model,
        key,
        storey=storey,
        path=path,
        height=height,
        profile=profile,
        predefined_type=predefined_type,
        object_type=object_type,
        start_post=start_post,
        end_post=end_post,
        base_offset=base_offset,
        post_material=post_material,
        rail_material=rail_material,
        infill_material=infill_material,
        shoe_material=shoe_material,
        glazing_material=glazing_material,
        name=name,
        fence_declaration=False,
    )


def _fence_railing(
    model: Building,
    key: str,
    *,
    storey: str,
    path: tuple[tuple[float, float], tuple[float, float]],
    height: float,
    profile: str,
    base_offset: float,
    material: str | None,
    start_post: bool,
    end_post: bool,
    name: str | None,
) -> str:
    """Record a fence after the public fence helper has validated its API."""

    return _declare_railing(
        model,
        key,
        storey=storey,
        path=path,
        height=height,
        profile=profile,
        predefined_type="USERDEFINED",
        object_type="Fence",
        start_post=start_post,
        end_post=end_post,
        base_offset=base_offset,
        post_material=material,
        infill_material=material,
        name=name,
        fence_declaration=True,
    )


def extrusion(
    model: Building,
    key: str,
    *,
    ifc_class: str,
    storey: str,
    position: tuple[float, float, float],
    size: tuple[float, float],
    height: float,
    material: str | None = None,
    name: str | None = None,
) -> str:
    """Declare a rectangular IFC extrusion for reusable component functions."""

    ifc_class = values.ifc_class(ifc_class)
    references = {"storey": storey}
    if material is not None:
        references["material"] = material
    width, depth = size
    return model.add_ifc(
        "extrusion",
        key,
        references=references,
        name=name or key,
        ifc_class=ifc_class,
        position=values.point3("extrusion position", position),
        size=(
            values.positive("extrusion width", width),
            values.positive("extrusion depth", depth),
        ),
        height=values.positive("extrusion height", height),
    )
