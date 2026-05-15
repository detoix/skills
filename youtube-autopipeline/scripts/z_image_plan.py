#!/usr/bin/env python3
"""Create a z-image generation plan from a script JSON payload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BROLL_SOURCE = "generated-image"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def safe_slug(value: str) -> str:
    cleaned = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        elif cleaned and cleaned[-1] != "-":
            cleaned.append("-")
    return "".join(cleaned).strip("-")[:48] or "visual"


def prompt_for_segment(segment: dict[str, Any], broll_query: dict[str, Any] | None, style: str) -> str:
    if broll_query:
        query_text = str(broll_query.get("query", "")).strip()
        must_include = str(broll_query.get("must_include", "")).strip()
        avoid = str(broll_query.get("avoid", "")).strip()
    else:
        query_text = ""
        must_include = ""
        avoid = ""
    # Do not feed on-screen copy or search-title copy into image prompts. Text-to-image models often
    # render garbled typography, so title/caption copy belongs in the composer.
    topic_text = " ".join(
        str(segment.get(key, "")).strip()
        for key in ("visual_direction", "narration")
        if str(segment.get(key, "")).strip()
    )
    if query_text:
        topic_text = query_text
        if must_include:
            topic_text = f"{topic_text}. Include: {must_include}"
        if avoid:
            topic_text = f"{topic_text}. Avoid: {avoid}"
    if not topic_text:
        topic_text = str(segment.get("segment_id", "visual beat"))
    return (
        f"Vertical 9:16 social video still, {style}. "
        f"Clear central subject, strong depth, polished editorial lighting, "
        f"clean negative space in upper and middle thirds for captions, no logos, "
        f"no readable private data, no UI screenshots unless explicitly requested, "
        f"no humans or faces unless explicitly requested, no letters, no words, no numbers, no text. "
        f"Scene: {topic_text}"
    )


def build_plan(script: dict[str, Any], output_dir: Path, style: str, limit: int | None) -> dict[str, Any]:
    segments = script.get("segments")
    if not isinstance(segments, list):
        raise ValueError("script JSON must contain a segments array")
    raw_queries = script.get("broll_queries") or []
    broll_queries = {
        item.get("segment_id"): item
        for item in raw_queries
        if isinstance(item, dict) and item.get("source_type") == "generated-image"
    }

    items = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_type = segment.get("type")
        segment_id = str(segment.get("segment_id") or f"S{len(items) + 1:02d}")
        broll_query = broll_queries.get(segment_id)
        panel_sources = {
            panel.get("source")
            for panel in segment.get("panels", [])
            if isinstance(panel, dict) and panel.get("kind") == "broll"
        }
        if segment_type != "B_ROLL" or (not broll_query and BROLL_SOURCE not in panel_sources):
            continue
        text = str(segment.get("visual_direction") or segment_id)
        output = output_dir / f"{segment_id}_{safe_slug(text)}.png"
        prompt = prompt_for_segment(segment, broll_query, style)
        items.append(
            {
                "segment_id": segment_id,
                "type": segment_type,
                "prompt": prompt,
                "output": str(output),
                "status": "planned",
                "review": {
                    "accepted": None,
                    "reviewer": None,
                    "notes": "",
                    "rejection_reason": "",
                },
                "timeline_candidate": {
                    "type": "B_ROLL",
                    "layout": segment.get("layout", "fullscreen"),
                    "panels": [{"kind": "broll", "source_type": BROLL_SOURCE, "path": str(output), "treatment": "still_motion"}],
                    "source": "z-image-turbo",
                    "review_required": True,
                },
                "command": [
                    "python",
                    "C:\\Users\\kdeptula\\skills\\z-image-turbo\\scripts\\generate.py",
                    "--prompt",
                    prompt,
                    "--output",
                    str(output),
                ],
            }
        )
        if limit and len(items) >= limit:
            break

    return {
        "source": "z-image-turbo",
        "usage": "generated vertical stills for B_ROLL panels, abstract concepts, and visual variety",
        "output_dir": str(output_dir),
        "items": items,
        "acceptance_criteria": [
            "vertical-safe subject placement",
            "clean caption negative space",
            "no fake logos, credentials, private data, or misleading real-brand UI",
            "not generic filler; must clarify the segment in under two seconds",
            "must be reviewed before use in timeline",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a z-image-turbo prompt and command manifest.")
    parser.add_argument("--script", required=True, help="script.json path from youtube-scriptwriter.")
    parser.add_argument("--project-dir", required=True, help="Project directory.")
    parser.add_argument("--output", help="Manifest path. Defaults to <project-dir>/manifests/z-image-plan.json")
    parser.add_argument("--image-dir", help="Image output directory. Defaults to <project-dir>/broll/generated")
    parser.add_argument("--style", default="high-quality documentary synthetic-motion aesthetic")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    script_path = Path(args.script).resolve()
    output = Path(args.output).resolve() if args.output else project_dir / "manifests" / "z-image-plan.json"
    image_dir = Path(args.image_dir).resolve() if args.image_dir else project_dir / "broll" / "generated"
    plan = build_plan(load_json(script_path), image_dir, args.style, args.limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Wrote z-image plan: {output}")
    print(f"Items: {len(plan['items'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
