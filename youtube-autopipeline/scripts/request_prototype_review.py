#!/usr/bin/env python3
"""Create a blocking human-review request for the portable prototype bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from package_prototype_bundle import DEFAULT_OUTPUT_RELATIVE_PATH, package_bundle
from production_gate import PROTOTYPE_OUTPUT_RELATIVE_PATH, PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH, create_prototype_review_request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate manifests/prototype-review-request.json.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    parser.add_argument("--bundle-output", help="Optional output ZIP path. Defaults to <project-dir>/outputs/prototype-bundle-no-mp4.zip.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    request = create_prototype_review_request(project_dir)
    output_path = project_dir / PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    bundle_output = Path(args.bundle_output).resolve() if args.bundle_output else project_dir / DEFAULT_OUTPUT_RELATIVE_PATH
    bundle = package_bundle(project_dir, bundle_output)
    print(
        json.dumps(
            {
                "review_request": str(output_path),
                "review_request_relative": PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH.as_posix(),
                "prototype_mp4": str(project_dir / PROTOTYPE_OUTPUT_RELATIVE_PATH),
                "prototype_mp4_relative": PROTOTYPE_OUTPUT_RELATIVE_PATH.as_posix(),
                "portable_bundle_zip_without_mp4": str(project_dir / bundle["bundle_zip"]),
                "portable_bundle_zip_without_mp4_relative": bundle["bundle_zip"],
                "resume_signal": "approved",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
