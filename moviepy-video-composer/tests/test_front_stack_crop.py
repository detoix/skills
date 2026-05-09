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


class FrontStackCropTests(unittest.TestCase):
    def test_front_stack_crop_box_for_vertical_half_panel(self):
        self.assertEqual(
            compose_video.front_stack_presenter_crop_box((1080, 1920), (1080, 960)),
            (0, 240, 1080, 960),
        )
        self.assertEqual(
            compose_video.front_stack_presenter_crop_box((720, 1280), (1080, 960)),
            (0, 160, 720, 640),
        )

    def test_front_presenter_panel_matches_front_path_segment(self):
        panel = {"kind": "presenter", "path": "synced/front/A04.mp4"}
        self.assertTrue(compose_video.is_front_presenter_panel(panel, panel["path"]))
        self.assertTrue(
            compose_video.is_front_presenter_panel(
                {"kind": "presenter"},
                "synced\\front\\A04.mp4",
            )
        )

    def test_profile_presenter_panel_is_not_front_stack_crop(self):
        panel = {"kind": "presenter", "path": "synced/profile/P04.mp4"}
        clip = DummyClip(1080, 1920)

        cropped, crop_box = compose_video.maybe_crop_front_stack_presenter(
            clip,
            panel,
            panel["path"],
            (1080, 960),
        )

        self.assertIs(cropped, clip)
        self.assertIsNone(crop_box)

    def test_broll_panel_is_not_front_stack_crop_even_under_front_path(self):
        panel = {"kind": "broll", "source": "manual", "path": "broll/front/demo.mp4"}
        clip = DummyClip(1080, 1920)

        cropped, crop_box = compose_video.maybe_crop_front_stack_presenter(
            clip,
            panel,
            panel["path"],
            (1080, 960),
        )

        self.assertIs(cropped, clip)
        self.assertIsNone(crop_box)

    def test_landscape_front_presenter_panel_is_not_cropped(self):
        panel = {"kind": "presenter", "path": "synced/front/A04.mp4"}
        clip = DummyClip(1920, 1080)

        cropped, crop_box = compose_video.maybe_crop_front_stack_presenter(
            clip,
            panel,
            panel["path"],
            (1080, 960),
        )

        self.assertIs(cropped, clip)
        self.assertIsNone(crop_box)

    def test_pip_center_square_crop_remains_centered(self):
        crop = compose_video.center_crop_to_square(DummyClip(1080, 1920))

        self.assertEqual(crop, {"x1": 0, "y1": 420, "width": 1080, "height": 1080})

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
                    "loop",
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
                    "loop",
                    "STACK_2 bottom clip",
                    (1080, 960),
                    {"kind": "broll", "path": "panel.png"},
                )

            self.assertEqual(clip, "fitted")
            self.assertEqual(handles, [source_clip, None, source_clip, "fitted", "scale_handle"])
            motion.assert_not_called()
            normalize.assert_called_once_with(image_path.resolve(), 2.0, 0.0, "loop", "STACK_2 bottom clip")
            scale.assert_called_once_with(source_clip, (1080, 960), "cover")

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
                    "loop",
                    "GRID_4 clip 1",
                    (540, 960),
                    {"kind": "broll", "path": "panel.png", "treatment": "still_motion"},
                )

            motion.assert_called_once_with(image_path.resolve(), 2.0, (540, 960), "push-in", "GRID_4 clip 1")


if __name__ == "__main__":
    unittest.main()
