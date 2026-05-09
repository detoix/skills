#!/usr/bin/env python3
"""Create the human approval artifact for an approved prototype."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from production_gate import PROTOTYPE_APPROVAL_RELATIVE_PATH, create_prototype_approval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate manifests/prototype-approval.json for the current prototype bundle.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    parser.add_argument("--resume-signal", required=True, help="Must be exactly 'approved' after human review.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.resume_signal != "approved":
        raise ValueError("--resume-signal must be exactly 'approved'")
    project_dir = Path(args.project_dir).resolve()
    approval = create_prototype_approval(project_dir)
    output_path = project_dir / PROTOTYPE_APPROVAL_RELATIVE_PATH
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
