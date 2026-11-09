"""Exercise the presentation material resolver across recycled IFC style IDs."""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


TEMPLATE = Path(__file__).resolve().parents[1] / "building_author/templates/presentation_phase.py"


class Material(dict):
    def __init__(self, name, style_id=0):
        super().__init__()
        self.name = name
        self.BIMStyleProperties = SimpleNamespace(ifc_definition_id=style_id)
        self.parameters = None


class Materials(list):
    def get(self, name):
        return next((material for material in self if material.name == name), None)

    def new(self, name):
        candidate_name = name
        suffix = 1
        while self.get(candidate_name) is not None:
            candidate_name = f"{name}.{suffix:03d}"
            suffix += 1
        material = Material(candidate_name)
        self.append(material)
        return material


class Style:
    def __init__(self, name):
        self.Name = name

    def is_a(self, ifc_class):
        return ifc_class == "IfcSurfaceStyle"


def material_batch():
    """Execute the actual resolver/assignment loop; shader construction is separate."""

    tree = ast.parse(TEMPLATE.read_text())
    helpers = {"material_style_name", "material_matches_key",
               "imported_materials", "fallback_material"}
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in helpers:
            selected.append(node)
        elif (isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "resolved_materials"
                      for target in node.targets)):
            selected.append(node)
        elif (isinstance(node, ast.For) and isinstance(node.iter, ast.GeneratorExp)
              and any(isinstance(child, ast.Constant) and child.value == "pbr-material"
                      for child in ast.walk(node.iter))):
            selected.append(node)
    if len(selected) != len(helpers) + 2:
        raise AssertionError("The presentation material resolver batch was not found")
    return compile(ast.Module(body=selected, type_ignores=[]), str(TEMPLATE), "exec")


class PresentationMaterialTest(unittest.TestCase):
    def fixture(self, order=("recess.dark", "glazing")):
        stale = Material("BA::recess.dark", style_id=17)
        glazing = Material("BA::glazing.001", style_id=17)
        masonry = Material("BA::masonry", style_id=23)
        materials = Materials([stale, glazing, masonry])
        styles = {17: Style("BA::glazing"), 23: Style("BA::masonry")}
        target = SimpleNamespace(type="MESH", data=SimpleNamespace(materials=[stale]))
        layered = SimpleNamespace(type="MESH", data=SimpleNamespace(materials=[masonry, glazing]))
        parameters = {
            "recess.dark": {"alpha": 1.0, "base_color": (0.04, 0.04, 0.04)},
            "glazing": {"alpha": 0.22, "base_color": (0.65, 0.78, 0.84)},
            "masonry": {"alpha": 1.0, "base_color": (0.7, 0.3, 0.2)},
        }

        def apply_pbr(material, values):
            material.parameters = values.copy()

        namespace = {
            "bpy": SimpleNamespace(data=SimpleNamespace(materials=materials)),
            "ifc_file": SimpleNamespace(by_id=styles.__getitem__),
            "apply_pbr": apply_pbr,
            "OPERATIONS": [
                {"kind": "pbr-material", "references": {"target": key},
                 "parameters": parameters[key]}
                for key in (*order, "masonry")
            ],
            "MATERIAL_TARGETS": {"recess.dark": ["recess"]},
            "objects": {"recess": target, "layered-wall": layered},
        }
        return namespace, stale, glazing, masonry

    def test_stale_style_id_cannot_turn_an_opaque_target_into_glass_in_either_order(self):
        for order in (("recess.dark", "glazing"), ("glazing", "recess.dark")):
            with self.subTest(order=order):
                namespace, stale, glazing, _ = self.fixture(order)
                exec(material_batch(), namespace)
                resolved = namespace["resolved_materials"]["recess.dark"]
                self.assertIsNot(resolved, stale)
                self.assertEqual(resolved.parameters["alpha"], 1.0)
                self.assertEqual(resolved["building_author_material_key"], "recess.dark")
                self.assertEqual(resolved.BIMStyleProperties.ifc_definition_id, 0)
                self.assertIs(namespace["objects"]["recess"].data.materials[0], resolved)
                self.assertEqual(glazing.parameters["alpha"], 0.22)
                self.assertEqual(glazing["building_author_material_key"], "glazing")
                self.assertEqual(stale.name, "BA::recess.dark")
                self.assertEqual(stale.BIMStyleProperties.ifc_definition_id, 17)
                self.assertIsNone(stale.parameters)

    def test_layered_slots_are_upgraded_in_place_and_keep_their_order(self):
        namespace, _, glazing, masonry = self.fixture()
        slots = namespace["objects"]["layered-wall"].data.materials
        exec(material_batch(), namespace)
        self.assertIs(slots[0], masonry)
        self.assertIs(slots[1], glazing)
        self.assertEqual(masonry.parameters["alpha"], 1.0)
        self.assertEqual(glazing.parameters["alpha"], 0.22)

    def test_rerun_reuses_the_tagged_fallback_despite_the_name_collision(self):
        namespace, _, _, _ = self.fixture()
        batch = material_batch()
        exec(batch, namespace)
        first = namespace["resolved_materials"]["recess.dark"]
        materials = namespace["bpy"].data.materials
        count = len(materials)
        exec(batch, namespace)
        self.assertIs(namespace["resolved_materials"]["recess.dark"], first)
        self.assertEqual(len(materials), count)

    def test_semantic_tag_prevents_recycled_id_from_overriding_a_renamed_material(self):
        namespace, stale, _, _ = self.fixture()
        stale.name = "BA::glazing.002"
        stale["building_author_material_key"] = "recess.dark"
        exec(material_batch(), namespace)
        self.assertIsNone(stale.parameters)
        self.assertEqual(stale["building_author_material_key"], "recess.dark")

    def test_tile_field_uses_the_resolved_material_object(self):
        namespace, stale, _, _ = self.fixture()
        exec(material_batch(), namespace)
        tree = ast.parse(TEMPLATE.read_text())
        assignment = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name) and node.test.id == "material_key"
            and any(isinstance(child, ast.Name) and child.id == "resolved_materials"
                    for child in ast.walk(node))
        )
        namespace["material_key"] = "recess.dark"
        namespace["mesh"] = SimpleNamespace(materials=[])
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(TEMPLATE), "exec"), namespace)
        assigned = namespace["mesh"].materials[0]
        self.assertIs(assigned, namespace["resolved_materials"]["recess.dark"])
        self.assertIsNot(assigned, stale)


if __name__ == "__main__":
    unittest.main()
