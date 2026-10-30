"""Check installation promotion and rollback without network or native builds."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import yue


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "runtime"
        self.root.mkdir()

    def args(self, *, rebuild=False, build_only=False):
        return SimpleNamespace(mkl_root=None, rebuild=rebuild, build_only=build_only,
                               backend="cpu", blas="off", blas_vendor="OpenBLAS", jobs=1)

    def existing_installation(self, *, matching=True):
        (self.root / "bin").mkdir()
        for name in yue.BINARIES:
            yue.binary_path(self.root, name).write_bytes(b"original executable fixture")
        configuration = {
            "installer_version": yue.INSTALLER_VERSION,
            "engine_revision": yue.ENGINE_REV,
            "platform": sys.platform,
            "architecture": yue.platform.machine(),
            "backend": "cpu", "blas": False, "blas_vendor": None, "mkl_root": None,
        } if matching else {"fixture": "original installation"}
        yue.write_json(self.root / "install.json", configuration)
        return (self.root / "install.json").read_bytes()

    def assert_original_installation(self, metadata):
        for name in yue.BINARIES:
            self.assertEqual(yue.binary_path(self.root, name).read_bytes(), b"original executable fixture")
        self.assertEqual((self.root / "install.json").read_bytes(), metadata)

    @contextmanager
    def mocked_build(self, check_error=None):
        (self.root / "engine").mkdir()
        build = self.root / "build" / "cpu-native"
        build.mkdir(parents=True)
        for name in yue.BINARIES:
            filename = yue.binary_path(self.root, name).name
            (build / filename).write_bytes(b"replacement executable fixture")
        with ExitStack() as stack:
            stack.enter_context(patch.object(yue.shutil, "which", return_value="available-tool"))
            stack.enter_context(patch.object(yue, "run"))
            stack.enter_context(patch.object(yue.subprocess, "check_output", return_value=yue.ENGINE_REV))
            stack.enter_context(patch.object(yue.subprocess, "run", return_value=SimpleNamespace(returncode=0)))
            checked = stack.enter_context(patch.object(yue, "check", side_effect=check_error))
            yield checked

    def test_full_setup_checks_dependencies_before_promoting_build_only_installation(self):
        metadata = self.existing_installation()
        available = lambda name: None if name == "ffmpeg" else "available-tool"
        with patch.object(yue.shutil, "which", side_effect=available), \
                patch.object(yue, "ensure_models") as models, patch.object(yue, "check") as checked:
            with self.assertRaisesRegex(ValueError, "ffmpeg"):
                yue.setup(self.args(), self.root)
        models.assert_not_called()
        checked.assert_not_called()
        self.assert_original_installation(metadata)

    def test_full_setup_can_reuse_binaries_without_a_build_toolchain(self):
        metadata = self.existing_installation()
        available = lambda name: "available-tool" if name in ("curl", "ffmpeg", "ffprobe") else None
        with patch.object(yue.shutil, "which", side_effect=available), \
                patch.object(yue, "ensure_models") as models, patch.object(yue, "check") as checked, \
                patch.object(yue, "run") as native_commands:
            yue.setup(self.args(), self.root)
        models.assert_called_once_with(self.root, model=None)
        checked.assert_called_once()
        native_commands.assert_not_called()
        self.assert_original_installation(metadata)

    def test_activation_rename_failure_restores_original_binaries(self):
        metadata = self.existing_installation(matching=False)
        original_rename = Path.rename

        def rename(source, destination):
            if source == self.root / ".bin-pending":
                raise PermissionError("injected activation failure")
            return original_rename(source, destination)

        with self.mocked_build() as checked, patch.object(Path, "rename", new=rename):
            with self.assertRaisesRegex(PermissionError, "injected activation failure"):
                yue.setup(self.args(rebuild=True, build_only=True), self.root)
        checked.assert_not_called()
        self.assert_original_installation(metadata)

    def test_binary_check_failure_restores_original_binaries(self):
        metadata = self.existing_installation(matching=False)
        with self.mocked_build(ValueError("injected dependency failure")) as checked:
            with self.assertRaisesRegex(ValueError, "injected dependency failure"):
                yue.setup(self.args(rebuild=True, build_only=True), self.root)
        checked.assert_called_once()
        self.assert_original_installation(metadata)


if __name__ == "__main__":
    unittest.main()
