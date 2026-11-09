"""Window sills: the weathering ledge a parametric window never builds.

Same split as `roof_windows.py`, `tiles.py` and `railings.py`: the shape is a
procedure, written out in code rather than loaded from a model file.
`add_window_representation` builds lining, panels and glazing but nothing
that projects past the wall face - IFC has no dedicated sill entity either,
so both the geometry and the classification are this skill's to state. See
`references/openings.md` for why an `IfcBuildingElementPart` aggregated onto
the window, not a standalone occurrence, is what "proper IFC" means here.
"""

from __future__ import annotations

from . import procedures
from .procedures import ProceduralMesh
from .values import AuthoringError

SillMesh = ProceduralMesh


def standard_sill_mesh(
    width: float,
    depth: float,
    thickness: float,
    *,
    corner: str | None = None,
    corner_reach: float = 0.0,
) -> SillMesh:
    """A flat projecting slab, in the opening's own frame.

    X across the opening, Y through the wall, Z up from the sill line - the
    same frame `compiler.opening_payload` already places the window in, so no
    second convention is invented. The slab is centred on the opening in X
    and on the wall in Y, with its top face at Z = 0 (the sill line) and its
    underside `thickness` below it - a caller wanting the wider footprint a
    real sill has states that as `width` and `depth`, not a separate margin
    this procedure would have to reinterpret.

    A window at a building corner sits close to where a second window, on
    the wall around that corner, has a sill of its own - and this one's
    plain rectangle stops `horn` short of that corner, same as it does
    everywhere else. Left alone, that is a real unfilled square exactly
    where the two sills should meet.

    `corner` names which end of this sill's own X axis faces that corner
    (`"start"` or `"end"`, the same vocabulary `along` already measures
    from), and `corner_reach` how far its Y = +depth/2 corner there is
    pushed out - or its Y = -depth/2 corner, if `corner_reach` is negative,
    since which physical side of the wall is which is this procedure's own
    local frame, not a fact it is told.

    The opposite corner at that end does not stay put - it shrinks back by
    `depth - corner_reach`, along the same axis the push moves on. That
    keeps this sill's own mitre at exactly 45 degrees to its own X and Y,
    regardless of how far it had to reach: the along-axis span from the
    shrunk corner to the pushed one is `corner_reach + (depth - corner_reach)
    = depth`, matching the across-axis span between them, which is always
    `depth` by construction. A window on the wall around the corner, cutting
    its own sill's mitre the same way from its own depth, produces a
    diagonal at the same 45 degrees - and two 45-degree lines through
    perpendicular walls are themselves parallel, so the two sills' mitres
    coincide as one line without either ever being told the other's numbers.
    A plain trapezoid results - the near corner pushed out, the far one
    pulled in - not two rectangles left short, driven through each other, or
    a shape wider than either.
    """

    if width <= 0 or depth <= 0 or thickness <= 0:
        raise AuthoringError(
            "window sill width, depth and thickness must be positive"
        )
    if corner not in (None, "start", "end"):
        raise AuthoringError(
            f"window sill corner must be 'start', 'end', or left unset; "
            f"got {corner!r}"
        )
    if corner_reach != 0.0 and corner is None:
        raise AuthoringError("window sill corner_reach needs a corner to mitre")

    half_x = width / 2.0
    half_y = depth / 2.0
    p_start_near = [-half_x, -half_y]
    p_end_near = [half_x, -half_y]
    p_end_far = [half_x, half_y]
    p_start_far = [-half_x, half_y]

    reach = abs(corner_reach)
    if corner is not None:
        # `corner_reach = 0` still mitres - it means the near corner needs
        # no push to reach its own target, not that there is no corner to
        # mitre towards. The far corner still shrinks back by the full
        # depth, or the two would still overlap: it is stating `corner`
        # that asks for the wedge, not the reach being nonzero.
        shrink = depth - reach
        if corner == "end":
            pushed, shrunk = (
                (p_end_far, p_end_near) if corner_reach >= 0
                else (p_end_near, p_end_far)
            )
            pushed[0] += reach
            shrunk[0] -= shrink
        else:
            pushed, shrunk = (
                (p_start_far, p_start_near) if corner_reach >= 0
                else (p_start_near, p_start_far)
            )
            pushed[0] -= reach
            shrunk[0] += shrink

    footprint = [
        tuple(p_start_near), tuple(p_end_near),
        tuple(p_end_far), tuple(p_start_far),
    ]
    verts = [(x, y, -thickness) for x, y in footprint]
    verts += [(x, y, 0.0) for x, y in footprint]
    count = len(footprint)
    faces = [
        tuple(range(count - 1, -1, -1)),  # underside, facing down
        tuple(range(count, 2 * count)),   # top, facing up
    ]
    for index in range(count):
        following = (index + 1) % count
        faces.append((index, following, count + following, count + index))
    quad_uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    uvs = [quad_uv] * len(faces)
    slots = ["sill"] * len(faces)
    return procedures.validate_mesh("standard_sill_mesh", (verts, faces, uvs, slots))
