"""Reusable window and door types and composed opening declarations.

Each preset defines an IFC opening type with a reusable section. For a
custom section, declare the lining and panels directly with
`window_lining()` and `window_panel()`.

The occurrence helpers compose the core declarations without adding
compiler operations.
"""

from __future__ import annotations

from .author import (
    Building,
    corner_opening,
    door_lining,
    door_panel,
    door_type,
    window,
    window_lining,
    window_panel,
    window_type,
)
from .values import AuthoringError


def sliding_window(
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
    is_external: bool = True,
    threshold_space: str | None = None,
    name: str | None = None,
) -> str:
    """Declare sliding glazing explicitly as a window, never as a door.

    This is a semantic wrapper around :func:`window`; it forwards the complete
    occurrence unchanged and therefore still emits the core ``window``
    operation and an ``IfcWindow``. The referenced type owns the actual panel
    operation and should declare ``SLIDINGHORIZONTAL`` or ``SLIDINGVERTICAL``.

    A floor-level terrace unit usually states ``sill_height=0.0``. Its low sill
    or passable appearance does not by itself make the element an ``IfcDoor``.
    """

    return window(
        model,
        key,
        wall=wall,
        window_type=window_type,
        along=along,
        sill_height=sill_height,
        overall_width=overall_width,
        overall_height=overall_height,
        direction_sense=direction_sense,
        lining_material=lining_material,
        framing_material=framing_material,
        glazing_material=glazing_material,
        is_external=is_external,
        threshold_space=threshold_space,
        name=name,
    )


def corner_window(
    model: Building,
    key: str,
    *,
    walls: tuple[str, str],
    window_types: tuple[str, str],
    along: tuple[float, float],
    sill_height: float,
    overall_widths: tuple[float, float],
    overall_height: float,
    direction_sense: tuple[str, str] = ("POSITIVE", "POSITIVE"),
    lining_material: str | None = None,
    framing_material: str | None = None,
    glazing_material: str | None = None,
    is_external: bool = True,
    reach: float = 0.05,
    name: str | None = None,
) -> tuple[str, str]:
    """Declare two windows and a corner cut with one IFC opening per host.

    ``walls``, ``window_types``, ``along``, ``overall_widths``, and
    ``direction_sense`` are ordered pairs describing the two legs. ``along``
    stays explicit because the correct frame junction depends on each type's
    lining depth and offset: centred frames can end at the reference-line
    corner, while flush box frames need a deliberate overlap or setback.

    The helper owns ``<key>.0`` and ``<key>.1`` for the two windows and
    ``<key>.opening`` for the extra ``corner_opening`` that clears both wall
    mitres. It returns the two window IDs so separate projecting sills can name
    them. Sills remain explicit because their mitre reach and exterior-side
    sign depend on wall buildup, projection, horn, and frame setback. A given
    ``name`` is a base display name: each leg appends its wall key and the
    corner cut appends ``Corner Opening``. The compiler emits a separate
    opening occurrence for each host wall from that one corner declaration.
    """

    pairs = {
        "walls": walls,
        "window_types": window_types,
        "along": along,
        "overall_widths": overall_widths,
        "direction_sense": direction_sense,
    }
    for label, pair in pairs.items():
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise AuthoringError(
                f"corner window {label} must contain exactly two values"
            )

    window_keys = (f"{key}.0", f"{key}.1")
    for index, window_key in enumerate(window_keys):
        window(
            model,
            window_key,
            wall=walls[index],
            window_type=window_types[index],
            along=along[index],
            sill_height=sill_height,
            overall_width=overall_widths[index],
            overall_height=overall_height,
            direction_sense=direction_sense[index],
            lining_material=lining_material,
            framing_material=framing_material,
            glazing_material=glazing_material,
            is_external=is_external,
            name=None if name is None else f"{name} - {walls[index]}",
        )
    corner_opening(
        model,
        f"{key}.opening",
        walls=walls,
        base=sill_height,
        height=overall_height,
        reach=reach,
        name=None if name is None else f"{name} - Corner Opening",
    )
    return window_keys


def casement_window_type(model: Building, key: str) -> str:
    """Declare a casement window with two side-hung sashes.

    The lining is 60 mm wide and 80 mm deep. The mullion is 90 mm wide,
    and the 70 mm sash band sits 40 mm in from the lining's outer edge.
    """

    return window_type(
        model,
        key,
        name="Casement Window",
        predefined_type="WINDOW",
        partitioning_type="DOUBLE_PANEL_VERTICAL",
        lining=window_lining(
            depth=0.08,
            thickness=0.06,
            mullion_thickness=0.09,
            to_panel_offset_x=0.04,
            to_panel_offset_y=0.025,
        ),
        panels=[
            window_panel(
                frame_depth=0.08,
                frame_thickness=0.07,
                operation_type="SIDEHUNGLEFTHAND",
                position="LEFT",
            ),
            window_panel(
                frame_depth=0.08,
                frame_thickness=0.07,
                operation_type="SIDEHUNGRIGHTHAND",
                position="RIGHT",
            ),
        ],
    )


def balcony_window_type(model: Building, key: str, *, hinge_side: str = "LEFT") -> str:
    """Conventional floor-level casement: four-sided lining and one sash.

    Uses the existing measured 80 mm casement section and the unmodified
    upstream window generator. The bottom frame is joinery, not flooring.
    """
    if hinge_side not in ("LEFT", "RIGHT"):
        raise AuthoringError("balcony hinge_side must be LEFT or RIGHT")
    return window_type(
        model, key, name="Balcony Window", partitioning_type="SINGLE_PANEL",
        lining=window_lining(depth=0.08, thickness=0.06,
                             to_panel_offset_x=0.04, to_panel_offset_y=0.025),
        panels=[window_panel(frame_depth=0.08, frame_thickness=0.07,
                             operation_type="SIDEHUNGLEFTHAND" if hinge_side == "LEFT" else "SIDEHUNGRIGHTHAND",
                             position="MIDDLE")],
    )


def lift_slide_window_type(
    model: Building, key: str, *, sliding_side: str = "LEFT", offset: float = 0.0,
    frame_depth: float = 0.174, jamb_width: float = 0.048, head_height: float = 0.048,
    threshold_height: float = 0.010, rail_width: float = 0.004, rail_height: float = 0.005,
    track_spacing: float = 0.087, sash_depth: float = 0.077,
    sash_face_width: float = 0.095, sash_bottom_height: float = 0.095,
    meeting_overlap: float = 0.050, interlock_width: float = 0.020,
    sealing_clearance: float = 0.002, glazing_thickness: float = 0.024,
    glazing_bite: float = 0.003,
) -> str:
    """A simplified, script-parametric two-track HST window, as native IFC.

    The 174 mm frame, 77 mm sash, 48 mm frame band and approximately 95 mm
    sash face follow published ALUPROF MB-77HS envelope dimensions:
    https://aluprof.com/files/downloads/MB-77HS_A3_EN.pdf
    Rail, threshold, clearances and interlock details are explicit generic
    approximations, not an exact product section or performance specification.

    LEFT/RIGHT is viewed in local X elevation; the sliding sash uses the
    inner (+Y) track. The assembly stays within z=0..overall_height: there is
    no implicit recess into flooring. Do not use a full-wall threshold_space
    patch. Rebuild from this script, not Bonsai's stock window editor.
    """
    from .window_assemblies import validate_lift_slide_assembly

    section = validate_lift_slide_assembly({
        "sliding_side": sliding_side, "frame_depth": frame_depth,
        "jamb_width": jamb_width, "head_height": head_height,
        "threshold_height": threshold_height, "rail_width": rail_width,
        "rail_height": rail_height, "track_spacing": track_spacing,
        "sash_depth": sash_depth, "sash_face_width": sash_face_width,
        "sash_bottom_height": sash_bottom_height, "meeting_overlap": meeting_overlap,
        "interlock_width": interlock_width, "sealing_clearance": sealing_clearance,
        "glazing_thickness": glazing_thickness, "glazing_bite": glazing_bite,
    })
    lining = window_lining(
        depth=section["frame_depth"], thickness=section["jamb_width"], offset=offset,
        to_panel_offset_x=section["jamb_width"] + section["sealing_clearance"],
    )
    lining["LiningToPanelOffsetY"] = None
    return window_type(
        model, key, name="Lift-Slide Window", partitioning_type="DOUBLE_PANEL_VERTICAL",
        lining=lining,
        panels=[window_panel(
            frame_depth=section["sash_depth"], frame_thickness=section["sash_face_width"],
            operation_type="SLIDINGHORIZONTAL" if side == sliding_side else "FIXEDCASEMENT",
            position=side,
        ) for side in ("LEFT", "RIGHT")],
        assembly={"kind": "LIFT_SLIDE", **section},
    )


def fixed_window_type(model: Building, key: str) -> str:
    """A single fixed light, in the same section as the casement.

    `FIXEDCASEMENT` is IFC's word for a pane that does not open, so a fixed
    light says so rather than being a casement that happens to carry no
    handle.
    """

    return window_type(
        model,
        key,
        name="Fixed Window",
        predefined_type="WINDOW",
        partitioning_type="SINGLE_PANEL",
        lining=window_lining(
            depth=0.08,
            thickness=0.06,
            to_panel_offset_x=0.04,
            to_panel_offset_y=0.025,
        ),
        panels=[
            window_panel(
                frame_depth=0.08,
                frame_thickness=0.07,
                operation_type="FIXEDCASEMENT",
                position="MIDDLE",
            )
        ],
    )


def panel_door_type(
    model: Building, key: str, *, operation_type: str = "SINGLE_SWING_LEFT"
) -> str:
    """Declare a single-leaf panel door with the requested swing."""

    return door_type(
        model,
        key,
        name="Panel Door",
        predefined_type="DOOR",
        operation_type=operation_type,
        lining=door_lining(
            depth=0.14,
            thickness=0.10,
            casing_thickness=0.05,
            casing_depth=0.012,
            to_panel_offset_x=0.01,
            to_panel_offset_y=0.03,
        ),
        panel=door_panel(depth=0.035, width_ratio=1.0),
    )


def sliding_door_type(
    model: Building, key: str, *, sliding_side: str = "LEFT"
) -> str:
    """A single sliding leaf: the panel door's section, on a track.

    The leaf is the same 0.035 m panel and the lining the same 0.14 x 0.10
    section as `panel_door_type`, so a sliding door and a swinging one read as
    one family; only the operation differs. IfcOpenShell's generator mounts a
    sliding panel outboard of the lining rather than inside a swing reveal,
    which is what a door running past its frame looks like. ``sliding_side``
    is the side the leaf parks on, in the opening's own local X elevation -
    the wall the parked leaf needs clear, so the run it opens against stays
    free for what the room puts there.
    """

    if sliding_side not in ("LEFT", "RIGHT"):
        raise AuthoringError("sliding door side must be LEFT or RIGHT")
    return door_type(
        model,
        key,
        name="Sliding Door",
        predefined_type="DOOR",
        operation_type=(
            "SLIDING_TO_LEFT" if sliding_side == "LEFT" else "SLIDING_TO_RIGHT"
        ),
        lining=door_lining(
            depth=0.14,
            thickness=0.10,
            casing_thickness=0.05,
            casing_depth=0.012,
            to_panel_offset_x=0.01,
            to_panel_offset_y=0.03,
        ),
        panel=door_panel(
            depth=0.035,
            width_ratio=1.0,
            operation_type="SLIDING",
            position="LEFT" if sliding_side == "LEFT" else "RIGHT",
        ),
    )
