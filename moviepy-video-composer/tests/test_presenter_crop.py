import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "compose_video.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("compose_video", SCRIPT_PATH)
compose_video = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["compose_video"] = compose_video
SPEC.loader.exec_module(compose_video)


class DummyClip:
    def __init__(self, width: int, height: int):
        self.w = width
        self.h = height
        self.size = (width, height)

    def cropped(self, **kwargs):
        return kwargs


class PresenterCropTests(unittest.TestCase):
    def test_presenter_crop_uses_explicit_panel_crop_only(self):
        panel = {"kind": "presenter", "path": "synced/front/A04.mp4", "crop": {"x": 0, "y": 120, "width": 1080, "height": 1080}}
        clip = DummyClip(1080, 1920)

        cropped = compose_video.crop_clip_to_rect(clip, panel["crop"], "test")

        self.assertEqual(cropped, {"x1": 0, "y1": 120, "width": 1080, "height": 1080})

    def test_presenter_crop_bounds_are_validated(self):
        clip = DummyClip(1080, 1920)

        with self.assertRaises(ValueError):
            compose_video.crop_clip_to_rect(clip, {"x": 0, "y": 1000, "width": 1080, "height": 1080}, "test")

    def test_presenter_overlay_without_crop_fails(self):
        with self.assertRaises(ValueError):
            compose_video.validate_and_expand_entry(
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [
                        {"kind": "broll", "source_type": "webpage", "path": "broll/site.mp4"},
                        {"kind": "presenter", "path": "synced/profile/P01.mp4", "treatment": "overlay", "overlay_scale": 0.34},
                    ],
                    "start_time": 0.0,
                    "end_time": 2.0,
                },
                0,
            )

    def test_stack2_presenter_without_crop_fails(self):
        with self.assertRaises(ValueError):
            compose_video.validate_and_expand_entry(
                {
                    "type": "B_ROLL",
                    "layout": "stack2",
                    "panels": [
                        {"kind": "presenter", "path": "synced/front/A04.mp4"},
                        {"kind": "broll", "source_type": "manual", "path": "broll/front/demo.mp4"},
                    ],
                    "start_time": 0.0,
                    "end_time": 2.0,
                },
                0,
            )

    def test_legacy_overlay_crop_fields_fail(self):
        with self.assertRaises(ValueError):
            compose_video.validate_and_expand_entry(
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [
                        {"kind": "broll", "source_type": "webpage", "path": "broll/site.mp4"},
                        {
                            "kind": "presenter",
                            "path": "synced/profile/P01.mp4",
                            "treatment": "overlay",
                            "overlay_crop_x": 0,
                            "overlay_crop_y": 420,
                            "overlay_crop_size": 1080,
                        },
                    ],
                    "start_time": 0.0,
                    "end_time": 2.0,
                },
                0,
            )

    def test_broll_still_motion_panel_uses_motion_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "panel.png"
            image_path.write_bytes(b"placeholder")

            with (
                patch.object(compose_video, "build_still_motion_image_clip", return_value=("motion", ["motion_handle"])) as motion,
                patch.object(compose_video, "normalize_video_clip") as normalize,
            ):
                clip, handles = compose_video.build_panel_clip(
                    root,
                    "panel.png",
                    2.0,
                    0.0,
                    "STACK_2 bottom clip",
                    (1080, 960),
                    {"kind": "broll", "path": "panel.png", "treatment": "still_motion", "motion_type": "pan-left"},
                )

            self.assertEqual(clip, "motion")
            self.assertEqual(handles, ["motion_handle"])
            normalize.assert_not_called()
            motion.assert_called_once_with(image_path.resolve(), 2.0, (1080, 960), "pan-left", "STACK_2 bottom clip")

    def test_broll_static_image_panel_keeps_standard_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "panel.png"
            image_path.write_bytes(b"placeholder")
            source_clip = DummyClip(100, 100)

            with (
                patch.object(compose_video, "build_still_motion_image_clip") as motion,
                patch.object(compose_video, "normalize_video_clip", return_value=(source_clip, None)) as normalize,
                patch.object(compose_video, "scale_clip_to_canvas", return_value=("fitted", ["scale_handle"])) as scale,
            ):
                clip, handles = compose_video.build_panel_clip(
                    root,
                    "panel.png",
                    2.0,
                    0.0,
                    "STACK_2 bottom clip",
                    (1080, 960),
                    {"kind": "broll", "path": "panel.png"},
                )

            self.assertEqual(clip, "fitted")
            self.assertEqual(handles, [source_clip, None, None, "fitted", "scale_handle"])
            motion.assert_not_called()
            normalize.assert_called_once_with(image_path.resolve(), 2.0, 0.0, "STACK_2 bottom clip", "loop_safe_broll")
            scale.assert_called_once_with(source_clip, (1080, 960), "cover")

    def test_stack2_presenter_with_crop_uses_crop_before_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video_path = root / "S03.mp4"
            video_path.write_bytes(b"placeholder")
            source_clip = DummyClip(1080, 1920)

            with (
                patch.object(compose_video, "normalize_video_clip", return_value=(source_clip, "source")) as normalize,
                patch.object(compose_video, "scale_clip_to_canvas", return_value=("fitted", ["scale_handle"])) as scale,
            ):
                clip, handles = compose_video.build_panel_clip(
                    root,
                    "S03.mp4",
                    2.0,
                    0.0,
                    "STACK_2 top clip",
                    (1080, 960),
                    {"kind": "presenter", "path": "S03.mp4", "crop": {"x": 0, "y": 120, "width": 1080, "height": 1080}},
                )

            self.assertEqual(clip, "fitted")
            cropped = {"x1": 0, "y1": 120, "width": 1080, "height": 1080}
            self.assertEqual(handles, [cropped, "source", cropped, "fitted", "scale_handle"])
            normalize.assert_called_once_with(video_path.resolve(), 2.0, 0.0, "STACK_2 top clip", "presenter")
            scale.assert_called_once_with(cropped, (1080, 960), "cover")

    def test_top_level_broll_treatment_is_rejected(self):
        with self.assertRaises(ValueError):
            compose_video.validate_and_expand_entry(
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "treatment": "evidence_overlay",
                    "panels": [{"kind": "broll", "source_type": "web-evidence", "path": "evidence.png", "treatment": "overlay"}],
                    "start_time": 0.0,
                    "end_time": 2.0,
                },
                0,
            )

    def test_web_evidence_overlay_expands_from_panel_treatments(self):
        expanded = compose_video.validate_and_expand_entry(
            {
                "type": "B_ROLL",
                "layout": "fullscreen",
                "panels": [
                    {"kind": "presenter", "path": "source-assets/presenter-front.mp4", "treatment": "blur"},
                    {"kind": "broll", "source_type": "web-evidence", "path": "evidence.png", "treatment": "overlay"},
                ],
                "start_time": 0.0,
                "end_time": 2.0,
            },
            0,
        )

        self.assertEqual(expanded["clip_path"], "evidence.png")
        self.assertEqual(expanded["background_path"], "source-assets/presenter-front.mp4")

    def test_pip_expands_from_presenter_overlay_treatment(self):
        expanded = compose_video.validate_and_expand_entry(
            {
                "type": "B_ROLL",
                "layout": "fullscreen",
                "panels": [
                    {"kind": "broll", "source_type": "webpage", "path": "broll/site.mp4"},
                    {
                        "kind": "presenter",
                        "path": "synced/profile/P01.mp4",
                        "treatment": "overlay",
                        "overlay_scale": 0.34,
                        "crop": {"x": 0, "y": 420, "width": 1080, "height": 1080},
                    },
                ],
                "start_time": 0.0,
                "end_time": 2.0,
            },
            0,
        )

        self.assertEqual(expanded["background_path"], "broll/site.mp4")
        self.assertEqual(expanded["overlay_path"], "synced/profile/P01.mp4")
        self.assertEqual(expanded["overlay_scale"], 0.34)
        self.assertEqual(expanded["overlay_crop"], {"x": 0, "y": 420, "width": 1080, "height": 1080})

    def test_pip_allows_still_motion_background_treatment(self):
        expanded = compose_video.validate_and_expand_entry(
            {
                "type": "B_ROLL",
                "layout": "fullscreen",
                "panels": [
                    {
                        "kind": "broll",
                        "source_type": "generated-image",
                        "path": "broll/generated/S06.png",
                        "treatment": "still_motion",
                        "motion_type": "pan-left",
                    },
                    {
                        "kind": "presenter",
                        "path": "synced/profile/P01.mp4",
                        "treatment": "overlay",
                        "overlay_scale": 0.34,
                        "crop": {"x": 0, "y": 420, "width": 1080, "height": 1080},
                    },
                ],
                "start_time": 0.0,
                "end_time": 2.0,
            },
            0,
        )

        self.assertEqual(expanded["background_path"], "broll/generated/S06.png")
        self.assertEqual(expanded["overlay_path"], "synced/profile/P01.mp4")

    def test_fullscreen_still_motion_expands_panel_motion_type(self):
        expanded = compose_video.validate_and_expand_entry(
            {
                "type": "B_ROLL",
                "layout": "fullscreen",
                "panels": [
                    {
                        "kind": "broll",
                        "source_type": "generated-image",
                        "path": "broll/generated/S01.png",
                        "treatment": "still_motion",
                        "motion_type": "pan-left",
                    }
                ],
                "start_time": 0.0,
                "end_time": 2.0,
            },
            0,
        )

        self.assertEqual(expanded["treatment"], "still_motion")
        self.assertEqual(expanded["motion_type"], "pan-left")

    def test_web_evidence_requires_blurred_presenter_panel(self):
        with self.assertRaises(ValueError):
            compose_video.validate_and_expand_entry(
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [{"kind": "broll", "source_type": "web-evidence", "path": "evidence.png", "treatment": "overlay"}],
                    "start_time": 0.0,
                    "end_time": 2.0,
                },
                0,
            )

    def test_panel_role_is_rejected(self):
        with self.assertRaises(ValueError):
            compose_video.validate_and_expand_entry(
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [{"kind": "broll", "source_type": "manual", "path": "panel.png", "role": "background"}],
                    "start_time": 0.0,
                    "end_time": 2.0,
                },
                0,
            )

    def test_broll_still_motion_panel_defaults_to_push_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "panel.png"
            image_path.write_bytes(b"placeholder")

            with patch.object(compose_video, "build_still_motion_image_clip", return_value=("motion", [])) as motion:
                compose_video.build_panel_clip(
                    root,
                    "panel.png",
                    2.0,
                    0.0,
                    "GRID_4 clip 1",
                    (540, 960),
                    {"kind": "broll", "path": "panel.png", "treatment": "still_motion"},
                )

            motion.assert_called_once_with(image_path.resolve(), 2.0, (540, 960), "push-in", "GRID_4 clip 1")

    def test_duration_fit_holds_tiny_presenter_tail(self):
        self.assertEqual(compose_video.duration_fit_action(5.95, 6.0, "presenter"), "hold_last_frame")

    def test_duration_fit_ping_pongs_bounded_presenter_tail(self):
        self.assertEqual(compose_video.duration_fit_action(5.2, 6.0, "presenter"), "ping_pong")

    def test_duration_fit_rejects_presenter_tail_over_limit(self):
        with self.assertRaises(ValueError):
            compose_video.duration_fit_action(5.0, 6.1, "presenter")

    def test_duration_fit_loops_loop_safe_broll(self):
        self.assertEqual(compose_video.duration_fit_action(3.0, 6.0, "loop_safe_broll"), "loop")

    def test_duration_fit_rejects_loop_unsafe_broll_over_hold_tail(self):
        with self.assertRaises(ValueError):
            compose_video.duration_fit_action(5.0, 5.5, "loop_unsafe_broll")


if __name__ == "__main__":
    unittest.main()
