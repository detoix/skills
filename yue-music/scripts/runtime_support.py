"""Standard-library platform support for the portable YuE runtime launcher."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import re
import signal
import subprocess
import sys


IS_WINDOWS = sys.platform == "win32"
BINARIES = ("yue-synth", "yue-plan", "yue-server")


def binary_path(root: Path, name: str) -> Path:
    return Path(root) / "bin" / (name + ".exe" if IS_WINDOWS else name)


def runtime_env(root: Path, threads: int = 2) -> dict:
    env = os.environ.copy()
    for key in ("YUE_THREADS", "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        env[key] = str(threads)
    env["MKL_DYNAMIC"] = env["OMP_DYNAMIC"] = "FALSE"
    key = "PATH" if IS_WINDOWS else "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    separator = ";" if IS_WINDOWS else os.pathsep
    env[key] = str(Path(root) / "bin") + (separator + env[key] if env.get(key) else "")
    return env


@contextmanager
def lock(root: Path):
    """Hold a nonblocking, process-owned lock until the context exits."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "operation.lock").open("a+b") as stream:
        if IS_WINDOWS:
            import msvcrt

            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise ValueError("Another setup or generation is using this runtime.") from None
                raise
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Another setup or generation is using this runtime.") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def process_options() -> dict:
    if IS_WINDOWS:
        return {"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def stop_process(process: subprocess.Popen, timeout: float = 10) -> None:
    """Stop and reap a launched child, tolerating a concurrent normal exit."""
    if process.poll() is not None:
        process.wait()
        return

    def send(force: bool) -> None:
        try:
            if IS_WINDOWS:
                process.kill() if force else process.terminate()
            else:
                os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except OSError:
            if process.poll() is None:
                raise

    send(False)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        send(True)
        process.wait()


def _is_library(name: str) -> bool:
    name = name.lower()
    return name.endswith((".dll", ".dylib")) or re.search(r"\.so(?:\.[0-9]+)*$", name) is not None


def collect_build_artifacts(build: Path) -> list[Path]:
    """Collect a complete executable set and relocatable shared libraries."""
    build = Path(build)
    directories = (build / "Release", build) if IS_WINDOWS else (build, build / "Release")
    required = {name + ".exe" if IS_WINDOWS else name for name in BINARIES}
    selected = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            name = path.name.casefold() if IS_WINDOWS else path.name
            if name not in required and not _is_library(name):
                continue
            if name in selected or not (path.is_file() or path.is_symlink()):
                continue
            if path.is_symlink():
                target = path.readlink()
                if target.is_absolute() or target.parent != Path(".") or not path.is_file():
                    raise ValueError(f"Shared artifacts must use valid same-directory relative symlinks: {path.name}")
            selected[name] = path
    missing = required - selected.keys()
    if missing:
        raise ValueError("Build is missing required executables: " + ", ".join(sorted(missing)))
    for path in selected.values():
        if path.is_symlink():
            target_name = path.readlink().name
            target_key = target_name.casefold() if IS_WINDOWS else target_name
            if target_key not in selected:
                raise ValueError(f"Build symlink target is not a collected artifact: {path.name}")
    return [selected[name] for name in sorted(selected)]
