"""The straight-skeleton seam, and the contract a weighted one must satisfy.

The skeleton itself runs inside Blender, where `bpypolyskel` lives. What
belongs here is the part that is pure Python and therefore testable: deciding
whether a declared roof is within the installed skeleton's reach, and building
the per-edge weights a weighted skeleton would consume.

Promotion path
--------------
`bpypolyskel` is a third-party package (prochitecture/bpypolyskel), not Bonsai
code. Its entry point is::

    polygonize(verts, firstVertIndex, numVerts, holesInfo=None,
               height=0.0, tan=0.0, faces=None, unitVectors=None)

`tan` is a single scalar, which is exactly what makes it unweighted. The
backward-compatible generalisation is to let `tan` accept either a float or
one value per edge - a scalar then reproduces today's behaviour byte for byte.
`weights()` below returns precisely that per-edge sequence, so promoting this
work upstream is a move plus a signature widening, not a redesign.

Until that lands, `classify()` refuses the weighted case loudly rather than
letting the unweighted skeleton emit a quietly wrong roof.
"""

from __future__ import annotations

import math

from .values import AuthoringError

#: Every sloping edge shares one pitch. The installed unweighted skeleton
#: handles this exactly; gables are applied afterwards as a post-process.
UNIFORM = "uniform"

#: Sloping edges disagree on pitch. Needs a weighted straight skeleton.
WEIGHTED = "weighted"

_ANGLE_EPS = 1e-6


def weights(angles: list[float]) -> list[float]:
    """Return the per-edge skeleton weights for the given pitches.

    The weight of an edge is ``tan(90 - pitch)``, matching what a weighted
    skeleton consumes as its edge speed and what `bpypolyskel` accepts today
    as a single scalar `tan`. Pitches are in degrees.
    """

    result = []
    for angle in angles:
        if not 0.0 <= angle < 90.0:
            raise AuthoringError(
                f"roof pitch must be at least zero and below ninety degrees, "
                f"got {angle}"
            )
        result.append(math.tan(math.radians(90.0 - angle)))
    return result


def sloping_angles(edges: list[dict]) -> list[float]:
    """Return the pitches of the edges that actually raise a plane."""

    return [
        float(edge["angle"]) for edge in edges if edge.get("defines_slope", True)
    ]


def classify(edges: list[dict]) -> str:
    """Decide which skeleton a declared roof boundary requires.

    ``edges`` are the roof's edge declarations. Gable edges impose no pitch,
    so they never force the weighted case - only disagreement between edges
    that genuinely raise a plane does.
    """

    angles = sloping_angles(edges)
    if not angles:
        raise AuthoringError(
            "a roof needs at least one edge that defines slope; every edge is "
            "currently a gable"
        )
    if max(angles) - min(angles) > _ANGLE_EPS:
        return WEIGHTED
    return UNIFORM


def require_supported(key: str, edges: list[dict]) -> float:
    """Validate a roof against the installed skeleton, returning its pitch.

    Raises for the weighted case, naming the offending pitches, so an
    unsupported roof fails at declaration time rather than producing geometry
    that merely looks plausible.
    """

    kind = classify(edges)
    angles = sloping_angles(edges)
    if kind == WEIGHTED:
        found = sorted({round(angle, 6) for angle in angles})
        raise AuthoringError(
            f"roof {key!r} declares differing pitches {found} on edges that "
            "define slope. The installed straight skeleton is unweighted and "
            "cannot resolve this. Use one pitch for all sloping edges, or "
            "make the differing edges gables (defines_slope=False)."
        )
    return angles[0]
