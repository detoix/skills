#!/usr/bin/env python3
"""Create the human approval artifact for an approved script."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from production_gate import APPROVAL_RELATIVE_PATH, SCRIPT_RELATIVE_PATH, GateFinding, create_approval, validate_script_contract, validate_script_visual_source_mix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate manifests/creative-approval.json for the current script.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    parser.add_argument("--resume-signal", required=True, help="Must be exactly 'approved' after human review.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.resume_signal != "approved":
        raise ValueError("--resume-signal must be exactly 'approved'")
    project_dir = Path(args.project_dir).resolve()
    script = json.loads((project_dir / SCRIPT_RELATIVE_PATH).read_text(encoding="utf-8-sig"))
    if not isinstance(script, dict):
        raise ValueError("script.json must be an object before approval")
    findings: list[GateFinding] = []
    validate_script_contract(script, findings)
    validate_script_visual_source_mix(script, findings)
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        for error in errors:
            print(f"ERROR: {error.code}: {error.message}", file=sys.stderr)
        return 1
    approval = create_approval(project_dir)
    output_path = project_dir / APPROVAL_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(approval, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"approval": str(output_path), "status": "approved"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
