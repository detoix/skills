#!/usr/bin/env python3
"""Create a blocking human-review request for script.json and visual-plan.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from production_gate import REVIEW_REQUEST_RELATIVE_PATH, create_review_request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate manifests/creative-review-request.json.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    request = create_review_request(project_dir)
    output_path = project_dir / REVIEW_REQUEST_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"review_request": str(output_path), "resume_signal": "approved"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
