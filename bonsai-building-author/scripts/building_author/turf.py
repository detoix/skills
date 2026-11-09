"""Explicit horizontal lawn areas; no room enclosure or scatter inference."""
from . import values
from .polygons import signed_area


def turf(model, key, *, site, boundary, elevation=0.0, name=None):
    """Declare an exterior IfcSpace footprint and its renderable turf surface.

    Coordinates and elevation are metres in the project's authored frame.
    Supports a simple concave or convex polygon; holes and slopes are not yet
    supported. The boundary is normalized counter-clockwise for upward normals.
    """
    points = values.boundary(boundary)
    from shapely.geometry import Polygon
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area < 1e-9:
        raise values.AuthoringError('turf boundary must be a simple polygon with positive area')
    if signed_area(points) < 0:
        points.reverse()
    return model.add_ifc('turf', key, references={'site': site},
                         boundary=points, elevation=values.number('turf elevation', elevation),
                         name=name or key)
