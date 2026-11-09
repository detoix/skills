"""Script-parametric lift-slide windows built with IfcOpenShell's solid tools.

This is a simplified two-track assembly, not a manufacturer's section model.
All section dimensions are explicit inputs; the named type documents their
source or approximation. IfcOpenShell owns frames, profiles and extrusions.
"""

from collections.abc import Mapping

from . import values
from .values import AuthoringError


_DIMENSIONS = (
    "frame_depth", "jamb_width", "head_height", "threshold_height",
    "rail_width", "rail_height", "track_spacing", "sash_depth",
    "sash_face_width", "sash_bottom_height", "meeting_overlap",
    "interlock_width", "sealing_clearance", "glazing_thickness", "glazing_bite",
)


def validate_lift_slide_assembly(assembly, overall_width=None, overall_height=None):
    """Normalize explicit metre dimensions and reject impossible sections."""

    if not isinstance(assembly, Mapping):
        raise AuthoringError("lift-slide assembly must be a mapping")
    expected = {*_DIMENSIONS, "sliding_side"}
    missing, extra = expected - set(assembly), set(assembly) - expected
    if missing:
        raise AuthoringError("lift-slide assembly is missing " + ", ".join(sorted(missing)))
    if extra:
        raise AuthoringError("unknown lift-slide assembly fields: " + ", ".join(sorted(extra)))
    result = {key: values.positive(f"lift-slide {key}", assembly[key]) for key in _DIMENSIONS}
    result["sliding_side"] = assembly["sliding_side"]
    if result["sliding_side"] not in ("LEFT", "RIGHT"):
        raise AuthoringError("lift-slide sliding_side must be LEFT or RIGHT")
    p = result
    gap = p["track_spacing"] - p["sash_depth"]
    if gap <= p["sealing_clearance"]:
        raise AuthoringError("lift-slide tracks need space for two interlock lips and sealing clearance")
    if p["track_spacing"] + p["sash_depth"] + 2 * p["sealing_clearance"] > p["frame_depth"]:
        raise AuthoringError("lift-slide sash tracks do not fit within frame_depth with sealing clearance")
    if p["rail_width"] >= p["sash_depth"]:
        raise AuthoringError("lift-slide rail_width must be smaller than sash_depth")
    if not p["interlock_width"] < p["meeting_overlap"] <= p["sash_face_width"]:
        raise AuthoringError("lift-slide interlock_width must fit inside meeting_overlap and the meeting stiles")
    if p["glazing_thickness"] + 2 * p["sealing_clearance"] >= p["sash_depth"]:
        raise AuthoringError("lift-slide glazing must fit inside sash_depth with sealing clearance")
    if p["glazing_bite"] >= min(p["sash_face_width"], p["sash_bottom_height"]):
        raise AuthoringError("lift-slide glazing_bite must be smaller than the sash frame bands")
    if overall_width is not None:
        width = values.positive("lift-slide overall_width", overall_width)
        sash_width = (width - 2 * (p["jamb_width"] + p["sealing_clearance"])
                      + p["meeting_overlap"]) / 2
        if sash_width <= 2 * p["sash_face_width"]:
            raise AuthoringError("lift-slide overall_width leaves no clear pane between the sash stiles")
    if overall_height is not None:
        height = values.positive("lift-slide overall_height", overall_height)
        sash_height = (height - p["head_height"] - p["sealing_clearance"]
                       - p["threshold_height"] - p["rail_height"])
        if sash_height <= p["sash_face_width"] + p["sash_bottom_height"]:
            raise AuthoringError("lift-slide overall_height leaves no clear pane above the low threshold")
    return result


def add_lift_slide_representation(
    file, *, context, overall_width, overall_height, assembly, part_of_product,
    lining_offset=0.0,
):
    """Create native swept solids and Lining/Framing/Glazing shape aspects.

    Inputs are metres, converted to the file's length unit. Local X runs from
    0 to width, Y from lining_offset to lining_offset + frame_depth, and Z
    from 0 to height. The sliding sash uses the inner (+Y) track; LEFT/RIGHT
    mirrors the X layout. The occurrence placement supplies the actual sill
    datum. No part is buried below it.
    """

    p = validate_lift_slide_assembly(assembly, overall_width, overall_height)
    offset = values.number("lift-slide lining_offset", lining_offset)
    # Import only when producing IFC, so declaration validation needs no live
    # Blender or IfcOpenShell installation.
    import numpy as np
    from ifcopenshell.api.geometry.add_shape_aspect import add_shape_aspect
    from ifcopenshell.api.geometry.add_window_representation import create_ifc_window_frame_simple
    from ifcopenshell.util.shape_builder import ShapeBuilder
    from ifcopenshell.util.unit import calculate_unit_scale

    scale = calculate_unit_scale(file)
    width, height = float(overall_width) / scale, float(overall_height) / scale
    p = {key: value / scale if key in _DIMENSIONS else value for key, value in p.items()}
    builder = ShapeBuilder(file)

    def frame(name, size, bands, position):
        items = create_ifc_window_frame_simple(
            builder, np.asarray(size, dtype=float), list(bands), np.asarray(position, dtype=float)
        )
        for item in items:
            item.SweptArea.ProfileName = name
        return items

    def box(name, size, position):
        profile = builder.profile(builder.rectangle(size=size[:2]), name=name)
        return builder.extrude(profile, size[2], position=position)

    lining = frame(
        "Head and jambs", (width, p["frame_depth"], height),
        (p["jamb_width"], p["head_height"], p["jamb_width"], 0.0), (0.0, 0.0, 0.0),
    )
    # The base and rails stop at the inner jamb faces. Their bottom/top
    # contacts are opposing faces, not duplicate exposed surfaces.
    clear_width = width - 2 * p["jamb_width"]
    lining.append(box("Low threshold", (clear_width, p["frame_depth"], p["threshold_height"]),
                      (p["jamb_width"], 0.0, 0.0)))
    track_centres = ((p["frame_depth"] - p["track_spacing"]) / 2,
                     (p["frame_depth"] + p["track_spacing"]) / 2)
    for label, centre in zip(("Fixed", "Sliding"), track_centres):
        lining.append(box(label + " track rail", (clear_width, p["rail_width"], p["rail_height"]),
                          (p["jamb_width"], centre - p["rail_width"] / 2, p["threshold_height"])))

    sash_bottom = p["threshold_height"] + p["rail_height"]
    sash_height = height - p["head_height"] - p["sealing_clearance"] - sash_bottom
    side_start = p["jamb_width"] + p["sealing_clearance"]
    sash_width = (width - 2 * side_start + p["meeting_overlap"]) / 2
    left_start, right_start = side_start, width - side_start - sash_width
    starts = ((right_start, left_start) if p["sliding_side"] == "LEFT"
              else (left_start, right_start))
    framing, glazing = [], []
    interlock_depth = (p["track_spacing"] - p["sash_depth"] - p["sealing_clearance"]) / 2
    for index, (label, centre, start) in enumerate(zip(("Fixed", "Sliding"), track_centres, starts)):
        sash_y = centre - p["sash_depth"] / 2
        framing.extend(frame(
            label + " sash", (sash_width, p["sash_depth"], sash_height),
            (p["sash_face_width"], p["sash_face_width"], p["sash_face_width"], p["sash_bottom_height"]),
            (start, sash_y, sash_bottom),
        ))
        # These attached lips extend toward one another across the track gap.
        # A positive sealing gap remains between them. X overlap belongs to
        # the two meeting stiles, not a conventional full-depth centre mullion.
        lip_y = (sash_y + p["sash_depth"] if index == 0 else sash_y - interlock_depth)
        framing.append(box(label + " meeting interlock",
                           (p["interlock_width"], interlock_depth, sash_height),
                           ((width - p["interlock_width"]) / 2, lip_y, sash_bottom)))
        bite = p["glazing_bite"]
        glazing.append(box(
            label + " glazing",
            (sash_width - 2 * p["sash_face_width"] + 2 * bite,
             p["glazing_thickness"],
             sash_height - p["sash_bottom_height"] - p["sash_face_width"] + 2 * bite),
            (start + p["sash_face_width"] - bite,
             centre - p["glazing_thickness"] / 2,
             sash_bottom + p["sash_bottom_height"] - bite),
        ))
    items = lining + framing + glazing
    if offset:
        builder.translate(items, (0.0, offset / scale, 0.0))
    representation = builder.get_representation(context, items, representation_type="SweptSolid")
    for role, role_items in (("Lining", lining), ("Framing", framing), ("Glazing", glazing)):
        add_shape_aspect(file, role, items=role_items, representation=representation,
                         part_of_product=part_of_product)
    return representation
