"""Construction materials with flat fallbacks and canonical recipe pointers."""

from __future__ import annotations

from .author import Building, material


STYLIZED_PLASTER_RECIPE = (
    "references/material-recipes/mm217-stylized-plaster.material.md"
)
STYLIZED_ROOF_TILES_RECIPE = (
    "references/material-recipes/mm204-roof-tile-surface.material.md"
)
HERRINGBONE_WOOD_RECIPE = (
    "references/material-recipes/mm161-herringbone-wood.material.md"
)


def _source_rgb(color: tuple[float, float, float]) -> tuple[float, float, float]:
    """Convert publisher sRGB coefficients for the simplified IFC fallback."""

    def linear(channel: float) -> float:
        return (
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    return tuple(linear(channel) for channel in color)


def stucco(model: Building, key: str) -> str:
    """Declare MM217 plaster with its canonical target-neutral recipe."""

    return material(
        model,
        key,
        ifc_name="Stylized plaster by Tarox",
        category="plaster",
        base_color=_source_rgb((0.949219, 0.890878, 0.808319)),
        roughness=0.90,
        material_recipe=STYLIZED_PLASTER_RECIPE,
    )


def roof_tile(model: Building, key: str) -> str:
    """Declare MM204 clay with its canonical target-neutral surface recipe."""

    return material(
        model,
        key,
        ifc_name="Stylized roof tile by ninao",
        category="tile",
        base_color=_source_rgb((0.863281, 0.219193, 0.219193)),
        roughness=0.62,
        material_recipe=STYLIZED_ROOF_TILES_RECIPE,
    )


def herringbone_wood(model: Building, key: str) -> str:
    """Declare MM161 wood with its canonical target-neutral recipe."""

    return material(
        model,
        key,
        ifc_name="Herringbone wood by Kyrylo",
        category="wood",
        base_color=_source_rgb((0.07, 0.069475, 0.0665)),
        roughness=0.49,
        material_recipe=HERRINGBONE_WOOD_RECIPE,
    )


def window_frame(model: Building, key: str) -> str:
    """Declare the dark metal for a skylight frame and sash."""

    return material(
        model,
        key,
        ifc_name="Window frame metal",
        category="metal",
        base_color=(0.095, 0.095, 0.095),
        roughness=0.3,
        metallic=0.8,
    )


def opening_frame(model: Building, key: str) -> str:
    """Declare the white finish for window frames and door linings."""

    return material(
        model,
        key,
        ifc_name="Window and door frame",
        category="joinery",
        base_color=(0.947, 0.947, 0.947),
        roughness=0.45,
    )


def polyester_coated_steel(model: Building, key: str) -> str:
    """Declare anthracite galvanized steel with its visible polymer coating.

    Betafence specifies galvanized steel with a plastic/polyester RAL 7016
    finish for the Nylofor/D-Lox system. The displayed colour is an ordinary
    sRGB approximation because RAL does not define one device-independent RGB
    triplet. The visible polymer is an opaque dielectric, so glTF metallic is
    deliberately zero even though the construction substrate is steel.
    """

    return material(
        model,
        key,
        ifc_name="Galvanized steel with anthracite polyester coating",
        category="steel",
        base_color=_source_rgb((56 / 255, 62 / 255, 66 / 255)),
        roughness=0.42,
        metallic=0.0,
        alpha=1.0,
        double_sided=False,
    )


def anthracite_aluminium(model: Building, key: str) -> str:
    """Declare the RAL 7021 lacquered aluminium used by Horizon 020.

    Dlimity's technical sheet identifies RAL 7021 lacquered aluminium but not
    a calibrated RGB value, roughness, or coating chemistry. This conservative
    GLB fallback uses a common dark-grey sRGB approximation and represents the
    visible lacquer as an opaque dielectric, while IFC keeps the substrate
    identity as aluminium. It uses scalar core glTF PBR inputs only.
    """

    return material(
        model,
        key,
        ifc_name="RAL 7021 lacquered aluminium",
        category="aluminium",
        base_color=_source_rgb((47 / 255, 50 / 255, 52 / 255)),
        roughness=0.42,
        metallic=0.0,
        alpha=1.0,
        double_sided=False,
    )


def glass(model: Building, key: str) -> str:
    """Declare the glazing shared by windows and skylights.

    The glTF material uses alpha for transparency and metallic for reflectance.
    """

    return material(
        model,
        key,
        ifc_name="Glazing",
        category="glass",
        base_color=(0.8, 0.8, 0.8),
        roughness=0.5,
        metallic=0.5,
        alpha=0.5,
    )
