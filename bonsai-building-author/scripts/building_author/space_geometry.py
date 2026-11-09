"""Resolve room regions from regenerated IFC walls, without Blender objects.

The wall primitive is a vertical extrusion, optionally clipped at its top by
a roof or slab. Its native world-XY triangle projection therefore preserves
the exact joined floor footprint, including mitres, notches and holes. This
is not a second wall-junction solver. Opening subtraction is disabled because
room bodies stop at wall faces; their floor-level openings receive separate,
owned flooring occurrences.
"""

from __future__ import annotations

import ifcopenshell.geom
import numpy as np
import shapely


# Numerical welding only, well below IFC construction and presentation
# tolerances. It prevents coincident tessellated join edges from leaving a
# floating-point crack that connects an otherwise enclosed room to outdoors.
PLAN_TOLERANCE = 1e-7
SPACE_UNIVERSE_PADDING = 5.0


def threshold_is_adjacent(room, patch):
    """Check shared edge contact within numerical precision, not exact equality.

    Native IFC triangulation and the declared opening rectangle can differ by
    less than the plan precision grid. Buffer only this adjacency measurement;
    neither room nor threshold geometry is modified. A point-only corner
    contact contributes at most two tolerance-length segments. Requiring four
    tolerances leaves numerical headroom at that point-contact limit.
    """

    if room.distance(patch) > PLAN_TOLERANCE:
        return False
    shared = room.boundary.intersection(patch.buffer(PLAN_TOLERANCE)).length
    return shared > 4.0 * PLAN_TOLERANCE


def native_wall_footprint(model, wall, settings=None):
    """Return (world-XY native footprint, lowest Z, highest Z) for one wall.

    Missing or invalid native geometry is a hard error; a declared rectangle
    would recreate the very join discrepancy this resolver exists to avoid.
    """

    if settings is None:
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        settings.set("disable-opening-subtractions", True)
    key = wall.Tag or wall.GlobalId
    try:
        shape = ifcopenshell.geom.create_shape(settings, wall)
        vertices = np.asarray(shape.geometry.verts, dtype=float).reshape((-1, 3))
        faces = np.asarray(shape.geometry.faces, dtype=int).reshape((-1, 3))
    except Exception as error:
        raise RuntimeError(f"wall '{key}': cannot read native IFC geometry") from error
    if not len(vertices) or not len(faces) or not np.isfinite(vertices).all():
        raise RuntimeError(f"wall '{key}': native IFC geometry is empty or invalid")

    triangles = [shapely.Polygon(vertices[face, :2]) for face in faces]
    projected = [triangle for triangle in triangles if triangle.area > 0.0]
    footprint = shapely.set_precision(shapely.unary_union(projected), PLAN_TOLERANCE)
    if (
        footprint.is_empty
        or not footprint.is_valid
        or footprint.geom_type not in {"Polygon", "MultiPolygon"}
    ):
        raise RuntimeError(f"wall '{key}': native IFC geometry has no valid plan footprint")
    return footprint, float(vertices[:, 2].min()), float(vertices[:, 2].max())


def resolve_space_regions(model, groups, entities):
    """Resolve each declared point against walls crossing its floor datum.

    Groups are the compiler's private ``space_payload`` contract. Geometry is
    cached per physical wall; enclosures are cached per storey/floor datum.
    A plinth ending at the floor or a wall starting above it is not a room
    boundary. The native Z range also excludes a wall clipped below the floor.
    """

    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    settings.set("disable-opening-subtractions", True)
    native = {}
    result = {}
    for group in groups:
        storey_key = group["storey"]
        by_datum = {}
        claimed = {}
        for space in group["spaces"]:
            datum = space["base_z"]
            if datum not in by_datum:
                obstacles = [
                    shapely.set_precision(shapely.Polygon(boundary), PLAN_TOLERANCE)
                    for boundary in group["virtual_obstacles"]
                ]
                for declared in group["walls"]:
                    if not (
                        declared["base_z"] <= datum + PLAN_TOLERANCE
                        and declared["base_z"] + declared["height"] > datum + PLAN_TOLERANCE
                    ):
                        continue
                    key = declared["key"]
                    if key not in native:
                        if key not in entities:
                            raise RuntimeError(f"wall '{key}': native IFC entity is missing")
                        native[key] = native_wall_footprint(model, entities[key], settings)
                    footprint, bottom, top = native[key]
                    if bottom <= datum + PLAN_TOLERANCE and top > datum + PLAN_TOLERANCE:
                        obstacles.append(footprint)
                if not obstacles:
                    raise RuntimeError(
                        f"storey '{storey_key}' at Z={datum:g} declares a space but has "
                        "no walls or virtual elements at its floor datum to enclose it"
                    )
                union = shapely.unary_union(obstacles)
                min_x, min_y, max_x, max_y = union.bounds
                universe = shapely.box(
                    min_x - SPACE_UNIVERSE_PADDING,
                    min_y - SPACE_UNIVERSE_PADDING,
                    max_x + SPACE_UNIVERSE_PADDING,
                    max_y + SPACE_UNIVERSE_PADDING,
                )
                free = universe.difference(union)
                regions = list(free.geoms) if free.geom_type == "MultiPolygon" else [free]
                # Outdoors is the component touching the universe boundary,
                # not necessarily the largest component of a large building.
                by_datum[datum] = [
                    region for region in regions
                    if not region.boundary.intersects(universe.boundary)
                ]
                claimed[datum] = {}

            point = shapely.Point(space["at"])
            matches = [
                (index, region) for index, region in enumerate(by_datum[datum])
                if region.contains(point)
            ]
            if not matches:
                raise RuntimeError(
                    f"space '{space['key']}': no enclosed region contains "
                    f"{tuple(space['at'])} on storey '{storey_key}' at Z={datum:g} - "
                    "check its walls and virtual elements"
                )
            index, region = matches[0]
            if index in claimed[datum]:
                raise RuntimeError(
                    f"spaces '{claimed[datum][index]}' and '{space['key']}' select "
                    "the same enclosed region - check their physical or virtual boundary"
                )
            claimed[datum][index] = space["key"]
            result[space["key"]] = region
    return result
