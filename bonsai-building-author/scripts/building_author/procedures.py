"""The contract every mesh-building procedure returns.

Tile and window procedures both hand back the same four things, so the code
that realises them in Blender never has to care which procedure it called:

    (verts, faces, uvs, slots)

``slots`` names a **material role** for each face - ``"tile"``, ``"frame"``,
``"glazing"`` - rather than a material. A procedure knows that a pane is glass
and a sash is not; it has no business knowing which glass the building
declared. The declaration maps roles onto real materials.

Assign a role to each face so frames and panes receive their own materials.
"""

from __future__ import annotations

from .values import AuthoringError

Point = tuple[float, float]
Vertex = tuple[float, float, float]
Face = tuple[int, ...]
ProceduralMesh = tuple[list[Vertex], list[Face], list[list[Point]], list[str]]


def validate_mesh(name: str, mesh: ProceduralMesh) -> ProceduralMesh:
    """Check a procedure's output before anything tries to build it."""

    verts, faces, uvs, slots = mesh
    if not verts or not faces:
        raise AuthoringError(f"{name} produced no geometry")
    if len(uvs) != len(faces):
        raise AuthoringError(
            f"{name} returned {len(uvs)} uv sets for {len(faces)} faces"
        )
    if len(slots) != len(faces):
        raise AuthoringError(
            f"{name} returned {len(slots)} material slots for "
            f"{len(faces)} faces"
        )
    for index, face in enumerate(faces):
        if len(face) < 3:
            raise AuthoringError(f"{name} face {index} has fewer than three corners")
        if len(uvs[index]) != len(face):
            raise AuthoringError(
                f"{name} face {index} has {len(face)} corners but "
                f"{len(uvs[index])} uvs"
            )
        for corner in face:
            if not 0 <= corner < len(verts):
                raise AuthoringError(
                    f"{name} face {index} refers to vertex {corner}, which "
                    f"does not exist"
                )
    return mesh


def roles(mesh: ProceduralMesh) -> list[str]:
    """The distinct material roles a mesh uses, in a stable order."""

    return sorted(set(mesh[3]))
