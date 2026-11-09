"""Native IFC swept-geometry regression for the explicit lift-slide assembly."""

import copy
import importlib
import unittest
from unittest.mock import patch

from building_author.values import AuthoringError
from building_author.window_assemblies import (
    add_lift_slide_representation, validate_lift_slide_assembly,
)

try:
    import numpy as np
    import ifcopenshell
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.root
    import ifcopenshell.api.unit
    import ifcopenshell.geom
    import ifcopenshell.util.shape
    import ifcopenshell.validate
    from ifcopenshell.util.shape_builder import ShapeBuilder
except ImportError:
    ifcopenshell = None


# The named type owns the actual defaults/provenance. These are explicit test
# inputs: broad published section sizes plus generic simplified small details.
ASSEMBLY = dict(
    frame_depth=.174, jamb_width=.048, head_height=.048,
    threshold_height=.010, rail_width=.004, rail_height=.005,
    track_spacing=.087, sash_depth=.077, sash_face_width=.095,
    sash_bottom_height=.095, meeting_overlap=.050, interlock_width=.020,
    sealing_clearance=.002, glazing_thickness=.024, glazing_bite=.003,
    sliding_side="RIGHT",
)


class LiftSlideAssemblyValidationTest(unittest.TestCase):
    def test_section_is_normalized_without_mutating_the_declaration(self):
        source = copy.deepcopy(ASSEMBLY)
        result = validate_lift_slide_assembly(source, 2.4, 2.3)
        self.assertEqual(result, ASSEMBLY)
        self.assertIsNot(result, source)
        self.assertEqual(source, ASSEMBLY)

    def test_invalid_or_unbuildable_sections_are_rejected(self):
        for changes in (
            {"track_spacing": .078}, {"frame_depth": .150},
            {"rail_width": .080}, {"meeting_overlap": .100},
            {"interlock_width": .060}, {"glazing_thickness": .077},
            {"glazing_bite": .096}, {"rail_height": 0},
            {"sliding_side": "BOTH"}, {"threshold_height": float("nan")},
            {"unknown_dimension": .1},
        ):
            with self.subTest(changes=changes), self.assertRaises(AuthoringError):
                validate_lift_slide_assembly({**ASSEMBLY, **changes}, 2.4, 2.3)
        with self.assertRaises(AuthoringError):
            validate_lift_slide_assembly({}, 2.4, 2.3)
        for width, height in ((.3, 2.3), (2.4, .2)):
            with self.subTest(size=(width, height)), self.assertRaises(AuthoringError):
                validate_lift_slide_assembly(ASSEMBLY, width, height)


@unittest.skipIf(ifcopenshell is None, "IfcOpenShell required for native assembly tests")
class LiftSlideIfcGeometryTest(unittest.TestCase):
    def setUp(self):
        self.shapes = []

    def fixture(self, prefix=None):
        file = ifcopenshell.file(schema="IFC4")
        ifcopenshell.api.root.create_entity(file, ifc_class="IfcProject", name="Assembly test")
        unit = ifcopenshell.api.unit.add_si_unit(file, unit_type="LENGTHUNIT", prefix=prefix)
        ifcopenshell.api.unit.assign_unit(file, units=[unit])
        context = ifcopenshell.api.context.add_context(file, context_type="Model")
        body = ifcopenshell.api.context.add_context(
            file, context_type="Model", context_identifier="Body",
            target_view="MODEL_VIEW", parent=context,
        )
        window = ifcopenshell.api.root.create_entity(file, ifc_class="IfcWindow", name="Lift-slide")
        window.Representation = file.create_entity("IfcProductDefinitionShape", Representations=[])
        return file, body, window

    def build(self, *, side="RIGHT", offset=0.0, prefix=None):
        file, body, window = self.fixture(prefix)
        representation = add_lift_slide_representation(
            file, context=body, overall_width=2.4, overall_height=2.3,
            assembly={**ASSEMBLY, "sliding_side": side},
            part_of_product=window.Representation, lining_offset=offset,
        )
        ifcopenshell.api.geometry.assign_representation(file, product=window, representation=representation)
        ifcopenshell.api.geometry.edit_object_placement(file, product=window)
        return file, representation, window

    def shape(self, item):
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), item)
        self.shapes.append(shape)
        return shape.geometry if hasattr(shape, "geometry") else shape

    def bounds(self, item):
        vertices = np.asarray(self.shape(item).verts).reshape(-1, 3)
        return np.array((vertices.min(axis=0), vertices.max(axis=0)))

    @staticmethod
    def by_name(representation):
        return {item.SweptArea.ProfileName: item for item in representation.Items}

    def test_upstream_frame_and_extrusion_helpers_build_every_native_solid(self):
        upstream = importlib.import_module("ifcopenshell.api.geometry.add_window_representation")
        with patch.object(upstream, "create_ifc_window_frame_simple",
                          wraps=upstream.create_ifc_window_frame_simple) as frames, \
                patch.object(ShapeBuilder, "extrude", autospec=True,
                             side_effect=ShapeBuilder.extrude) as extrusions:
            _, representation, _ = self.build()
        self.assertEqual(frames.call_count, 3)
        self.assertEqual(frames.call_args_list[0].args[2][-1], 0)
        self.assertEqual(extrusions.call_count, 10)
        self.assertEqual(representation.RepresentationType, "SweptSolid")
        self.assertTrue(all(item.is_a("IfcExtrudedAreaSolid") for item in representation.Items))
        for item in representation.Items:
            self.assertGreater(ifcopenshell.util.shape.get_volume(self.shape(item)), 0)

    def test_ifc_schema_and_three_disjoint_material_role_assignments(self):
        file, representation, window = self.build()
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(file, logger)
        self.assertEqual(logger.statements, [])
        aspects = {aspect.Name: aspect for aspect in window.Representation.HasShapeAspects}
        self.assertEqual(set(aspects), {"Lining", "Framing", "Glazing"})
        ids = []
        for role, count in (("Lining", 4), ("Framing", 4), ("Glazing", 2)):
            items = aspects[role].ShapeRepresentations[0].Items
            self.assertEqual(len(items), count)
            ids.extend(item.id() for item in items)
        self.assertEqual(len(set(ids)), 10)
        self.assertEqual(set(ids), {item.id() for item in representation.Items})

    def test_full_envelope_low_base_two_tracks_and_actual_rail_seating(self):
        _, representation, window = self.build()
        np.testing.assert_allclose(self.bounds(window), ((0, 0, 0), (2.4, .174, 2.3)), atol=1e-8)
        parts = self.by_name(representation)
        np.testing.assert_allclose(self.bounds(parts["Low threshold"]),
                                   ((.048, 0, 0), (2.352, .174, .010)), atol=1e-8)
        sash_bounds = {}
        for role, centre in (("Fixed", .0435), ("Sliding", .1305)):
            rail = self.bounds(parts[role + " track rail"])
            sash = self.bounds(parts[role + " sash"])
            sash_bounds[role] = sash
            np.testing.assert_allclose(rail[:, 0], (.048, 2.352), atol=1e-8)
            np.testing.assert_allclose(rail[:, 1], (centre - .002, centre + .002), atol=1e-8)
            np.testing.assert_allclose(rail[:, 2], (.010, .015), atol=1e-8)
            self.assertAlmostEqual(sash[0, 2], rail[1, 2])
            self.assertAlmostEqual(sash[1, 2], 2.250)
        self.assertAlmostEqual(sash_bounds["Sliding"][0, 1] - sash_bounds["Fixed"][1, 1], .010)
        self.assertAlmostEqual(sash_bounds["Fixed"][1, 0] - sash_bounds["Sliding"][0, 0], .050)
        fixed_lip = self.bounds(parts["Fixed meeting interlock"])
        moving_lip = self.bounds(parts["Sliding meeting interlock"])
        self.assertAlmostEqual(moving_lip[0, 1] - fixed_lip[1, 1], .002)

    def test_glass_has_positive_hidden_frame_bite_and_depth_clearance(self):
        _, representation, _ = self.build()
        parts = self.by_name(representation)
        for role in ("Fixed", "Sliding"):
            sash, pane = (self.bounds(parts[role + suffix]) for suffix in (" sash", " glazing"))
            self.assertAlmostEqual(pane[0, 0], sash[0, 0] + .095 - .003)
            self.assertAlmostEqual(pane[1, 0], sash[1, 0] - .095 + .003)
            self.assertAlmostEqual(pane[0, 2], sash[0, 2] + .095 - .003)
            self.assertAlmostEqual(pane[1, 2], sash[1, 2] - .095 + .003)
            self.assertGreater(pane[0, 1] - sash[0, 1], .002)
            self.assertGreater(sash[1, 1] - pane[1, 1], .002)

    def test_left_hand_is_an_x_reflection_with_same_track_depth_and_positive_solids(self):
        _, right, _ = self.build(side="RIGHT")
        _, left, _ = self.build(side="LEFT")
        for name, right_item in self.by_name(right).items():
            actual = self.bounds(self.by_name(left)[name])
            expected = self.bounds(right_item)
            expected[:, 0] = 2.4 - expected[::-1, 0]
            np.testing.assert_allclose(actual, expected, atol=1e-8, err_msg=name)

    def test_lining_offset_and_project_units_preserve_si_geometry(self):
        _, original, _ = self.build()
        _, shifted, _ = self.build(offset=-.061, prefix="MILLI")
        for name, item in self.by_name(original).items():
            expected = self.bounds(item)
            expected[:, 1] -= .061
            np.testing.assert_allclose(self.bounds(self.by_name(shifted)[name]), expected, atol=1e-8)

    def test_invalid_size_fails_before_adding_any_ifc_entities(self):
        file, context, window = self.fixture()
        count = len(list(file))
        with self.assertRaises(AuthoringError):
            add_lift_slide_representation(
                file, context=context, overall_width=.3, overall_height=2.3,
                assembly=ASSEMBLY, part_of_product=window.Representation,
            )
        self.assertEqual(len(list(file)), count)


if __name__ == "__main__":
    unittest.main()
