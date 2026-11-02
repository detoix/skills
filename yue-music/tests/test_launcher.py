"""Validate the real CLI without weights, downloads, or generated audio."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import yue


class LauncherTests(unittest.TestCase):
    def test_attention_selection_keeps_full_request_and_dry_run_side_effect_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = {"style": "dance", "lyrics": "[Verse]\nStay with me",
                       "semantic_tokens": [1, 2, 3, 4], "abc": "X:1\nK:C\nC D E F|",
                       "steps": 32, "seed": 17, "lm_seed": 23, "duration": 200}
            source = base / "replay.json"
            source.write_text(json.dumps(request), encoding="utf-8")
            for device, option, expected in (("Vulkan0", "auto", "tiled-gemm"),
                                              ("CPU", "auto", "flash"),
                                              ("CUDA0", "auto", "flash"),
                                              ("Vulkan0", "flash", "flash")):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "yue.py"), "replay", "--request", str(source),
                     "--device", device, "--nar-attention", option, "--nar-query-tile", "128",
                     "--out-dir", str(base / "take"), "--dry-run"],
                    capture_output=True, text=True, check=True,
                )
                data = json.loads(result.stdout)
                self.assertEqual(data["nar_attention"], expected)
                self.assertEqual(data["nar_query_tile"], 128)
                self.assertEqual(data["request"], {**request, "output_format": "wav24"})
                self.assertFalse((base / "take").exists())

    def test_invalid_query_tile_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "take"
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "yue.py"), "generate", "--style", "dance",
                 "--nar-query-tile", "129", "--out-dir", str(out), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(out.exists())

    def test_model_selection_does_not_require_other_backbones(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            manifest = yue.read_json(yue.SKILL / "assets/models.json")
            names = [entry["name"] for entry in manifest["files"] if entry["name"] != yue.VAE]
            for name in names:
                self.assertEqual([entry["name"] for entry in yue.model_files(root, name)], [name, yue.VAE])
            with self.assertRaisesRegex(ValueError, "Select --model"):
                yue.model_files(root)
            (models / names[0]).touch()
            self.assertEqual(yue.model_files(root)[0]["name"], names[0])
            (models / names[1]).touch()
            with self.assertRaisesRegex(ValueError, "Select --model"):
                yue.model_files(root)
            with self.assertRaisesRegex(ValueError, "Unknown model"):
                yue.model_files(root, "missing.gguf")

    def test_json_artifacts_preserve_unicode_with_legacy_shell_decoding(self):
        data = {"lyrics": "Zażółć gęślą jaźń. 日本語"}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            yue.write_json(path, data)
            self.assertEqual(json.loads(path.read_bytes().decode("cp1250")), data)
            self.assertEqual(yue.read_json(path), data)

    def test_lyrics_file_overrides_request_without_shell_text_conversion(self):
        lyrics = "[Verse]\nZażółć gęślą jaźń.\n日本語\n"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            text = base / "tekst żółć.txt"
            text.write_bytes(b"\xef\xbb\xbf" + lyrics.replace("\n", "\r\n").encode("utf-8"))
            request = base / "request.json"
            request.write_text(json.dumps({"style": "rock", "lyrics": "incorrect text"}), encoding="utf-8-sig")
            out = base / "take"
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "yue.py"), "generate", "--request", str(request),
                 "--lyrics-file", str(text), "--out-dir", str(out), "--dry-run"],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            self.assertEqual(json.loads(result.stdout)["request"]["lyrics"], lyrics)
            self.assertFalse(out.exists())

    def test_dry_run_from_unicode_path_has_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "Music żółć" / "yue-music"
            scripts = skill / "scripts"
            scripts.mkdir(parents=True)
            for name in ("yue.py", "runtime_support.py"):
                shutil.copy2(SCRIPTS / name, scripts / name)
            out = Path(temporary) / "audio with spaces" / "take"
            result = subprocess.run(
                [sys.executable, str(scripts / "yue.py"), "generate", "--style", "eurodance",
                 "--lyrics", "[Verse]\nDance in the light", "--duration", "200", "--steps", "32",
                 "--out-dir", str(out), "--dry-run"],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            data = json.loads(result.stdout)
            self.assertEqual(Path(data["runtime"]), skill / ".runtime")
            self.assertEqual(data["request"]["duration"], 200)
            self.assertEqual(data["request"]["steps"], 32)
            self.assertFalse((skill / ".runtime").exists())
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
