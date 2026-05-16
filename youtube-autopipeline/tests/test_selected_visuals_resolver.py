import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "selected_visuals_resolver.py"


spec = importlib.util.spec_from_file_location("selected_visuals_resolver", SCRIPT_PATH)
resolver = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(resolver)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class SelectedVisualsResolverTests(unittest.TestCase):
    def write_script(self, root: Path, source_type: str, *, segment_id: str = "S01") -> None:
        write_json(
            root / "script.json",
            {
                "metadata": {"format_mode": "vertical"},
                "segments": [
                    {
                        "segment_id": segment_id,
                        "type": "B_ROLL",
                        "start_seconds": 0,
                        "end_seconds": 3,
                        "duration_seconds": 3,
                        "layout": "fullscreen",
                        "narration": "Test narration.",
                        "visual_direction": "Test visual",
                        "editor_notes": "Valid asset",
                        "panels": [{"kind": "broll", "source_type": source_type}],
                    }
                ],
                "tts_chunks": [],
                "broll_queries": [],
                "assembly_notes": [],
            },
        )

    def resolve(self, root: Path, item: dict) -> tuple[dict, list[str]]:
        manifest_path = root / "manifests" / "selected-visuals.json"
        write_json(manifest_path, {"schema_version": 1, "items": [item]})
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return resolver.resolve_manifest(root, manifest_path, manifest)

    def test_missing_source_type_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "manual")
            asset = root / "broll" / "manual" / "asset.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"asset")

            _, errors = self.resolve(root, {"segment_id": "S01", "scene_id": "V01", "section_pattern": "fullscreen-image", "local_path": "broll/manual/asset.png"})

            self.assertTrue(any("source_type" in error for error in errors), errors)

    def test_source_type_matching_script_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "manual")
            asset = root / "broll" / "manual" / "asset.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"asset")

            resolved, errors = self.resolve(
                root,
                {
                    "segment_id": "S01",
                    "scene_id": "V01",
                    "section_pattern": "fullscreen-image",
                    "source_type": "manual",
                    "local_path": "broll/manual/asset.png",
                    "accepted": True,
                    "reason": "Manual asset selected",
                    "risk": "none",
                },
            )

            self.assertFalse(errors, errors)
            self.assertEqual(resolved["items"][0]["source_type"], "manual")
            self.assertIn("sha256", resolved["items"][0])

    def test_source_type_mismatch_with_script_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "webpage")
            asset = root / "broll" / "manual" / "asset.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"asset")

            _, errors = self.resolve(
                root,
                {
                    "segment_id": "S01",
                    "scene_id": "V01",
                    "section_pattern": "fullscreen-image",
                    "source_type": "manual",
                    "local_path": "broll/manual/asset.png",
                    "accepted": True,
                    "reason": "Wrong source type",
                    "risk": "none",
                },
            )

            self.assertTrue(any("does not match script" in error for error in errors), errors)

    def test_generated_folder_with_manual_source_type_stays_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "manual")
            asset = root / "broll" / "generated" / "local.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"local graphic")

            resolved, errors = self.resolve(
                root,
                {
                    "segment_id": "S01",
                    "scene_id": "V01",
                    "section_pattern": "fullscreen-image",
                    "source_type": "manual",
                    "local_path": "broll/generated/local.png",
                    "accepted": True,
                    "reason": "Local manual graphic",
                    "risk": "none",
                },
            )

            self.assertFalse(errors, errors)
            self.assertEqual(resolved["items"][0]["source_type"], "manual")

    def test_generated_image_without_accepted_z_image_plan_entry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "generated-image")
            asset = root / "broll" / "generated" / "S01.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"generated")

            _, errors = self.resolve(
                root,
                {
                    "segment_id": "S01",
                    "scene_id": "V01",
                    "section_pattern": "fullscreen-generated-motion",
                    "source_type": "generated-image",
                    "local_path": "broll/generated/S01.png",
                    "accepted": True,
                    "reason": "Generated image",
                    "risk": "none",
                },
            )

            self.assertTrue(any("z-image-plan" in error for error in errors), errors)

    def test_generated_image_with_accepted_z_image_plan_entry_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "generated-image")
            asset = root / "broll" / "generated" / "S01.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"generated")
            write_json(
                root / "manifests" / "z-image-plan.json",
                {"items": [{"output": "broll/generated/S01.png", "review": {"accepted": True}}]},
            )

            _, errors = self.resolve(
                root,
                {
                    "segment_id": "S01",
                    "scene_id": "V01",
                    "section_pattern": "fullscreen-generated-motion",
                    "source_type": "generated-image",
                    "local_path": "broll/generated/S01.png",
                    "accepted": True,
                    "reason": "Generated image",
                    "risk": "none",
                },
            )

            self.assertFalse(errors, errors)

    def test_webpage_without_source_url_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "webpage")
            asset = root / "broll" / "web" / "capture.webm"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"web")

            _, errors = self.resolve(
                root,
                {
                    "segment_id": "S01",
                    "scene_id": "V01",
                    "section_pattern": "fullscreen-webpage",
                    "source_type": "webpage",
                    "local_path": "broll/web/capture.webm",
                    "accepted": True,
                    "reason": "Web capture",
                    "risk": "none",
                },
            )

            self.assertTrue(any("source_url" in error for error in errors), errors)

    def test_synthetic_motion_without_board_proof_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_script(root, "synthetic-motion")
            asset = root / "broll" / "boards" / "S01" / "S01.webm"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"board")

            _, errors = self.resolve(
                root,
                {
                    "segment_id": "S01",
                    "scene_id": "V01",
                    "section_pattern": "synthetic-motion-capture",
                    "source_type": "synthetic-motion",
                    "local_path": "broll/boards/S01/S01.webm",
                    "accepted": True,
                    "reason": "Board clip",
                    "risk": "synthetic",
                },
            )

            self.assertTrue(any("board-manifest" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
