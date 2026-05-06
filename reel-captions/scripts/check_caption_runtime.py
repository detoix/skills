#!/usr/bin/env python
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path


def media_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidate = Path(userprofile) / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / f"{name}.exe"
        if candidate.exists():
            return str(candidate)
    return None


def main() -> int:
    report = {
        "python": sys.executable,
        "whisperx": importlib.util.find_spec("whisperx") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "ffmpeg": media_tool("ffmpeg"),
        "ffprobe": media_tool("ffprobe"),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["whisperx"] and report["ffmpeg"] and report["ffprobe"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
