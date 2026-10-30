"""Exercise platform support without downloading weights or running inference."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import runtime_support as support


class RuntimeSupportTests(unittest.TestCase):
    def test_binary_paths_and_environment(self):
        root = Path("runtime with spaces")
        suffix = ".exe" if support.IS_WINDOWS else ""
        self.assertEqual(support.binary_path(root, "yue-synth"), root / "bin" / ("yue-synth" + suffix))
        with patch.dict(os.environ, {"UNCHANGED": "value"}, clear=True):
            env = support.runtime_env(root, 3)
            self.assertEqual(env["UNCHANGED"], "value")
            for key in ("YUE_THREADS", "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
                self.assertEqual(env[key], "3")
            self.assertEqual(env["MKL_DYNAMIC"], "FALSE")
            self.assertEqual(env["OMP_DYNAMIC"], "FALSE")
            self.assertNotIn("YUE_THREADS", os.environ)

    def test_windows_paths_and_environment(self):
        root = Path("runtime with spaces")
        with patch.object(support, "IS_WINDOWS", True), patch.dict(os.environ, {"PATH": "existing"}, clear=True):
            self.assertEqual(support.binary_path(root, "yue-plan"), root / "bin" / "yue-plan.exe")
            self.assertEqual(support.runtime_env(root)["PATH"], str(root / "bin") + ";existing")
            self.assertNotIn("LD_LIBRARY_PATH", support.runtime_env(root))

    def test_windows_process_flags(self):
        with patch.object(support, "IS_WINDOWS", True), \
                patch.object(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000, create=True), \
                patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, create=True):
            self.assertEqual(support.process_options(), {"creationflags": 0x4200})

    def test_lock_excludes_another_process_and_releases(self):
        code = (
            "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
            "from runtime_support import lock\n"
            "try:\n"
            "    with lock(Path(sys.argv[2])): print('acquired')\n"
            "except ValueError:\n"
            "    print('busy'); sys.exit(3)\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            command = [sys.executable, "-c", code, str(SCRIPTS), str(root)]
            with support.lock(root):
                busy = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual((busy.returncode, busy.stdout.strip()), (3, "busy"), busy.stderr)
            free = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual((free.returncode, free.stdout.strip()), (0, "acquired"), free.stderr)
            with self.assertRaisesRegex(RuntimeError, "body failed"):
                with support.lock(root):
                    raise RuntimeError("body failed")
            released = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(released.returncode, 0, released.stderr)

    def test_stop_process_reaps_running_and_finished_children(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **support.process_options())
        try:
            support.stop_process(process, timeout=0.5)
            self.assertIsNotNone(process.poll())
            support.stop_process(process, timeout=0.5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    @unittest.skipIf(support.IS_WINDOWS, "POSIX signal escalation")
    def test_stop_process_escalates_when_term_is_ignored(self):
        code = (
            "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            "print('ready',flush=True); time.sleep(60)"
        )
        process = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                                   text=True, **support.process_options())
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            support.stop_process(process, timeout=0.1)
            self.assertLess(process.returncode, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()

    def test_artifacts_require_all_binaries_and_ignore_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            suffix = ".exe" if support.IS_WINDOWS else ""
            for name in support.BINARIES[:-1]:
                (build / (name + suffix)).write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "yue-server"):
                support.collect_build_artifacts(build)
            (build / (support.BINARIES[-1] + suffix)).write_bytes(b"fixture")
            (build / "private.log").write_text("fixture", encoding="utf-8")
            (build / "CMakeCache.txt").write_text("fixture", encoding="utf-8")
            (build / "not.so.txt").write_text("fixture", encoding="utf-8")
            found = support.collect_build_artifacts(build)
            self.assertEqual({path.name for path in found}, {name + suffix for name in support.BINARIES})

    def test_windows_release_executables_and_dlls_take_precedence(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(support, "IS_WINDOWS", True):
            build = Path(temporary)
            release = build / "Release"
            release.mkdir()
            for directory in (build, release):
                for name in support.BINARIES:
                    (directory / (name + ".exe")).write_bytes(b"fixture")
                (directory / "ggml.dll").write_bytes(b"fixture")
            (build / "fallback.dll").write_bytes(b"fixture")
            found = support.collect_build_artifacts(build)
            by_name = {path.name: path for path in found}
            self.assertEqual(len(found), len(by_name))
            for name in (*[name + ".exe" for name in support.BINARIES], "ggml.dll"):
                self.assertEqual(by_name[name].parent, release)
            self.assertEqual(by_name["fallback.dll"].parent, build)

    @unittest.skipIf(support.IS_WINDOWS, "Shared-library symlink fixture needs POSIX symlink support")
    def test_collect_preserves_relative_shared_library_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            for name in support.BINARIES:
                (build / name).write_bytes(b"fixture")
            (build / "libggml.so.1").write_bytes(b"fixture")
            (build / "libggml.so").symlink_to("libggml.so.1")
            (build / "libexample.dylib").write_bytes(b"fixture")
            found = {path.name: path for path in support.collect_build_artifacts(build)}
            self.assertTrue(found["libggml.so"].is_symlink())
            self.assertEqual(found["libggml.so"].readlink(), Path("libggml.so.1"))
            self.assertIn("libggml.so.1", found)
            self.assertIn("libexample.dylib", found)

    @unittest.skipIf(support.IS_WINDOWS, "Shared-library symlink fixture needs POSIX symlink support")
    def test_collect_rejects_nonrelocatable_library_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            for name in support.BINARIES:
                (build / name).write_bytes(b"fixture")
            target = build / "libggml.so.1"
            target.write_bytes(b"fixture")
            (build / "libggml.so").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "same-directory relative symlinks"):
                support.collect_build_artifacts(build)


if __name__ == "__main__":
    unittest.main()
