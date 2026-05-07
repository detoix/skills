import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_reel_captions.py"
SPEC = importlib.util.spec_from_file_location("generate_reel_captions", SCRIPT_PATH)
captions = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(captions)


class FinalAudioAlignmentTests(unittest.TestCase):
    def write_project(self, root: Path, manifest_chunks: list[dict]) -> Path:
        (root / "manifests").mkdir()
        script = {
            "tts_chunks": [
                {"chunk_id": "T10", "voice_text": "Przed zakupem sprawdź też pilot."},
                {"chunk_id": "T11", "voice_text": "Etykieta energetyczna w Unii jest od A do G."},
            ]
        }
        script_path = root / "script.json"
        script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        manifest = {"duration_seconds": 86.76, "tts_chunks": manifest_chunks}
        (root / "manifests" / "final-audio-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )
        return script_path

    def test_uses_final_audio_manifest_start_not_scaled_script_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_path = self.write_project(
                root,
                [
                    {"chunk": "T10", "timeline_start_seconds": 63.48, "duration_seconds": 8.48},
                    {"chunk": "T11", "timeline_start_seconds": 72.56, "duration_seconds": 6.56},
                ],
            )
            _transcript, segments, info = captions.load_script_segments(script_path, 86.76)

            self.assertEqual(info["alignment_source"], "final-audio-manifest")
            self.assertEqual(segments[1]["start"], 72.56)
            self.assertNotAlmostEqual(segments[1]["start"], 76.17, places=2)

    def test_missing_final_audio_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifests").mkdir()
            script_path = root / "script.json"
            script_path.write_text(
                json.dumps({"tts_chunks": [{"chunk_id": "T11", "voice_text": "Tekst."}]}),
                encoding="utf-8",
            )
            with self.assertRaises(FileNotFoundError):
                captions.load_script_segments(script_path, 86.76)

    def test_missing_chunk_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_path = self.write_project(
                root,
                [{"chunk": "T10", "timeline_start_seconds": 63.48, "duration_seconds": 8.48}],
            )
            with self.assertRaisesRegex(ValueError, "T11"):
                captions.load_script_segments(script_path, 86.76)

    def test_missing_timeline_start_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_path = self.write_project(
                root,
                [
                    {"chunk": "T10", "timeline_start_seconds": 63.48, "duration_seconds": 8.48},
                    {"chunk": "T11", "duration_seconds": 6.56},
                ],
            )
            with self.assertRaisesRegex(ValueError, "timeline_start_seconds"):
                captions.load_script_segments(script_path, 86.76)


if __name__ == "__main__":
    unittest.main()
