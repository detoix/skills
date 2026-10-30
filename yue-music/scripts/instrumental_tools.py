#!/usr/bin/env python3
"""Fetch pinned official YuE2 score tools, then convert, prepare or validate ABC.

This wrapper exposes CPU-only score preparation, never upstream inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SKILL = Path(__file__).resolve().parents[1]
MANIFEST = SKILL / "assets" / "instrumental-tools.json"
EXPECTED_FILES = {"abc_tools.py", "common.py", "instrumentalize.py",
                  "compile_score.py", "instrumental.py", "LICENSE"}


def verified(path: Path, spec: dict) -> bool:
    return (path.is_file() and path.stat().st_size == spec["bytes"]
            and hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"])


def tool_directory(runtime: Path) -> Path:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    revision, files = manifest["revision"], manifest["files"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or set(files) != EXPECTED_FILES:
        raise ValueError("Invalid instrumental-tool manifest")
    root = runtime.resolve() / "instrumental-tools" / revision
    root.mkdir(parents=True, exist_ok=True)
    for name, spec in files.items():
        if not (type(spec["bytes"]) is int and 0 < spec["bytes"] <= 256 * 1024
                and re.fullmatch(r"[0-9a-f]{64}", spec["sha256"])
                and spec["url"].startswith(
                    "https://raw.githubusercontent.com/multimodal-art-projection/YuE/" + revision + "/")):
            raise ValueError("Invalid pinned source: " + name)
        target = root / name
        if verified(target, spec):
            continue
        fd, temporary = tempfile.mkstemp(prefix="." + name + ".", dir=root)
        os.close(fd)
        temporary = Path(temporary)
        try:
            # Bounded retries, time, redirects and size; hashes remain authoritative.
            subprocess.run([
                "curl", "--fail", "--location", "--silent", "--show-error",
                "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "3",
                "--retry", "3", "--retry-delay", "1", "--connect-timeout", "15",
                "--max-time", "45", "--max-filesize", "262144",
                "--output", str(temporary), spec["url"],
            ], check=True, timeout=200)
            if not verified(temporary, spec):
                raise ValueError("Downloaded file failed size/hash check: " + name)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    # Verify the complete package before executing any of its code.
    if not all(verified(root / name, spec) for name, spec in files.items()):
        raise ValueError("Instrumental tools failed final verification")
    return root


def fresh_output(path: Path) -> Path:
    path = path.resolve()
    if path.exists():
        raise ValueError("Output directory already exists; choose a new path: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=SKILL / ".runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert", help="Move Vocal notes into Ins and verify the transfer")
    convert.add_argument("source", type=Path)
    convert.add_argument("--out-dir", type=Path, required=True)
    prepare = commands.add_parser("prepare", help="Validate an instrumental ABC and prepare its request")
    prepare.add_argument("--abc", type=Path, required=True)
    prepare.add_argument("--style-file", type=Path, required=True)
    prepare.add_argument("--out-dir", type=Path, required=True)
    prepare.add_argument("--seed", type=int, required=True)
    prepare.add_argument("--id", default="instrumental")
    validate = commands.add_parser("validate", help="Print structural validation; this does not inspect audio")
    validate.add_argument("--abc", type=Path, required=True)
    args = parser.parse_args()
    try:
        source = args.source if args.command == "convert" else args.abc
        source = source.resolve(strict=True)
        output = fresh_output(args.out_dir) if args.command != "validate" else None
        style = None
        if args.command == "prepare":
            style = args.style_file.resolve(strict=True)
            if not 0 <= args.seed < 2**63:
                raise ValueError("seed must be in 0..2**63-1")
        root = tool_directory(args.runtime)
        if args.command == "convert":
            command = [sys.executable, str(root / "instrumentalize.py"), str(source),
                       "--output", str(output)]
        elif args.command == "prepare":
            command = [sys.executable, str(root / "instrumental.py"), "prepare",
                       "--abc", str(source), "--style-file", str(style),
                       "--output", str(output), "--seed", str(args.seed), "--id", args.id]
        else:
            code = ("import json,sys; from pathlib import Path; "
                    "sys.path.insert(0,sys.argv[1]); "
                    "from instrumental import validate_score; from abc_tools import report; "
                    "print(json.dumps(report(validate_score(Path(sys.argv[2]).read_text(encoding='utf-8'))),"
                    "indent=2,default=str))")
            command = [sys.executable, "-c", code, str(root), str(source)]
        return subprocess.run(command, check=False).returncode
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("Instrumental preparation failed: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
