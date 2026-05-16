#!/usr/bin/env python3
"""Build a prototype timeline with text placeholders for generated-image panels."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Any


OUTPUT_SIZES = {
    "landscape": (1920, 1080),
    "vertical": (1080, 1920),
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_id(value: Any, fallback: str) -> str:
    raw = str(value or fallback).strip().lower()
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
    return cleaned or fallback


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def segment_by_id(script: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(script, dict) or not isinstance(script.get("segments"), list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for segment in script["segments"]:
        if isinstance(segment, dict) and isinstance(segment.get("segment_id"), str):
            result[segment["segment_id"]] = segment
    return result


def placeholder_text(entry: dict[str, Any], panel: dict[str, Any], segment: dict[str, Any] | None) -> str:
    candidates = [
        panel.get("prompt"),
        panel.get("visual_brief"),
        panel.get("description"),
        segment.get("visual_direction") if segment else None,
        segment.get("editor_notes") if segment else None,
        entry.get("visual_idea"),
        entry.get("caption_text"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return "Generated image placeholder"


def render_placeholder_png(path: Path, text: str, size: tuple[int, int]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render prototype text placeholders.") from exc

    width, height = size
    image = Image.new("RGB", size, (18, 22, 30))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("arial.ttf", max(28, width // 32))
        body_font = ImageFont.truetype("arial.ttf", max(22, width // 44))
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    margin = max(48, width // 18)
    title = "GENERATED IMAGE PLACEHOLDER"
    draw.text((margin, margin), title, fill=(220, 232, 255), font=title_font)
    wrapped = textwrap.wrap(text, width=max(24, width // 24))
    y = margin * 2 + 44
    for line in wrapped[:18]:
        draw.text((margin, y), line, fill=(245, 247, 250), font=body_font)
        y += max(28, height // 38)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def replace_generated_image_panels(
    timeline: list[dict[str, Any]],
    script: Any,
    project_dir: Path,
    *,
    output_format: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    segments = segment_by_id(script)
    output_size = OUTPUT_SIZES[output_format]
    placeholders: list[dict[str, Any]] = []
    prototype: list[dict[str, Any]] = []
    for entry_index, entry in enumerate(timeline):
        copied_entry = dict(entry)
        panels = copied_entry.get("panels")
        if isinstance(panels, list):
            copied_panels = []
            for panel_index, panel in enumerate(panels):
                copied_panel = dict(panel) if isinstance(panel, dict) else panel
                if isinstance(copied_panel, dict) and copied_panel.get("kind") == "broll" and copied_panel.get("source_type") == "generated-image":
                    segment_id = str(copied_entry.get("segment_id") or f"entry-{entry_index + 1}")
                    segment = segments.get(segment_id)
                    text = placeholder_text(copied_entry, copied_panel, segment)
                    safe_segment = sanitize_id(segment_id, f"entry-{entry_index + 1}")
                    rel_path = Path("prototype") / "placeholders" / f"{safe_segment}_panel_{panel_index + 1}.png"
                    abs_path = project_dir / rel_path
                    render_placeholder_png(abs_path, text, output_size)
                    copied_panel["path"] = str(rel_path).replace("\\", "/")
                    placeholders.append(
                        {
                            "segment_id": segment_id,
                            "panel_index": panel_index,
                            "placeholder_text": text,
                            "sha256": sha256_text(text),
                            "placeholder_path": str(rel_path).replace("\\", "/"),
                            "placeholder_file_sha256": sha256_file(abs_path),
                        }
                    )
                copied_panels.append(copied_panel)
            copied_entry["panels"] = copied_panels
        prototype.append(copied_entry)
    return prototype, placeholders


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create timeline.prototype.json with generated-image text placeholders.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    parser.add_argument("--timeline", default="timeline.json", help="Input timeline path, relative to project-dir or absolute.")
    parser.add_argument("--script", default="script.json", help="Script path, relative to project-dir or absolute.")
    parser.add_argument("--output", default="timeline.prototype.json", help="Output prototype timeline path.")
    parser.add_argument("--placeholders-manifest", default="manifests/prototype-placeholders.json", help="Output placeholder manifest path.")
    parser.add_argument("--format", choices=sorted(OUTPUT_SIZES), default="vertical", help="Placeholder canvas format.")
    return parser.parse_args()


def resolve_path(project_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_dir / path


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    timeline_path = resolve_path(project_dir, args.timeline)
    script_path = resolve_path(project_dir, args.script)
    output_path = resolve_path(project_dir, args.output)
    placeholders_path = resolve_path(project_dir, args.placeholders_manifest)
    timeline = load_json(timeline_path)
    if not isinstance(timeline, list):
        raise ValueError("timeline must be an array")
    script = load_json(script_path)
    prototype, placeholders = replace_generated_image_panels(
        timeline,
        script,
        project_dir,
        output_format=args.format,
    )
    write_json(output_path, prototype)
    write_json(placeholders_path, {"schema_version": 1, "placeholders": placeholders})
    print(json.dumps({"timeline": str(output_path), "placeholders": len(placeholders)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
