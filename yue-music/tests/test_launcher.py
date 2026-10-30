"""Validate the real CLI without weights, downloads, or generated audio."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class LauncherTests(unittest.TestCase):
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
