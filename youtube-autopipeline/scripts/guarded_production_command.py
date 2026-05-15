#!/usr/bin/env python3
"""Run an external production command only after the required gate passes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from production_gate import run_creative_gate, run_prototype_approved_gate
from production_metrics import end_stage, infer_stage, start_stage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate and run an external production command.")
    parser.add_argument("--project-dir", required=True, help="Project directory.")
    parser.add_argument("--stage", help="Stage name for production timing logs. Inferred from command when omitted.")
    parser.add_argument(
        "--gate-profile",
        choices=("prototype", "production"),
        default="production",
        help="prototype requires only the Creative Gate; production requires the Prototype Approved Gate.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Missing command after --")
    project_dir = Path(args.project_dir).resolve()
    gate_name = "creative_gate" if args.gate_profile == "prototype" else "prototype_approved_gate"
    gate_command = ["production_gate.py", "--project-dir", str(project_dir)]
    if args.gate_profile == "production":
        gate_command.extend(["--gate", "prototype-approved"])
    gate_record = start_stage(project_dir, gate_name, command=gate_command)
    try:
        findings = run_creative_gate(project_dir) if args.gate_profile == "prototype" else run_prototype_approved_gate(project_dir)
    except Exception as exc:
        end_stage(project_dir, gate_record, status="error", error=str(exc))
        raise
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        for finding in findings:
            print(f"{finding.severity}: {finding.code}: {finding.message}", file=sys.stderr)
        end_stage(project_dir, gate_record, status="fail", return_code=1, metadata={"errors": len(errors)})
        return 1
    end_stage(project_dir, gate_record, status="pass", return_code=0)

    stage = args.stage or infer_stage(command)
    command_record = start_stage(project_dir, stage, command=command)
    try:
        completed = subprocess.run(command, check=False)
    except Exception as exc:
        end_stage(project_dir, command_record, status="error", error=str(exc))
        raise
    status = "pass" if completed.returncode == 0 else "fail"
    end_stage(project_dir, command_record, status=status, return_code=completed.returncode)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
