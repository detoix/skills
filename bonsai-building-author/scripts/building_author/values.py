"""Value checks shared by every declaration function.

Each check takes a caller-supplied label so the error names the offending
argument, and returns the coerced value so declarations stay one-liners.
"""

from __future__ import annotations

import math
import re

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_IFC_CLASS = re.compile(r"^Ifc[A-Za-z0-9]+$")

# Spelled as the schema spells them, so a declaration and the IFC it produces
# read the same. `IfcWallTypeEnum` and `IfcDirectionSenseEnum` respectively.
WALL_TYPES = frozenset(
    {
        "MOVABLE",
        "PARAPET",
        "PARTITIONING",
        "PLUMBINGWALL",
        "SHEAR",
        "SOLIDWALL",
        "STANDARD",
        "POLYGONAL",
        "ELEMENTEDWALL",
        "USERDEFINED",
        "NOTDEFINED",
    }
)
DIRECTION_SENSE = frozenset({"POSITIVE", "NEGATIVE"})

# `IfcSlabTypeEnum` and `IfcSpaceTypeEnum`. Spelled as the schema spells them.
SLAB_TYPES = frozenset(
    {"FLOOR", "ROOF", "LANDING", "BASESLAB", "USERDEFINED", "NOTDEFINED"}
)
SPACE_TYPES = frozenset(
    {
        "SPACE",
        "PARKING",
        "GFA",
        "INTERNAL",
        "EXTERNAL",
        "USERDEFINED",
        "NOTDEFINED",
    }
)

# `IfcRailingTypeEnum`, IFC4 - not IFC4.3, which adds `FENCE`. Spelled as the
# schema spells them.
RAILING_TYPES = frozenset(
    {"BALUSTRADE", "GUARDRAIL", "HANDRAIL", "USERDEFINED", "NOTDEFINED"}
)

# `IfcWindowTypeEnum`, `IfcWindowTypePartitioningEnum`, `IfcDoorTypeEnum` and
# `IfcDoorTypeOperationEnum`. Spelled as the schema spells them.
WINDOW_TYPES = frozenset(
    {"WINDOW", "SKYLIGHT", "LIGHTDOME", "USERDEFINED", "NOTDEFINED"}
)
DOOR_TYPES = frozenset({"DOOR", "GATE", "TRAPDOOR", "USERDEFINED", "NOTDEFINED"})

#: The partitionings IfcOpenShell's window generator can actually build. The
#: schema also allows USERDEFINED and NOTDEFINED, which are excluded because
#: they name no panel layout for it to lay out.
WINDOW_PARTITIONING = frozenset(
    {
        "SINGLE_PANEL",
        "DOUBLE_PANEL_HORIZONTAL",
        "DOUBLE_PANEL_VERTICAL",
        "TRIPLE_PANEL_BOTTOM",
        "TRIPLE_PANEL_HORIZONTAL",
        "TRIPLE_PANEL_LEFT",
        "TRIPLE_PANEL_RIGHT",
        "TRIPLE_PANEL_TOP",
        "TRIPLE_PANEL_VERTICAL",
    }
)

#: How many panels each partitioning carries, and how many mullions and
#: transoms divide them. Read off the panel schemas IfcOpenShell's window
#: generator lays out: a partitioning is a grid, so `DOUBLE_PANEL_VERTICAL` is
#: two columns divided by one mullion and `TRIPLE_PANEL_HORIZONTAL` three rows
#: divided by two transoms. A division with no thickness, or an offset left at
#: zero, produces a panel of zero width - so both are checked rather than
#: passed on to fail as a shape error.
WINDOW_PARTS = {
    #                        panels, mullions, transoms
    "SINGLE_PANEL": (1, 0, 0),
    "DOUBLE_PANEL_HORIZONTAL": (2, 0, 1),
    "DOUBLE_PANEL_VERTICAL": (2, 1, 0),
    "TRIPLE_PANEL_BOTTOM": (3, 1, 1),
    "TRIPLE_PANEL_HORIZONTAL": (3, 0, 2),
    "TRIPLE_PANEL_LEFT": (3, 1, 1),
    "TRIPLE_PANEL_RIGHT": (3, 1, 1),
    "TRIPLE_PANEL_TOP": (3, 1, 1),
    "TRIPLE_PANEL_VERTICAL": (3, 2, 0),
}


def ratio(label: str, value: float) -> float:
    """An `IfcNormalisedRatioMeasure` that divides something: strictly inside.

    Zero or one would put a mullion on the window's own edge, leaving a panel
    of no width, so the range is open at both ends rather than clamped.
    """

    result = number(label, value)
    if not 0.0 < result < 1.0:
        raise AuthoringError(
            f"{label} must be a ratio strictly between zero and one"
        )
    return result

#: The operations IfcOpenShell's door generator can build. The schema's
#: remaining values - folding, revolving, rolling up - have no generator, so
#: accepting them would produce a door that is not the door that was declared.
DOOR_OPERATIONS = frozenset(
    {
        "SINGLE_SWING_LEFT",
        "SINGLE_SWING_RIGHT",
        "DOUBLE_SWING_LEFT",
        "DOUBLE_SWING_RIGHT",
        "DOUBLE_DOOR_SINGLE_SWING",
        "DOUBLE_DOOR_DOUBLE_SWING",
        "SLIDING_TO_LEFT",
        "SLIDING_TO_RIGHT",
        "DOUBLE_DOOR_SLIDING",
    }
)

#: `IfcWindowPanelProperties.OperationType` and `.PanelPosition`, and their
#: door counterparts. Carried onto the type's property sets so the IFC says
#: how a panel opens, not only what it looks like.
WINDOW_PANEL_OPERATIONS = frozenset(
    {
        "SIDEHUNGRIGHTHAND",
        "SIDEHUNGLEFTHAND",
        "TILTANDTURNRIGHTHAND",
        "TILTANDTURNLEFTHAND",
        "TOPHUNG",
        "BOTTOMHUNG",
        "PIVOTHORIZONTAL",
        "PIVOTVERTICAL",
        "SLIDINGHORIZONTAL",
        "SLIDINGVERTICAL",
        "REMOVABLECASEMENT",
        "FIXEDCASEMENT",
        "OTHEROPERATION",
        "NOTDEFINED",
    }
)
WINDOW_PANEL_POSITIONS = frozenset(
    {"LEFT", "MIDDLE", "RIGHT", "BOTTOM", "TOP", "NOTDEFINED"}
)
DOOR_PANEL_OPERATIONS = frozenset(
    {
        "SWINGING",
        "DOUBLE_ACTING",
        "SLIDING",
        "FOLDING",
        "REVOLVING",
        "ROLLINGUP",
        "FIXEDPANEL",
        "USERDEFINED",
        "NOTDEFINED",
    }
)
DOOR_PANEL_POSITIONS = frozenset({"LEFT", "MIDDLE", "RIGHT", "NOTDEFINED"})


class AuthoringError(ValueError):
    """Raised when a building script is invalid before execution."""


def identifier(label: str, value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise AuthoringError(
            f"{label} must be lowercase and contain only letters, digits, "
            "dots, underscores, or hyphens"
        )
    return value


def ifc_class(value: str) -> str:
    if not isinstance(value, str) or not _IFC_CLASS.fullmatch(value):
        raise AuthoringError(f"invalid IFC class: {value!r}")
    return value


def number(label: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthoringError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AuthoringError(f"{label} must be finite")
    return result


def positive(label: str, value: float) -> float:
    result = number(label, value)
    if result <= 0:
        raise AuthoringError(f"{label} must be greater than zero")
    return result


def unit_interval(label: str, value: float) -> float:
    result = number(label, value)
    if not 0.0 <= result <= 1.0:
        raise AuthoringError(f"{label} must be between zero and one")
    return result


def non_negative(label: str, value: float) -> float:
    result = number(label, value)
    if result < 0:
        raise AuthoringError(f"{label} must not be negative")
    return result


def pitch(label: str, value: float) -> float:
    """A roof pitch in degrees: flat is allowed, vertical is not."""

    result = number(label, value)
    if not 0.0 <= result < 90.0:
        raise AuthoringError(
            f"{label} must be at least zero and below ninety degrees"
        )
    return result


def integer(label: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuthoringError(f"{label} must be a whole number")
    return value


def priority(label: str, value: int) -> int:
    """`IfcMaterialLayer.Priority`, a normalised integer in [0, 100]."""

    result = integer(label, value)
    if not 0 <= result <= 100:
        raise AuthoringError(f"{label} must be between zero and one hundred")
    return result


def enumeration(label: str, value: str, allowed: frozenset[str]) -> str:
    """One value of an IFC enumeration, named exactly as the schema names it."""

    if value not in allowed:
        raise AuthoringError(
            f"{label} must be one of {', '.join(sorted(allowed))}; got {value!r}"
        )
    return value


def point2(label: str, value: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise AuthoringError(f"{label} must contain two coordinates")
    return (number(f"{label} x", value[0]), number(f"{label} y", value[1]))


def point3(
    label: str,
    value: tuple[float, float, float],
) -> tuple[float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise AuthoringError(f"{label} must contain three coordinates")
    return (
        number(f"{label} x", value[0]),
        number(f"{label} y", value[1]),
        number(f"{label} z", value[2]),
    )


def axis(
    value: tuple[tuple[float, float], tuple[float, float]],
    label: str = "wall axis",
) -> tuple[tuple[float, float], tuple[float, float]]:
    """A straight reference line: two distinct points, named by `label`.

    Shared by every declaration that runs along a straight line rather than a
    closed footprint - a wall's `axis`, a railing's `path` - the same way
    `boundary()` is shared by every closed-footprint declaration.
    """

    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise AuthoringError(f"{label} must contain two points")
    start = point2(f"{label} start", value[0])
    end = point2(f"{label} end", value[1])
    if start == end:
        raise AuthoringError(f"{label} points must be different")
    return start, end


def boundary(
    value: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """A closed footprint, given as its corners without repeating the first.

    Shared by every declaration that takes a plan footprint - a roof's base,
    a slab's outline - so the same closure and repeat-corner checks apply to
    both.
    """

    if not isinstance(value, (tuple, list)) or len(value) < 3:
        raise AuthoringError("a boundary needs at least three corners")
    points = [
        point2(f"boundary corner {index}", corner)
        for index, corner in enumerate(value)
    ]
    if points[0] == points[-1]:
        points.pop()
        if len(points) < 3:
            raise AuthoringError("a boundary needs at least three corners")
    for index, corner in enumerate(points):
        if corner == points[index - 1]:
            raise AuthoringError(
                f"boundary corner {index} repeats the previous corner"
            )
    return points


def rgb(
    value: tuple[float, float, float],
) -> tuple[float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise AuthoringError("base_color must contain three RGB channels")
    return tuple(
        unit_interval(f"base_color channel {index}", channel)
        for index, channel in enumerate(value)
    )
