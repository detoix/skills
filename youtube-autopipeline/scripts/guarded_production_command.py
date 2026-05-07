#!/usr/bin/env python3
"""Run an external production command only after the creative gate passes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from production_gate import run_creative_gate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate and run an external production command.")
    parser.add_argument("--project-dir", required=True, help="Project directory.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Missing command after --")
    findings = run_creative_gate(Path(args.project_dir))
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        for finding in findings:
            print(f"{finding.severity}: {finding.code}: {finding.message}", file=sys.stderr)
        return 1
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
