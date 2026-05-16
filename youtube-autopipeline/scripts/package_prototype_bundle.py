#!/usr/bin/env python3
"""Package a portable prototype bundle without the review MP4."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from production_gate import (
    PROTOTYPE_MANIFEST_RELATIVE_PATH,
    PROTOTYPE_OUTPUT_RELATIVE_PATH,
    PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH,
    FINAL_AUDIO_MANIFEST_RELATIVE_PATH,
    FINAL_AUDIO_RELATIVE_PATH,
    TIMELINE_PROTOTYPE_RELATIVE_PATH,
    TTS_PROTOTYPE_MANIFEST_RELATIVE_PATH,
    SCRIPT_RELATIVE_PATH,
    is_portable_relative_path,
    run_creative_gate,
    validate_prototype_manifest,
)


DEFAULT_OUTPUT_RELATIVE_PATH = Path("outputs") / "prototype-bundle-no-mp4.zip"
REQUIRED_RELATIVE_PATHS = {
    SCRIPT_RELATIVE_PATH,
    TIMELINE_PROTOTYPE_RELATIVE_PATH,
    TTS_PROTOTYPE_MANIFEST_RELATIVE_PATH,
    FINAL_AUDIO_MANIFEST_RELATIVE_PATH,
    FINAL_AUDIO_RELATIVE_PATH,
    PROTOTYPE_MANIFEST_RELATIVE_PATH,
    PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH,
}
EXCLUDED_RELATIVE_PATHS = {PROTOTYPE_OUTPUT_RELATIVE_PATH}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def add_if_portable(paths: set[Path], value: Any) -> None:
    if is_portable_relative_path(value):
        paths.add(Path(str(value)))


def collect_manifest_paths(value: Any, paths: set[Path]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"path", "audio_path", "placeholder_path", "nativeImage", "originalUploadedImage", "prompt_audio_path", "reference_audio_path"}:
                add_if_portable(paths, child)
            collect_manifest_paths(child, paths)
    elif isinstance(value, list):
        for child in value:
            collect_manifest_paths(child, paths)


def collect_timeline_paths(value: Any, paths: set[Path]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"path", "clip_path", "overlay_path", "audio_path", "image_path"}:
                add_if_portable(paths, child)
            collect_timeline_paths(child, paths)
    elif isinstance(value, list):
        for child in value:
            collect_timeline_paths(child, paths)


def existing_project_files(project_dir: Path, relative_paths: set[Path]) -> list[Path]:
    files: list[Path] = []
    missing: list[str] = []
    for relative_path in sorted(relative_paths, key=lambda item: item.as_posix()):
        normalized = Path(relative_path.as_posix())
        if normalized in EXCLUDED_RELATIVE_PATHS:
            continue
        full_path = project_dir / normalized
        if full_path.is_file():
            files.append(normalized)
        elif normalized in REQUIRED_RELATIVE_PATHS:
            missing.append(normalized.as_posix())
    if missing:
        raise FileNotFoundError(f"Missing required bundle files: {', '.join(missing)}")
    return files


def project_relative_posix(project_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Output path must be inside project-dir for a portable handoff: {path}") from exc


def package_bundle(project_dir: Path, output_path: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    findings = run_creative_gate(project_dir, write_state=False)
    script = load_json(project_dir / SCRIPT_RELATIVE_PATH)
    prototype_manifest = load_json(project_dir / PROTOTYPE_MANIFEST_RELATIVE_PATH)
    validate_prototype_manifest(prototype_manifest, project_dir, findings, script)
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        messages = "; ".join(f"{finding.code}: {finding.message}" for finding in errors)
        raise ValueError(f"Cannot package prototype bundle: {messages}")

    relative_paths = set(REQUIRED_RELATIVE_PATHS)
    collect_manifest_paths(prototype_manifest, relative_paths)
    timeline = load_json(project_dir / TIMELINE_PROTOTYPE_RELATIVE_PATH)
    collect_timeline_paths(timeline, relative_paths)

    output_path = output_path.resolve()
    output_relative_posix = project_relative_posix(project_dir, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_relative = Path(output_relative_posix)

    files = existing_project_files(project_dir, relative_paths)
    if output_relative in files:
        files.remove(output_relative)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in files:
            archive.write(project_dir / relative_path, relative_path.as_posix())

    return {
        "bundle_zip": output_relative_posix,
        "bundle_zip_local_path": str(output_path),
        "excluded_review_mp4": PROTOTYPE_OUTPUT_RELATIVE_PATH.as_posix(),
        "files": [path.as_posix() for path in files],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a portable prototype ZIP without outputs/prototype.mp4.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    parser.add_argument("--output", help="Output ZIP path. Defaults to <project-dir>/outputs/prototype-bundle-no-mp4.zip.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    output_path = Path(args.output).resolve() if args.output else project_dir / DEFAULT_OUTPUT_RELATIVE_PATH
    result = package_bundle(project_dir, output_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
