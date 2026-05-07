import importlib.util
import sys
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
