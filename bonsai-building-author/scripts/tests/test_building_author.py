"""Checks that run without Blender: declaration, validation, compilation.

Run from `scripts/`:

    python -m unittest discover -s tests

Anything needing a live Blender or IFC session belongs in a Bonsai MCP
session instead, per references/runtime-preflight.md.
"""

from __future__ import annotations

import ast
import inspect
import json
import math
import runpy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from building_author import (  # noqa: E402
    AuthoringError,
    Building,
    building,
    composed_window,
    composed_window_type,
    corner_opening,
    covering,
    door,
    driveway_gate,
    door_lining,
    door_panel,
    door_type,
    downspout,
    extend_to_structure,
    extrusion,
    fence,
    gate_fence_connections,
    gutter,
    material,
    project,
    pedestrian_gate,
    railing,
    roof as author_roof,
    roof_edge,
    roof_window,
    layer,
    site,
    slab,
    slab_type,
    space,
    storey,
    virtual_element,
    wall,
    wall_type,
    window,
    window_divider,
    window_lining,
    window_panel,
    window_rectangle,
    window_sill,
    window_triangle,
    window_type,
)
from building_author import (  # noqa: E402
    caps,
    compiler,
    composed_windows,
    gutters,
    junctions,
    polygons,
    procedures,
    railings,
    roof_windows,
    sills,
    skeleton,
    tiles,
    trims,
)
from building_author.compiler import (  # noqa: E402
    CompileError,
    SILL_RISE,
    covering_payload,
    corner_opening_payload,
    extend_to_structure_payload,
    gate_payload,
    gutter_payload,
    opening_payload,
    railing_payload,
    roof_payload,
    sill_payload,
    slab_payload,
    space_payload,
    wall_payload,
    walls_with_openings_payload,
)
from building_author.materials import (  # noqa: E402
    HERRINGBONE_WOOD_RECIPE,
    STYLIZED_PLASTER_RECIPE,
    STYLIZED_ROOF_TILES_RECIPE,
    anthracite_aluminium,
    glass,
    herringbone_wood,
    polyester_coated_steel,
    roof_tile,
    stucco,
)
from building_author.openings import (  # noqa: E402
    casement_window_type,
    corner_window,
    fixed_window_type,
    panel_door_type,
    sliding_door_type,
    sliding_window,
)
def minimal() -> Building:
    model = Building("test-house")
    project(model, "proj", name="Test Project")
    site(model, "plot", project="proj")
    building(model, "house", site="plot")
    storey(model, "ground", building="house", elevation=0.0)
    return model


def typed() -> Building:
    """A model carrying one three-layer wall type, thickness 0.30."""

    model = minimal()
    material(model, "plaster", ifc_name="Plaster", category="plaster",
             base_color=(0.9, 0.9, 0.88), roughness=0.9)
    material(model, "block", ifc_name="Block", category="masonry",
             base_color=(0.75, 0.75, 0.72), roughness=0.9)
    wall_type(model, "ext.300", predefined_type="SOLIDWALL", layers=[
        layer("plaster", 0.010, priority=10, category="Inner finish"),
        layer("block", 0.280, priority=90, category="LoadBearing"),
        layer("plaster", 0.010, priority=10, category="Outer finish"),
    ])
    return model


ROOF_MATERIAL_KEYS = {
    "top_material": "roof.top",
    "ceiling_material": "roof.ceiling",
    "side_material": "roof.side",
}


def roof(model: Building, key: str, **settings) -> str:
    """Declare the three test roof materials once, then author a roof."""

    existing = {operation.key for operation in model.operations}
    for index, material_key in enumerate(ROOF_MATERIAL_KEYS.values()):
        if material_key not in existing:
            material(
                model,
                material_key,
                ifc_name=material_key,
                category="roof",
                base_color=(0.2 + index * 0.1,) * 3,
                roughness=0.8,
            )
    arguments = dict(ROOF_MATERIAL_KEYS)
    arguments.update(settings)
    return author_roof(model, key, **arguments)


class DeclarationTest(unittest.TestCase):
    def test_material_emits_ifc_and_presentation(self):
        model = minimal()
        material(
            model,
            "brick",
            ifc_name="Brick",
            category="brick",
            base_color=(0.4, 0.1, 0.1),
            roughness=0.8,
        )
        kinds = [op.kind for op in model.operations]
        self.assertIn("material", kinds)
        self.assertIn("pbr-material", kinds)

    def test_presentation_targets_the_material_key(self):
        model = minimal()
        stucco(model, "stucco.white")
        pbr = next(o for o in model.operations if o.kind == "pbr-material")
        self.assertEqual(pbr.references["target"], "stucco.white")

    def test_wall_records_its_type_reference(self):
        model = typed()
        wall(model, "w1", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (4.0, 0.0)), height=3.0)
        w = next(o for o in model.operations if o.kind == "wall")
        self.assertEqual(w.references["wall_type"], "ext.300")

    def test_wall_type_references_every_layer_material(self):
        model = typed()
        t = next(o for o in model.operations if o.kind == "wall-type")
        self.assertEqual(t.references["layer.0.material"], "plaster")
        self.assertEqual(t.references["layer.1.material"], "block")

    def test_extend_to_structure_uses_ifc_relationship_roles(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (4.0, 0.0)), height=3.0)
        roof(model, "r", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        extend_to_structure(
            model,
            "w.top",
            relating_element="r",
            related_element="w",
        )
        operation = next(
            item for item in model.operations
            if item.kind == "extend-to-structure"
        )
        self.assertEqual(operation.references["relating_element"], "r")
        self.assertEqual(operation.references["related_element"], "w")
        self.assertEqual(operation.parameters["termination"], "UNDERSIDE")

    def test_extend_to_structure_accepts_a_top_surface_termination(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (4.0, 0.0)), height=3.0)
        roof(model, "r", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        extend_to_structure(
            model,
            "w.top",
            relating_element="r",
            related_element="w",
            termination="TOP_SURFACE",
        )
        operation = next(
            item for item in model.operations
            if item.kind == "extend-to-structure"
        )
        self.assertEqual(operation.parameters["termination"], "TOP_SURFACE")

    def test_extend_to_structure_rejects_an_unknown_termination(self):
        model = typed()
        with self.assertRaisesRegex(AuthoringError, "TOP_SURFACE, UNDERSIDE"):
            extend_to_structure(
                model,
                "w.top",
                relating_element="r",
                related_element="w",
                termination="TOP",
            )

    def test_roof_records_all_three_required_material_roles(self):
        model = minimal()
        roof(model, "r", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        operation = next(item for item in model.operations if item.kind == "roof")
        self.assertEqual(
            operation.references,
            {"storey": "ground", **ROOF_MATERIAL_KEYS},
        )
        parameters = inspect.signature(author_roof).parameters
        for role in ROOF_MATERIAL_KEYS:
            self.assertIs(parameters[role].default, inspect.Signature.empty)


class RecipeTest(unittest.TestCase):
    """Lock canonical recipe pointers and simplified render fallbacks."""

    def parameters(self, recipe, kind):
        model = minimal()
        recipe(model, "key")
        return next(o for o in model.operations if o.kind == kind).parameters

    def test_material_recipes_emit_recipe_path_and_ifc_fallbacks(self):
        recipes = (
            (
                stucco,
                STYLIZED_PLASTER_RECIPE,
                (0.8883463833645842, 0.7694818765965709, 0.6180238205957986),
                0.90,
            ),
            (
                roof_tile,
                STYLIZED_ROOF_TILES_RECIPE,
                (0.7166969120301967, 0.03940300726747273, 0.03940300726747273),
                0.62,
            ),
            (
                herringbone_wood,
                HERRINGBONE_WOOD_RECIPE,
                (0.00598105957261676, 0.005920947642698869, 0.005586980607524099),
                0.49,
            ),
        )

        for recipe, recipe_path, expected_color, expected_roughness in recipes:
            with self.subTest(material_recipe=recipe_path):
                model = minimal()
                recipe(model, "key")
                ifc = next(
                    operation
                    for operation in model.operations
                    if operation.kind == "material"
                )
                pbr = next(
                    operation
                    for operation in model.operations
                    if operation.kind == "pbr-material"
                )
                self.assertEqual(pbr.parameters["material_recipe"], recipe_path)
                self.assertEqual(ifc.parameters["base_color"], expected_color)
                self.assertEqual(pbr.parameters["base_color"], expected_color)
                self.assertEqual(pbr.parameters["roughness"], expected_roughness)

    def test_glass_matches_the_reference_pane(self):
        """Check the shared glazing preset."""
        p = self.parameters(glass, "pbr-material")
        self.assertEqual(p["base_color"], (0.8, 0.8, 0.8))
        self.assertEqual(p["metallic"], 0.5)
        self.assertEqual(p["roughness"], 0.5)
        self.assertEqual(p["alpha"], 0.5)

    def test_the_pack_declares_exactly_one_glazing(self):
        import building_author.materials as pack
        glazing = [
            name for name in dir(pack)
            if not name.startswith("_") and callable(getattr(pack, name))
            and "glaz" in (getattr(pack, name).__doc__ or "").lower()
        ]
        self.assertEqual(glazing, ["glass"])

    def test_glass_carries_transparency_into_ifc(self):
        p = self.parameters(glass, "material")
        self.assertEqual(p["alpha"], 0.5)

    def test_fence_coatings_are_opaque_core_glb_materials(self):
        for declaration, category in (
            (polyester_coated_steel, "steel"),
            (anthracite_aluminium, "aluminium"),
        ):
            with self.subTest(material=declaration.__name__):
                model = minimal()
                declaration(model, "fence.finish")
                ifc = next(
                    operation
                    for operation in model.operations
                    if operation.kind == "material"
                )
                pbr = next(
                    operation
                    for operation in model.operations
                    if operation.kind == "pbr-material"
                )
                self.assertEqual(ifc.parameters["category"], category)
                self.assertEqual(ifc.parameters["alpha"], 1.0)
                self.assertEqual(pbr.parameters["alpha"], 1.0)
                self.assertEqual(pbr.parameters["metallic"], 0.0)
                self.assertEqual(pbr.parameters["roughness"], 0.42)
                self.assertFalse(pbr.parameters["double_sided"])
                self.assertNotIn("material_recipe", pbr.parameters)

    def test_horizon_finish_preserves_its_published_ral_identity(self):
        model = minimal()
        anthracite_aluminium(model, "fence.finish")
        ifc = next(
            operation for operation in model.operations
            if operation.kind == "material"
        )
        self.assertEqual(ifc.parameters["ifc_name"],
                         "RAL 7021 lacquered aluminium")

    def test_presentation_resets_reused_opaque_materials_out_of_blend_mode(self):
        model = minimal()
        polyester_coated_steel(model, "fence.finish")
        source = model.blender_source()
        self.assertIn('else "OPAQUE"', source)
        self.assertIn('else "DITHERED"', source)
        self.assertIn('"double_sided": false', source)
        self.assertIn("use_backface_culling", source)


class ProceduralMaterialRecipeTest(unittest.TestCase):
    """Recipes are canonical; each carries its own one-line credit."""

    ROOT = Path(__file__).resolve().parents[2]
    THIRD_PARTY_RECIPES = {
        STYLIZED_ROOF_TILES_RECIPE: ("CC0", "ninao"),
        # The MM161 attribution string must travel with generated artifacts.
        HERRINGBONE_WOOD_RECIPE: ("CC-BY", "Kyrylo"),
        STYLIZED_PLASTER_RECIPE: ("CC0", "Tarox"),
    }
    ORIGINAL_RECIPES = {
        "references/material-recipes/honey-timber-facade.material.md":
            "original.honey-timber-facade",
    }

    def test_renderer_neutral_recipes_are_the_only_execution_contracts(self):
        recipe_dir = self.ROOT / "references" / "material-recipes"
        primitives = recipe_dir / "primitives.md"
        self.assertTrue(primitives.is_file(), primitives)
        self.assertIn("Renderer-neutral", primitives.read_text(encoding="utf-8"))

        for recipe_path, (license_name, author_name) in self.THIRD_PARTY_RECIPES.items():
            with self.subTest(material_recipe=recipe_path):
                self.assertTrue(recipe_path.endswith(".material.md"))
                recipe = self.ROOT / recipe_path
                self.assertTrue(recipe.is_file(), recipe)
                text = recipe.read_text(encoding="utf-8")
                lowered = text.casefold()
                self.assertTrue(text.startswith("---\n"))
                self.assertIn("schema: building-author/material-recipe/v1", text)
                self.assertIn("primitives.md", text)
                self.assertIn(license_name.casefold(), lowered)
                self.assertIn(author_name.casefold(), lowered)
                for contract_word in (
                    "mapping",
                    "outputs",
                    "visual",
                    "acceptance",
                ):
                    self.assertIn(contract_word, lowered)

        for recipe_path, recipe_id in self.ORIGINAL_RECIPES.items():
            with self.subTest(original_material_recipe=recipe_path):
                recipe = self.ROOT / recipe_path
                self.assertTrue(recipe.is_file(), recipe)
                text = recipe.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                self.assertIn("schema: building-author/material-recipe/v1", text)
                self.assertIn(f"id: {recipe_id}", text)
                self.assertIn("source_author: Project-authored original", text)
                self.assertIn("No third-party texture or graph incorporated", text)
                self.assertIn("primitives.md", text)
                self.assertIn("## Acceptance checks", text)
                self.assertNotIn("data:image", text)

        self.assertEqual(
            {path.name for path in recipe_dir.glob("*.material.md")},
            {Path(path).name for path in self.THIRD_PARTY_RECIPES}
            | {Path(path).name for path in self.ORIGINAL_RECIPES},
        )
        for obsolete in (
            "scripts/building_author/procedural_materials.py",
            "scripts/building_author/threejs_materials.mjs",
            "scripts/material_qa_blender.py",
        ):
            self.assertFalse((self.ROOT / obsolete).exists(), obsolete)


class ExampleMaterialRecipeTest(unittest.TestCase):
    def test_example_targets_facade_roof_covering_and_terrace(self):
        namespace = runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "example_build.py"),
            run_name="_building_author_example_material_test",
        )
        operations = {
            (operation.kind, operation.key): operation
            for operation in namespace["model"].operations
        }

        facade = operations[("wall-type", "ext.470")]
        outer_finishes = [
            entry
            for entry in facade.parameters["layers"]
            if entry["category"] == "Outer finish"
        ]
        self.assertEqual(
            [entry["material"] for entry in outer_finishes],
            ["stucco.white"],
        )

        roof = operations[("roof", "main-roof")]
        self.assertEqual(roof.parameters["covering_material"], "tile.terracotta")
        self.assertEqual(
            {role: roof.references[role] for role in ROOF_MATERIAL_KEYS},
            {
                "top_material": "concrete",
                "ceiling_material": "plaster.internal",
                "side_material": "stucco.white",
            },
        )
        self.assertEqual(roof.parameters["verge_trim_material"], "metal.zinc")
        roof_covering = operations[("roof-tiles", "main-roof.tiles")]
        self.assertEqual(roof_covering.references["material"], "tile.terracotta")

        bedroom = operations[("covering", "bedroom.flooring")]
        living = operations[("covering", "living-room.flooring")]
        self.assertEqual(bedroom.references["space"], "bedroom")
        self.assertEqual(bedroom.references["material"], "timber.flooring")
        self.assertEqual(living.references["space"], "living-room")
        self.assertEqual(living.references["material"], "tile.ceramic")
        self.assertNotIn("boundary", bedroom.parameters)

        internal_door = operations[("door", "bedroom-door")]
        self.assertEqual(internal_door.references["threshold_space"], "bedroom")
        compiled_coverings = covering_payload(namespace["model"])
        threshold = next(
            item
            for item in compiled_coverings["thresholds"]
            if item["source"] == "bedroom-door"
        )
        self.assertEqual(threshold["material"], "timber.flooring")
        self.assertEqual(threshold["thickness"], 0.015)

        terrace = operations[("slab", "terrace")]
        self.assertEqual(terrace.references["material"], "timber.decking")

        expected_recipes = {
            "stucco.white.pbr": STYLIZED_PLASTER_RECIPE,
            "tile.terracotta.pbr": STYLIZED_ROOF_TILES_RECIPE,
            "timber.decking.pbr": HERRINGBONE_WOOD_RECIPE,
            "timber.flooring.pbr": HERRINGBONE_WOOD_RECIPE,
        }
        for operation_key, recipe_path in expected_recipes.items():
            self.assertEqual(
                operations[("pbr-material", operation_key)].parameters[
                    "material_recipe"
                ],
                recipe_path,
            )

    def test_example_has_one_matching_street_fence_and_gate_family(self):
        namespace = runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "example_build.py"),
            run_name="_building_author_example_fence_test",
        )
        model = namespace["model"]
        model.validate()
        operations = {
            (operation.kind, operation.key): operation
            for operation in model.operations
        }
        fence_keys = (
            "boundary.street.west",
            "boundary.street.middle",
            "boundary.street.east",
        )
        gate_keys = (
            "boundary.street.wicket",
            "boundary.street.driveway",
        )
        for key in fence_keys:
            operation = operations[("railing", key)]
            self.assertEqual(
                operation.parameters["profile"], "fence.horizontal-slat"
            )
            self.assertEqual(operation.parameters["base_offset"], -0.300)
            self.assertEqual(
                operation.references["post_material"], "fence.aluminium"
            )
            self.assertEqual(
                operation.references["infill_material"], "fence.aluminium"
            )
        for key in gate_keys:
            operation = operations[("gate", key)]
            self.assertEqual(
                operation.parameters["profile"], "fence.horizontal-slat"
            )
            self.assertEqual(operation.references["material"], "fence.aluminium")

        west = operations[("railing", fence_keys[0])]
        middle = operations[("railing", fence_keys[1])]
        east = operations[("railing", fence_keys[2])]
        self.assertFalse(west.parameters["end_post"])
        self.assertFalse(middle.parameters["start_post"])
        self.assertFalse(middle.parameters["end_post"])
        self.assertFalse(east.parameters["start_post"])
        self.assertEqual(
            west.parameters["path"][1], namespace["WICKET_CONNECTIONS"][0]
        )
        self.assertEqual(
            middle.parameters["path"][0],
            namespace["WICKET_CONNECTIONS"][1],
        )
        self.assertEqual(
            middle.parameters["path"][1],
            namespace["DRIVEWAY_CONNECTIONS"][0],
        )
        self.assertEqual(
            east.parameters["path"][0],
            namespace["DRIVEWAY_CONNECTIONS"][1],
        )

        finish = operations[("pbr-material", "fence.aluminium.pbr")]
        self.assertEqual(finish.parameters["alpha"], 1.0)
        self.assertEqual(finish.parameters["metallic"], 0.0)
        compiled_gates = {entry["key"]: entry for entry in gate_payload(model)}
        self.assertEqual(set(compiled_gates), set(gate_keys))
        self.assertTrue(all(
            entry["position"][2] == -0.300
            for entry in compiled_gates.values()
        ))
        compile(model.ifc_source(), "<minimal-house-ifc>", "exec")
        compile(model.blender_source(), "<minimal-house-presentation>", "exec")


class ValidationTest(unittest.TestCase):
    def test_rejects_noncanonical_material_recipe_paths(self):
        invalid = (
            "",
            "/absolute.material.md",
            "C:/outside.material.md",
            "../escape.material.md",
            "wrong.json",
            "references/material-recipes/unused/missing.material.md",
            "references/material-recipes/missing.material.md",
        )
        for recipe_path in invalid:
            with self.subTest(material_recipe=recipe_path):
                model = minimal()
                with self.assertRaisesRegex(AuthoringError, "material_recipe"):
                    material(
                        model,
                        "m",
                        ifc_name="M",
                        category="c",
                        base_color=(0.1, 0.2, 0.3),
                        roughness=0.5,
                        material_recipe=recipe_path,
                    )

    def test_rejects_rgba_base_color(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            material(
                model,
                "m",
                ifc_name="M",
                category="c",
                base_color=(0.1, 0.2, 0.3, 1.0),
                roughness=0.5,
            )

    def test_rejects_alpha_above_one(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            material(
                model,
                "m",
                ifc_name="M",
                category="c",
                base_color=(0.1, 0.2, 0.3),
                roughness=0.5,
                alpha=1.5,
            )

    def test_rejects_non_boolean_double_sided_material_state(self):
        model = minimal()
        with self.assertRaisesRegex(AuthoringError, "double_sided"):
            material(
                model,
                "m",
                ifc_name="M",
                category="c",
                base_color=(0.1, 0.2, 0.3),
                roughness=0.5,
                double_sided=0,
            )

    def test_rejects_zero_length_wall(self):
        model = typed()
        with self.assertRaises(AuthoringError):
            wall(model, "w", storey="ground", wall_type="ext.300",
                 axis=((1.0, 1.0), (1.0, 1.0)), height=3.0)

    def test_rejects_bad_ifc_class(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            extrusion(
                model,
                "e",
                ifc_class="NotAnIfcClass",
                storey="ground",
                position=(0.0, 0.0, 0.0),
                size=(1.0, 1.0),
                height=1.0,
            )

    def test_rejects_unresolved_reference(self):
        model = typed()
        wall(model, "w", storey="missing-storey", wall_type="ext.300",
             axis=((0.0, 0.0), (1.0, 0.0)), height=3.0)
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_rejects_duplicate_key(self):
        model = typed()
        for _ in range(2):
            wall(model, "w", storey="ground", wall_type="ext.300",
                 axis=((0.0, 0.0), (1.0, 0.0)), height=3.0)
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_requires_exactly_one_project(self):
        with self.assertRaises(AuthoringError):
            Building("empty").validate()
        model = minimal()
        project(model, "second", name="Second")
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_extend_to_structure_requires_a_roof_or_slab_as_relating_element(self):
        model = typed()
        for key, y in (("a", 0.0), ("b", 1.0)):
            wall(model, key, storey="ground", wall_type="ext.300",
                 axis=((0.0, y), (4.0, y)), height=3.0)
        extend_to_structure(
            model,
            "a.top",
            relating_element="b",
            related_element="a",
        )
        with self.assertRaisesRegex(AuthoringError, "must be a roof or slab"):
            model.validate()

    def test_extend_to_structure_accepts_a_slab_as_relating_element(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (4.0, 0.0)), height=3.0)
        slab_type(model, "ceiling.200", layers=[
            layer("block", 0.2, priority=90, category="LoadBearing"),
        ])
        slab(model, "ceiling", storey="ground", slab_type="ceiling.200",
             boundary=SQUARE, base_offset=3.0)
        extend_to_structure(
            model,
            "w.top",
            relating_element="ceiling",
            related_element="w",
        )
        model.validate()

    def test_a_wall_names_only_one_structure_above(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (4.0, 0.0)), height=3.0)
        roof(model, "r1", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        roof(model, "r2", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        extend_to_structure(model, "w.r1", relating_element="r1",
                            related_element="w")
        extend_to_structure(model, "w.r2", relating_element="r2",
                            related_element="w")
        with self.assertRaisesRegex(AuthoringError, "only one structure above"):
            model.validate()

    def test_extend_to_structure_requires_a_wall_as_related_element(self):
        model = with_roof()
        roof(model, "other", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        extend_to_structure(
            model,
            "r.top",
            relating_element="r",
            related_element="other",
        )
        with self.assertRaisesRegex(AuthoringError, "must be a wall"):
            model.validate()


SQUARE = [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)]


def with_roof(**overrides) -> Building:
    model = minimal()
    settings = {
        "storey": "ground",
        "boundary": SQUARE,
        "angle": 40.0,
        "thickness": 0.30,
    }
    settings.update(overrides)
    roof(model, "r", **settings)
    return model


class OverhangTest(unittest.TestCase):
    def test_uniform_overhang_grows_the_polygon(self):
        edges = [
            (SQUARE[i], SQUARE[(i + 1) % 4], 0.5) for i in range(4)
        ]
        result = polygons.offset_polygon(edges)
        self.assertEqual(len(result), 4)
        for (x, y), (ox, oy) in zip(SQUARE, result):
            self.assertAlmostEqual(abs(ox - x), 0.5, places=9)
            self.assertAlmostEqual(abs(oy - y), 0.5, places=9)

    def test_zero_overhang_is_the_identity(self):
        edges = [(SQUARE[i], SQUARE[(i + 1) % 4], 0.0) for i in range(4)]
        for original, offset in zip(SQUARE, polygons.offset_polygon(edges)):
            self.assertAlmostEqual(original[0], offset[0], places=9)
            self.assertAlmostEqual(original[1], offset[1], places=9)

    def test_per_edge_overhang_mitres_the_corner(self):
        """Neighbours with different overhangs still meet at one corner."""
        overhangs = [0.5, 0.2, 0.5, 0.2]
        edges = [
            (SQUARE[i], SQUARE[(i + 1) % 4], overhangs[i]) for i in range(4)
        ]
        result = polygons.offset_polygon(edges)
        self.assertEqual(len(result), 4)
        # Corner 1 joins edge 0 (south, 0.5) and edge 1 (east, 0.2).
        self.assertAlmostEqual(result[1][0], 8.2, places=9)
        self.assertAlmostEqual(result[1][1], -0.5, places=9)

    def test_clockwise_boundary_still_grows(self):
        reversed_square = list(reversed(SQUARE))
        edges = [
            (reversed_square[i], reversed_square[(i + 1) % 4], 0.5)
            for i in range(4)
        ]
        result = polygons.offset_polygon(edges)
        self.assertGreater(polygons.bounds(result)[1], 8.0)

    def test_rejects_degenerate_boundary(self):
        with self.assertRaises(AuthoringError):
            polygons.offset_polygon([(SQUARE[0], SQUARE[1], 0.0)])


class TileLayoutTest(unittest.TestCase):
    """Check the layout grid and course offsets."""

    FACE = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]

    def rows(self, profile):
        grouped = {}
        for u, v in tiles.centres(self.FACE, profile):
            grouped.setdefault(round(v, 6), []).append(u)
        return grouped

    def test_spacing_is_the_module_so_tiles_touch(self):
        """Fixed step, not stretched: stretching is what left the gaps."""
        grouped = self.rows(tiles.CLAY_TILE)
        first = sorted(grouped[min(grouped)])
        gaps = {round(b - a, 6) for a, b in zip(first, first[1:])}
        self.assertEqual(gaps, {round(tiles.CLAY_TILE.width, 6)})

    def test_courses_step_by_the_module(self):
        vs = sorted(self.rows(tiles.CLAY_TILE))
        gaps = {round(b - a, 6) for a, b in zip(vs, vs[1:])}
        self.assertEqual(gaps, {round(tiles.CLAY_TILE.length, 6)})

    def test_grid_is_floor_snapped_not_face_fitted(self):
        """Anchor the grid at floor(min / module) * module.

        Every centre must land on that grid - offset by half a tile on
        staggered courses - rather than on one fitted to the face bounds.
        """
        face = [(1.1, 0.7), (6.0, 0.7), (6.0, 4.0), (1.1, 4.0)]
        tile = tiles.CLAY_TILE
        start_u = math.floor(1.1 / tile.width) * tile.width
        start_v = (math.floor(0.7 / tile.length) * tile.length
                   + tile.length / 2.0)

        for u, v in tiles.centres(face, tile):
            courses = (v - start_v) / tile.length
            self.assertAlmostEqual(courses, round(courses), places=6)
            stagger = tile.width / 2.0 if round(courses) % 2 else 0.0
            columns = (u - start_u - stagger) / tile.width
            self.assertAlmostEqual(columns, round(columns), places=6)

    def test_first_course_lower_edge_lands_on_the_eave(self):
        """Courses run from the eave upwards, not centred on it.

        Centring the first course on v = 0 buries half the eave tile below the
        roof edge, so cropping leaves a stunted first band instead of a full
        course.
        """
        tile = tiles.CLAY_TILE
        rows = sorted({v for _, v in tiles.centres(self.FACE, tile)})
        self.assertAlmostEqual(rows[0], tile.length / 2.0, places=9)
        self.assertGreater(rows[0], 0.0)

    def test_every_course_is_a_full_module_above_the_eave(self):
        tile = tiles.CLAY_TILE
        rows = sorted({round(v, 6) for _, v in tiles.centres(self.FACE, tile)})
        for index, v in enumerate(rows):
            self.assertAlmostEqual(
                v, tile.length / 2.0 + index * tile.length, places=6)

    def test_a_non_lapping_field_clears_the_face_and_every_course(self):
        """No tray face is coplanar with another course or the crop prism.

        See `tiles.course_clearance`: butting trays would otherwise hand the
        crop's boolean exact coincidences it can silently resolve into a hole,
        and the standing seam is the one covering with no tilt to avoid them.
        """

        seam = tiles.STANDING_SEAM
        rows = sorted({v for _, v in tiles.centres(self.FACE, seam)})
        clearances = [tiles.course_clearance(v, seam) for v in rows]
        self.assertTrue(all(clearance > 0.0 for clearance in clearances))
        steps = {
            round(later - earlier, 9)
            for earlier, later in zip(clearances, clearances[1:])
        }
        self.assertEqual(steps, {round(tiles.COURSE_CLEARANCE, 9)})
        self.assertLess(max(clearances), 0.005)
        self.assertGreaterEqual(min(clearances), tiles.FIELD_LIFT)
        # a lapping profile needs none of it: its own tilt separates courses
        self.assertEqual(tiles.course_clearance(rows[0], tiles.CLAY_TILE), 0.0)

    def test_grid_ignores_where_the_face_happens_to_start(self):
        """Shifting the face by a whole module reproduces the same grid."""
        tile = tiles.CLAY_TILE
        a = tiles.centres(self.FACE, tile)
        shifted = [(u + tile.width, v + tile.length) for u, v in self.FACE]
        b = tiles.centres(shifted, tile)
        self.assertEqual(
            [(round(u, 6), round(v, 6)) for u, v in a],
            [(round(u - tile.width, 6), round(v - tile.length, 6))
             for u, v in b],
        )

    def test_shifted_layout_staggers_by_half_a_tile(self):
        """Half the module, not half the spacing."""
        grouped = self.rows(tiles.CLAY_TILE)
        ordered = [min(grouped[v]) for v in sorted(grouped)]
        self.assertAlmostEqual(ordered[1] - ordered[0],
                               tiles.CLAY_TILE.width / 2.0, places=9)

    def test_straight_layout_aligns_every_course(self):
        profile = tiles.TileProfile(
            key="t", width=0.3, length=0.2,
            build=tiles.clay_tile_mesh, stagger=0.0)
        grouped = {}
        for u, v in tiles.centres(self.FACE, profile):
            grouped.setdefault(round(v, 6), []).append(u)
        ordered = [min(grouped[v]) for v in sorted(grouped)]
        for value in ordered[1:]:
            self.assertAlmostEqual(value, ordered[0], places=9)

    def test_a_tile_is_kept_when_any_corner_overlaps(self):
        """Deliberate over-coverage: trim hides the overhang, no cutting."""
        tile = tiles.CLAY_TILE
        overhanging = [
            (u, v) for u, v in tiles.centres(self.FACE, tile)
            if u - tile.width / 2 < -1e-9 or u + tile.width / 2 > 6.0 + 1e-9
        ]
        self.assertTrue(overhanging)

    def test_triangular_face_keeps_only_covered_tiles(self):
        triangle = [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0)]
        self.assertLess(
            len(tiles.centres(triangle, tiles.CLAY_TILE)),
            len(tiles.centres(self.FACE, tiles.CLAY_TILE)))

    def test_layout_is_identical_for_different_tile_shapes(self):
        """Layout reads width, length and layout - never the shape."""
        boxy = tiles.TileProfile(key="a", width=0.31, length=0.2056,
                                 build=tiles.clay_tile_mesh)
        wavy = tiles.TileProfile(key="b", width=0.31, length=0.2056,
                                 build=tiles.celtic_tile_mesh)
        self.assertEqual(tiles.centres(self.FACE, boxy),
                         tiles.centres(self.FACE, wavy))

    def test_clay_and_pantile_share_layout_module(self):
        for profile in (tiles.CLAY_TILE, tiles.CELTIC_TILE):
            with self.subTest(profile.key):
                self.assertAlmostEqual(profile.width, 0.3, places=6)
                self.assertAlmostEqual(profile.length, 0.4, places=6)

    def test_headlap_is_a_sane_fraction_of_the_tile(self):
        """A 0.47 tile on a 0.4 course laps 0.07, not half its own length."""
        for profile in (tiles.CLAY_TILE, tiles.CELTIC_TILE):
            with self.subTest(profile.key):
                verts, _, _, _ = profile.geometry()
                mesh_length = max(v[1] for v in verts) - min(v[1] for v in verts)
                headlap = mesh_length - profile.length
                self.assertGreater(headlap, 0.0)
                self.assertLess(headlap, profile.length / 2.0)

    def test_authored_tilt_gives_one_thickness_of_rise_per_course(self):
        """Why 6 degrees is the right tilt for a 0.4 course and 0.04 tile."""
        rise = tiles.CLAY_TILE.length * math.tan(tiles.TILE_TILT)
        self.assertAlmostEqual(rise, 0.04, places=2)
        self.assertAlmostEqual(math.degrees(tiles.TILE_TILT), 6.0, places=6)

    def test_rejects_unknown_profile(self):
        with self.assertRaises(AuthoringError):
            tiles.profile("tile.nonexistent")

    def test_rejects_a_face_with_too_few_points(self):
        with self.assertRaises(AuthoringError):
            tiles.centres([(0.0, 0.0), (1.0, 0.0)], tiles.CLAY_TILE)


class TileProcedureTest(unittest.TestCase):
    """Check the mesh contract for every tile procedure.

    The contract every procedure must meet is checked against all of them, but
    the procedures themselves share no code.
    """

    def procedures(self):
        return sorted(tiles.PROFILES.values(), key=lambda p: p.key)

    @staticmethod
    def signed_volume(mesh):
        """Six times the enclosed volume, signed by the face winding."""

        verts, faces, _, _ = mesh
        total = 0.0
        for face in faces:
            for i in range(1, len(face) - 1):
                a, b, c = verts[face[0]], verts[face[i]], verts[face[i + 1]]
                total += (
                    a[0] * (b[1] * c[2] - b[2] * c[1])
                    - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])
                ) / 6.0
        return total

    def test_every_procedure_faces_outward(self):
        """An inside-out field is deleted whole by the crop, silently.

        `crop_to_face` intersects each field with a prism, and INTERSECT
        against an inverted solid returns nothing at all - no error, no
        warning, just a roof with no covering on it. Every other check here
        passes on an inverted mesh.
        """
        for profile in self.procedures():
            with self.subTest(profile.key):
                self.assertGreater(self.signed_volume(profile.geometry()), 0.0)

    def test_no_procedure_repeats_a_point(self):
        """A repeated point is a zero-area face, and the EXACT solver
        rejects the whole field rather than the one face.
        """
        for profile in self.procedures():
            with self.subTest(profile.key):
                verts, faces, _, _ = profile.geometry()
                for face in faces:
                    for i in range(len(face)):
                        self.assertNotEqual(
                            verts[face[i]],
                            verts[face[(i + 1) % len(face)]],
                        )

    def test_every_procedure_returns_a_closed_mesh(self):
        for profile in self.procedures():
            with self.subTest(profile.key):
                _, faces, _, _ = profile.geometry()
                edges = {}
                for face in faces:
                    for i in range(len(face)):
                        pair = frozenset((face[i], face[(i + 1) % len(face)]))
                        edges[pair] = edges.get(pair, 0) + 1
                self.assertTrue(all(n == 2 for n in edges.values()))

    def test_mesh_fits_within_its_module_across_the_eave(self):
        """Never wider than the grid step, or neighbours would collide.

        The shortfall is the joint between tiles - 0.2928 in a 0.3 module -
        so this checks it fits and stays snug, not that it matches exactly.
        """
        for profile in self.procedures():
            with self.subTest(profile.key):
                verts, _, _, _ = profile.geometry()
                width = max(v[0] for v in verts) - min(v[0] for v in verts)
                # A folded covering is drawn as a centreline, so half its
                # gauge falls outside the bay it is stated at. That is the
                # sheet, not a collision with the next bay.
                gauge = max(v[2] for v in verts) - min(v[2] for v in verts)
                self.assertLessEqual(width, profile.width + gauge)
                self.assertGreater(width, profile.width * 0.9)

    def test_mesh_is_longer_than_its_course_so_it_laps(self):
        """The lap lives in the procedure, not in the layout.

        A covering that does not lap runs exactly its own course instead:
        a standing seam tray is one sheet from eave to ridge, so its
        `length` is the tray and there is no exposure to overhang.
        """
        for profile in self.procedures():
            with self.subTest(profile.key):
                verts, _, _, _ = profile.geometry()
                ys = [v[1] for v in verts]
                if profile.laps:
                    self.assertGreater(max(ys) - min(ys), profile.length)
                else:
                    self.assertAlmostEqual(max(ys) - min(ys),
                                           profile.length, places=9)

    def test_head_sits_on_the_plane(self):
        for profile in self.procedures():
            with self.subTest(profile.key):
                verts, _, _, _ = profile.geometry()
                half = max(v[1] for v in verts)
                head = [v for v in verts if abs(v[1] - half) < 1e-9]
                # Within half a gauge: a folded sheet is drawn about its
                # own centreline, so its underside sits that far below.
                gauge = max(v[2] for v in verts) - min(v[2] for v in verts)
                self.assertAlmostEqual(min(v[2] for v in head), 0.0,
                                       delta=gauge)

    def test_tail_rides_up_so_courses_lap(self):
        """Only where there is a lap: a tray has none to lift clear of."""
        for profile in self.procedures():
            if not profile.laps:
                continue
            with self.subTest(profile.key):
                verts, _, _, _ = profile.geometry()
                half = max(v[1] for v in verts)
                head = min(v[2] for v in verts if abs(v[1] - half) < 1e-9)
                tail = min(v[2] for v in verts if abs(v[1] + half) < 1e-9)
                self.assertGreater(tail, head)

    def test_no_face_collapses_to_a_zero_area_uv(self):
        for profile in self.procedures():
            with self.subTest(profile.key):
                _, faces, uvs, _ = profile.geometry()
                self.assertEqual(len(uvs), len(faces))
                for face, face_uvs in zip(faces, uvs):
                    self.assertEqual(len(face), len(face_uvs))
                    area = 0.0
                    for i in range(len(face_uvs)):
                        u1, v1 = face_uvs[i]
                        u2, v2 = face_uvs[(i + 1) % len(face_uvs)]
                        area += u1 * v2 - u2 * v1
                    self.assertGreater(abs(area) / 2.0, 1e-6)

    def test_procedures_are_deterministic(self):
        for profile in self.procedures():
            with self.subTest(profile.key):
                self.assertEqual(profile.geometry(), profile.geometry())

    def test_clay_is_the_plain_box(self):
        verts, faces, _, _ = tiles.clay_tile_mesh()
        self.assertEqual(len(verts), 8)
        self.assertEqual(len(faces), 6)

    def test_celtic_has_a_rolled_edge(self):
        """Its section is not flat, unlike clay's."""
        verts, faces, _, _ = tiles.celtic_tile_mesh()
        self.assertGreater(len(verts), 8)
        head = max(v[1] for v in verts)
        heights = {round(v[2], 4) for v in verts if abs(v[1] - head) < 1e-9}
        self.assertGreater(len(heights), 2)

    def test_geometry_validates_the_profile(self):
        broken = tiles.TileProfile(
            key="t", width=0.0, length=0.2, build=tiles.clay_tile_mesh,
        )
        with self.assertRaises(AuthoringError):
            broken.geometry()

    def test_every_tile_names_a_cap_that_exists(self):
        for profile in self.procedures():
            with self.subTest(profile.key):
                self.assertIsNotNone(caps.profile(profile.cap))


class CapSeatingTest(unittest.TestCase):
    """Where a cap sits is derived from the covering and the run's own fold."""

    #: A clay tile's own envelope, and a 30 degree roof's ridge bisector.
    ENVELOPE = 0.089
    COSINE = math.cos(math.radians(30.0))

    def test_tangent_is_the_roof_pitch_on_a_ridge(self):
        """A ridge's bisector is vertical, so the fold angle is the pitch."""
        seat = caps.seating(self.ENVELOPE, self.COSINE, caps.HALF_ROUND.foot)
        self.assertAlmostEqual(seat.tangent, math.tan(math.radians(30.0)),
                               places=9)

    def test_the_foot_lands_on_the_covering_surface(self):
        """The whole point of the seat: the skirt starts where the tiles are.

        The covering's top surface, measured from the arris along the cap's
        own up, is `envelope / cosine - across * tangent`. Seating the foot at
        exactly that offset is what lets the skirt then lie flat along it.
        """
        for cap in sorted(caps.PROFILES.values(), key=lambda p: p.key):
            with self.subTest(cap.key):
                seat = caps.seating(self.ENVELOPE, self.COSINE, cap.foot)
                surface = (
                    self.ENVELOPE / self.COSINE - cap.foot * seat.tangent
                )
                self.assertAlmostEqual(seat.seat, surface, places=9)

    def test_the_skirt_lies_along_the_covering_for_its_whole_width(self):
        """Not only its foot: the tip has to land on the same plane."""
        for cap in sorted(caps.PROFILES.values(), key=lambda p: p.key):
            with self.subTest(cap.key):
                seat = caps.seating(self.ENVELOPE, self.COSINE, cap.foot)
                tip = cap.width / 2.0
                tip_up = seat.seat - (tip - cap.foot) * seat.tangent
                surface = self.ENVELOPE / self.COSINE - tip * seat.tangent
                self.assertAlmostEqual(tip_up, surface, places=9)

    def test_a_steeper_roof_seats_the_cap_lower(self):
        shallow = caps.seating(self.ENVELOPE, math.cos(math.radians(15.0)),
                               caps.HALF_ROUND.foot)
        steep = caps.seating(self.ENVELOPE, math.cos(math.radians(45.0)),
                             caps.HALF_ROUND.foot)
        self.assertGreater(shallow.seat, steep.seat)

    def test_the_seat_never_sinks_the_cap_into_the_roof(self):
        """A thin covering on a steep roof clamps rather than going negative."""
        seat = caps.seating(0.001, math.cos(math.radians(60.0)),
                            caps.HALF_ROUND.foot)
        self.assertEqual(seat.seat, 0.0)

    def test_a_flat_roof_seats_by_the_envelope_alone(self):
        seat = caps.seating(self.ENVELOPE, 1.0, caps.HALF_ROUND.foot)
        self.assertAlmostEqual(seat.tangent, 0.0, places=12)
        self.assertAlmostEqual(seat.seat, self.ENVELOPE, places=12)

    def test_rejects_a_cosine_outside_its_range(self):
        for cosine in (0.0, -0.5, 1.5):
            with self.subTest(cosine), self.assertRaises(AuthoringError):
                caps.seating(self.ENVELOPE, cosine, caps.HALF_ROUND.foot)

    def test_rejects_a_negative_envelope(self):
        with self.assertRaises(AuthoringError):
            caps.seating(-0.01, self.COSINE, caps.HALF_ROUND.foot)


class CapLayoutTest(unittest.TestCase):
    """The fitted module, and the one rule that keeps a run gapless."""

    def runs(self):
        """Run lengths from far shorter than a piece to far longer."""

        # All above the longest nose in the registry: an arris shorter than
        # the closure that has to finish it is refused, not fitted.
        return [0.25, 0.39, 0.4, 0.41, 0.75, 1.0, 2.0, 3.4, 5.0, 12.37]

    def test_the_pieces_exactly_span_the_run(self):
        for cap in sorted(caps.PROFILES.values(), key=lambda p: p.key):
            for length in self.runs():
                with self.subTest(cap.key, length=length):
                    spacing = caps.spacing(length, cap)
                    self.assertAlmostEqual(spacing.stations[0], 0.0, places=12)
                    # The last piece's own tip, nose included, lands on the
                    # arris - not its body's end. Anything else overhangs the
                    # eave by a nose.
                    self.assertAlmostEqual(
                        spacing.stations[-1] + spacing.piece, length, places=9
                    )

    def test_the_step_never_stretches_past_the_module(self):
        """Rounding up can only compress; rounding to nearest can stretch."""
        for cap in sorted(caps.PROFILES.values(), key=lambda p: p.key):
            for length in self.runs():
                with self.subTest(cap.key, length=length):
                    spacing = caps.spacing(length, cap)
                    self.assertLessEqual(spacing.step, cap.module + 1e-12)

    def test_consecutive_pieces_never_leave_a_gap(self):
        """Check cap overlap even on short runs.

        Each piece reaches `piece` from its own station, and the next starts
        one `step` along, so the socket engages exactly while `piece >= step`.
        """
        for cap in sorted(caps.PROFILES.values(), key=lambda p: p.key):
            for length in self.runs():
                with self.subTest(cap.key, length=length):
                    spacing = caps.spacing(length, cap)
                    self.assertGreaterEqual(spacing.piece, spacing.step)
                    self.assertAlmostEqual(
                        spacing.piece - spacing.step, cap.nose, places=12
                    )

    def test_a_run_barely_longer_than_its_nose_gets_one_piece(self):
        spacing = caps.spacing(0.25, caps.HALF_ROUND)
        self.assertEqual(len(spacing.stations), 1)
        self.assertAlmostEqual(spacing.piece, 0.25, places=12)

    def test_rejects_a_run_shorter_than_the_nose_that_closes_it(self):
        with self.assertRaises(AuthoringError) as caught:
            caps.spacing(caps.HALF_ROUND.nose * 0.5, caps.HALF_ROUND)
        self.assertIn("shorter than", str(caught.exception))

    def test_a_run_of_whole_modules_is_not_compressed(self):
        cap = caps.HALF_ROUND
        spacing = caps.spacing(cap.module * 6.0 + cap.nose, cap)
        self.assertEqual(len(spacing.stations), 6)
        self.assertAlmostEqual(spacing.step, cap.module, places=12)

    def test_rejects_a_run_with_no_length(self):
        for length in (0.0, -1.0):
            with self.subTest(length), self.assertRaises(AuthoringError):
                caps.spacing(length, caps.HALF_ROUND)


class CapProcedureTest(unittest.TestCase):
    """Check the mesh contract for every cap procedure."""

    LENGTH = 0.40

    def procedures(self):
        return sorted(caps.PROFILES.values(), key=lambda p: p.key)

    #: A relief every lipped cap has something to close over.
    RELIEF = 0.040

    def seating(self, cap):
        return caps.seating(0.089, math.cos(math.radians(30.0)), cap.foot,
                            self.RELIEF)

    def geometry(self, cap):
        return cap.geometry(self.seating(cap), self.LENGTH)

    def test_every_procedure_returns_a_closed_mesh(self):
        for cap in self.procedures():
            with self.subTest(cap.key):
                _, faces, _, _ = self.geometry(cap)
                edges = {}
                for face in faces:
                    for i in range(len(face)):
                        pair = frozenset((face[i], face[(i + 1) % len(face)]))
                        edges[pair] = edges.get(pair, 0) + 1
                self.assertTrue(all(n == 2 for n in edges.values()))

    def test_every_procedure_names_one_role(self):
        for cap in self.procedures():
            with self.subTest(cap.key):
                self.assertEqual(procedures.roles(self.geometry(cap)), ["cap"])

    def test_the_section_is_no_wider_than_the_profile_says(self):
        """The one dimension a run's neighbours and the covering both rely on."""
        for cap in self.procedures():
            with self.subTest(cap.key):
                verts, _, _, _ = self.geometry(cap)
                across = [v[0] for v in verts]
                width = max(across) - min(across)
                # Half the sheet thickness sits outside the centreline at each
                # tip, which is the only thing the stated width excludes.
                self.assertLessEqual(width, cap.width + cap.thickness + 1e-9)
                self.assertGreater(width, cap.width * 0.95)

    def test_the_sweep_runs_the_length_it_was_given(self):
        for cap in self.procedures():
            with self.subTest(cap.key):
                verts, _, _, _ = self.geometry(cap)
                along = [v[2] for v in verts]
                self.assertAlmostEqual(min(along), 0.0, places=12)
                self.assertAlmostEqual(max(along), self.LENGTH, places=12)

    def test_the_barrel_closes_over_at_the_foot(self):
        """The dome: the run's last piece is looked at from directly below.

        Not a plate across the mouth - that closes the hole and still reads
        as a tube sawn off. The barrel has to come down onto its own skirts,
        which is what makes one repeated mesh finish properly at an eave.
        """
        for cap in self.procedures():
            with self.subTest(cap.key):
                verts, _, _, _ = self.geometry(cap)
                # The body carries no intermediate rings - it is one band from
                # the head's inset to where the dome starts - so this is the
                # station that has the section at full height.
                full = max(
                    v[1] for v in verts if abs(v[2] - cap.nose) < 1e-9
                )
                mouth = max(
                    v[1] for v in verts if abs(v[2] - self.LENGTH) < 1e-9
                )
                seat = self.seating(cap).seat
                self.assertLess(mouth - seat, (full - seat) * 0.5)

    def test_the_dome_falls_away_monotonically(self):
        """A quarter ellipse, so it leaves the barrel tangent and arrives flat.

        Sampled station by station: a closure that rose again anywhere would
        read as a bulge rather than as a moulded end.
        """
        for cap in self.procedures():
            with self.subTest(cap.key):
                verts, _, _, _ = self.geometry(cap)
                crowns = {}
                for x, up, z in verts:
                    key = round(z, 6)
                    crowns[key] = max(crowns.get(key, up), up)
                dome = [
                    crowns[z] for z in sorted(crowns)
                    if z > self.LENGTH - cap.nose - 1e-9
                ]
                for near, far in zip(dome, dome[1:]):
                    self.assertLessEqual(far, near + 1e-9)

    def test_the_head_is_drawn_in_under_the_dome_that_covers_it(self):
        """Why one mesh can repeat: the next piece's nose fits over this head."""
        for cap in self.procedures():
            with self.subTest(cap.key):
                verts, _, _, _ = self.geometry(cap)
                head = max(v[1] for v in verts if abs(v[2]) < 1e-9)
                body = max(
                    v[1] for v in verts
                    if abs(v[2] - cap.nose) < 1e-9
                )
                self.assertAlmostEqual(body - head, cap.inset, delta=1e-4)
                # And by more than the sheet, or the two would z-fight.
                self.assertGreater(cap.inset, cap.thickness)

    def test_the_skirts_hold_their_width_along_the_body(self):
        """They lie on the covering for the body's whole length.

        Over the dome they pull in with everything else - past the last course
        there is nothing left for them to lie on, and a tip that stayed full
        width would end the piece in a flat strip.
        """
        for cap in self.procedures():
            with self.subTest(cap.key):
                verts, _, _, _ = self.geometry(cap)
                body = [
                    max(abs(v[0]) for v in verts if abs(v[2] - station) < 1e-9)
                    for station in (0.0, cap.nose, self.LENGTH - cap.nose)
                ]
                self.assertAlmostEqual(min(body), max(body), delta=1e-6)
                mouth = max(
                    abs(v[0]) for v in verts if abs(v[2] - self.LENGTH) < 1e-9
                )
                self.assertLess(mouth, max(body) * 0.5)

    def test_the_crown_stands_over_the_foot(self):
        for cap in self.procedures():
            with self.subTest(cap.key):
                seat = self.seating(cap)
                verts, _, _, _ = self.geometry(cap)
                self.assertGreater(
                    max(v[1] for v in verts), seat.seat + cap.crown * 0.9
                )

    def test_every_cap_faces_outward(self):
        """An inside-out cap renders with its lighting inverted, and nothing
        else here would notice.

        It passes the closed-mesh check, the point-count check and every
        dimension test. `_wound` normalises the section's winding so a
        procedure can draw its own in whichever direction reads best, and this
        is what says the normalisation works - the same signed-volume guard
        that caught `standing_seam_mesh` shipping inverted.
        """
        for cap in self.procedures():
            with self.subTest(cap.key):
                self.assertGreater(
                    TileProcedureTest.signed_volume(self.geometry(cap)), 0.0
                )

    def test_the_section_is_solid_rather_than_a_shell(self):
        """A hollow cap is a tunnel running down every ridge and hip.

        The skirts only touch a corrugated covering's high points, so each low
        point is a slot into that tunnel - a dark mark per bay on the pantile
        and the standing seam. Solid, there is nothing to see into, and it is
        half the geometry besides, since nothing ever sees a wall's inside.

        Asked as a question about the void rather than about area: the point
        under the crown is *inside* the material. A shell has the barrel's
        middle in open air, and no threshold on area can say so for all three
        - their gauges differ by twenty times, so a shell's own section runs
        anywhere from a fraction of a solid one to thirteen times it.
        """
        for cap in self.procedures():
            with self.subTest(cap.key):
                verts, _, _, _ = self.geometry(cap)
                section = [(v[0], v[1]) for v in verts if abs(v[2]) < 1e-9]
                # The crown is a point on some caps and a flat on others, so
                # take the section's own highest point rather than the axis's.
                crest = max(up for _, up in section)
                floor = min(up for across, up in section if abs(across) < 1e-9)
                under_crown = (0.0, (crest + floor) / 2.0)
                self.assertTrue(polygons.contains(under_crown, section))

    def test_no_face_collapses_to_a_zero_area_uv(self):
        for cap in self.procedures():
            with self.subTest(cap.key):
                _, faces, uvs, _ = self.geometry(cap)
                for face, face_uvs in zip(faces, uvs):
                    self.assertEqual(len(face), len(face_uvs))
                    area = 0.0
                    for i in range(len(face_uvs)):
                        u1, v1 = face_uvs[i]
                        u2, v2 = face_uvs[(i + 1) % len(face_uvs)]
                        area += u1 * v2 - u2 * v1
                    self.assertGreater(abs(area) / 2.0, 1e-9)

    def test_procedures_are_deterministic(self):
        for cap in self.procedures():
            with self.subTest(cap.key):
                self.assertEqual(self.geometry(cap), self.geometry(cap))

    def test_each_covering_names_a_cap_of_its_own(self):
        """Three coverings, three caps, no two sharing.

        And one cap per covering, used on its ridges and its hips alike -
        `edge_kind` tells the two apart and deliberately nothing here does.
        """
        chosen = [profile.cap for profile in tiles.PROFILES.values()]
        self.assertEqual(len(chosen), len(set(chosen)))
        self.assertEqual(set(chosen), set(caps.PROFILES))

    def test_the_three_designs_are_distinct_shapes(self):
        """Not one silhouette with a parameter: different point counts."""
        counts = {
            cap.key: len(self.geometry(cap)[0]) for cap in self.procedures()
        }
        self.assertEqual(len(set(counts.values())), len(counts), counts)

    def tip_fall(self, cap, relief):
        """How far the skirt turns down at its outermost point."""

        verts, _, _, _ = cap.geometry(
            caps.seating(0.089, math.cos(math.radians(30.0)), cap.foot, relief),
            self.LENGTH,
        )
        tip = max(abs(v[0]) for v in verts)
        at_tip = [v[1] for v in verts if abs(abs(v[0]) - tip) < 1e-6]
        return max(at_tip) - min(at_tip)

    def test_the_lip_is_the_relief_and_nothing_else(self):
        """A covering with relief gets a lip; one without gets a straight skirt.

        There is no flag saying which: the turn-down *is* the relief, so a
        flat covering disables it by having none. That is why `tile.clay`
        takes a plain skirt without anyone selecting one.
        """
        for cap in self.procedures():
            with self.subTest(cap.key):
                self.assertGreater(
                    self.tip_fall(cap, self.RELIEF), self.RELIEF * 0.9
                )
                self.assertLess(
                    self.tip_fall(cap, 0.0), cap.thickness * 1.5
                )

    def test_a_lip_tracks_the_relief_it_closes(self):
        """Derived from the covering, not stated on the profile."""
        for cap in self.procedures():
            with self.subTest(cap.key):
                self.assertAlmostEqual(
                    self.tip_fall(cap, 0.050) - self.tip_fall(cap, 0.010),
                    0.040,
                    places=9,
                )


    def test_geometry_validates_the_profile(self):
        broken = caps.CapProfile(
            key="c", width=0.3, foot=0.2, crown=0.1, thickness=0.01,
            module=0.4, nose=0.05, inset=0.02, rim=0.012,
            build=caps.half_round_cap_mesh,
        )
        with self.assertRaises(AuthoringError) as caught:
            broken.geometry(self.seating(caps.HALF_ROUND), self.LENGTH)
        self.assertIn("no skirt", str(caught.exception))

    def test_rejects_a_piece_with_no_length(self):
        with self.assertRaises(AuthoringError):
            caps.HALF_ROUND.geometry(self.seating(caps.HALF_ROUND), 0.0)


class WindowProcedureTest(unittest.TestCase):
    """Check the skylight frame and glazing meshes."""

    WIDTH, HEIGHT = 0.94, 1.40

    def geometry(self):
        return roof_windows.standard_roof_window_mesh(self.WIDTH, self.HEIGHT)

    def shells(self):
        """Split the mesh into connected components."""
        _, faces, _, _ = self.geometry()
        parent = {}

        def find(x):
            root = x
            while parent.setdefault(root, root) != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        for face in faces:
            for vertex in face[1:]:
                first, second = find(face[0]), find(vertex)
                if first != second:
                    parent[first] = second
        groups = {}
        for face in faces:
            groups.setdefault(find(face[0]), []).append(face)
        return list(groups.values())

    def test_is_frame_sash_and_glazing(self):
        """Three shells, like a real roof window - not one ring and a pane."""
        self.assertEqual(len(self.shells()), 3)

    def test_every_shell_is_closed(self):
        for index, faces in enumerate(self.shells()):
            with self.subTest(shell=index):
                edges = {}
                for face in faces:
                    for slot in range(len(face)):
                        pair = frozenset(
                            (face[slot], face[(slot + 1) % len(face)])
                        )
                        edges[pair] = edges.get(pair, 0) + 1
                self.assertTrue(all(n == 2 for n in edges.values()))

    def test_no_two_shells_share_a_coordinate_plane(self):
        """The z-fighting guard.

        A pane coplanar with the frame reveal can flicker in the renderer.
        Keep the frame and pane faces separated.
        """
        verts, _, _, _ = self.geometry()
        planes = []
        for faces in self.shells():
            used = {index for face in faces for index in face}
            planes.append(
                [
                    {round(verts[index][axis], 6) for index in used}
                    for axis in (0, 1, 2)
                ]
            )
        for first in range(len(planes)):
            for second in range(first + 1, len(planes)):
                for axis in (0, 1, 2):
                    shared = planes[first][axis] & planes[second][axis]
                    self.assertFalse(
                        shared,
                        f"shells {first} and {second} share axis {axis} "
                        f"planes {sorted(shared)}",
                    )

    def test_frame_laps_beyond_the_opening(self):
        """The lap is what covers the tiles the opening cut."""
        verts, _, _, _ = self.geometry()
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        self.assertAlmostEqual(max(xs) - min(xs),
                               self.WIDTH + 2 * roof_windows.FLASHING, places=9)
        self.assertAlmostEqual(max(ys) - min(ys),
                               self.HEIGHT + 2 * roof_windows.FLASHING, places=9)

    def test_daylight_matches_the_declared_opening(self):
        """The frame's inner edge is the hole cut in the roof."""
        verts, _, _, _ = self.geometry()
        xs = sorted({round(v[0], 6) for v in verts})
        self.assertAlmostEqual(xs[1], -self.WIDTH / 2.0, places=6)
        self.assertAlmostEqual(xs[-2], self.WIDTH / 2.0, places=6)

    def test_glazing_floats_inside_the_sash(self):
        verts, _, _, _ = self.geometry()
        zs = sorted({round(v[2], 6) for v in verts})
        self.assertGreater(zs[0], -0.05)
        self.assertAlmostEqual(zs[-1], roof_windows.UPSTAND, places=6)

    def test_geometry_is_deterministic(self):
        self.assertEqual(self.geometry(), self.geometry())

    def test_rejects_a_window_too_small_for_its_frame(self):
        with self.assertRaises(AuthoringError):
            roof_windows.standard_roof_window_mesh(0.05, 0.05)

    def test_rejects_a_nonpositive_size(self):
        with self.assertRaises(AuthoringError):
            roof_windows.standard_roof_window_mesh(0.0, 1.0)

    def test_rejects_unknown_profile(self):
        with self.assertRaises(AuthoringError):
            roof_windows.profile("window.nonexistent")


class RoofWindowDeclarationTest(unittest.TestCase):
    def model(self, **overrides):
        model = with_roof()
        settings = {
            "roof": "r", "edge": 0, "along": 3.0, "up_slope": 1.5,
            "width": 0.94, "height": 1.40,
        }
        settings.update(overrides)
        roof_window(model, "sky", **settings)
        return model

    def test_window_reaches_the_roof_payload(self):
        model = self.model()
        model.validate()
        payload = roof_payload(model)[0]
        self.assertEqual(len(payload["roof_windows"]), 1)
        window = payload["roof_windows"][0]
        self.assertEqual(window["edge"], 0)
        self.assertEqual(window["profile"], "window.standard")

    def test_window_emits_a_frame_presentation_operation(self):
        model = self.model()
        frame = next(
            o for o in model.operations if o.kind == "roof-window-frame"
        )
        self.assertEqual(frame.references["target"], "sky")

    def test_windows_are_grouped_under_their_own_roof(self):
        model = self.model()
        roof(model, "r2", storey="ground", boundary=SQUARE, angle=40.0,
             thickness=0.3)
        roof_window(model, "sky2", roof="r2", edge=2, along=2.0,
                    up_slope=1.0, width=0.94, height=1.40)
        model.validate()
        payload = {item["key"]: item for item in roof_payload(model)}
        self.assertEqual([w["key"] for w in payload["r"]["roof_windows"]], ["sky"])
        self.assertEqual([w["key"] for w in payload["r2"]["roof_windows"]], ["sky2"])

    def test_rejects_a_negative_edge(self):
        with self.assertRaises(AuthoringError):
            self.model(edge=-1)

    def test_rejects_a_nonpositive_size(self):
        with self.assertRaises(AuthoringError):
            self.model(width=0.0)


class PredefinedTypeTest(unittest.TestCase):
    """IfcRoof.PredefinedType is derived, so it cannot drift from geometry."""

    def kind(self, gables=(), angle=40.0, boundary=None):
        model = minimal()
        roof(model, "r", storey="ground", boundary=boundary or SQUARE,
             angle=angle, thickness=0.3)
        for index in gables:
            roof_edge(model, "r", index, defines_slope=False)
        model.validate()
        return roof_payload(model)[0]["predefined_type"]

    def test_no_gables_is_a_hip_roof(self):
        self.assertEqual(self.kind(), "HIP_ROOF")

    def test_two_opposite_gables_is_a_gable_roof(self):
        self.assertEqual(self.kind(gables=(1, 3)), "GABLE_ROOF")

    def test_one_sloping_edge_is_a_shed_roof(self):
        self.assertEqual(self.kind(gables=(1, 2, 3)), "SHED_ROOF")

    def test_a_single_gable_is_a_hipped_gable_roof(self):
        self.assertEqual(self.kind(gables=(1,)), "HIPPED_GABLE_ROOF")

    def test_zero_pitch_is_a_flat_roof(self):
        self.assertEqual(self.kind(angle=0.0), "FLAT_ROOF")


class SkeletonTest(unittest.TestCase):
    def edges(self, *specs):
        return [
            {"index": i, "angle": angle, "defines_slope": slopes}
            for i, (angle, slopes) in enumerate(specs)
        ]

    def test_uniform_pitch_is_supported(self):
        edges = self.edges((40.0, True), (40.0, True), (40.0, True))
        self.assertEqual(skeleton.classify(edges), skeleton.UNIFORM)

    def test_gables_do_not_force_the_weighted_case(self):
        edges = self.edges((40.0, True), (12.0, False), (40.0, True))
        self.assertEqual(skeleton.classify(edges), skeleton.UNIFORM)

    def test_differing_sloping_pitches_need_a_weighted_skeleton(self):
        edges = self.edges((40.0, True), (25.0, True), (40.0, True))
        self.assertEqual(skeleton.classify(edges), skeleton.WEIGHTED)

    def test_weighted_case_fails_loudly_with_the_pitches_named(self):
        edges = self.edges((40.0, True), (25.0, True))
        with self.assertRaises(AuthoringError) as caught:
            skeleton.require_supported("r", edges)
        self.assertIn("25.0", str(caught.exception))
        self.assertIn("40.0", str(caught.exception))

    def test_all_gables_is_rejected(self):
        with self.assertRaises(AuthoringError):
            skeleton.classify(self.edges((40.0, False), (40.0, False)))

    def test_weights_are_the_skeleton_edge_speeds(self):
        """tan(90 - pitch): what a weighted skeleton consumes per edge."""
        self.assertAlmostEqual(skeleton.weights([45.0])[0], 1.0, places=9)
        self.assertAlmostEqual(skeleton.weights([0.0])[0], math.tan(math.radians(90.0)), places=3)

    def test_weights_reject_a_vertical_pitch(self):
        with self.assertRaises(AuthoringError):
            skeleton.weights([90.0])


class RoofDeclarationTest(unittest.TestCase):
    def test_payload_carries_the_three_material_roles(self):
        payload = roof_payload(with_roof())[0]
        self.assertEqual(
            payload["materials"],
            {"Top": "roof.top", "Ceiling": "roof.ceiling", "Side": "roof.side"},
        )

    def test_each_roof_role_references_a_material(self):
        model = with_roof(top_material="ground")
        with self.assertRaisesRegex(AuthoringError, "top_material must be a material"):
            model.validate()

    def test_presentation_preserves_the_roofs_ifc_material_slots(self):
        tree = ast.parse(with_roof().blender_source())
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "MATERIAL_TARGETS"
                for target in node.targets
            )
        )
        self.assertEqual(json.loads(assignment.value.args[0].value), {})

    def test_roof_defaults_apply_to_every_edge(self):
        model = with_roof(overhang=0.4)
        edges = model.roof_edges("r")
        self.assertEqual(len(edges), 4)
        self.assertTrue(all(e["defines_slope"] for e in edges))
        self.assertTrue(all(e["overhang"] == 0.4 for e in edges))
        self.assertTrue(all(e["angle"] == 40.0 for e in edges))

    def test_roof_edge_overrides_only_its_own_edge(self):
        model = with_roof(overhang=0.4)
        roof_edge(model, "r", 1, defines_slope=False, overhang=0.0)
        edges = model.roof_edges("r")
        self.assertFalse(edges[1]["defines_slope"])
        self.assertEqual(edges[1]["overhang"], 0.0)
        self.assertTrue(edges[0]["defines_slope"])
        self.assertEqual(edges[0]["overhang"], 0.4)

    def test_multiple_roofs_are_independent(self):
        model = with_roof()
        roof(model, "r2", storey="ground", boundary=SQUARE, angle=25.0,
             thickness=0.2)
        roof_edge(model, "r2", 0, defines_slope=False)
        model.validate()
        payload = {item["key"]: item for item in roof_payload(model)}
        self.assertEqual(set(payload), {"r", "r2"})
        self.assertEqual(payload["r"]["angle"], 40.0)
        self.assertEqual(payload["r2"]["angle"], 25.0)
        self.assertEqual(payload["r"]["gable_indices"], [])
        self.assertEqual(payload["r2"]["gable_indices"], [0])

    def test_base_z_resolves_against_the_storey(self):
        model = minimal()
        storey(model, "first", building="house", elevation=3.0)
        roof(model, "r", storey="first", boundary=SQUARE, angle=40.0,
             thickness=0.3, base_offset=0.5)
        self.assertAlmostEqual(roof_payload(model)[0]["base_z"], 3.5, places=9)

    def test_covering_emits_the_tile_presentation_operation(self):
        model = minimal()
        roof_tile(model, "tile.dark")
        roof(model, "r", storey="ground", boundary=SQUARE, angle=40.0,
             thickness=0.3, covering="tile.clay", covering_material="tile.dark")
        model.validate()
        op = next(o for o in model.operations if o.kind == "roof-tiles")
        self.assertEqual(op.references["target"], "r")
        self.assertEqual(op.references["material"], "tile.dark")
        # Only the profile keys travel; the factories own the shapes.
        self.assertEqual(
            op.parameters,
            {"profile": "tile.clay", "stagger": None, "cap": "cap.segmental"},
        )

    def test_covering_cap_overrides_the_tile_profile_own(self):
        model = minimal()
        roof(model, "r", storey="ground", boundary=SQUARE, angle=40.0,
             thickness=0.3, covering="tile.clay", covering_cap="cap.seam")
        model.validate()
        op = next(o for o in model.operations if o.kind == "roof-tiles")
        self.assertEqual(op.parameters["cap"], "cap.seam")

    def test_rejects_an_unknown_cap(self):
        with self.assertRaises(AuthoringError) as caught:
            roof(minimal(), "r", storey="ground", boundary=SQUARE, angle=40.0,
                 thickness=0.3, covering="tile.clay", covering_cap="cap.nope")
        self.assertIn("unknown cap profile", str(caught.exception))

    def test_rejects_a_cap_on_a_roof_with_no_covering(self):
        with self.assertRaises(AuthoringError) as caught:
            roof(minimal(), "r", storey="ground", boundary=SQUARE, angle=40.0,
                 thickness=0.3, covering_cap="cap.half_round")
        self.assertIn("nothing for it to cap", str(caught.exception))

    def test_roof_without_covering_emits_no_tiles(self):
        model = with_roof()
        self.assertFalse([o for o in model.operations if o.kind == "roof-tiles"])

    def test_overhang_reaches_the_payload(self):
        model = with_roof(overhang=0.5)
        payload = roof_payload(model)[0]
        self.assertAlmostEqual(polygons.bounds(payload["overhang_boundary"])[1],
                               8.5, places=9)

    def test_validate_rejects_differing_pitches(self):
        model = with_roof()
        roof_edge(model, "r", 1, angle=25.0)
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("unweighted", str(caught.exception))

    def test_validate_rejects_an_out_of_range_edge(self):
        model = with_roof()
        roof_edge(model, "r", 9, defines_slope=False)
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("boundary has 4 edges", str(caught.exception))

    def test_rejects_a_vertical_pitch(self):
        with self.assertRaises(AuthoringError):
            with_roof(angle=90.0)

    def test_rejects_a_boundary_with_too_few_corners(self):
        with self.assertRaises(AuthoringError):
            with_roof(boundary=[(0.0, 0.0), (1.0, 0.0)])

    def test_closing_corner_is_dropped_not_duplicated(self):
        model = with_roof(boundary=SQUARE + [SQUARE[0]])
        self.assertEqual(len(model.roof_edges("r")), 4)

    def test_rejects_a_repeated_corner(self):
        with self.assertRaises(AuthoringError):
            with_roof(boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 0.0), (0.0, 6.0)])

    def test_rejects_negative_overhang(self):
        with self.assertRaises(AuthoringError):
            with_roof(overhang=-0.2)


class CompileTest(unittest.TestCase):
    def sources(self) -> tuple[str, str]:
        model = typed()
        stucco(model, "stucco.white")
        glass(model, "glazing.main")
        wall(model, "w1", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (4.0, 0.0)), height=3.0)
        return model.ifc_source(), model.blender_source()

    def test_both_phases_are_valid_python(self):
        for source in self.sources():
            ast.parse(source)

    def test_no_placeholder_survives(self):
        for source in self.sources():
            self.assertNotIn("@@", source)

    def test_templates_on_disk_are_valid_python(self):
        templates = (
            Path(__file__).resolve().parents[1]
            / "building_author"
            / "templates"
        )
        found = sorted(templates.glob("*.py"))
        self.assertTrue(found, "no templates found")
        for path in found:
            ast.parse(path.read_text(encoding="utf-8"))

    def test_material_targets_reach_the_presentation_phase(self):
        _, blender = self.sources()
        self.assertIn("stucco.white", blender)
        self.assertIn(STYLIZED_PLASTER_RECIPE, blender)
        self.assertIn("building_author_material_recipe", blender)

    def test_ifc_styles_and_blender_upgrades_use_semantic_material_keys(self):
        ifc, blender = self.sources()
        self.assertIn("name=f\"BA::{operation['key']}\"", ifc)
        self.assertIn('f"BA::{material_key}"', blender)
        self.assertIn("imported_materials(material_key)", blender)

    def test_compiling_is_deterministic(self):
        self.assertEqual(self.sources(), self.sources())


if __name__ == "__main__":
    unittest.main()


class JunctionTest(unittest.TestCase):
    """Corners are derived from the reference lines, so they cannot disagree."""

    def walls(self, *axes):
        return [
            {
                "key": f"w{index}",
                "start": start,
                "end": end,
                "base_z": 0.0,
                "height": 3.0,
            }
            for index, (start, end) in enumerate(axes)
        ]

    def test_shared_endpoint_is_a_corner(self):
        found = junctions.connections(
            self.walls(((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 4.0)))
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["relating_connection"], "ATEND")
        self.assertEqual(found[0]["related_connection"], "ATSTART")

    def test_start_to_start_is_still_a_corner(self):
        found = junctions.connections(
            self.walls(((0.0, 0.0), (5.0, 0.0)), ((0.0, 0.0), (0.0, 4.0)))
        )
        self.assertEqual(found[0]["relating_connection"], "ATSTART")
        self.assertEqual(found[0]["related_connection"], "ATSTART")

    def test_end_landing_mid_span_is_a_t_junction(self):
        found = junctions.connections(
            self.walls(((0.0, 0.0), (8.0, 0.0)), ((4.0, 0.0), (4.0, 3.0)))
        )
        self.assertEqual(len(found), 1)
        # The wall that ends is the relating element, as connect_wall produces.
        self.assertEqual(found[0]["relating"], "w1")
        self.assertEqual(found[0]["relating_connection"], "ATSTART")
        self.assertEqual(found[0]["related"], "w0")
        self.assertEqual(found[0]["related_connection"], "ATPATH")

    def test_crossing_without_a_shared_end_is_not_a_junction(self):
        self.assertEqual(
            junctions.connections(
                self.walls(((0.0, 0.0), (8.0, 0.0)), ((4.0, -2.0), (4.0, 2.0)))
            ),
            [],
        )

    def test_walls_that_never_meet_are_not_connected(self):
        self.assertEqual(
            junctions.connections(
                self.walls(((0.0, 0.0), (5.0, 0.0)), ((0.0, 3.0), (5.0, 3.0)))
            ),
            [],
        )

    def test_a_closed_loop_makes_one_corner_per_wall(self):
        found = junctions.connections(
            self.walls(
                ((0.0, 0.0), (8.0, 0.0)),
                ((8.0, 0.0), (8.0, 6.0)),
                ((8.0, 6.0), (0.0, 6.0)),
                ((0.0, 6.0), (0.0, 0.0)),
            )
        )
        self.assertEqual(len(found), 4)

    def test_each_pair_is_emitted_once(self):
        found = junctions.connections(
            self.walls(((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 4.0)))
        )
        pairs = {frozenset((c["relating"], c["related"])) for c in found}
        self.assertEqual(len(pairs), len(found))

    def test_collinear_walls_meeting_end_to_end_still_connect(self):
        found = junctions.connections(
            self.walls(((0.0, 0.0), (4.0, 0.0)), ((4.0, 0.0), (9.0, 0.0)))
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["related_connection"], "ATSTART")

    def test_float_error_still_counts_as_touching(self):
        found = junctions.connections(
            self.walls(((0.0, 0.0), (0.3, 0.0)), ((0.1 + 0.2, 0.0), (0.3, 4.0)))
        )
        self.assertEqual(len(found), 1)

    def stacked(self, *extents):
        """One axis, several walls along it at the given base and height."""

        return [
            {
                "key": f"w{index}",
                "start": (0.0, 0.0),
                "end": (8.0, 0.0),
                "base_z": base_z,
                "height": height,
            }
            for index, (base_z, height) in enumerate(extents)
        ]

    def test_a_plinth_under_its_own_wall_is_not_a_junction(self):
        # Sharing the axis is what recesses the plinth face; the two walls
        # meet top to base and never occupy a common height.
        self.assertEqual(
            junctions.connections(self.stacked((-0.3, 0.3), (0.0, 3.0))), []
        )

    def test_walls_sharing_a_height_still_connect(self):
        found = junctions.connections(
            [
                {"key": "full", "start": (0.0, 0.0), "end": (8.0, 0.0),
                 "base_z": 0.0, "height": 6.0},
                {"key": "upper", "start": (8.0, 0.0), "end": (8.0, 4.0),
                 "base_z": 3.0, "height": 3.0},
            ]
        )
        self.assertEqual(len(found), 1)


class WallPayloadTest(unittest.TestCase):
    """The layer set is placed against the reference line, IFC's way."""

    def payload(self, **kwargs):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0, **kwargs)
        model.validate()
        return wall_payload(model)["walls"][0]

    def test_thickness_is_summed_from_the_layers(self):
        self.assertAlmostEqual(self.payload()["thickness"], 0.30, places=9)

    def test_default_offset_centres_the_wall_on_its_reference_line(self):
        # POSITIVE stacks toward +Y, so the base sits half a thickness at -Y.
        self.assertAlmostEqual(
            self.payload()["offset_from_reference_line"], -0.15, places=9
        )

    def test_default_offset_follows_the_direction_sense(self):
        self.assertAlmostEqual(
            self.payload(direction_sense="NEGATIVE")[
                "offset_from_reference_line"
            ],
            0.15,
            places=9,
        )

    def test_a_named_offset_is_passed_through_untouched(self):
        self.assertAlmostEqual(
            self.payload(offset_from_reference_line=0.0)[
                "offset_from_reference_line"
            ],
            0.0,
            places=9,
        )

    def test_base_offset_stacks_on_the_storey_elevation(self):
        model = typed()
        storey(model, "first", building="house", elevation=3.0)
        wall(model, "w", storey="first", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0, base_offset=0.2)
        self.assertAlmostEqual(
            wall_payload(model)["walls"][0]["base_z"], 3.2, places=9
        )

    def test_junctions_reach_the_payload(self):
        model = typed()
        wall(model, "a", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0)
        wall(model, "b", storey="ground", wall_type="ext.300",
             axis=((5.0, 0.0), (5.0, 4.0)), height=3.0)
        self.assertEqual(len(wall_payload(model)["junctions"]), 1)

    def test_junctions_do_not_connect_walls_on_different_storeys(self):
        model = typed()
        storey(model, "attic", building="house", elevation=3.0)
        wall(model, "ground-wall", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0)
        wall(model, "attic-wall", storey="attic", wall_type="ext.300",
             axis=((5.0, 0.0), (5.0, 4.0)), height=3.0)
        self.assertEqual(wall_payload(model)["junctions"], [])


class ExtendToStructurePayloadTest(unittest.TestCase):
    def test_payload_preserves_ifc_relationship_roles(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0)
        roof(model, "r", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        extend_to_structure(
            model,
            "w.top",
            relating_element="r",
            related_element="w",
        )
        self.assertEqual(
            extend_to_structure_payload(model),
            [{
                "key": "w.top",
                "relating_element": "r",
                "related_element": "w",
                "termination": "UNDERSIDE",
            }],
        )

    def test_payload_preserves_the_top_surface_termination(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0)
        roof(model, "r", storey="ground", boundary=SQUARE,
             angle=40.0, thickness=0.3)
        extend_to_structure(
            model,
            "w.top",
            relating_element="r",
            related_element="w",
            termination="TOP_SURFACE",
        )
        self.assertEqual(
            extend_to_structure_payload(model)[0]["termination"],
            "TOP_SURFACE",
        )

    def test_payload_preserves_a_slab_as_the_relating_element(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0)
        slab_type(model, "ceiling.200", layers=[
            layer("block", 0.2, priority=90, category="LoadBearing"),
        ])
        slab(model, "ceiling", storey="ground", slab_type="ceiling.200",
             boundary=SQUARE, base_offset=3.0)
        extend_to_structure(
            model,
            "w.top",
            relating_element="ceiling",
            related_element="w",
        )
        self.assertEqual(
            extend_to_structure_payload(model)[0]["relating_element"],
            "ceiling",
        )


class WallTypeValidationTest(unittest.TestCase):
    def test_rejects_a_type_without_layers(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            wall_type(model, "empty", layers=[])

    def test_rejects_a_priority_outside_the_ifc_range(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            layer("plaster", 0.01, priority=101)

    def test_rejects_a_predefined_type_outside_the_enumeration(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            wall_type(model, "t", predefined_type="EXTERNAL",
                      layers=[layer("plaster", 0.01, priority=10)])

    def test_rejects_a_direction_sense_outside_the_enumeration(self):
        model = typed()
        with self.assertRaises(AuthoringError):
            wall(model, "w", storey="ground", wall_type="ext.300",
                 axis=((0.0, 0.0), (5.0, 0.0)), height=3.0,
                 direction_sense="LEFT")

    def test_rejects_a_layer_material_that_was_never_declared(self):
        model = minimal()
        wall_type(model, "t", layers=[layer("missing", 0.01, priority=10)])
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_rejects_a_wall_whose_type_was_never_declared(self):
        model = minimal()
        wall(model, "w", storey="ground", wall_type="missing",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0)
        with self.assertRaises(AuthoringError):
            model.validate()


def slab_typed() -> Building:
    """A model carrying one two-layer slab type, thickness 0.20."""

    model = minimal()
    material(model, "concrete", ifc_name="Concrete", category="concrete",
             base_color=(0.72, 0.71, 0.68), roughness=0.85)
    material(model, "screed", ifc_name="Screed", category="screed",
             base_color=(0.78, 0.76, 0.72), roughness=0.8)
    slab_type(model, "floor.200", predefined_type="BASESLAB", layers=[
        layer("concrete", 0.150, priority=90, category="LoadBearing"),
        layer("screed", 0.050, priority=10, category="Finish"),
    ])
    return model


class SlabDeclarationTest(unittest.TestCase):
    def test_slab_records_its_type_reference(self):
        model = slab_typed()
        slab(model, "s", storey="ground", slab_type="floor.200", boundary=SQUARE)
        s = next(o for o in model.operations if o.kind == "slab")
        self.assertEqual(s.references["slab_type"], "floor.200")

    def test_slab_type_references_every_layer_material(self):
        model = slab_typed()
        t = next(o for o in model.operations if o.kind == "slab-type")
        self.assertEqual(t.references["layer.0.material"], "concrete")
        self.assertEqual(t.references["layer.1.material"], "screed")


class SlabTypeValidationTest(unittest.TestCase):
    def test_rejects_a_type_without_layers(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            slab_type(model, "empty", layers=[])

    def test_rejects_a_predefined_type_outside_the_enumeration(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            slab_type(model, "t", predefined_type="EXTERNAL",
                      layers=[layer("concrete", 0.15, priority=90)])

    def test_rejects_a_boundary_with_fewer_than_three_corners(self):
        model = slab_typed()
        with self.assertRaises(AuthoringError):
            slab(model, "s", storey="ground", slab_type="floor.200",
                 boundary=[(0.0, 0.0), (1.0, 0.0)])

    def test_rejects_a_slab_whose_type_was_never_declared(self):
        model = minimal()
        slab(model, "s", storey="ground", slab_type="missing", boundary=SQUARE)
        with self.assertRaises(AuthoringError):
            model.validate()


class SlabPayloadTest(unittest.TestCase):
    def test_thickness_is_summed_from_the_layers(self):
        model = slab_typed()
        slab(model, "s", storey="ground", slab_type="floor.200", boundary=SQUARE)
        self.assertAlmostEqual(
            slab_payload(model)[0]["thickness"], 0.20, places=9
        )

    def test_base_offset_stacks_on_the_storey_elevation(self):
        model = slab_typed()
        storey(model, "first", building="house", elevation=3.0)
        slab(model, "s", storey="first", slab_type="floor.200",
             boundary=SQUARE, base_offset=-0.2)
        self.assertAlmostEqual(
            slab_payload(model)[0]["base_z"], 2.8, places=9
        )


STEP = [(-0.3, -0.3), (4.3, -0.3), (4.3, 4.3), (-0.3, 4.3)]


def tiered(model: Building | None = None, **overrides) -> Building:
    """A model carrying one two-tier slab of a single material."""

    model = model if model is not None else slab_typed()
    slab(
        model,
        overrides.pop("key", "t"),
        storey=overrides.pop("storey", "ground"),
        material=overrides.pop("material", "concrete"),
        tiers=overrides.pop("tiers", [(STEP, 0.150), (SQUARE, 0.150)]),
        base_offset=overrides.pop("base_offset", -0.300),
        **overrides,
    )
    return model


class TieredSlabTest(unittest.TestCase):
    def test_tiers_stack_bottom_up_from_the_base_offset(self):
        entry = slab_payload(tiered())[0]
        self.assertAlmostEqual(entry["base_z"], -0.300, places=9)
        self.assertEqual(
            [round(tier["base_z"], 9) for tier in entry["tiers"]],
            [-0.300, -0.150],
        )
        self.assertAlmostEqual(entry["thickness"], 0.300, places=9)

    def test_uneven_tiers_are_not_assumed_even(self):
        entry = slab_payload(tiered(tiers=[(STEP, 0.080), (SQUARE, 0.220)]))[0]
        self.assertEqual(
            [round(tier["base_z"], 9) for tier in entry["tiers"]],
            [-0.300, -0.220],
        )

    def test_each_tier_keeps_its_own_boundary(self):
        entry = slab_payload(tiered())[0]
        self.assertNotEqual(
            entry["tiers"][0]["boundary"], entry["tiers"][1]["boundary"]
        )
        self.assertEqual(
            entry["tiers"][1]["boundary"], [list(point) for point in SQUARE]
        )

    def test_a_tiered_slab_carries_no_layer_set(self):
        """Tiers have different profiles, which is exactly what a layer set
        cannot describe, so a tiered slab takes a single material instead.
        """

        entry = slab_payload(tiered())[0]
        self.assertIsNone(entry["slab_type"])
        self.assertEqual(entry["material"], "concrete")
        self.assertIsNone(entry["boundary"])

    def test_a_layered_slab_is_untouched(self):
        model = slab_typed()
        slab(model, "s", storey="ground", slab_type="floor.200",
             boundary=SQUARE)
        entry = slab_payload(model)[0]
        self.assertEqual(entry["tiers"], [])
        self.assertEqual(entry["slab_type"], "floor.200")
        self.assertIsNone(entry["material"])

    def test_rejects_a_slab_type_and_tiers_together(self):
        model = slab_typed()
        slab(model, "s", storey="ground", slab_type="floor.200",
             material="concrete", tiers=[(SQUARE, 0.2)])
        with self.assertRaisesRegex(
            AuthoringError, "both a slab_type and tiers"
        ):
            model.validate()

    def test_rejects_neither(self):
        model = slab_typed()
        with self.assertRaisesRegex(
            AuthoringError, "needs a boundary, or tiers"
        ):
            slab(model, "s", storey="ground")

    def test_rejects_a_boundary_and_tiers_together(self):
        model = slab_typed()
        with self.assertRaisesRegex(
            AuthoringError, "both a boundary and tiers"
        ):
            slab(model, "s", storey="ground", material="concrete",
                 boundary=SQUARE, tiers=[(SQUARE, 0.2)])

    def test_rejects_tiers_without_a_material(self):
        model = slab_typed()
        slab(model, "s", storey="ground", tiers=[(SQUARE, 0.2)])
        with self.assertRaisesRegex(AuthoringError, "names no material"):
            model.validate()

    def test_rejects_a_malformed_tier(self):
        model = slab_typed()
        with self.assertRaisesRegex(
            AuthoringError, r"\(boundary, height\) pair"
        ):
            slab(model, "s", storey="ground", material="concrete",
                 tiers=[(SQUARE,)])

    def test_rejects_a_tier_of_no_height(self):
        model = slab_typed()
        with self.assertRaises(AuthoringError):
            slab(model, "s", storey="ground", material="concrete",
                 tiers=[(SQUARE, 0.0)])

    def test_predefined_type_reaches_the_payload(self):
        entry = slab_payload(tiered(predefined_type="FLOOR"))[0]
        self.assertEqual(entry["predefined_type"], "FLOOR")


def railing_declared(model: Building | None = None, **overrides) -> Building:
    """A model carrying one declared railing, ordinary defaults overridden by
    keyword - the same shortcut `slab_typed()` is for a slab's type. Pass an
    already-built `model` when a test needs its own setup - an extra storey,
    an extra material - before the railing is declared onto it.
    """

    model = model if model is not None else minimal()
    railing(
        model,
        overrides.pop("key", "r"),
        storey=overrides.pop("storey", "ground"),
        path=overrides.pop("path", ((0.0, 0.0), (4.0, 0.0))),
        height=overrides.pop("height", 1.0),
        **overrides,
    )
    return model


class RailingDeclarationTest(unittest.TestCase):
    def test_records_its_path(self):
        r = next(o for o in railing_declared().operations if o.kind == "railing")
        self.assertEqual(r.parameters["path"], ((0.0, 0.0), (4.0, 0.0)))

    def test_defaults_to_guardrail_predefined_type(self):
        r = next(o for o in railing_declared().operations if o.kind == "railing")
        self.assertEqual(r.parameters["predefined_type"], "GUARDRAIL")

    def test_defaults_to_the_steel_profile(self):
        r = next(o for o in railing_declared().operations if o.kind == "railing")
        self.assertEqual(r.parameters["profile"], "guardrail.steel")

    def test_records_every_material_role_as_a_reference(self):
        model = railing_declared(
            profile="balustrade.glass",
            shoe_material="aluminium", glazing_material="glass",
        )
        r = next(o for o in model.operations if o.kind == "railing")
        self.assertEqual(r.references["shoe_material"], "aluminium")
        self.assertEqual(r.references["glazing_material"], "glass")

    def test_material_references_are_optional(self):
        r = next(o for o in railing_declared().operations if o.kind == "railing")
        for role in ("post_material", "rail_material", "infill_material",
                     "shoe_material", "glazing_material"):
            self.assertNotIn(role, r.references)


class RailingValidationTest(unittest.TestCase):
    def test_rejects_a_zero_length_path(self):
        with self.assertRaises(AuthoringError):
            railing_declared(path=((0.0, 0.0), (0.0, 0.0)))

    def test_rejects_a_nonpositive_height(self):
        with self.assertRaises(AuthoringError):
            railing_declared(height=0.0)

    def test_rejects_a_predefined_type_outside_the_enumeration(self):
        with self.assertRaises(AuthoringError):
            railing_declared(predefined_type="FENCE")

    def test_userdefined_needs_an_object_type(self):
        with self.assertRaises(AuthoringError):
            railing_declared(predefined_type="USERDEFINED")

    def test_object_type_is_only_for_userdefined(self):
        with self.assertRaises(AuthoringError):
            railing_declared(object_type="Fence")

    def test_rejects_an_unknown_profile(self):
        with self.assertRaises(AuthoringError):
            railing_declared(profile="guardrail.gold")

    def test_rejects_a_railing_on_an_undeclared_storey(self):
        model = railing_declared(storey="missing")
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_rejects_a_railing_referencing_an_undeclared_material(self):
        model = railing_declared(post_material="missing")
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_rejects_a_railing_whose_storey_reference_has_the_wrong_kind(self):
        model = railing_declared(storey="house")
        with self.assertRaisesRegex(AuthoringError, "storey must be a storey"):
            model.validate()

    def test_rejects_a_railing_whose_material_reference_has_the_wrong_kind(self):
        model = railing_declared(post_material="ground")
        with self.assertRaisesRegex(AuthoringError, "must be a material"):
            model.validate()

    def test_rejects_a_fence_profile_disguised_as_a_guardrail(self):
        with self.assertRaisesRegex(AuthoringError, "through fence"):
            railing_declared(profile="fence.welded-mesh", height=1.23)

    def test_even_a_manually_classified_fence_profile_uses_the_narrow_helper(self):
        with self.assertRaisesRegex(AuthoringError, "through fence"):
            railing_declared(
                profile="fence.welded-mesh",
                height=1.23,
                predefined_type="USERDEFINED",
                object_type="Fence",
            )

    def test_public_railing_has_no_fence_declaration_escape_hatch(self):
        self.assertNotIn("_fence_declaration", inspect.signature(railing).parameters)
        with self.assertRaises(TypeError):
            railing_declared(_fence_declaration=True)

    def test_rejects_a_guardrail_disguised_as_a_fence(self):
        with self.assertRaisesRegex(AuthoringError, "needs a fence profile"):
            railing_declared(
                predefined_type="USERDEFINED",
                object_type="Fence",
            )

    def test_rejects_endpoint_post_suppression_on_a_guardrail(self):
        with self.assertRaisesRegex(AuthoringError, "only be suppressed"):
            railing_declared(end_post=False)


class RailingPayloadTest(unittest.TestCase):
    def test_base_z_stacks_on_the_storey_elevation(self):
        model = minimal()
        storey(model, "first", building="house", elevation=3.0)
        railing_declared(model, storey="first", base_offset=0.18)
        self.assertAlmostEqual(railing_payload(model)[0]["base_z"], 3.18, places=9)

    def test_profile_reaches_the_payload(self):
        model = railing_declared(profile="guardrail.timber")
        self.assertEqual(railing_payload(model)[0]["profile"], "guardrail.timber")

    def test_materials_are_keyed_by_shape_aspect_name(self):
        model = minimal()
        material(model, "steel", ifc_name="Steel", category="metal",
                 base_color=(0.1, 0.1, 0.1), roughness=0.3, metallic=0.8)
        railing_declared(
            model, post_material="steel", rail_material="steel",
            infill_material="steel",
        )
        self.assertEqual(
            railing_payload(model)[0]["materials"],
            {"Post": "steel", "Rail": "steel", "Infill": "steel"},
        )

    def test_only_declared_roles_are_present(self):
        model = minimal()
        material(model, "steel", ifc_name="Steel", category="metal",
                 base_color=(0.1, 0.1, 0.1), roughness=0.3, metallic=0.8)
        railing_declared(model, rail_material="steel")
        self.assertEqual(railing_payload(model)[0]["materials"], {"Rail": "steel"})

    def test_userdefined_object_type_reaches_the_payload(self):
        entry = railing_payload(
            railing_declared(
                predefined_type="USERDEFINED", object_type="AccessBarrier"
            )
        )[0]
        self.assertEqual(entry["object_type"], "AccessBarrier")


class RailingProfileRegistryTest(unittest.TestCase):
    def test_rejects_unknown_profile(self):
        with self.assertRaises(AuthoringError):
            railings.profile("guardrail.gold")

    def test_every_registered_profile_is_keyed_by_its_own_key(self):
        for key, entry in railings.PROFILES.items():
            with self.subTest(profile=key):
                self.assertEqual(entry.key, key)


class GuardrailProcedureTest(unittest.TestCase):
    """The shared post-infill-rail shape behind the steel and timber
    profiles, tested the way a roof window's frame is."""

    LENGTH, HEIGHT = 4.0, 1.0

    def shells(self, faces, slots, role):
        return [face for face, slot in zip(faces, slots) if slot == role]

    def gaps(self, verts, faces, slots, role):
        """Every infill bar's [low, high] z-span, sorted."""
        spans = []
        for face in self.shells(faces, slots, role):
            zs = {round(verts[index][2], 9) for index in face}
            if len(zs) == 2:
                spans.append(tuple(sorted(zs)))
        return sorted(set(spans))

    def check_profile(self, geometry_fn, roles, sphere_rule_gap):
        verts, faces, _, slots = geometry_fn(self.LENGTH, self.HEIGHT)
        with self.subTest("roles"):
            self.assertEqual(set(slots), roles)
        with self.subTest("closed"):
            edges = {}
            for face in faces:
                for slot in range(len(face)):
                    pair = frozenset((face[slot], face[(slot + 1) % len(face)]))
                    edges[pair] = edges.get(pair, 0) + 1
            self.assertTrue(all(count == 2 for count in edges.values()))
        with self.subTest("deterministic"):
            self.assertEqual(geometry_fn(self.LENGTH, self.HEIGHT),
                              geometry_fn(self.LENGTH, self.HEIGHT))
        with self.subTest("sphere rule"):
            # Every gap the infill has to close: the deck to the first bar,
            # bar to bar, and the last bar to the rail's own underside - not
            # just the middle ones.
            bars = self.gaps(verts, faces, slots, "infill")
            rail_low = min(
                verts[index][2]
                for face, role in zip(faces, slots) if role == "rail"
                for index in face
            )
            boundaries = sorted(
                [0.0, rail_low] + [z for span in bars for z in span]
            )
            gaps = [b - a for a, b in zip(boundaries[::2], boundaries[1::2])]
            self.assertTrue(
                all(gap <= sphere_rule_gap + 1e-9 for gap in gaps),
                f"a gap in {gaps} exceeds the {sphere_rule_gap} m sphere-rule "
                "maximum this profile is meant to honour",
            )

    def test_steel_guardrail(self):
        self.check_profile(
            railings.steel_guardrail_mesh,
            {"post", "infill", "rail"},
            railings.STEEL_INFILL_CLEAR_GAP,
        )

    def test_timber_guardrail(self):
        self.check_profile(
            railings.timber_guardrail_mesh,
            {"post", "infill", "rail"},
            railings.TIMBER_INFILL_CLEAR_GAP,
        )

    def test_a_post_always_lands_at_both_ends(self):
        verts, faces, _, slots = railings.steel_guardrail_mesh(
            self.LENGTH, self.HEIGHT
        )
        post_xs = [
            verts[index][0]
            for face, role in zip(faces, slots) if role == "post"
            for index in face
        ]
        self.assertAlmostEqual(
            min(post_xs), -railings.STEEL_TUBE / 2.0, places=6
        )
        self.assertAlmostEqual(
            max(post_xs), self.LENGTH + railings.STEEL_TUBE / 2.0, places=6
        )

    def test_rejects_a_nonpositive_length(self):
        with self.assertRaises(AuthoringError):
            railings.steel_guardrail_mesh(0.0, 1.0)

    def test_rejects_a_height_too_short_for_its_own_rail(self):
        with self.assertRaises(AuthoringError):
            railings.timber_guardrail_mesh(4.0, 0.02)


class GlassBalustradeProcedureTest(unittest.TestCase):
    LENGTH, HEIGHT = 4.0, 1.0

    def geometry(self):
        return railings.glass_balustrade_mesh(self.LENGTH, self.HEIGHT)

    def test_has_shoe_and_glazing_roles_only(self):
        _, _, _, slots = self.geometry()
        self.assertEqual(set(slots), {"shoe", "glazing"})

    def test_has_no_posts(self):
        """The whole point of a frameless balustrade."""
        _, _, _, slots = self.geometry()
        self.assertNotIn("post", slots)
        self.assertNotIn("rail", slots)

    def test_glazing_sits_on_the_shoe_not_the_deck(self):
        verts, faces, _, slots = self.geometry()
        glazing_zs = {
            round(verts[index][2], 6)
            for face, role in zip(faces, slots) if role == "glazing"
            for index in face
        }
        self.assertGreater(min(glazing_zs), 0.0)
        self.assertAlmostEqual(max(glazing_zs), self.HEIGHT, places=6)

    def test_every_shell_is_closed(self):
        _, faces, _, _ = self.geometry()
        edges = {}
        for face in faces:
            for slot in range(len(face)):
                pair = frozenset((face[slot], face[(slot + 1) % len(face)]))
                edges[pair] = edges.get(pair, 0) + 1
        self.assertTrue(all(count == 2 for count in edges.values()))

    def test_geometry_is_deterministic(self):
        self.assertEqual(self.geometry(), self.geometry())

    def test_rejects_a_nonpositive_length(self):
        with self.assertRaises(AuthoringError):
            railings.glass_balustrade_mesh(0.0, 1.0)

    def test_rejects_a_height_that_does_not_clear_the_shoe(self):
        with self.assertRaises(AuthoringError):
            railings.glass_balustrade_mesh(4.0, 0.01)


class FenceDeclarationTest(unittest.TestCase):
    def declared(self, **overrides):
        model = minimal()
        material(model, "metal", ifc_name="Coated metal", category="metal",
                 base_color=(0.1, 0.12, 0.1), roughness=0.35, metallic=0.7)
        fence(
            model,
            "boundary.north",
            storey="ground",
            path=overrides.pop("path", ((0.0, 0.0), (5.0, 0.0))),
            height=overrides.pop("height", 1.23),
            material="metal",
            **overrides,
        )
        return model

    def test_defaults_to_the_real_welded_mesh_profile(self):
        operation = next(
            item for item in self.declared().operations if item.kind == "railing"
        )
        self.assertEqual(operation.parameters["profile"], "fence.welded-mesh")

    def test_maps_to_ifc4_userdefined_fence(self):
        operation = next(
            item for item in self.declared().operations if item.kind == "railing"
        )
        self.assertEqual(operation.parameters["predefined_type"], "USERDEFINED")
        self.assertEqual(operation.parameters["object_type"], "Fence")

    def test_one_material_binds_posts_and_panel_infill(self):
        entry = railing_payload(self.declared())[0]
        self.assertEqual(
            entry["materials"], {"Post": "metal", "Infill": "metal"}
        )

    def test_endpoint_post_ownership_reaches_the_payload(self):
        entry = railing_payload(
            self.declared(start_post=False, end_post=False)
        )[0]
        self.assertFalse(entry["start_post"])
        self.assertFalse(entry["end_post"])

    def test_ifc_source_sets_object_type_on_the_userdefined_railing(self):
        source = self.declared().ifc_source()
        self.assertIn('"object_type": "Fence"', source)
        self.assertIn('entity.ObjectType = railing["object_type"]', source)

    def test_accepts_the_horizontal_slat_profile(self):
        operation = next(
            item for item in self.declared(
                profile="fence.horizontal-slat", height=1.2
            ).operations
            if item.kind == "railing"
        )
        self.assertEqual(operation.parameters["profile"], "fence.horizontal-slat")

    def test_rejects_a_guardrail_profile(self):
        with self.assertRaises(AuthoringError):
            self.declared(profile="guardrail.steel")

    def test_rejects_a_non_catalogue_nylofor_height(self):
        with self.assertRaises(AuthoringError):
            self.declared(height=1.20)

    def test_rejects_a_non_catalogue_horizon_height(self):
        with self.assertRaises(AuthoringError):
            self.declared(profile="fence.horizontal-slat", height=1.25)

    def test_endpoint_post_flags_must_be_booleans(self):
        with self.assertRaisesRegex(AuthoringError, "must be booleans"):
            self.declared(end_post=0)


class WeldedMeshFenceProcedureTest(unittest.TestCase):
    def test_has_post_and_infill_roles_only(self):
        _, _, _, slots = railings.nylofor_2d_fence_mesh(5.0, 1.23)
        self.assertEqual(set(slots), {"post", "infill"})

    def test_full_panels_repeat_at_the_published_2500_mm_width(self):
        self.assertEqual(
            railings._bay_ends(
                5.5,
                railings.NYLOFOR_2D_POST_CENTRES,
                railings.NYLOFOR_2D_POST_WIDTH
                + 2.0 * railings.NYLOFOR_2D_PANEL_EDGE_GAP,
            ),
            [0.0, 2.52, 5.04, 5.5],
        )

    def test_post_section_and_panel_mount_match_d_lox(self):
        verts, faces, _, slots = railings.nylofor_2d_fence_mesh(2.52, 1.23)
        post_points = [
            verts[index]
            for face, role in zip(faces, slots)
            if role == "post"
            for index in face
        ]
        infill_points = [
            verts[index]
            for face, role in zip(faces, slots)
            if role == "infill"
            for index in face
        ]
        self.assertAlmostEqual(
            max(point[0] for point in post_points)
            - min(point[0] for point in post_points),
            2.52 + railings.NYLOFOR_2D_POST_WIDTH,
            places=9,
        )
        first_post = [point for point in post_points if point[0] < 0.1]
        self.assertAlmostEqual(
            max(point[1] for point in first_post)
            - min(point[1] for point in first_post),
            railings.NYLOFOR_2D_POST_DEPTH,
            places=9,
        )
        self.assertLess(max(point[1] for point in infill_points),
                        min(point[1] for point in post_points))

    def test_twin_wires_touch_opposite_faces_of_the_vertical_wire(self):
        expected = (
            railings.NYLOFOR_2D_VERTICAL_WIRE
            + 2.0 * railings.NYLOFOR_2D_HORIZONTAL_WIRE
        )
        verts, faces, _, slots = railings.nylofor_2d_fence_mesh(2.5, 1.23)
        ys = [
            verts[index][1]
            for face, role in zip(faces, slots) if role == "infill"
            for index in face
        ]
        self.assertAlmostEqual(max(ys) - min(ys), expected, places=9)

    def test_vertical_wire_centres_do_not_overrun_the_2500_mm_panel(self):
        verts, faces, _, slots = railings.nylofor_2d_fence_mesh(2.52, 1.23)
        infill_xs = [
            verts[index][0]
            for face, role in zip(faces, slots)
            if role == "infill"
            for index in face
        ]
        self.assertAlmostEqual(
            max(infill_xs) - min(infill_xs),
            railings.NYLOFOR_2D_PANEL_WIDTH,
            places=9,
        )

    def test_every_shell_is_closed(self):
        _, faces, _, _ = railings.nylofor_2d_fence_mesh(2.5, 1.23)
        edges = {}
        for face in faces:
            for index in range(len(face)):
                pair = frozenset((face[index], face[(index + 1) % len(face)]))
                edges[pair] = edges.get(pair, 0) + 1
        self.assertTrue(all(count == 2 for count in edges.values()))

    def test_body_stays_inside_its_declared_height(self):
        verts, _, _, _ = railings.nylofor_2d_fence_mesh(2.5, 1.23)
        zs = [point[2] for point in verts]
        self.assertAlmostEqual(min(zs), 0.0, places=9)
        self.assertAlmostEqual(max(zs), 1.23, places=9)

    def test_suppressed_endpoint_post_is_not_generated(self):
        verts, faces, _, slots = railings.nylofor_2d_fence_mesh(
            2.52, 1.23, end_post=False
        )
        post_xs = [
            verts[index][0]
            for face, role in zip(faces, slots)
            if role == "post"
            for index in face
        ]
        self.assertLess(max(post_xs), 0.1)

    def test_tiny_remainder_is_redistributed_instead_of_inverted(self):
        minimum = (
            railings.NYLOFOR_2D_POST_WIDTH
            + 2.0 * railings.NYLOFOR_2D_PANEL_EDGE_GAP
        )
        ends = railings._bay_ends(
            railings.NYLOFOR_2D_POST_CENTRES + 0.001,
            railings.NYLOFOR_2D_POST_CENTRES,
            minimum,
        )
        spans = [following - current for current, following in zip(ends, ends[1:])]
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(span > minimum for span in spans))
        railings.nylofor_2d_fence_mesh(
            railings.NYLOFOR_2D_POST_CENTRES + 0.001, 1.23
        )


class HorizontalSlatFenceProcedureTest(unittest.TestCase):
    def test_has_post_and_infill_roles_only(self):
        _, _, _, slots = railings.horizon_020_fence_mesh(4.5, 1.2)
        self.assertEqual(set(slots), {"post", "infill"})

    def test_post_bays_never_exceed_the_technical_sheet_1800_mm_span(self):
        ends = railings._bay_ends(
            4.5,
            railings.HORIZON_020_MAX_SPAN,
            railings.HORIZON_020_POST_WIDTH + 2.0 * railings.CLEARANCE,
        )
        self.assertTrue(all(b - a <= 1.8 for a, b in zip(ends, ends[1:])))
        self.assertEqual(ends, [0.0, 1.8, 3.6, 4.5])

    def test_exact_module_and_epsilon_boundaries_remain_positive(self):
        minimum = railings.HORIZON_020_POST_WIDTH + 2.0 * railings.CLEARANCE
        for length in (3.599999999, 3.6, 3.600000001, 3.61):
            with self.subTest(length=length):
                ends = railings._bay_ends(
                    length, railings.HORIZON_020_MAX_SPAN, minimum
                )
                spans = [b - a for a, b in zip(ends, ends[1:])]
                self.assertTrue(all(span > minimum for span in spans))
                self.assertTrue(all(
                    span <= railings.HORIZON_020_MAX_SPAN + 1e-9
                    for span in spans
                ))
                railings.horizon_020_fence_mesh(length, 1.2)

    def test_slat_height_and_clear_gap_match_the_product(self):
        verts, faces, _, slots = railings.horizon_020_fence_mesh(2.0, 1.2)
        spans = set()
        for face, role in zip(faces, slots):
            if role != "infill":
                continue
            zs = sorted({round(verts[index][2], 9) for index in face})
            if len(zs) == 2 and math.isclose(
                zs[1] - zs[0], railings.HORIZON_020_SLAT_HEIGHT
            ):
                spans.add(tuple(zs))
        ordered = sorted(spans)
        self.assertGreater(len(ordered), 1)
        self.assertTrue(all(math.isclose(
            following[0] - current[1], railings.HORIZON_020_SLAT_GAP
        ) for current, following in zip(ordered, ordered[1:])))

    def test_the_complete_technical_sheet_height_series_is_buildable(self):
        for height in sorted(railings.HORIZON_020_HEIGHTS):
            with self.subTest(height=height):
                verts, _, _, _ = railings.horizon_020_fence_mesh(1.8, height)
                self.assertAlmostEqual(max(point[2] for point in verts), height)

    def test_geometry_is_deterministic(self):
        self.assertEqual(
            railings.horizon_020_fence_mesh(2.0, 1.2),
            railings.horizon_020_fence_mesh(2.0, 1.2),
        )

    def test_suppressed_fence_end_engages_gate_post_without_duplicating_it(self):
        clear_start = 0.9
        post_width = railings.horizon_020_gate_dimensions(
            1.0, 1.32, 1
        ).post_width
        support_centre = clear_start - post_width / 2.0
        fence_start = -2.0
        fence_mesh = railings.horizon_020_fence_mesh(
            support_centre - fence_start, 1.32, end_post=False
        )
        verts, faces, _, slots = fence_mesh
        post_xs = [
            fence_start + verts[index][0]
            for face, role in zip(faces, slots)
            if role == "post"
            for index in face
        ]
        infill_xs = [
            fence_start + verts[index][0]
            for face, role in zip(faces, slots)
            if role == "infill"
            for index in face
        ]
        gate_post_min = clear_start - post_width
        self.assertLess(max(post_xs), gate_post_min)
        self.assertAlmostEqual(
            max(infill_xs), gate_post_min + railings.CLEARANCE, places=9
        )


class GateFenceConnectionTest(unittest.TestCase):
    def test_horizon_connections_are_the_gate_post_centres(self):
        connections = gate_fence_connections(
            ((0.9, -3.0), (1.9, -3.0)),
            height=1.32,
            profile="fence.horizontal-slat",
            leaves=1,
        )
        for point, expected in zip(connections, ((0.86, -3.0), (1.94, -3.0))):
            self.assertAlmostEqual(point[0], expected[0], places=9)
            self.assertAlmostEqual(point[1], expected[1], places=9)

    def test_d_lox_connection_aligns_front_faces_of_unequal_depth_posts(self):
        connections = gate_fence_connections(
            ((0.0, 0.0), (0.985, 0.0)),
            height=1.63,
            profile="fence.welded-mesh",
            leaves=1,
        )
        for point, expected in zip(
            connections, ((-0.04, -0.02), (1.025, -0.02))
        ):
            self.assertAlmostEqual(point[0], expected[0], places=9)
            self.assertAlmostEqual(point[1], expected[1], places=9)

        fence_start = -2.0
        fence_mesh = railings.nylofor_2d_fence_mesh(
            connections[0][0] - fence_start, 1.63, end_post=False
        )
        verts, faces, _, slots = fence_mesh
        panel_ys = [
            connections[0][1] + verts[index][1]
            for face, role in zip(faces, slots)
            if role == "infill"
            for index in face
        ]
        gate_post_front = -0.08 / 2.0
        self.assertAlmostEqual(
            max(panel_ys), gate_post_front - railings.CLEARANCE, places=9
        )

    def test_connections_follow_a_diagonal_gate_frame(self):
        left, right = gate_fence_connections(
            ((1.0, 2.0), (4.0, 6.0)),
            height=1.32,
            profile="fence.horizontal-slat",
            leaves=2,
        )
        self.assertAlmostEqual(left[0], 1.0 - 0.6 * 0.04, places=9)
        self.assertAlmostEqual(left[1], 2.0 - 0.8 * 0.04, places=9)
        self.assertAlmostEqual(right[0], 4.0 + 0.6 * 0.04, places=9)
        self.assertAlmostEqual(right[1], 6.0 + 0.8 * 0.04, places=9)


def matching_gate_declared(*, pedestrian=False, **overrides):
    model = minimal()
    polyester_coated_steel(model, "fence.finish")
    declaration = pedestrian_gate if pedestrian else driveway_gate
    path = (
        ((0.0, 0.0), (0.985, 0.0))
        if pedestrian
        else ((0.0, 0.0), (3.010, 0.0))
    )
    declaration(
        model,
        overrides.pop("key", "boundary.gate"),
        storey=overrides.pop("storey", "ground"),
        path=overrides.pop("path", path),
        height=overrides.pop("height", 1.63),
        material=overrides.pop("material", "fence.finish"),
        **overrides,
    )
    return model


class GateDeclarationTest(unittest.TestCase):
    def operation(self, model):
        return next(item for item in model.operations if item.kind == "gate")

    def test_driveway_gate_is_a_two_leaf_swing_gate(self):
        operation = self.operation(matching_gate_declared())
        self.assertEqual(operation.parameters["leaves"], 2)
        self.assertEqual(
            operation.parameters["operation_type"],
            "DOUBLE_DOOR_SINGLE_SWING",
        )

    def test_pedestrian_gate_is_the_one_leaf_wicket(self):
        operation = self.operation(matching_gate_declared(pedestrian=True))
        self.assertEqual(operation.parameters["leaves"], 1)
        self.assertEqual(
            operation.parameters["operation_type"], "SINGLE_SWING_LEFT"
        )

    def test_nylofor_dimensions_preserve_clear_and_installed_widths(self):
        driveway = self.operation(matching_gate_declared()).parameters
        wicket = self.operation(
            matching_gate_declared(pedestrian=True)
        ).parameters
        self.assertAlmostEqual(driveway["passage_width"], 3.010, places=9)
        self.assertAlmostEqual(driveway["post_centres"], 3.090, places=9)
        self.assertAlmostEqual(driveway["installed_width"], 3.170, places=9)
        self.assertAlmostEqual(wicket["passage_width"], 0.985, places=9)
        self.assertAlmostEqual(wicket["post_centres"], 1.065, places=9)
        self.assertAlmostEqual(wicket["installed_width"], 1.145, places=9)

    def test_nylofor_accepts_the_union_of_its_conflicting_official_tables(self):
        for height in sorted(railings.NYLOFOR_GATE_HEIGHTS):
            with self.subTest(height=height):
                model = matching_gate_declared(height=height)
                model.validate()

    def test_3010_gate_uses_larger_posts_only_at_2430_height(self):
        through_2030 = self.operation(
            matching_gate_declared(height=2.03)
        ).parameters
        at_2430 = self.operation(
            matching_gate_declared(height=2.43)
        ).parameters
        self.assertAlmostEqual(through_2030["post_centres"], 3.090, places=9)
        self.assertAlmostEqual(through_2030["installed_width"], 3.170, places=9)
        self.assertAlmostEqual(at_2430["post_centres"], 3.110, places=9)
        self.assertAlmostEqual(at_2430["installed_width"], 3.210, places=9)

    def test_horizon_matching_gates_accept_made_to_measure_widths(self):
        driveway = matching_gate_declared(
            profile="fence.horizontal-slat",
            height=1.32,
            path=((0.0, 0.0), (3.0, 0.0)),
        )
        wicket = matching_gate_declared(
            pedestrian=True,
            profile="fence.horizontal-slat",
            height=1.32,
            path=((0.0, 0.0), (1.0, 0.0)),
        )
        driveway.validate()
        wicket.validate()
        self.assertAlmostEqual(
            self.operation(driveway).parameters["installed_width"],
            3.16,
            places=9,
        )
        self.assertAlmostEqual(
            self.operation(wicket).parameters["installed_width"],
            1.16,
            places=9,
        )

    def test_material_is_bound_to_every_gate_shape_role(self):
        entry = gate_payload(matching_gate_declared())[0]
        self.assertEqual(
            entry["materials"],
            {
                "Post": "fence.finish",
                "Framing": "fence.finish",
                "Infill": "fence.finish",
            },
        )

    def test_rejects_a_non_catalogue_nylofor_width(self):
        with self.assertRaisesRegex(AuthoringError, "free passage"):
            matching_gate_declared(path=((0.0, 0.0), (3.0, 0.0)))

    def test_rejects_a_non_catalogue_gate_height(self):
        with self.assertRaisesRegex(AuthoringError, "height must be one of"):
            matching_gate_declared(height=1.60)

    def test_rejects_an_unknown_profile(self):
        with self.assertRaisesRegex(AuthoringError, "unknown gate profile"):
            matching_gate_declared(profile="fence.palisade")

    def test_rejects_a_non_swing_pedestrian_operation(self):
        with self.assertRaisesRegex(AuthoringError, "pedestrian gate"):
            matching_gate_declared(
                pedestrian=True,
                operation_type="DOUBLE_DOOR_SINGLE_SWING",
            )

    def test_rejects_an_invalid_direction_sense(self):
        with self.assertRaises(AuthoringError):
            matching_gate_declared(direction_sense="OUTWARD")

    def test_validate_rejects_wrong_kind_storey_and_material_references(self):
        wrong_storey = minimal()
        driveway_gate(
            wrong_storey,
            "g",
            storey="house",
            path=((0.0, 0.0), (3.0, 0.0)),
            height=1.32,
            profile="fence.horizontal-slat",
        )
        with self.assertRaisesRegex(AuthoringError, "storey must be a storey"):
            wrong_storey.validate()

        wrong_material = minimal()
        driveway_gate(
            wrong_material,
            "g",
            storey="ground",
            path=((0.0, 0.0), (3.0, 0.0)),
            height=1.32,
            profile="fence.horizontal-slat",
            material="ground",
        )
        with self.assertRaisesRegex(AuthoringError, "must be a material"):
            wrong_material.validate()

    def test_ifc_source_builds_a_standalone_ifcdoor_gate(self):
        model = matching_gate_declared()
        self.assertEqual(compiler.opening_payload(model), [])
        source = model.ifc_source()
        gate_block = source.split("for gate in GATES:", 1)[1].split(
            "\ndef section_profile", 1
        )[0]
        self.assertIn('ifc_class="IfcDoor"', gate_block)
        self.assertIn('predefined_type="GATE"', gate_block)
        self.assertIn('entity.OperationType = gate["operation_type"]', gate_block)
        self.assertNotIn("add_feature(", gate_block)
        self.assertNotIn("add_filling", gate_block)
        compile(source, "<gate-ifc-source>", "exec")


class GatePayloadTest(unittest.TestCase):
    def test_base_z_stacks_on_storey_and_offset(self):
        model = minimal()
        storey(model, "upper", building="house", elevation=2.8)
        anthracite_aluminium(model, "finish")
        driveway_gate(
            model,
            "g",
            storey="upper",
            path=((0.0, 0.0), (3.0, 0.0)),
            height=1.32,
            profile="fence.horizontal-slat",
            base_offset=-0.15,
            material="finish",
        )
        self.assertAlmostEqual(gate_payload(model)[0]["position"][2], 2.65)

    def test_negative_sense_anchors_at_end_and_reverses_the_local_frame(self):
        model = matching_gate_declared(
            profile="fence.horizontal-slat",
            height=1.32,
            path=((1.0, 2.0), (4.0, 6.0)),
            direction_sense="NEGATIVE",
        )
        entry = gate_payload(model)[0]
        self.assertEqual(entry["position"][:2], [4.0, 6.0])
        self.assertAlmostEqual(
            entry["angle"], math.atan2(4.0, 3.0) + math.pi, places=9
        )

    def test_reversing_sense_preserves_the_same_world_envelope(self):
        path = ((1.0, 2.0), (4.0, 6.0))
        entries = []
        for sense in ("POSITIVE", "NEGATIVE"):
            model = matching_gate_declared(
                profile="fence.horizontal-slat",
                height=1.32,
                path=path,
                direction_sense=sense,
            )
            entries.append(gate_payload(model)[0])
        mesh = railings.horizon_020_gate_mesh(5.0, 1.32, 2)

        def world_bounds(entry):
            angle = entry["angle"]
            cosine, sine = math.cos(angle), math.sin(angle)
            px, py, pz = entry["position"]
            points = [
                (
                    px + cosine * x - sine * y,
                    py + sine * x + cosine * y,
                    pz + z,
                )
                for x, y, z in mesh[0]
            ]
            return tuple(
                (min(point[axis] for point in points),
                 max(point[axis] for point in points))
                for axis in range(3)
            )

        positive, negative = map(world_bounds, entries)
        for positive_axis, negative_axis in zip(positive, negative):
            self.assertAlmostEqual(positive_axis[0], negative_axis[0], places=9)
            self.assertAlmostEqual(positive_axis[1], negative_axis[1], places=9)


class GateProcedureTest(unittest.TestCase):
    CASES = (
        (railings.nylofor_2d_gate_mesh, 0.985, 1.63, 1),
        (railings.nylofor_2d_gate_mesh, 3.010, 1.63, 2),
        (railings.horizon_020_gate_mesh, 1.0, 1.32, 1),
        (railings.horizon_020_gate_mesh, 3.0, 1.32, 2),
    )

    def assert_closed(self, faces):
        edges = {}
        for face in faces:
            for index in range(len(face)):
                edge = frozenset((face[index], face[(index + 1) % len(face)]))
                edges[edge] = edges.get(edge, 0) + 1
        self.assertTrue(all(count == 2 for count in edges.values()))

    def test_every_supported_gate_is_closed_deterministic_and_role_split(self):
        for geometry, width, height, leaves in self.CASES:
            with self.subTest(
                procedure=geometry.__name__, width=width, leaves=leaves
            ):
                mesh = geometry(width, height, leaves)
                verts, faces, _, slots = mesh
                self.assertEqual(set(slots), {"post", "framing", "infill"})
                self.assert_closed(faces)
                self.assertEqual(mesh, geometry(width, height, leaves))
                self.assertAlmostEqual(min(point[2] for point in verts), 0.0)
                self.assertAlmostEqual(max(point[2] for point in verts), height)

    def test_every_generated_member_has_positive_extents(self):
        for geometry, width, height, leaves in self.CASES:
            with self.subTest(procedure=geometry.__name__, leaves=leaves):
                verts, faces, _, slots = geometry(width, height, leaves)
                self.assertEqual(len(verts) % 8, 0)
                self.assertEqual(len(faces), len(verts) // 8 * 6)
                self.assertEqual(len(slots), len(faces))
                for member_index, start in enumerate(range(0, len(verts), 8)):
                    member = verts[start:start + 8]
                    for axis in range(3):
                        coordinates = [point[axis] for point in member]
                        self.assertGreater(max(coordinates) - min(coordinates), 0.0)
                    signed_volume = 0.0
                    for face in faces[member_index * 6:(member_index + 1) * 6]:
                        a = verts[face[0]]
                        for index in range(1, len(face) - 1):
                            b = verts[face[index]]
                            c = verts[face[index + 1]]
                            signed_volume += (
                                a[0] * (b[1] * c[2] - b[2] * c[1])
                                + a[1] * (b[2] * c[0] - b[0] * c[2])
                                + a[2] * (b[0] * c[1] - b[1] * c[0])
                            ) / 6.0
                    self.assertGreater(signed_volume, 0.0)

    def test_gate_body_owns_support_posts_outside_the_clear_passage(self):
        for profile_key, geometry, width, height, leaves in (
            ("fence.welded-mesh", railings.nylofor_2d_gate_mesh,
             3.010, 1.63, 2),
            ("fence.horizontal-slat", railings.horizon_020_gate_mesh,
             3.0, 1.32, 2),
        ):
            with self.subTest(profile=profile_key):
                dimensions = railings.gate_profile(profile_key).dimensions(
                    width, height, leaves
                )
                verts, _, _, _ = geometry(width, height, leaves)
                self.assertAlmostEqual(
                    min(point[0] for point in verts),
                    -dimensions.post_width,
                    places=9,
                )
                self.assertAlmostEqual(
                    max(point[0] for point in verts),
                    width + dimensions.post_width,
                    places=9,
                )


class VirtualElementDeclarationTest(unittest.TestCase):
    def test_records_its_axis(self):
        model = minimal()
        virtual_element(model, "v", storey="ground",
                         axis=((0.0, 0.0), (2.0, 0.0)))
        v = next(o for o in model.operations if o.kind == "virtual-element")
        self.assertEqual(v.parameters["axis"], ((0.0, 0.0), (2.0, 0.0)))

    def test_rejects_a_zero_length_axis(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            virtual_element(model, "v", storey="ground",
                             axis=((0.0, 0.0), (0.0, 0.0)))

    def test_rejects_a_virtual_element_on_an_undeclared_storey(self):
        model = minimal()
        virtual_element(model, "v", storey="missing",
                         axis=((0.0, 0.0), (2.0, 0.0)))
        with self.assertRaises(AuthoringError):
            model.validate()


class SpaceDeclarationTest(unittest.TestCase):
    def test_records_its_point_height_and_type(self):
        model = minimal()
        space(model, "s", storey="ground", at=(1.0, 2.0), height=2.5)
        s = next(o for o in model.operations if o.kind == "space")
        self.assertEqual(s.parameters["at"], (1.0, 2.0))
        self.assertEqual(s.parameters["height"], 2.5)
        self.assertEqual(s.parameters["predefined_type"], "SPACE")

    def test_rejects_a_predefined_type_outside_the_enumeration(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            space(model, "s", storey="ground", at=(1.0, 2.0), height=2.5,
                  predefined_type="ROOM")

    def test_rejects_a_nonpositive_height(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            space(model, "s", storey="ground", at=(1.0, 2.0), height=0.0)


class SpacePayloadTest(unittest.TestCase):
    """Physical boundaries name regenerated walls; only virtuals carry rectangles."""

    def test_only_storeys_with_a_declared_space_are_grouped(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0)
        self.assertEqual(space_payload(model), [])

    def test_physical_boundaries_reference_native_walls_and_their_vertical_span(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (5.0, 0.0)), height=3.0,
             direction_sense="NEGATIVE", base_offset=-.2)
        space(model, "s", storey="ground", at=(2.0, 1.0), height=2.5)
        group = space_payload(model)[0]
        self.assertEqual(group["walls"], [{"key": "w", "base_z": -.2, "height": 3.0}])
        self.assertEqual(group["virtual_obstacles"], [])
        self.assertNotIn("obstacles", group)

    def test_a_virtual_element_contributes_a_thin_obstacle(self):
        model = minimal()
        virtual_element(model, "v", storey="ground",
                         axis=((0.0, 0.0), (2.0, 0.0)))
        space(model, "s", storey="ground", at=(1.0, 1.0), height=2.5)
        group = space_payload(model)[0]
        self.assertEqual(group["walls"], [])
        obstacles = group["virtual_obstacles"]
        ys = [point[1] for point in obstacles[0]]
        self.assertAlmostEqual(max(ys) - min(ys), 0.002)

    def test_spaces_are_grouped_by_their_own_storey(self):
        model = typed()
        storey(model, "first", building="house", elevation=3.0)
        space(model, "ground-space", storey="ground", at=(1.0, 1.0), height=2.5)
        space(model, "first-space", storey="first", at=(1.0, 1.0), height=2.5)
        groups = {group["storey"]: group for group in space_payload(model)}
        self.assertEqual(
            {item["key"] for item in groups["ground"]["spaces"]},
            {"ground-space"},
        )
        self.assertEqual(
            {item["key"] for item in groups["first"]["spaces"]},
            {"first-space"},
        )


def floored_opening() -> Building:
    """One floor-level door whose patch belongs to its named room."""

    model = typed()
    wall(
        model,
        "w",
        storey="ground",
        wall_type="ext.300",
        axis=((0.0, 0.0), (4.0, 0.0)),
        height=3.0,
    )
    space(model, "room", storey="ground", at=(2.0, 1.0), height=2.5)
    covering(
        model,
        "room.flooring",
        space="room",
        material="plaster",
        thickness=0.02,
    )
    panel_door_type(model, "dt")
    door(
        model,
        "d",
        wall="w",
        door_type="dt",
        along=2.0,
        overall_width=0.9,
        overall_height=2.1,
        threshold_space="room",
    )
    return model


class CoveringDeclarationTest(unittest.TestCase):
    def test_a_flooring_covering_has_no_boundary_or_elevation_override(self):
        model = floored_opening()
        operation = next(item for item in model.operations if item.kind == "covering")
        self.assertEqual(
            operation.references,
            {"space": "room", "material": "plaster"},
        )
        self.assertEqual(operation.parameters["predefined_type"], "FLOORING")
        self.assertNotIn("boundary", operation.parameters)
        self.assertNotIn("base_offset", operation.parameters)

    def test_rejects_a_nonpositive_finish_thickness(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            covering(model, "floor", space="room", material="finish", thickness=0)

    def test_rejects_more_than_one_main_covering_for_a_space(self):
        model = floored_opening()
        covering(
            model,
            "room.flooring.second",
            space="room",
            material="block",
            thickness=0.01,
        )
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("more than one main flooring", str(caught.exception))

    def test_covering_space_role_must_name_an_ifc_space(self):
        model = typed()
        covering(
            model,
            "floor",
            space="ground",
            material="plaster",
            thickness=0.02,
        )
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("space must be a space", str(caught.exception))

    def test_threshold_owner_must_have_a_main_covering(self):
        model = typed()
        wall(
            model,
            "w",
            storey="ground",
            wall_type="ext.300",
            axis=((0.0, 0.0), (4.0, 0.0)),
            height=3.0,
        )
        space(model, "room", storey="ground", at=(2.0, 1.0), height=2.5)
        panel_door_type(model, "dt")
        door(
            model,
            "d",
            wall="w",
            door_type="dt",
            along=2.0,
            overall_width=0.9,
            overall_height=2.1,
            threshold_space="room",
        )
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("exactly one main flooring covering", str(caught.exception))

    def test_a_raised_opening_cannot_claim_a_room_floor_threshold(self):
        model = typed()
        wall(
            model,
            "w",
            storey="ground",
            wall_type="ext.300",
            axis=((0.0, 0.0), (4.0, 0.0)),
            height=3.0,
        )
        space(model, "room", storey="ground", at=(2.0, 1.0), height=2.5)
        covering(
            model,
            "room.flooring",
            space="room",
            material="plaster",
            thickness=0.02,
        )
        panel_door_type(model, "dt")
        door(
            model,
            "d",
            wall="w",
            door_type="dt",
            along=2.0,
            overall_width=0.9,
            overall_height=2.1,
            base_offset=0.1,
            threshold_space="room",
        )
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("not floor-level", str(caught.exception))

    def test_threshold_owner_must_be_on_the_opening_storey(self):
        model = typed()
        storey(model, "first", building="house", elevation=3.0)
        wall(
            model,
            "w",
            storey="ground",
            wall_type="ext.300",
            axis=((0.0, 0.0), (4.0, 0.0)),
            height=3.0,
        )
        space(model, "room", storey="first", at=(2.0, 1.0), height=2.5)
        covering(
            model,
            "room.flooring",
            space="room",
            material="plaster",
            thickness=0.02,
        )
        panel_door_type(model, "dt")
        door(
            model,
            "d",
            wall="w",
            door_type="dt",
            along=2.0,
            overall_width=0.9,
            overall_height=2.1,
            threshold_space="room",
        )
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("not opening storey", str(caught.exception))


class CoveringPayloadTest(unittest.TestCase):
    def payload(self):
        model = floored_opening()
        model.validate()
        return covering_payload(model)

    def test_main_covering_top_is_the_space_base_datum(self):
        main = self.payload()["main"][0]
        self.assertAlmostEqual(main["base_z"], -0.02, places=9)
        self.assertAlmostEqual(main["base_z"] + main["thickness"], 0.0, places=9)

    def test_threshold_is_a_separate_stable_occurrence(self):
        payload = self.payload()
        main = payload["main"][0]
        threshold = payload["thresholds"][0]
        self.assertEqual(threshold["key"], "d.threshold-flooring")
        self.assertNotEqual(threshold["key"], main["key"])
        self.assertEqual(threshold["space"], "room")

    def test_threshold_inherits_the_owners_finish_and_clears_the_plinth_datum(self):
        payload = self.payload()
        main = payload["main"][0]
        threshold = payload["thresholds"][0]
        for field in (
            "material",
            "thickness",
            "predefined_type",
        ):
            self.assertEqual(threshold[field], main[field])
        self.assertAlmostEqual(
            threshold["base_z"],
            main["base_z"] + compiler.THRESHOLD_RISE,
            places=9,
        )
        # The space base datum is where a plinth under the host wall tops
        # out; the patch's finished face stands above it, not on it.
        finished = threshold["base_z"] + threshold["thickness"]
        self.assertAlmostEqual(
            finished,
            main["base_z"] + main["thickness"] + compiler.THRESHOLD_RISE,
            places=9,
        )
        self.assertGreater(finished, 0.0)

    def test_threshold_uses_opening_width_and_exact_wall_thickness(self):
        boundary = self.payload()["thresholds"][0]["boundary"]
        xs = [point[0] for point in boundary]
        ys = [point[1] for point in boundary]
        self.assertAlmostEqual(max(xs) - min(xs), 0.9, places=9)
        self.assertAlmostEqual(max(ys) - min(ys), 0.3, places=9)
        self.assertNotAlmostEqual(
            max(ys) - min(ys),
            0.3 + 2.0 * compiler.OPENING_REACH,
            places=9,
        )

    def test_ifc_source_builds_and_contains_coverings_in_the_space(self):
        source = floored_opening().ifc_source()
        self.assertIn('ifc_class="IfcCovering"', source)
        self.assertIn('relating_structure=entities[item["space"]]', source)
        self.assertIn("is not adjacent to its opening", source)
        self.assertIn("d.threshold-flooring", source)

    def test_virtual_boundary_can_own_one_separate_threshold_patch(self):
        model = minimal()
        material(
            model,
            "finish",
            ifc_name="Finish",
            category="flooring",
            base_color=(0.5, 0.5, 0.5),
            roughness=0.5,
        )
        space(model, "room", storey="ground", at=(1.0, 1.0), height=2.5)
        covering(
            model,
            "room.flooring",
            space="room",
            material="finish",
            thickness=0.01,
        )
        virtual_element(
            model,
            "open-boundary",
            storey="ground",
            axis=((0.0, 0.0), (2.0, 0.0)),
            threshold_space="room",
        )
        model.validate()
        threshold = covering_payload(model)["thresholds"][0]
        xs = [point[0] for point in threshold["boundary"]]
        ys = [point[1] for point in threshold["boundary"]]
        self.assertEqual(threshold["key"], "open-boundary.threshold-flooring")
        self.assertAlmostEqual(max(xs) - min(xs), 2.0, places=9)
        self.assertAlmostEqual(
            max(ys) - min(ys), compiler.VIRTUAL_ELEMENT_WIDTH, places=9
        )



class TileSweepBoundsTest(unittest.TestCase):
    """The sweep must reach every tile the corner test would keep.

    Bounding the sweep by the tile centre leaves a course short of the edge by
    up to half a module. The stagger moves that shortfall between courses, so
    it reads as every second course ending early.
    """

    def face(self, width, height):
        return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]

    def courses(self, face, profile):
        found = {}
        for u, v in tiles.centres(face, profile):
            found.setdefault(round(v, 6), []).append(u)
        return [sorted(found[v]) for v in sorted(found)]

    def test_every_course_reaches_the_rake(self):
        # 3.1 is not a whole number of 0.3 modules, which is what exposes it.
        profile = tiles.CELTIC_TILE
        for course in self.courses(self.face(3.1, 2.0), profile):
            self.assertGreaterEqual(
                max(course) + profile.width / 2.0, 3.1 - 1e-9
            )

    def test_staggered_courses_hold_as_many_tiles_as_straight_ones(self):
        counts = {len(c) for c in self.courses(self.face(3.1, 2.0), tiles.CELTIC_TILE)}
        self.assertEqual(len(counts), 1)

    def test_the_top_course_reaches_the_ridge(self):
        # 1.7 is not a whole number of 0.4 modules.
        profile = tiles.CLAY_TILE
        top = max(v for _, v in tiles.centres(self.face(2.0, 1.7), profile))
        self.assertGreaterEqual(top + profile.length / 2.0, 1.7 - 1e-9)

    def test_a_face_of_whole_modules_lays_no_tile_that_only_touches(self):
        profile = tiles.CELTIC_TILE
        half = profile.width / 2.0
        for u, _ in tiles.centres(self.face(3.0, 2.0), profile):
            self.assertLess(u - half, 3.0 - 1e-9)
            self.assertGreater(u + half, 1e-9)

    def test_no_tile_is_kept_without_a_corner_on_the_face(self):
        face = self.face(3.1, 2.0)
        profile = tiles.CELTIC_TILE
        half_w, half_l = profile.width / 2.0, profile.length / 2.0
        for u, v in tiles.centres(face, profile):
            corners = [
                (u + du, v + dv)
                for du in (half_w, -half_w)
                for dv in (half_l, -half_l)
            ]
            self.assertTrue(
                any(polygons.contains(c, face) for c in corners),
                f"tile at {(u, v)} has no corner on the face",
            )


class TileBondTest(unittest.TestCase):
    """The stagger is a fraction of a width, accumulating up the roof."""

    FACE = [(0.0, 0.0), (3.1, 0.0), (3.1, 2.1), (0.0, 2.1)]

    def phases(self, stagger):
        """Each course's column phase: where its grid sits within one module.

        Read modulo the width, because the sweep may step a course back a
        whole module to cover the near rake - that moves the leftmost tile
        without moving the bond.
        """

        width = tiles.CLAY_TILE.width
        grouped = {}
        for u, v in tiles.centres(self.FACE, tiles.CLAY_TILE, stagger):
            grouped.setdefault(round(v, 6), []).append(u)
        return [round(min(grouped[v]) % width, 9) for v in sorted(grouped)]

    def test_zero_stacks_every_course_in_the_same_columns(self):
        columns = self.phases(0.0)
        self.assertGreater(len(columns), 3)
        for value in columns[1:]:
            self.assertAlmostEqual(value, columns[0], places=9)

    def test_a_half_is_the_broken_bond_and_repeats_every_two_courses(self):
        columns = self.phases(0.5)
        width = tiles.CLAY_TILE.width
        self.assertAlmostEqual(
            (columns[1] - columns[0]) % width, width / 2.0, places=9
        )
        self.assertAlmostEqual(columns[2], columns[0], places=9)

    def test_a_third_repeats_every_three_courses(self):
        columns = self.phases(1.0 / 3.0)
        width = tiles.CLAY_TILE.width
        self.assertAlmostEqual(
            (columns[1] - columns[0]) % width, width / 3.0, places=9
        )
        self.assertAlmostEqual(
            (columns[2] - columns[0]) % width, 2.0 * width / 3.0, places=9
        )
        self.assertAlmostEqual(columns[3], columns[0], places=9)

    def test_the_default_is_a_half(self):
        self.assertEqual(tiles.CLAY_TILE.stagger, 0.5)
        self.assertEqual(tiles.CELTIC_TILE.stagger, 0.5)
        self.assertEqual(self.phases(None), self.phases(0.5))

    def test_every_bond_covers_the_face_the_same(self):
        """The bond moves tiles sideways; it must not leave a course short."""

        width = tiles.CLAY_TILE.width
        for stagger in (0.0, 0.25, 1.0 / 3.0, 0.5, 0.75, 0.9):
            grouped = {}
            for u, v in tiles.centres(self.FACE, tiles.CLAY_TILE, stagger):
                grouped.setdefault(round(v, 6), []).append(u)
            for v, row in grouped.items():
                self.assertGreaterEqual(
                    max(row) + width / 2.0, 3.1 - 1e-9,
                    f"stagger {stagger}, course {v} stops short",
                )
                self.assertLessEqual(
                    min(row) - width / 2.0, 1e-9,
                    f"stagger {stagger}, course {v} starts late",
                )

    def test_rejects_a_bond_of_one_or_more(self):
        # A whole width lands back on the same columns, so the range stops
        # short of one rather than wrapping silently.
        for value in (1.0, 1.5, -0.1):
            with self.assertRaises(AuthoringError):
                tiles.centres(self.FACE, tiles.CLAY_TILE, value)

    def test_rejects_a_non_numeric_bond(self):
        with self.assertRaises(AuthoringError):
            tiles.centres(self.FACE, tiles.CLAY_TILE, "half")

    def test_roof_rejects_a_bond_outside_the_range(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            roof(model, "r", storey="ground", boundary=SQUARE, angle=40.0,
                 thickness=0.3, covering="tile.clay", covering_stagger=1.0)

    def test_roof_carries_the_bond_into_the_payload(self):
        model = minimal()
        roof(model, "r", storey="ground", boundary=SQUARE, angle=40.0,
             thickness=0.3, covering="tile.clay", covering_stagger=0.0)
        model.validate()
        self.assertEqual(roof_payload(model)[0]["covering_stagger"], 0.0)


def walled() -> Building:
    """A model carrying one 0.30 wall along the X axis, ready to be opened."""

    model = typed()
    wall(model, "w", storey="ground", wall_type="ext.300",
         axis=((0.0, 0.0), (6.0, 0.0)), height=3.0)
    return model


def opened(**overrides) -> Building:
    """That wall with one casement window in it."""

    model = walled()
    casement_window_type(model, "wt")
    settings = {
        "wall": "w", "window_type": "wt", "along": 3.0, "sill_height": 0.9,
        "overall_width": 1.6, "overall_height": 1.4,
    }
    settings.update(overrides)
    window(model, "win", **settings)
    return model


GABLE_WIDTH = 4.42
GABLE_CENTRE = GABLE_WIDTH / 2.0
GABLE_TRANSOM = 2.30
GABLE_SPRING = 2.75
GABLE_RIDGE = 4.30


def gable_glazing():
    """The two-level garden glazing: rectangles below a profiled gable."""

    pieces = [
        # The centre edges are owned by one explicit divider, not two
        # coincident piece profiles.
        window_rectangle(
            0.0, 0.0, GABLE_CENTRE, GABLE_TRANSOM,
            profile_edges=("bottom", "left", "top"), pane="ground.left",
        ),
        window_rectangle(
            GABLE_CENTRE, 0.0, GABLE_CENTRE, GABLE_TRANSOM,
            profile_edges=("bottom", "right", "top"), pane="ground.right",
        ),
        # Ground-floor top profiles already form the transom.  These narrow
        # rectangles therefore own only the outer jambs, and deliberately
        # omit their tops where the triangular glazing continues them.
        window_rectangle(
            0.0, GABLE_TRANSOM, GABLE_CENTRE,
            GABLE_SPRING - GABLE_TRANSOM,
            profile_edges=("left",), pane="upper.left",
        ),
        window_triangle(
            (0.0, GABLE_SPRING),
            (GABLE_CENTRE, GABLE_SPRING),
            (GABLE_CENTRE, GABLE_RIDGE),
            profile_edges=("skew",),
            pane="upper.left",
        ),
        window_rectangle(
            GABLE_CENTRE, GABLE_TRANSOM, GABLE_CENTRE,
            GABLE_SPRING - GABLE_TRANSOM,
            profile_edges=("right",), pane="upper.right",
        ),
        window_triangle(
            (GABLE_CENTRE, GABLE_SPRING),
            (GABLE_WIDTH, GABLE_SPRING),
            (GABLE_CENTRE, GABLE_RIDGE),
            profile_edges=("skew",),
            pane="upper.right",
        ),
    ]
    dividers = [
        window_divider(
            (GABLE_CENTRE, 0.0), (GABLE_CENTRE, GABLE_RIDGE)
        )
    ]
    return pieces, dividers


def composed_facade() -> Building:
    """A short host wall carrying the full-height garden glazing."""

    model = walled()
    composed_window_type(
        model,
        "cwt.gable",
        profile_width=0.06,
        profile_depth=0.08,
        glazing_thickness=0.006,
    )
    pieces, dividers = gable_glazing()
    composed_window(
        model,
        "gable-window",
        wall="w",
        window_type="cwt.gable",
        along=3.0,
        sill_height=0.0,
        pieces=pieces,
        dividers=dividers,
        framing_material="block",
        glazing_material="plaster",
    )
    return model


class ComposedWindowPieceTest(unittest.TestCase):
    def test_rectangle_profiles_every_edge_by_default(self):
        piece = window_rectangle(1.0, 2.0, 3.0, 4.0)
        self.assertEqual(
            piece["boundary"],
            ((1.0, 2.0), (4.0, 2.0), (4.0, 6.0), (1.0, 6.0)),
        )
        self.assertEqual(piece["profile_edges"], (0, 1, 2, 3))

    def test_rectangle_profiles_are_optional_per_edge(self):
        piece = window_rectangle(
            0.0, 0.0, 2.0, 1.0, profile_edges=("left", "bottom")
        )
        # Boundary order is bottom, right, top, left.  In particular, the
        # rectangle can omit the top where triangular glazing continues it.
        self.assertEqual(piece["profile_edges"], (0, 3))
        self.assertEqual(
            window_rectangle(
                0.0, 0.0, 2.0, 1.0, profile_edges=()
            )["profile_edges"],
            (),
        )

    def test_triangle_can_keep_only_its_skew_profile(self):
        piece = window_triangle(
            (0.0, GABLE_SPRING),
            (GABLE_CENTRE, GABLE_SPRING),
            (GABLE_CENTRE, GABLE_RIDGE),
            profile_edges=("skew",),
        )
        # Edge 0 is the base and edge 1 the central vertical.  Neither gets a
        # member; the triangle supplies only the sloping gable profile.
        self.assertEqual(piece["profile_edges"], (2,))


class ComposedWindowGeometryTest(unittest.TestCase):
    PROFILE = {
        "profile_width": 0.06,
        "profile_depth": 0.08,
        "glazing_thickness": 0.006,
    }

    def test_rectangle_and_triangle_form_one_connected_outline(self):
        pieces = [
            window_rectangle(
                0.0, 0.0, 2.0, 1.0,
                profile_edges=("bottom", "right", "left"),
                pane="trapezoid",
            ),
            window_triangle(
                (0.0, 1.0), (2.0, 1.0), (2.0, 2.0),
                profile_edges=("skew",), pane="trapezoid",
            ),
        ]
        outline = composed_windows.opening_outline(pieces)
        self.assertEqual(composed_windows.bounds(pieces), (0.0, 0.0, 2.0, 2.0))
        self.assertAlmostEqual(
            abs(polygons.signed_area(outline)) / 2.0, 3.0, places=9
        )

    def test_disconnected_pieces_are_not_one_window(self):
        pieces = [
            window_rectangle(0.0, 0.0, 1.0, 1.0),
            window_rectangle(2.0, 0.0, 1.0, 1.0),
        ]
        with self.assertRaises(AuthoringError):
            composed_windows.opening_outline(pieces)

    def test_the_gable_is_the_declared_442_by_430_composition(self):
        pieces, _ = gable_glazing()
        outline = composed_windows.opening_outline(pieces)
        self.assertEqual(
            composed_windows.bounds(pieces),
            (0.0, 0.0, GABLE_WIDTH, GABLE_RIDGE),
        )
        expected_corners = {
            (0.0, 0.0),
            (GABLE_WIDTH, 0.0),
            (GABLE_WIDTH, GABLE_SPRING),
            (GABLE_CENTRE, GABLE_RIDGE),
            (0.0, GABLE_SPRING),
        }
        self.assertTrue(expected_corners.issubset(set(outline)))
        expected_area = (
            GABLE_WIDTH * GABLE_SPRING
            + GABLE_WIDTH * (GABLE_RIDGE - GABLE_SPRING) / 2.0
        )
        self.assertAlmostEqual(
            abs(polygons.signed_area(outline)) / 2.0,
            expected_area,
            places=9,
        )

    def test_gable_mesh_has_framing_and_glazing_roles(self):
        pieces, dividers = gable_glazing()
        mesh = composed_windows.composed_window_mesh(
            pieces, dividers, **self.PROFILE
        )
        self.assertEqual(set(mesh[3]), {"framing", "glazing"})

    def test_a_frameless_piece_still_has_glazing(self):
        mesh = composed_windows.composed_window_mesh(
            [window_rectangle(
                0.0, 0.0, 1.0, 1.0, profile_edges=(), pane="plain"
            )],
            [],
            **self.PROFILE,
        )
        self.assertEqual(set(mesh[3]), {"glazing"})

    def test_gable_mesh_is_deterministic(self):
        pieces, dividers = gable_glazing()

        def geometry():
            return composed_windows.composed_window_mesh(
                pieces, dividers, **self.PROFILE
            )

        self.assertEqual(geometry(), geometry())


class WindowTypeTest(unittest.TestCase):
    """The type carries the section; IFC puts it there, not on the occurrence."""

    def test_partitioning_fixes_the_panel_count(self):
        model = minimal()
        with self.assertRaises(AuthoringError) as caught:
            window_type(model, "t", partitioning_type="DOUBLE_PANEL_VERTICAL",
                        lining=window_lining(depth=0.08, thickness=0.06,
                                             mullion_thickness=0.09),
                        panels=[window_panel(frame_depth=0.08,
                                             frame_thickness=0.07)])
        self.assertIn("2 panels", str(caught.exception))

    def test_a_mullioned_window_needs_a_mullion_thickness(self):
        """Zero thickness makes a panel of zero width, deep inside Bonsai."""
        model = minimal()
        with self.assertRaises(AuthoringError) as caught:
            window_type(model, "t", partitioning_type="DOUBLE_PANEL_VERTICAL",
                        lining=window_lining(depth=0.08, thickness=0.06),
                        panels=[window_panel(frame_depth=0.08,
                                             frame_thickness=0.07)] * 2)
        self.assertIn("MullionThickness", str(caught.exception))

    def test_a_transomed_window_needs_a_transom_thickness(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            window_type(model, "t", partitioning_type="DOUBLE_PANEL_HORIZONTAL",
                        lining=window_lining(depth=0.08, thickness=0.06),
                        panels=[window_panel(frame_depth=0.08,
                                             frame_thickness=0.07)] * 2)

    def test_one_mullion_halves_the_window_by_default(self):
        model = minimal()
        casement_window_type(model, "wt")
        lining = next(o for o in model.operations
                      if o.kind == "window-type").parameters["lining"]
        self.assertEqual(lining["FirstMullionOffset"], 0.5)
        self.assertIsNone(lining["SecondMullionOffset"])

    def test_two_mullions_divide_into_thirds_by_default(self):
        model = minimal()
        window_type(model, "t", partitioning_type="TRIPLE_PANEL_VERTICAL",
                    lining=window_lining(depth=0.08, thickness=0.06,
                                         mullion_thickness=0.06),
                    panels=[window_panel(frame_depth=0.08,
                                         frame_thickness=0.07)] * 3)
        lining = next(o for o in model.operations
                      if o.kind == "window-type").parameters["lining"]
        self.assertAlmostEqual(lining["FirstMullionOffset"], 1 / 3, places=9)
        self.assertAlmostEqual(lining["SecondMullionOffset"], 2 / 3, places=9)

    def test_a_partitioning_without_a_division_carries_no_offset(self):
        model = minimal()
        fixed_window_type(model, "wt")
        lining = next(o for o in model.operations
                      if o.kind == "window-type").parameters["lining"]
        for attribute in ("FirstMullionOffset", "SecondMullionOffset",
                          "FirstTransomOffset", "SecondTransomOffset"):
            self.assertIsNone(lining[attribute], attribute)

    def test_an_offset_is_a_ratio_not_a_distance(self):
        """IFC types these as IfcNormalisedRatioMeasure, so 1.6 m is refused."""
        with self.assertRaises(AuthoringError):
            window_lining(depth=0.08, thickness=0.06, mullion_thickness=0.09,
                          first_mullion_offset=1.6)

    def test_divisions_must_be_ordered(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            window_type(model, "t", partitioning_type="TRIPLE_PANEL_VERTICAL",
                        lining=window_lining(depth=0.08, thickness=0.06,
                                             mullion_thickness=0.06,
                                             first_mullion_offset=0.7,
                                             second_mullion_offset=0.3),
                        panels=[window_panel(frame_depth=0.08,
                                             frame_thickness=0.07)] * 3)

    def test_rejects_a_partitioning_outside_the_enumeration(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            window_type(model, "t", partitioning_type="QUAD_PANEL",
                        lining=window_lining(depth=0.08, thickness=0.06),
                        panels=[window_panel(frame_depth=0.08,
                                             frame_thickness=0.07)])

    def test_rejects_a_panel_operation_outside_the_enumeration(self):
        with self.assertRaises(AuthoringError):
            window_panel(frame_depth=0.08, frame_thickness=0.07,
                         operation_type="OPENS_OUTWARD")


class DoorTypeTest(unittest.TestCase):
    def test_operation_type_must_be_one_bonsai_can_build(self):
        model = minimal()
        with self.assertRaises(AuthoringError):
            door_type(model, "t", operation_type="REVOLVING",
                      lining=door_lining(depth=0.14, thickness=0.10),
                      panel=door_panel(depth=0.035))

    def test_panel_width_is_a_normalised_ratio(self):
        with self.assertRaises(AuthoringError):
            door_panel(depth=0.035, width_ratio=1.4)

    def test_absent_casing_is_unset_not_zero(self):
        """CasingDepth is IfcPositiveLengthMeasure, so zero is not a length."""
        lining = door_lining(depth=0.14, thickness=0.10)
        for attribute in ("CasingThickness", "CasingDepth", "ThresholdDepth"):
            self.assertIsNone(lining[attribute], attribute)

    def test_a_declared_casing_must_be_positive(self):
        with self.assertRaises(AuthoringError):
            door_lining(depth=0.14, thickness=0.10, casing_thickness=0.0)

    def test_the_sliding_recipe_is_the_panel_section_with_a_sliding_operation(self):
        model = typed()
        sliding_door_type(model, "dt.sliding")
        sliding = next(item for item in model.operations if item.kind == "door-type").parameters
        model = typed()
        panel_door_type(model, "dt.panel")
        panel = next(item for item in model.operations if item.kind == "door-type").parameters
        self.assertEqual(sliding["lining"], panel["lining"])
        self.assertEqual(sliding["panel"]["PanelDepth"], panel["panel"]["PanelDepth"])
        self.assertEqual(sliding["operation_type"], "SLIDING_TO_LEFT")
        self.assertEqual(sliding["panel"]["PanelOperation"], "SLIDING")
        self.assertEqual(sliding["panel"]["PanelPosition"], "LEFT")

    def test_sliding_side_must_be_left_or_right(self):
        with self.assertRaises(AuthoringError):
            sliding_door_type(typed(), "dt.sliding", sliding_side="SIDEWAYS")


class ComposedWindowDeclarationTest(unittest.TestCase):
    def test_type_records_the_shared_profile_section(self):
        operation = next(
            item for item in composed_facade().operations
            if item.kind == "composed-window-type"
        )
        self.assertAlmostEqual(operation.parameters["profile_width"], 0.06)
        self.assertAlmostEqual(operation.parameters["profile_depth"], 0.08)
        self.assertAlmostEqual(operation.parameters["glazing_thickness"], 0.006)

    def test_window_records_its_wall_type_and_materials(self):
        operation = next(
            item for item in composed_facade().operations
            if item.kind == "composed-window"
        )
        self.assertEqual(operation.references["wall"], "w")
        self.assertEqual(
            operation.references["composed_window_type"], "cwt.gable"
        )
        self.assertEqual(operation.references["framing_material"], "block")
        self.assertEqual(operation.references["glazing_material"], "plaster")


class ComposedWindowPayloadTest(unittest.TestCase):
    def payload(self):
        model = composed_facade()
        model.validate()
        return model, compiler.composed_window_payload(model)[0]

    def test_overall_size_is_the_composition_bounds(self):
        _, payload = self.payload()
        self.assertAlmostEqual(payload["overall_width"], GABLE_WIDTH, places=9)
        self.assertAlmostEqual(payload["overall_height"], GABLE_RIDGE, places=9)

    def test_height_is_not_clipped_to_the_host_wall_or_storey(self):
        model, payload = self.payload()
        host = wall_payload(model)["walls"][0]
        self.assertGreater(payload["overall_height"], host["height"])
        self.assertAlmostEqual(payload["overall_height"], 4.30, places=9)
        self.assertEqual(payload["storey"], "ground")

    def test_one_outline_and_one_through_depth_describe_the_void(self):
        _, payload = self.payload()
        self.assertTrue(payload["opening_outline"])
        self.assertAlmostEqual(
            payload["opening_through"], 0.30 + 2.0 * compiler.OPENING_REACH,
            places=9,
        )


class OpeningPlacementTest(unittest.TestCase):
    """An opening is declared against its host wall's reference line."""

    def payload(self, model, key="win"):
        model.validate()
        return {item["key"]: item for item in opening_payload(model)}[key]

    def test_lining_is_centred_in_the_wall_thickness(self):
        # A 0.30 wall centred on its reference line, and a 0.08 lining.
        self.assertAlmostEqual(self.payload(opened())["position"][1], -0.04,
                               places=9)

    def test_along_measures_to_the_centre_of_the_opening(self):
        # Declared at 3.0 along and 1.6 wide, so its left edge is at 2.2.
        self.assertAlmostEqual(self.payload(opened())["position"][0], 2.2,
                               places=9)

    def test_sill_height_measures_from_the_wall_base(self):
        self.assertAlmostEqual(self.payload(opened())["position"][2], 0.9,
                               places=9)

    def test_the_cutter_spans_the_whole_wall_and_reaches_past_it(self):
        payload = self.payload(opened())
        self.assertAlmostEqual(payload["opening_size"]["through"], 0.30 + 2 * 0.05,
                               places=9)

    def test_the_cutter_matches_the_declared_opening_in_elevation(self):
        payload = self.payload(opened())
        self.assertAlmostEqual(payload["opening_size"]["width"], 1.6, places=9)
        self.assertAlmostEqual(payload["opening_size"]["height"], 1.4, places=9)
        self.assertAlmostEqual(payload["opening_position"][2], 0.9 + 0.7,
                               places=9)

    def test_a_door_on_the_floor_cuts_below_it(self):
        """A cutter flush with the wall base leaves a coplanar boolean face."""
        model = walled()
        panel_door_type(model, "dt")
        door(model, "d", wall="w", door_type="dt", along=2.0,
             overall_width=0.9, overall_height=2.1)
        payload = self.payload(model, "d")
        self.assertAlmostEqual(payload["opening_size"]["height"], 2.1 + 0.05,
                               places=9)
        self.assertLess(
            payload["opening_position"][2] - payload["opening_size"]["height"] / 2, 0.0)

    def test_a_raised_door_stops_at_its_own_base(self):
        model = walled()
        panel_door_type(model, "dt")
        door(model, "d", wall="w", door_type="dt", along=2.0, base_offset=0.15,
             overall_width=0.9, overall_height=2.1)
        self.assertAlmostEqual(self.payload(model, "d")["opening_size"]["height"],
                               2.1, places=9)

    def test_the_opening_turns_with_its_wall(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (0.0, 6.0)), height=3.0)
        casement_window_type(model, "wt")
        window(model, "win", wall="w", window_type="wt", along=3.0,
               sill_height=0.9, overall_width=1.6, overall_height=1.4)
        self.assertAlmostEqual(self.payload(model)["angle"], math.pi / 2,
                               places=9)

    def test_base_offset_stacks_on_the_storey_elevation(self):
        model = typed()
        storey(model, "first", building="house", elevation=3.0)
        wall(model, "w", storey="first", wall_type="ext.300",
             axis=((0.0, 0.0), (6.0, 0.0)), height=3.0)
        casement_window_type(model, "wt")
        window(model, "win", wall="w", window_type="wt", along=3.0,
               sill_height=0.9, overall_width=1.6, overall_height=1.4)
        # Storey at 3.0 plus a 0.9 sill measured from the wall's own base.
        self.assertAlmostEqual(self.payload(model)["position"][2], 3.9, places=9)


class OpeningResolutionTest(unittest.TestCase):
    """IFC states a division as a ratio; the generator wants a distance."""

    def test_a_ratio_becomes_a_distance_at_the_declared_width(self):
        payload = opening_payload(opened(overall_width=1.6))[0]
        self.assertAlmostEqual(payload["lining"]["FirstMullionOffset"], 0.8,
                               places=9)

    def test_one_type_resolves_differently_at_two_sizes(self):
        """Which is the whole point of IFC measuring it as a ratio."""
        model = opened()
        window(model, "win2", wall="w", window_type="wt", along=1.0,
               sill_height=0.9, overall_width=2.4, overall_height=1.4)
        model.validate()
        found = {item["key"]: item for item in opening_payload(model)}
        self.assertAlmostEqual(found["win"]["lining"]["FirstMullionOffset"],
                               0.8, places=9)
        self.assertAlmostEqual(found["win2"]["lining"]["FirstMullionOffset"],
                               1.2, places=9)

    def test_an_absent_division_resolves_to_zero(self):
        model = walled()
        fixed_window_type(model, "wt")
        window(model, "win", wall="w", window_type="wt", along=3.0,
               sill_height=0.9, overall_width=0.9, overall_height=1.1)
        model.validate()
        self.assertEqual(
            opening_payload(model)[0]["lining"]["FirstMullionOffset"], 0.0)

    def test_materials_map_onto_the_shape_aspects_the_generator_names(self):
        model = opened(lining_material="plaster", framing_material="block",
                       glazing_material="plaster")
        self.assertEqual(
            opening_payload(model)[0]["materials"],
            {"Lining": "plaster", "Framing": "block", "Glazing": "plaster"},
        )

    def test_a_window_too_narrow_for_its_divisions_is_refused_by_name(self):
        model = opened(overall_width=0.35)
        with self.assertRaises(AuthoringError) as caught:
            model.validate()
        self.assertIn("win", str(caught.exception))
        self.assertIn("nothing of", str(caught.exception))

    def test_an_opening_on_a_wall_that_was_never_declared_is_refused(self):
        model = walled()
        casement_window_type(model, "wt")
        window(model, "win", wall="missing", window_type="wt", along=3.0,
               sill_height=0.9, overall_width=1.6, overall_height=1.4)
        with self.assertRaises(AuthoringError):
            model.validate()


class OpeningDeclarationTest(unittest.TestCase):
    def test_an_opening_emits_no_presentation_operation(self):
        """Its whole body is IfcOpenShell's, including a door's own lever."""
        model = opened()
        panel_door_type(model, "dt")
        door(model, "d", wall="w", door_type="dt", along=1.0,
             overall_width=0.9, overall_height=2.1)
        self.assertFalse([o for o in model.operations
                          if o.phase == "presentation"
                          and o.references.get("target") in ("win", "d")])

    def test_a_window_records_its_wall_and_type(self):
        operation = next(o for o in opened().operations if o.kind == "window")
        self.assertEqual(operation.references["wall"], "w")
        self.assertEqual(operation.references["window_type"], "wt")

    def test_a_door_is_internal_unless_declared_otherwise(self):
        model = walled()
        panel_door_type(model, "dt")
        door(model, "d", wall="w", door_type="dt", along=2.0,
             overall_width=0.9, overall_height=2.1)
        operation = next(o for o in model.operations if o.kind == "door")
        self.assertFalse(operation.parameters["is_external"])

    def test_a_window_is_external_unless_declared_otherwise(self):
        operation = next(o for o in opened().operations if o.kind == "window")
        self.assertTrue(operation.parameters["is_external"])

    def test_rejects_a_nonpositive_size(self):
        with self.assertRaises(AuthoringError):
            opened(overall_width=0.0)

    def test_rejects_a_negative_sill(self):
        with self.assertRaises(AuthoringError):
            opened(sill_height=-0.2)


class SillProcedureTest(unittest.TestCase):
    WIDTH, DEPTH, THICKNESS = 1.7, 0.38, 0.03

    def geometry(self):
        return sills.standard_sill_mesh(self.WIDTH, self.DEPTH, self.THICKNESS)

    def test_footprint_matches_the_declared_size(self):
        verts, _, _, _ = self.geometry()
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        self.assertAlmostEqual(max(xs) - min(xs), self.WIDTH, places=9)
        self.assertAlmostEqual(max(ys) - min(ys), self.DEPTH, places=9)

    def test_top_face_sits_on_the_sill_line(self):
        """Z = 0 is the sill line the compiler places the mesh's origin at."""
        verts, _, _, _ = self.geometry()
        zs = [v[2] for v in verts]
        self.assertAlmostEqual(max(zs), 0.0, places=9)
        self.assertAlmostEqual(min(zs), -self.THICKNESS, places=9)

    def test_every_face_is_the_sill_role(self):
        _, _, _, slots = self.geometry()
        self.assertEqual(set(slots), {"sill"})

    def test_geometry_is_deterministic(self):
        self.assertEqual(self.geometry(), self.geometry())

    def test_rejects_a_nonpositive_size(self):
        with self.assertRaises(AuthoringError):
            sills.standard_sill_mesh(0.0, self.DEPTH, self.THICKNESS)
        with self.assertRaises(AuthoringError):
            sills.standard_sill_mesh(self.WIDTH, 0.0, self.THICKNESS)
        with self.assertRaises(AuthoringError):
            sills.standard_sill_mesh(self.WIDTH, self.DEPTH, 0.0)

    def test_a_positive_reach_pushes_the_end_corner_towards_positive_y(self):
        verts, _, _, _ = sills.standard_sill_mesh(
            self.WIDTH, self.DEPTH, self.THICKNESS, corner="end", corner_reach=0.3)
        half_x, half_y = self.WIDTH / 2.0, self.DEPTH / 2.0
        shrink = self.DEPTH - 0.3
        footprint = {(round(x, 9), round(y, 9)) for x, y, z in verts if z == 0.0}
        self.assertIn((half_x + 0.3, half_y), footprint)
        # The far corner at the same end shrinks back rather than staying
        # put, so this sill's own mitre is a trapezoid at 45 degrees.
        self.assertIn((half_x - shrink, -half_y), footprint)
        # The other end's two corners stay exactly put.
        self.assertIn((-half_x, -half_y), footprint)
        self.assertIn((-half_x, half_y), footprint)

    def test_a_negative_reach_pushes_the_end_corner_towards_negative_y(self):
        verts, _, _, _ = sills.standard_sill_mesh(
            self.WIDTH, self.DEPTH, self.THICKNESS, corner="end", corner_reach=-0.3)
        half_x, half_y = self.WIDTH / 2.0, self.DEPTH / 2.0
        shrink = self.DEPTH - 0.3
        footprint = {(round(x, 9), round(y, 9)) for x, y, z in verts if z == 0.0}
        self.assertIn((half_x + 0.3, -half_y), footprint)
        self.assertIn((half_x - shrink, half_y), footprint)

    def test_the_start_corner_mitres_on_the_opposite_side(self):
        verts, _, _, _ = sills.standard_sill_mesh(
            self.WIDTH, self.DEPTH, self.THICKNESS, corner="start", corner_reach=0.3)
        half_x, half_y = self.WIDTH / 2.0, self.DEPTH / 2.0
        shrink = self.DEPTH - 0.3
        footprint = {(round(x, 9), round(y, 9)) for x, y, z in verts if z == 0.0}
        self.assertIn((-half_x - 0.3, half_y), footprint)
        self.assertIn((-half_x + shrink, -half_y), footprint)
        # The other end's two corners stay exactly put.
        self.assertIn((half_x, -half_y), footprint)
        self.assertIn((half_x, half_y), footprint)

    def test_the_mitre_is_exactly_45_degrees_in_its_own_frame(self):
        """`Δalong == Δacross == depth`, whatever `corner_reach` is - the
        property that lets two perpendicular sills' mitres coincide without
        either knowing the other's numbers."""

        verts, _, _, _ = sills.standard_sill_mesh(
            self.WIDTH, self.DEPTH, self.THICKNESS, corner="end", corner_reach=0.12)
        # The two corners at the untouched end both sit at x = -half_x; the
        # pushed and shrunk corners are the two distinct x values above it.
        footprint = sorted({(x, y) for x, y, z in verts if z == 0.0})
        shrunk, pushed = footprint[-2], footprint[-1]
        self.assertAlmostEqual(pushed[0] - shrunk[0], self.DEPTH, places=9)
        self.assertAlmostEqual(pushed[1] - shrunk[1], self.DEPTH, places=9)

    def test_a_zero_reach_still_mitres_by_shrinking_the_far_corner(self):
        """`corner_reach=0` means the near corner needs no push to reach its
        own target - not that there is no corner to mitre towards. The far
        corner still shrinks back by the full depth, or a second sill whose
        own near corner already reaches this one's target would overlap it
        outright rather than meeting it on a seam."""

        verts, _, _, _ = sills.standard_sill_mesh(
            self.WIDTH, self.DEPTH, self.THICKNESS, corner="end", corner_reach=0.0)
        half_x, half_y = self.WIDTH / 2.0, self.DEPTH / 2.0
        footprint = {(round(x, 9), round(y, 9)) for x, y, z in verts if z == 0.0}
        self.assertIn((half_x, half_y), footprint)  # near corner, unpushed
        self.assertIn((half_x - self.DEPTH, -half_y), footprint)  # far corner, shrunk by the full depth
        self.assertIn((-half_x, -half_y), footprint)
        self.assertIn((-half_x, half_y), footprint)

    def test_a_corner_with_no_reach_differs_from_no_corner_at_all(self):
        mitred = sills.standard_sill_mesh(
            self.WIDTH, self.DEPTH, self.THICKNESS, corner="end", corner_reach=0.0)
        plain = sills.standard_sill_mesh(self.WIDTH, self.DEPTH, self.THICKNESS)
        self.assertNotEqual(mitred, plain)

    def test_rejects_a_reach_without_a_corner(self):
        with self.assertRaises(AuthoringError):
            sills.standard_sill_mesh(
                self.WIDTH, self.DEPTH, self.THICKNESS, corner_reach=0.1)

    def test_rejects_an_unknown_corner(self):
        with self.assertRaises(AuthoringError):
            sills.standard_sill_mesh(
                self.WIDTH, self.DEPTH, self.THICKNESS, corner="middle")


class WindowSillDeclarationTest(unittest.TestCase):
    """A sill states no `along` or `sill_height` of its own - it is solved
    from the window and wall it names, the same way `opening_payload` solves
    the opening itself."""

    def payload(self, model):
        model.validate()
        return sill_payload(model)[0]

    def test_reaches_the_payload(self):
        model = opened()
        window_sill(model, "sill", window="win")
        self.assertEqual(self.payload(model)["key"], "sill")

    def test_footprint_grows_by_horn_and_projection(self):
        model = opened()
        window_sill(model, "sill", window="win", horn=0.05, projection=0.04)
        payload = self.payload(model)
        # 1.6 wide window, 0.30 wall: horns and projection add on each side.
        self.assertAlmostEqual(payload["width"], 1.6 + 2 * 0.05, places=9)
        self.assertAlmostEqual(payload["depth"], 0.30 + 2 * 0.04, places=9)

    def test_sits_at_the_window_sill_line(self):
        """Raised by `SILL_RISE`, not exactly on it - the wall's own
        opening void has its bottom face exactly at the sill line too, so
        left alone the two are coincident, overlapping faces."""

        model = opened()
        window_sill(model, "sill", window="win")
        self.assertAlmostEqual(self.payload(model)["position"][2],
                               0.9 + SILL_RISE, places=9)

    def test_centres_through_the_walls_thickness(self):
        model = opened()
        window_sill(model, "sill", window="win")
        # The wall is centred on its reference line, so the wall's own
        # centre - and the sill's - is at Y = 0, not the window lining's.
        self.assertAlmostEqual(self.payload(model)["position"][1], 0.0,
                               places=9)

    def test_turns_with_its_wall(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (0.0, 6.0)), height=3.0)
        casement_window_type(model, "wt")
        window(model, "win", wall="w", window_type="wt", along=3.0,
               sill_height=0.9, overall_width=1.6, overall_height=1.4)
        window_sill(model, "sill", window="win")
        self.assertAlmostEqual(self.payload(model)["angle"], math.pi / 2,
                               places=9)

    def test_rejects_a_sill_on_a_window_that_was_never_declared(self):
        model = opened()
        window_sill(model, "sill", window="missing")
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_material_is_optional(self):
        model = opened()
        window_sill(model, "sill", window="win")
        self.assertIsNone(self.payload(model)["material"])

    def test_declared_material_reaches_the_payload(self):
        model = opened()
        stucco(model, "render")
        window_sill(model, "sill", window="win", material="render")
        self.assertEqual(self.payload(model)["material"], "render")

    def test_corner_and_reach_pass_through_to_the_payload(self):
        model = opened()
        window_sill(model, "sill", window="win", corner="end", corner_reach=0.28)
        payload = self.payload(model)
        self.assertEqual(payload["corner"], "end")
        self.assertAlmostEqual(payload["corner_reach"], 0.28, places=9)

    def test_a_plain_sill_carries_no_corner(self):
        model = opened()
        window_sill(model, "sill", window="win")
        payload = self.payload(model)
        self.assertIsNone(payload["corner"])
        self.assertEqual(payload["corner_reach"], 0.0)

    def test_rejects_a_reach_without_a_corner_at_declare_time(self):
        model = opened()
        with self.assertRaises(AuthoringError):
            window_sill(model, "sill", window="win", corner_reach=0.1)

    def test_rejects_an_unknown_corner_at_declare_time(self):
        model = opened()
        with self.assertRaises(AuthoringError):
            window_sill(model, "sill", window="win", corner="middle")


def cornered() -> Building:
    """Two 0.30 walls meeting at right angles at the origin - wall-a's own
    end and wall-b's own start, not the simplest start-start pairing."""

    model = typed()
    wall(model, "wall-a", storey="ground", wall_type="ext.300",
         axis=((6.0, 0.0), (0.0, 0.0)), height=3.0)
    wall(model, "wall-b", storey="ground", wall_type="ext.300",
         axis=((0.0, 0.0), (0.0, 6.0)), height=3.0)
    return model


class OpeningHelperTest(unittest.TestCase):
    def test_sliding_window_is_still_a_window_and_forwards_the_occurrence(self):
        model = walled()
        window_type(
            model,
            "wt.slider",
            partitioning_type="DOUBLE_PANEL_VERTICAL",
            lining=window_lining(
                depth=0.08,
                thickness=0.06,
                mullion_thickness=0.06,
                to_panel_offset_x=0.04,
                to_panel_offset_y=0.025,
            ),
            panels=[
                window_panel(
                    frame_depth=0.08,
                    frame_thickness=0.07,
                    operation_type="SLIDINGHORIZONTAL",
                    position=position,
                )
                for position in ("LEFT", "RIGHT")
            ],
        )

        declared = sliding_window(
            model,
            "terrace-slider",
            wall="w",
            window_type="wt.slider",
            along=3.2,
            sill_height=0.0,
            overall_width=2.8,
            overall_height=2.3,
            direction_sense="NEGATIVE",
            lining_material="plaster",
            framing_material="block",
            glazing_material="plaster",
            is_external=False,
            name="Terrace Sliding Window",
        )

        self.assertEqual(declared, "terrace-slider")
        self.assertFalse([item for item in model.operations if item.kind == "door"])
        operation = next(
            item for item in model.operations if item.key == "terrace-slider"
        )
        self.assertEqual(operation.kind, "window")
        self.assertEqual(operation.references, {
            "wall": "w",
            "window_type": "wt.slider",
            "lining_material": "plaster",
            "framing_material": "block",
            "glazing_material": "plaster",
        })
        self.assertEqual(operation.parameters, {
            "name": "Terrace Sliding Window",
            "along": 3.2,
            "sill_height": 0.0,
            "overall_width": 2.8,
            "overall_height": 2.3,
            "direction_sense": "NEGATIVE",
            "is_external": False,
        })
        model.validate()
        payload = next(
            item for item in opening_payload(model)
            if item["key"] == "terrace-slider"
        )
        self.assertEqual(payload["kind"], "window")
        self.assertEqual(payload["base"], 0.0)
        ast.parse(model.ifc_source())

    def test_corner_window_composes_two_legs_and_one_corner_cut_declaration(self):
        model = cornered()
        fixed_window_type(model, "wt.a")
        fixed_window_type(model, "wt.b")

        declared = corner_window(
            model,
            "kitchen-corner",
            walls=("wall-a", "wall-b"),
            window_types=("wt.a", "wt.b"),
            along=(5.37, 0.43),
            sill_height=0.82,
            overall_widths=(1.20, 0.80),
            overall_height=1.35,
            direction_sense=("NEGATIVE", "POSITIVE"),
            lining_material="plaster",
            framing_material="block",
            glazing_material="plaster",
            is_external=False,
            reach=0.07,
            name="Kitchen Corner Window",
        )

        self.assertEqual(declared, ("kitchen-corner.0", "kitchen-corner.1"))
        found = {item.key: item for item in model.operations}
        self.assertEqual(found["kitchen-corner.0"].kind, "window")
        self.assertEqual(found["kitchen-corner.1"].kind, "window")
        self.assertEqual(found["kitchen-corner.opening"].kind, "corner-opening")
        for index, expected in enumerate((
            ("wall-a", "wt.a", 5.37, 1.20, "NEGATIVE"),
            ("wall-b", "wt.b", 0.43, 0.80, "POSITIVE"),
        )):
            operation = found[f"kitchen-corner.{index}"]
            wall_key, type_key, along, width, sense = expected
            self.assertEqual(operation.references["wall"], wall_key)
            self.assertEqual(operation.references["window_type"], type_key)
            self.assertEqual(operation.references["lining_material"], "plaster")
            self.assertEqual(operation.references["framing_material"], "block")
            self.assertEqual(operation.references["glazing_material"], "plaster")
            self.assertEqual(operation.parameters["along"], along)
            self.assertEqual(operation.parameters["overall_width"], width)
            self.assertEqual(operation.parameters["overall_height"], 1.35)
            self.assertEqual(operation.parameters["sill_height"], 0.82)
            self.assertEqual(operation.parameters["direction_sense"], sense)
            self.assertFalse(operation.parameters["is_external"])
            self.assertEqual(
                operation.parameters["name"],
                f"Kitchen Corner Window - {wall_key}",
            )
        opening = found["kitchen-corner.opening"]
        self.assertEqual(
            opening.references, {"wall.0": "wall-a", "wall.1": "wall-b"}
        )
        self.assertEqual(opening.parameters["base"], 0.82)
        self.assertEqual(opening.parameters["height"], 1.35)
        self.assertEqual(opening.parameters["reach"], 0.07)
        self.assertEqual(
            opening.parameters["name"], "Kitchen Corner Window - Corner Opening"
        )
        model.validate()
        self.assertEqual(
            corner_opening_payload(model)[0]["key"], "kitchen-corner.opening"
        )
        ast.parse(model.ifc_source())

    def test_corner_window_rejects_malformed_pairs_before_declaring_any_leg(self):
        settings = {
            "walls": ("wall-a", "wall-b"),
            "window_types": ("wt.a", "wt.b"),
            "along": (5.4, 0.4),
            "sill_height": 0.9,
            "overall_widths": (1.2, 0.8),
            "overall_height": 1.4,
            "direction_sense": ("POSITIVE", "POSITIVE"),
        }
        for label in (
            "walls",
            "window_types",
            "along",
            "overall_widths",
            "direction_sense",
        ):
            with self.subTest(pair=label):
                model = cornered()
                before = model.operations
                malformed = dict(settings)
                malformed[label] = (settings[label][0],)
                with self.assertRaises(AuthoringError):
                    corner_window(model, "corner", **malformed)
                self.assertEqual(model.operations, before)


class CornerOpeningDeclarationTest(unittest.TestCase):
    """A corner cut where two walls meet, sized from both walls'
    own declared thickness rather than reached by guesswork - and neither
    wall's own axis, length, or mitre is ever touched to get it."""

    def payload(self, model):
        model.validate()
        return corner_opening_payload(model)[0]

    def test_reaches_the_payload(self):
        model = cornered()
        corner_opening(model, "corner", walls=("wall-a", "wall-b"),
                       base=0.9, height=1.4)
        self.assertEqual(self.payload(model)["key"], "corner")

    def test_size_is_each_walls_own_thickness(self):
        model = cornered()
        corner_opening(model, "corner", walls=("wall-a", "wall-b"),
                       base=0.9, height=1.4, reach=0.05)
        size = self.payload(model)["size"]
        # Through wall-a is wall-a's own thickness; along it is wall-b's -
        # both walls share the 0.30 type here, plus 0.05 reach each side.
        self.assertAlmostEqual(size["through"], 0.30 + 2 * 0.05, places=9)
        self.assertAlmostEqual(size["along"], 0.30 + 2 * 0.05, places=9)
        self.assertAlmostEqual(size["height"], 1.4, places=9)

    def test_sits_at_the_declared_base(self):
        model = cornered()
        corner_opening(model, "corner", walls=("wall-a", "wall-b"),
                       base=0.9, height=1.4)
        self.assertAlmostEqual(self.payload(model)["position"][2], 0.9,
                               places=9)

    def test_finds_the_shared_corner_at_wall_as_own_end(self):
        model = cornered()
        corner_opening(model, "corner", walls=("wall-a", "wall-b"),
                       base=0.0, height=1.4)
        position = self.payload(model)["position"]
        self.assertAlmostEqual(position[0], 0.0, places=9)
        self.assertAlmostEqual(position[1], 0.0, places=9)

    def test_neither_wall_is_touched(self):
        model = cornered()
        corner_opening(model, "corner", walls=("wall-a", "wall-b"),
                       base=0.9, height=1.4)
        model.validate()
        by_key = {w["key"]: w for w in wall_payload(model)["walls"]}
        self.assertEqual(by_key["wall-a"]["start"], [6.0, 0.0])
        self.assertEqual(by_key["wall-a"]["end"], [0.0, 0.0])
        self.assertEqual(by_key["wall-b"]["start"], [0.0, 0.0])
        self.assertEqual(by_key["wall-b"]["end"], [0.0, 6.0])

    def test_rejects_more_or_fewer_than_two_walls(self):
        model = cornered()
        with self.assertRaises(AuthoringError):
            corner_opening(model, "corner", walls=("wall-a",),
                           base=0.9, height=1.4)

    def test_rejects_naming_the_same_wall_twice(self):
        model = cornered()
        corner_opening(model, "corner", walls=("wall-a", "wall-a"),
                       base=0.9, height=1.4)
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_rejects_a_role_that_is_not_a_wall(self):
        model = opened()
        corner_opening(model, "corner", walls=("w", "win"),
                       base=0.9, height=1.4)
        with self.assertRaises(AuthoringError):
            model.validate()

    def test_rejects_walls_that_do_not_share_an_endpoint(self):
        model = typed()
        wall(model, "wall-a", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (6.0, 0.0)), height=3.0)
        wall(model, "wall-b", storey="ground", wall_type="ext.300",
             axis=((0.0, 3.0), (0.0, 6.0)), height=3.0)
        corner_opening(model, "corner", walls=("wall-a", "wall-b"),
                       base=0.9, height=1.4)
        model.validate()
        with self.assertRaises(CompileError):
            corner_opening_payload(model)


class ComposedWindowCompileTest(unittest.TestCase):
    def sources(self):
        model = composed_facade()
        return model.ifc_source(), model.blender_source()

    def test_both_phases_are_valid_python(self):
        for source in self.sources():
            ast.parse(source)

    def test_no_placeholder_survives(self):
        for source in self.sources():
            self.assertNotIn("@@", source)

    def test_the_composition_reaches_the_ifc_phase(self):
        ifc_source, _ = self.sources()
        self.assertIn("gable-window", ifc_source)
        self.assertIn("opening_outline", ifc_source)


class OpeningCompileTest(unittest.TestCase):
    def sources(self):
        model = opened(lining_material="plaster", glazing_material="block")
        panel_door_type(model, "dt")
        door(model, "d", wall="w", door_type="dt", along=1.0,
             overall_width=0.9, overall_height=2.1,
             direction_sense="NEGATIVE")
        return model.ifc_source(), model.blender_source()

    def test_both_phases_are_valid_python(self):
        for source in self.sources():
            ast.parse(source)

    def test_no_placeholder_survives(self):
        for source in self.sources():
            self.assertNotIn("@@", source)

    def test_the_openings_reach_the_ifc_phase(self):
        ifc_source, _ = self.sources()
        self.assertIn("win", ifc_source)
        self.assertIn("SINGLE_SWING_LEFT", ifc_source)

    def test_compiling_is_deterministic(self):
        self.assertEqual(self.sources(), self.sources())


class WallsWithOpeningsPayloadTest(unittest.TestCase):
    """The presentation phase recalculates every wall an opening voids.

    Guards the bug where a wall carrying three openings reached the live
    scene at the polygon count of a plain unopened box: `add_feature` only
    ever writes the `IfcRelVoidsElement` relationship, and nothing else in
    the IFC phase forces the wall's Blender mesh back in sync with the voids
    it now carries. See walls.md and openings.md.
    """

    def test_an_unopened_wall_is_absent(self):
        model = walled()
        model.validate()
        self.assertEqual(walls_with_openings_payload(model), [])

    def test_a_wall_with_one_opening_is_named_once(self):
        model = opened()
        model.validate()
        self.assertEqual(walls_with_openings_payload(model), ["w"])

    def test_a_wall_with_composed_glazing_is_named_once(self):
        model = composed_facade()
        model.validate()
        self.assertEqual(walls_with_openings_payload(model), ["w"])

    def test_a_wall_with_several_openings_is_still_named_once(self):
        model = opened()
        panel_door_type(model, "dt")
        door(model, "d", wall="w", door_type="dt", along=1.0,
             overall_width=0.9, overall_height=2.1)
        window(model, "win2", wall="w", window_type="wt", along=5.0,
               sill_height=0.9, overall_width=1.0, overall_height=1.2)
        model.validate()
        self.assertEqual(walls_with_openings_payload(model), ["w"])

    def test_two_opened_walls_are_both_named(self):
        model = opened()
        wall(model, "w2", storey="ground", wall_type="ext.300",
             axis=((0.0, 4.0), (6.0, 4.0)), height=3.0)
        window(model, "win2", wall="w2", window_type="wt", along=2.0,
               sill_height=0.9, overall_width=1.0, overall_height=1.2)
        model.validate()
        self.assertEqual(walls_with_openings_payload(model), ["w", "w2"])

    def test_the_recalculation_reaches_the_presentation_phase(self):
        model = opened()
        model.validate()
        source = model.blender_source()
        self.assertIn("bim.recalculate_wall", source)
        self.assertIn('"w"', source)

    def test_an_unopened_wall_does_not_reach_the_recalculation_list(self):
        model = walled()
        model.validate()
        source = model.blender_source()
        self.assertIn("WALLS_WITH_OPENINGS = json.loads('[]')", source)


class OpeningDirectionSenseTest(unittest.TestCase):
    """IFC carries the hung side in OperationType and the rest in placement.

    So a door has four states: two operation types times two placements. The
    schema has no attribute for which way it swings, and Bonsai's own
    `bim.toggle_door_swing` flips the object for exactly this reason.
    """

    def payload(self, model, key):
        model.validate()
        return {item["key"]: item for item in opening_payload(model)}[key]

    def door_payload(self, **overrides):
        model = walled()
        panel_door_type(model, "dt", operation_type=overrides.pop(
            "operation_type", "SINGLE_SWING_LEFT"))
        settings = {"wall": "w", "door_type": "dt", "along": 2.0,
                    "overall_width": 1.0, "overall_height": 2.1}
        settings.update(overrides)
        door(model, "d", **settings)
        return self.payload(model, "d")

    def test_positive_is_the_default_and_does_not_turn(self):
        self.assertAlmostEqual(self.door_payload()["angle"], 0.0, places=9)

    def test_negative_turns_the_opening_half_a_turn(self):
        self.assertAlmostEqual(
            self.door_payload(direction_sense="NEGATIVE")["angle"],
            math.pi, places=9)

    def test_a_turned_opening_starts_from_the_opposite_corner(self):
        """Turned about its own height, the body reaches the other way."""
        forward = self.door_payload()
        turned = self.door_payload(direction_sense="NEGATIVE")
        # Declared at 2.0 along and 1.0 wide, so the corners are 1.5 and 2.5.
        self.assertAlmostEqual(forward["position"][0], 1.5, places=9)
        self.assertAlmostEqual(turned["position"][0], 2.5, places=9)

    def test_a_turned_opening_starts_from_the_other_face(self):
        # A 0.30 wall centred on its reference line, and a 0.14 door lining.
        self.assertAlmostEqual(self.door_payload()["position"][1], -0.07,
                               places=9)
        self.assertAlmostEqual(
            self.door_payload(direction_sense="NEGATIVE")["position"][1], 0.07,
            places=9)

    def test_the_four_states_are_two_types_by_two_placements(self):
        found = {
            (operation_type, sense): (
                self.door_payload(operation_type=operation_type,
                                  direction_sense=sense)["angle"]
            )
            for operation_type in ("SINGLE_SWING_LEFT", "SINGLE_SWING_RIGHT")
            for sense in ("POSITIVE", "NEGATIVE")
        }
        self.assertEqual(len(found), 4)
        # The hung side never moves the placement; only the sense does.
        self.assertEqual(found[("SINGLE_SWING_LEFT", "POSITIVE")],
                         found[("SINGLE_SWING_RIGHT", "POSITIVE")])
        self.assertNotEqual(found[("SINGLE_SWING_LEFT", "POSITIVE")],
                            found[("SINGLE_SWING_LEFT", "NEGATIVE")])

    def test_the_cutter_never_turns_with_the_opening(self):
        """It is a box about its own centre, so a half turn is a no-op."""
        forward = self.door_payload()
        turned = self.door_payload(direction_sense="NEGATIVE")
        self.assertEqual(forward["opening_angle"], turned["opening_angle"])
        self.assertEqual(forward["opening_position"],
                         turned["opening_position"])
        self.assertEqual(forward["opening_size"], turned["opening_size"])

    def test_a_window_turns_the_same_way(self):
        forward = self.payload(opened(), "win")
        turned = self.payload(opened(direction_sense="NEGATIVE"), "win")
        self.assertAlmostEqual(turned["angle"] - forward["angle"], math.pi,
                               places=9)

    def test_the_turn_stacks_on_the_wall_angle(self):
        model = typed()
        wall(model, "w", storey="ground", wall_type="ext.300",
             axis=((0.0, 0.0), (0.0, 6.0)), height=3.0)
        casement_window_type(model, "wt")
        window(model, "win", wall="w", window_type="wt", along=3.0,
               sill_height=0.9, overall_width=1.6, overall_height=1.4,
               direction_sense="NEGATIVE")
        self.assertAlmostEqual(self.payload(model, "win")["angle"],
                               math.pi / 2 + math.pi, places=9)

    def test_rejects_a_sense_outside_the_enumeration(self):
        with self.assertRaises(AuthoringError):
            self.door_payload(direction_sense="INWARD")


def guttered(**overrides) -> Building:
    """A roof with an overhang and gutters on every eave unless told otherwise.

    The boundary is deliberately longer in X than Y, so a run length is never
    ambiguous about which edge it came from.
    """

    edges = overrides.pop("edges", (0, 1, 2, 3))
    model = minimal()
    roof(model, "main-roof", storey="ground",
         boundary=[(0.0, 0.0), (10.0, 0.0), (10.0, 7.0), (0.0, 7.0)],
         angle=30.0, thickness=0.30, base_offset=3.0, overhang=0.5)
    for index in edges:
        gutter(model, f"main-roof.eave.{index}", roof="main-roof",
               edge=index, **overrides)
    return model


class GutterSectionTest(unittest.TestCase):
    def test_every_registered_profile_is_keyed_by_its_own_key(self):
        for key, entry in gutters.PROFILES.items():
            with self.subTest(profile=key):
                self.assertEqual(entry.key, key)

    def test_rejects_unknown_profile(self):
        with self.assertRaises(AuthoringError):
            gutters.profile("gutter.gold")

    def test_every_ring_closes(self):
        for key, entry in gutters.PROFILES.items():
            with self.subTest(profile=key):
                ring = entry.ring(0.125, entry.default_thickness)
                self.assertEqual(ring[0], ring[-1])

    def test_a_ring_has_two_sides_and_a_repeated_first_point(self):
        section = gutters.box_section(0.125)
        ring = gutters.sheet_ring(section, 0.0006)
        self.assertEqual(len(ring), 2 * len(section) + 1)

    def test_thickness_survives_a_fold(self):
        """Why the offset is mitred rather than per-vertex: a naive offset
        pinches a ninety degree fold, and the sheet stops being one gauge.
        """

        thickness = 0.02
        section = gutters.box_section(0.125)
        ring = gutters.sheet_ring(section, thickness)
        count = len(section)
        outward, inward = ring[:count], list(reversed(ring[count:-1]))

        def distance_to_run(point, run):
            best = float("inf")
            for start, end in zip(run, run[1:]):
                span_x, span_y = end[0] - start[0], end[1] - start[1]
                length = span_x * span_x + span_y * span_y
                along = max(0.0, min(1.0, (
                    (point[0] - start[0]) * span_x
                    + (point[1] - start[1]) * span_y
                ) / length))
                best = min(best, math.dist(
                    point,
                    (start[0] + along * span_x, start[1] + along * span_y),
                ))
            return best

        for index in range(count - 1):
            middle = (
                (outward[index][0] + outward[index + 1][0]) / 2.0,
                (outward[index][1] + outward[index + 1][1]) / 2.0,
            )
            with self.subTest(segment=index):
                self.assertAlmostEqual(
                    distance_to_run(middle, inward), thickness, places=9
                )

    def test_rejects_a_section_of_one_point(self):
        with self.assertRaises(AuthoringError):
            gutters.offset_open_polyline([(0.0, 0.0)], 0.001)

    def test_rejects_a_thickness_of_zero(self):
        with self.assertRaises(AuthoringError):
            gutters.sheet_ring(gutters.box_section(0.125), 0.0)

    def test_projection_reads_the_built_section(self):
        design = gutters.profile("gutter.half_round")
        self.assertAlmostEqual(design.projection(0.125), 0.125, places=9)

    def test_every_section_sits_on_its_back_datum(self):
        """`v = 0` is the fascia face and the body hangs outboard of it. A
        centred section puts half the gutter inboard of the eave line it is
        placed on, which is inside the roof.
        """

        for key, entry in gutters.PROFILES.items():
            with self.subTest(profile=key):
                section = entry.section(0.125)
                self.assertAlmostEqual(max(v for _, v in section), 0.0, places=9)
                self.assertLess(min(v for _, v in section), 0.0)

    def test_the_sole_is_the_lowest_point_of_the_section(self):
        for key, entry in gutters.PROFILES.items():
            with self.subTest(profile=key):
                sole = entry.sole(0.125)
                u, v = sole.up, sole.across
                section = entry.section(0.125)
                self.assertAlmostEqual(u, min(p[0] for p in section), places=9)
                self.assertLessEqual(min(p[1] for p in section), v)
                self.assertLessEqual(v, max(p[1] for p in section))

    def test_a_box_sole_is_the_middle_of_its_flat_run(self):
        sole = gutters.profile("gutter.box").sole(0.125)
        u, v = sole.up, sole.across
        self.assertAlmostEqual(u, -0.1, places=9)
        self.assertAlmostEqual(v, -0.0625, places=9)

    def test_a_sole_is_outboard_of_the_back_datum(self):
        """The body hangs outboard, so the sole's across value is negative.
        A sign flip here puts every downspout on the far side of its own
        gutter, hanging beside it and catching nothing.
        """

        for key, entry in gutters.PROFILES.items():
            with self.subTest(profile=key):
                self.assertLess(entry.sole(0.125).across, 0.0)

    def test_a_plate_is_filled_not_annular(self):
        """A stop-end closes the trough, so its profile is the section closed
        into a polygon. `ring()` is the sheet's own outline and extrudes into
        a hollow slice of the run that closes nothing.
        """

        design = gutters.profile("gutter.half_round")
        plate = design.plate(0.125)
        section = design.section(0.125)
        self.assertEqual(plate[0], plate[-1])
        self.assertEqual(len(plate), len(section) + 1)
        self.assertLess(len(plate), len(design.ring(0.125, 0.0007)))


class MitreNormalTest(unittest.TestCase):
    def test_a_square_corner_bisects(self):
        normal = gutters.mitre_normal((1.0, 0.0), (0.0, 1.0))
        self.assertAlmostEqual(normal[0], 2 ** -0.5, places=9)
        self.assertAlmostEqual(normal[1], 2 ** -0.5, places=9)

    def test_a_straight_joint_keeps_the_run_direction(self):
        self.assertEqual(
            gutters.mitre_normal((1.0, 0.0), (1.0, 0.0)), (1.0, 0.0)
        )

    def test_two_runs_doubling_back_have_no_bisector(self):
        self.assertIsNone(gutters.mitre_normal((1.0, 0.0), (-1.0, 0.0)))

    def test_the_normal_is_the_sum_not_the_difference(self):
        """The joint line is the difference of the two directions; the plane's
        normal is their sum. Swapping the two mitres the wrong way, and the
        runs miss each other instead of meeting.
        """

        normal = gutters.mitre_normal((1.0, 0.0), (0.0, 1.0))
        self.assertGreater(normal[0] + normal[1], 0.0)


class GutterDeclarationTest(unittest.TestCase):
    def test_defaults_to_a_125_half_round(self):
        parameters = guttered().operations[-1].parameters
        self.assertEqual(parameters["profile"], "gutter.half_round")
        self.assertAlmostEqual(parameters["nominal_size"], 0.125, places=9)

    def test_thickness_falls_back_to_the_profile_gauge(self):
        parameters = guttered().operations[-1].parameters
        self.assertAlmostEqual(
            parameters["thickness"],
            gutters.HALF_ROUND.default_thickness,
            places=9,
        )

    def test_a_stated_thickness_wins(self):
        parameters = guttered(thickness=0.0012).operations[-1].parameters
        self.assertAlmostEqual(parameters["thickness"], 0.0012, places=9)

    def test_rejects_a_negative_edge(self):
        with self.assertRaises(AuthoringError):
            guttered(edges=(-1,))

    def test_rejects_an_unknown_profile(self):
        with self.assertRaises(AuthoringError):
            guttered(profile="gutter.gold")


class GutterValidationTest(unittest.TestCase):
    def test_rejects_an_edge_the_boundary_does_not_have(self):
        model = guttered(edges=(7,))
        with self.assertRaisesRegex(AuthoringError, "boundary has 4 edges"):
            model.validate()

    def test_rejects_two_gutters_on_one_edge(self):
        model = guttered(edges=(0,))
        gutter(model, "second", roof="main-roof", edge=0)
        with self.assertRaisesRegex(AuthoringError, "both hang on"):
            model.validate()

    def test_rejects_a_downspout_past_the_end_of_its_run(self):
        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=99.0,
                  length=2.5)
        with self.assertRaisesRegex(AuthoringError, "11.000 m long"):
            model.validate()

    def test_accepts_a_downspout_inside_its_run(self):
        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                  length=2.5)
        model.validate()

    def test_rejects_a_swan_neck_that_cannot_fall(self):
        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                  length=2.5, standoff=0.05, drop=0.0)
        with self.assertRaisesRegex(AuthoringError, "water cannot flow down"):
            model.validate()

    def test_rejects_a_gauge_thicker_than_the_pipe(self):
        model = guttered(edges=(0,))
        with self.assertRaisesRegex(AuthoringError, "meet in the middle"):
            downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                      length=2.5, nominal_size=0.10, sheet_thickness=0.06)

    def test_rejects_a_gauge_thicker_than_a_rectangular_pipe(self):
        model = guttered(edges=(0,))
        with self.assertRaisesRegex(AuthoringError, "meet in the middle"):
            downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                      length=2.5, profile="downspout.rectangular",
                      nominal_size=0.08, sheet_thickness=0.04)

    def test_rejects_an_unknown_pipe_profile(self):
        model = guttered(edges=(0,))
        with self.assertRaises(AuthoringError):
            downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                      length=2.5, profile="downspout.oval")


class GutterPayloadTest(unittest.TestCase):
    def by_key(self, model):
        return {entry["key"]: entry for entry in gutter_payload(model)}

    def test_the_run_follows_the_overhang_line_not_the_boundary(self):
        entry = self.by_key(guttered())["main-roof.eave.0"]
        self.assertEqual(entry["start"], [-0.5, -0.5])
        self.assertAlmostEqual(entry["length"], 11.0, places=9)

    def test_base_z_stacks_on_the_storey_elevation(self):
        entry = self.by_key(guttered())["main-roof.eave.0"]
        # the run hangs just under the drip edge by its own upstand, NOT by
        # the roof's thickness: the whole section is outboard of the roof's
        # face, so its height cannot clash whatever the roof is made of.
        design = gutters.profile("gutter.half_round")
        self.assertAlmostEqual(
            entry["base_z"], 3.0 - gutters.hang(design, 0.125), places=9
        )
        self.assertGreater(entry["base_z"], 3.0 - 0.05)

    def test_every_corner_mitres_when_every_edge_is_guttered(self):
        for entry in gutter_payload(guttered()):
            with self.subTest(gutter=entry["key"]):
                self.assertEqual(entry["ends"]["start"]["kind"], "mitre")
                self.assertEqual(entry["ends"]["end"]["kind"], "mitre")

    def test_a_lone_run_stop_ends_at_both_ends(self):
        entry = self.by_key(guttered(edges=(0,)))["main-roof.eave.0"]
        self.assertEqual(entry["ends"]["start"]["kind"], "stop_end")
        self.assertEqual(entry["ends"]["end"]["kind"], "stop_end")

    def test_a_run_mitres_only_against_a_neighbour_that_exists(self):
        entry = self.by_key(guttered(edges=(0, 1)))["main-roof.eave.0"]
        self.assertEqual(entry["ends"]["start"]["kind"], "stop_end")
        self.assertEqual(entry["ends"]["end"]["kind"], "mitre")
        self.assertEqual(entry["ends"]["end"]["against"], "main-roof.eave.1")

    def test_a_run_hangs_from_the_drip_edge_not_the_soffit(self):
        """The section is wholly outboard of the roof's face, so its height
        cannot clash whatever the roof's thickness is. Hanging it by that
        thickness puts it on the soffit line - the bottom of the fascia
        instead of the top - which no clearance check would flag, because
        there was never a clash to flag.
        """

        entry = self.by_key(guttered())["main-roof.eave.0"]
        design = gutters.profile(entry["profile"])
        top = entry["base_z"] + design.rise(entry["nominal_size"])
        self.assertLess(top, 3.0)
        self.assertAlmostEqual(top, 3.0 - gutters.EAVE_CLEARANCE, places=9)

    def test_the_hang_ignores_the_roofs_thickness(self):
        """Two roofs of different buildup hang their gutters identically."""

        def hung(thickness):
            model = minimal()
            roof(model, "r", storey="ground",
                 boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
                 angle=30.0, thickness=thickness, base_offset=3.0,
                 overhang=0.5)
            gutter(model, "r.eave.0", roof="r", edge=0)
            return gutter_payload(model)[0]["base_z"]

        self.assertAlmostEqual(hung(0.10), hung(0.60), places=9)

    def test_the_mitre_is_stated_in_the_runs_own_frame(self):
        """Every square corner reads the same locally, whichever way the run
        points in the world. That is the property which lets two runs land on
        one plane without either being handed the other's numbers.
        """

        for entry in gutter_payload(guttered()):
            with self.subTest(gutter=entry["key"]):
                normal = entry["ends"]["end"]["normal"]
                self.assertAlmostEqual(normal[0], 2 ** -0.5, places=9)
                self.assertAlmostEqual(normal[1], 2 ** -0.5, places=9)

    def test_a_start_mitre_reverses_its_end_counterpart(self):
        entry = self.by_key(guttered())["main-roof.eave.0"]
        start = entry["ends"]["start"]["normal"]
        self.assertAlmostEqual(start[0], -(2 ** -0.5), places=9)
        self.assertAlmostEqual(start[1], 2 ** -0.5, places=9)

    def test_a_straight_downspout_has_three_segments(self):
        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                  length=2.5)
        path = self.by_key(model)["main-roof.eave.0"]["downspouts"][0]["path"]
        self.assertEqual(len(path), 4)
        self.assertAlmostEqual(path[-1][2], -2.5, places=9)

    def test_a_shoe_kicks_outboard_and_hangs_below(self):
        """The kick goes to negative Y - away from the building - so the water
        leaves the pipe pointing off the wall rather than at its own plinth.
        """

        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                  length=2.5, termination="shoe", standoff=0.22)
        path = self.by_key(model)["main-roof.eave.0"]["downspouts"][0]["path"]
        self.assertEqual(len(path), 5)
        self.assertLess(path[-1][1], path[-2][1])
        self.assertLess(path[-1][2], path[-2][2])
        kick = gutters.SHOE_LENGTH * math.sin(math.radians(gutters.SHOE_ANGLE))
        self.assertAlmostEqual(path[-1][1], 0.22 - kick, places=9)

    def test_length_is_the_whole_fall_not_the_last_segment(self):
        """Both pipes fall `length` to the end of the straight run, so changing
        the swan neck moves no part of the pipe except the neck.
        """

        model = guttered(edges=(0,))
        downspout(model, "a", gutter="main-roof.eave.0", along=1.0,
                  length=2.5, drop=0.10, standoff=0.20)
        downspout(model, "b", gutter="main-roof.eave.0", along=2.0,
                  length=2.5, drop=0.30, standoff=0.40)
        paths = {s["key"]: s["path"]
                 for s in self.by_key(model)["main-roof.eave.0"]["downspouts"]}
        self.assertAlmostEqual(paths["a"][-1][2], -2.5, places=9)
        self.assertAlmostEqual(paths["b"][-1][2], -2.5, places=9)

    def test_rejects_a_neck_that_uses_the_whole_fall(self):
        model = guttered(edges=(0,))
        with self.assertRaisesRegex(AuthoringError, "whole run"):
            downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                      length=0.3, drop=0.2, standoff=0.2)

    def test_rejects_an_unknown_termination(self):
        model = guttered(edges=(0,))
        with self.assertRaises(AuthoringError):
            downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                      length=2.5, termination="splayed")

    def test_a_round_pipe_resolves_to_a_bored_disk(self):
        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                  length=2.5, nominal_size=0.100, sheet_thickness=0.0015)
        pipe = self.by_key(model)["main-roof.eave.0"]["downspouts"][0]["pipe"]
        self.assertEqual(pipe["shape"], "round")
        self.assertAlmostEqual(pipe["radius"], 0.050, places=9)
        self.assertAlmostEqual(pipe["inner_radius"], 0.0485, places=9)

    def test_a_rectangular_pipe_resolves_to_a_hollow_rectangle(self):
        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                  length=2.5, profile="downspout.rectangular",
                  nominal_size=0.080, sheet_thickness=0.0015)
        pipe = self.by_key(model)["main-roof.eave.0"]["downspouts"][0]["pipe"]
        self.assertEqual(pipe["shape"], "rectangular")
        self.assertAlmostEqual(pipe["x"], 0.080, places=9)
        self.assertAlmostEqual(pipe["y"], 0.080, places=9)
        self.assertAlmostEqual(pipe["wall"], 0.0015, places=9)
        self.assertGreater(pipe["fillet"], 0.0)

    def test_each_pipe_profile_defaults_to_its_own_catalogued_size(self):
        model = guttered(edges=(0,))
        downspout(model, "a", gutter="main-roof.eave.0", along=1.0, length=2.5)
        downspout(model, "b", gutter="main-roof.eave.0", along=2.0, length=2.5,
                  profile="downspout.rectangular")
        sizes = {s["key"]: s["nominal_size"]
                 for s in self.by_key(model)["main-roof.eave.0"]["downspouts"]}
        self.assertAlmostEqual(sizes["a"], gutters.PIPE_ROUND.default_size)
        self.assertAlmostEqual(sizes["b"], gutters.PIPE_RECTANGULAR.default_size)

    def test_downspouts_reach_the_run_they_drop_from(self):
        model = guttered(edges=(0,))
        downspout(model, "ds", gutter="main-roof.eave.0", along=3.0,
                  length=2.5)
        entry = self.by_key(model)["main-roof.eave.0"]
        self.assertEqual(
            [spout["key"] for spout in entry["downspouts"]], ["ds"]
        )

    def test_the_drop_point_lands_under_the_gutter(self):
        """The point a downspout hangs from has to be the section's own lowest
        point: centred across the trough, and at its sole.

        Run over **every** profile, not just the default. A half-round's sole
        sits at `(-nominal/2, -nominal/2)` - up and across identical - so it
        passes even when the two are transposed, and passing on it proves
        nothing. A box gutter's sole is at `(-0.8 * nominal, -nominal/2)`,
        where a swap is 37.5 mm of sideways error at 125 mm.
        """

        for key in sorted(gutters.PROFILES):
            with self.subTest(profile=key):
                model = guttered(edges=(0,), profile=key)
                entry = self.by_key(model)["main-roof.eave.0"]
                point = entry["drop_point"]
                section = gutters.profile(key).section(entry["nominal_size"])
                lowest = min(u for u, _ in section)
                self.assertAlmostEqual(point["up"], lowest, places=9)
                self.assertLess(point["across"], 0.0)
                self.assertAlmostEqual(
                    point["across"],
                    sum(v for u, v in section if abs(u - lowest) < 1e-12)
                    / sum(1 for u, _ in section if abs(u - lowest) < 1e-12),
                    places=9,
                )

    def test_the_drop_point_is_centred_across_the_trough(self):
        """A pipe hangs on the middle of its gutter's width, whatever section
        that gutter has.
        """

        for key in sorted(gutters.PROFILES):
            with self.subTest(profile=key):
                model = guttered(edges=(0,), profile=key)
                entry = self.by_key(model)["main-roof.eave.0"]
                section = gutters.profile(key).section(entry["nominal_size"])
                middle = (min(v for _, v in section)
                          + max(v for _, v in section)) / 2.0
                self.assertAlmostEqual(
                    entry["drop_point"]["across"], middle, places=9
                )


class TrimEdgeClassifierTests(unittest.TestCase):
    """The one rule that decides which edges carry which trim.

    The edge direction follows face A's outward winding. Reversing the face
    order reverses this direction too; the BMesh adapter resolves that order.
    """

    PITCH = math.radians(40.0)

    def sloping(self, toward):
        """A roof face's outward normal, tipped down toward `toward` in plan."""

        return (
            toward[0] * math.sin(self.PITCH),
            toward[1] * math.sin(self.PITCH),
            math.cos(self.PITCH),
        )

    def test_a_level_fold_between_two_faces_is_a_ridge(self):
        north = self.sloping((0.0, 1.0))
        south = self.sloping((0.0, -1.0))
        self.assertEqual(
            trims.edge_kind(north, south, (1.0, 0.0, 0.0)),
            trims.RIDGE,
        )

    def test_the_same_fold_raking_is_a_hip(self):
        east = self.sloping((1.0, 0.0))
        south = self.sloping((0.0, -1.0))
        direction = (1.0, -1.0, -math.tan(self.PITCH))
        length = math.sqrt(sum(component * component for component in direction))
        direction = tuple(component / length for component in direction)
        self.assertEqual(
            trims.edge_kind(east, south, direction),
            trims.HIP,
        )

    def test_two_faces_folding_inward_are_a_valley(self):
        """Two wings rise away from their common reflex eaves corner."""

        rise = math.tan(self.PITCH)
        along_x = self.sloping((0.0, 1.0))
        along_y = self.sloping((1.0, 0.0))
        # Face A walks uphill from the reflex corner along this valley.
        direction = (-1.0, -1.0, rise)
        length = math.sqrt(sum(component * component for component in direction))
        direction = tuple(component / length for component in direction)
        self.assertEqual(
            trims.edge_kind(along_x, along_y, direction),
            trims.VALLEY,
        )

    def test_a_level_edge_against_no_surface_is_an_eave(self):
        south = self.sloping((0.0, -1.0))
        rafter_cut = (0.0, -1.0, 0.0)
        self.assertEqual(
            trims.edge_kind(south, rafter_cut, (1.0, 0.0, 0.0)),
            trims.EAVE,
        )

    def test_a_raking_edge_against_no_surface_is_a_verge(self):
        """What a gable raises, and the only edge a flashing lands on."""

        south = self.sloping((0.0, -1.0))
        gable = (1.0, 0.0, 0.0)
        direction = (0.0, math.cos(self.PITCH), math.sin(self.PITCH))
        self.assertEqual(
            trims.edge_kind(south, gable, direction),
            trims.VERGE,
        )

    def test_an_edge_between_two_non_surfaces_carries_nothing(self):
        self.assertIsNone(
            trims.edge_kind((1.0, 0.0, 0.0), (0.0, 0.0, -1.0),
                            (0.0, 1.0, 0.0))
        )

    def test_reversing_faces_and_their_wound_edge_preserves_the_fold(self):
        north = self.sloping((0.0, 1.0))
        south = self.sloping((0.0, -1.0))
        self.assertEqual(trims.edge_kind(north, south, (1.0, 0.0, 0.0)), trims.RIDGE)
        self.assertEqual(trims.edge_kind(south, north, (-1.0, 0.0, 0.0)), trims.RIDGE)

    def test_coplanar_roof_subdivisions_carry_no_trim(self):
        normal = self.sloping((0.0, 1.0))
        self.assertIsNone(trims.edge_kind(normal, normal, (1.0, 0.0, 0.0)))


class VergeTrimSectionTests(unittest.TestCase):
    def test_the_board_hangs_below_the_arris_it_stands_on(self):
        """`upstand` is the lip above the roof's own edge; the rest of the
        board laps down over it. The **bottom** is what has to be below zero -
        the centre sits above it whenever the lip is more than half the board,
        which is true of every profile shipped here.
        """

        for key in sorted(trims.PROFILES):
            with self.subTest(profile=key):
                profile = trims.profile(key)
                across, up = profile.centre()
                self.assertLess(up - profile.height / 2.0, 0.0)
                self.assertGreater(across, 0.0)

    def test_the_outer_face_sits_on_the_gable_plane(self):
        """Flush is what the whole placement is for: the section's zero is the
        arris, so the board's outer face is the roof's own edge and its centre
        is exactly half a thickness inboard of it.
        """

        profile = trims.profile("verge.standard")
        across, _ = profile.centre()
        self.assertAlmostEqual(across, profile.thickness / 2.0, places=9)

    def test_the_top_stands_its_upstand_above_the_arris(self):
        profile = trims.profile("verge.standard")
        _, up = profile.centre()
        self.assertAlmostEqual(
            up + profile.height / 2.0, profile.upstand, places=9
        )

    def test_overrides_replace_only_what_they_state(self):
        resolved = trims.profile("verge.standard").resolved(height=0.4)
        self.assertAlmostEqual(resolved["height"], 0.4)
        self.assertAlmostEqual(
            resolved["thickness"], trims.profile("verge.standard").thickness
        )

    def test_refuses_a_board_that_would_float_above_the_roof(self):
        """An upstand at or past the height puts the whole board above the
        arris with nothing lapping the edge - geometry the kernel would build
        happily and no one would notice until they looked.
        """

        with self.assertRaises(AuthoringError):
            trims.profile("verge.standard").resolved(height=0.15, upstand=0.15)

    def test_refuses_a_negative_or_zero_dimension(self):
        for override in ({"height": 0.0}, {"thickness": -0.01},
                         {"upstand": -0.01}):
            with self.subTest(override=override):
                with self.assertRaises(AuthoringError):
                    trims.profile("verge.standard").resolved(**override)

    def test_refuses_an_unknown_profile(self):
        with self.assertRaises(AuthoringError):
            trims.profile("verge.invented")


class RoofVergeTrimDeclarationTests(unittest.TestCase):
    def roofed(self, **extra):
        model = Building("trimmed")
        project(model, "p")
        site(model, "s", project="p")
        building(model, "b", site="s")
        storey(model, "st", building="b", elevation=0.0)
        roof(model, "r", storey="st",
             boundary=[(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
             angle=35.0, thickness=0.30, covering="tile.clay", **extra)
        roof_edge(model, "r", 1, defines_slope=False)
        roof_edge(model, "r", 3, defines_slope=False)
        return model

    def test_a_roof_carries_its_trim_choice_and_no_edge_list(self):
        """Which edges are verges is a fact about the solid, so it is
        classified where the solid exists rather than travelling in a payload.
        """

        entry = roof_payload(
            self.roofed(verge_trim="verge.standard",
                        verge_trim_material="metal.zinc")
        )[0]
        self.assertEqual(entry["verge_trim"], "verge.standard")
        self.assertEqual(entry["verge_trim_material"], "metal.zinc")
        self.assertNotIn("edges", entry["verge_trim_section"])

    def test_the_section_arrives_resolved(self):
        """The template branches on nothing and recomputes nothing."""

        entry = roof_payload(self.roofed(verge_trim="verge.standard"))[0]
        profile = trims.profile("verge.standard")
        section = entry["verge_trim_section"]
        self.assertEqual(section["height"], profile.height)
        self.assertEqual(section["thickness"], profile.thickness)
        # The centre must agree with the section it was solved beside, upstand
        # and all - not merely be a pair of numbers.
        self.assertEqual(
            entry["verge_trim_centre"],
            list(profile.centre(upstand=section["upstand"])),
        )

    def test_a_non_numeric_dimension_is_refused_by_name(self):
        """Named at the declaration, like every other number on `roof()`,
        rather than as a TypeError from a comparison three modules away.
        """

        for override in ({"verge_trim_height": "170mm"},
                         {"verge_trim_thickness": "80"},
                         {"verge_trim_upstand": object()}):
            with self.subTest(override=override):
                with self.assertRaises(AuthoringError):
                    self.roofed(verge_trim="verge.standard", **override)

    def test_the_lip_clears_the_covering_that_is_laid(self):
        """The defect this exists for: the catalogue's own fixing height left
        0.011 m of daylight over a clay tile, and board and tiles read as one
        object from any distance.
        """

        entry = roof_payload(self.roofed(verge_trim="verge.standard"))[0]
        envelope = tiles.profile("tile.clay").envelope()
        self.assertAlmostEqual(
            entry["verge_trim_section"]["upstand"],
            trims.upstand_over(envelope),
            places=9,
        )
        self.assertGreaterEqual(
            entry["verge_trim_section"]["upstand"] - envelope,
            trims.COVER_LIP,
        )

    def test_a_stated_upstand_beats_the_derived_one(self):
        entry = roof_payload(
            self.roofed(verge_trim="verge.standard", verge_trim_upstand=0.11)
        )[0]
        self.assertAlmostEqual(entry["verge_trim_section"]["upstand"], 0.11)

    def test_an_uncovered_roof_falls_back_to_the_profile(self):
        """Nothing to clear, so nothing to derive from."""

        model = Building("bare")
        project(model, "p")
        site(model, "s", project="p")
        building(model, "b", site="s")
        storey(model, "st", building="b", elevation=0.0)
        roof(model, "r", storey="st",
             boundary=[(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
             angle=35.0, thickness=0.30, verge_trim="verge.standard")
        entry = roof_payload(model)[0]
        self.assertAlmostEqual(
            entry["verge_trim_section"]["upstand"],
            trims.profile("verge.standard").upstand,
        )

    def test_an_override_reaches_the_payload(self):
        entry = roof_payload(
            self.roofed(verge_trim="verge.standard", verge_trim_height=0.4)
        )[0]
        self.assertAlmostEqual(entry["verge_trim_section"]["height"], 0.4)

    def test_an_undeclared_trim_stays_absent(self):
        entry = roof_payload(self.roofed())[0]
        self.assertIsNone(entry["verge_trim"])
        self.assertIsNone(entry["verge_trim_section"])

    def test_an_impossible_trim_is_refused_at_declaration(self):
        with self.assertRaises(AuthoringError):
            self.roofed(verge_trim="verge.standard",
                        verge_trim_height=0.1, verge_trim_upstand=0.2)

    def test_an_unknown_trim_profile_is_refused_by_name(self):
        with self.assertRaises(AuthoringError):
            self.roofed(verge_trim="verge.invented")


class CapDomeValidationTest(unittest.TestCase):
    """A piece has to close over, and its head has to clear what closes on it."""

    def profile(self, **overrides):
        fields = dict(
            key="c", width=0.30, foot=0.11, crown=0.14, thickness=0.018,
            module=0.30, nose=0.045, inset=0.022, rim=0.012,
            build=caps.half_round_cap_mesh,
        )
        fields.update(overrides)
        return caps.CapProfile(**fields)

    def test_rejects_a_cap_with_no_nose(self):
        """Which is a tube, seen straight up from the eave below it."""
        with self.assertRaises(AuthoringError) as caught:
            self.profile(nose=0.0).validate()
        self.assertIn("open tube", str(caught.exception))

    def test_rejects_a_nose_that_eats_the_whole_module(self):
        with self.assertRaises(AuthoringError) as caught:
            self.profile(nose=0.16).validate()
        self.assertIn("no body", str(caught.exception))

    def test_rejects_a_head_the_dome_cannot_clear(self):
        with self.assertRaises(AuthoringError) as caught:
            self.profile(inset=0.010).validate()
        self.assertIn("no clearance", str(caught.exception))

    def test_accepts_the_ordinary_case(self):
        self.profile().validate()

    def test_rejects_a_cap_with_no_rim(self):
        """No step at the closure is a run with no joint anywhere on it."""
        with self.assertRaises(AuthoringError) as caught:
            self.profile(rim=0.0).validate()
        self.assertIn("one extruded tube", str(caught.exception))

    def test_a_rim_is_not_measured_against_the_gauge(self):
        """It is a step in the silhouette, not a fold in the surface."""
        self.profile(rim=0.012, thickness=0.018).validate()

    def test_rejects_a_nose_longer_than_its_piece(self):
        with self.assertRaises(AuthoringError):
            self.profile().geometry(
                caps.seating(0.089, math.cos(math.radians(30.0)), 0.11), 0.020
            )


class TurfTests(unittest.TestCase):
    def scene(self):
        from building_author import Building, project, site
        model = Building("turf-test")
        project(model, "project")
        site(model, "site", project="project")
        return model

    def test_concave_boundary_and_compilation(self):
        from building_author import turf
        from building_author.polygons import signed_area
        model = self.scene()
        turf(model, "lawn", site="site", elevation=-.32,
             boundary=[(0,0),(0,3),(1,3),(1,1),(3,1),(3,0)], name="A label")
        model.validate()
        operation = model.operations[-1]
        self.assertEqual(operation.references, {"site": "site"})
        self.assertEqual(signed_area(operation.parameters["boundary"])/2, 5)
        self.assertEqual(operation.parameters["elevation"], -.32)
        ast.parse(model.ifc_source())
        ast.parse(model.blender_source())

    def test_invalid_geometry_and_site(self):
        from building_author import turf
        for boundary in [[(0,0),(1,1),(2,2)], [(0,0),(3,3),(0,3),(2,0)]]:
            with self.assertRaises(AuthoringError):
                turf(self.scene(), "lawn", site="site", boundary=boundary)
        model = self.scene()
        turf(model, "lawn", site="project", boundary=[(0,0),(2,0),(2,2)])
        with self.assertRaises(AuthoringError):
            model.validate()
