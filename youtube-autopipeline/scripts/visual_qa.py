#!/usr/bin/env python3
"""Extract representative frames and write a visual QA manifest for rendered reels."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    local = Path.home() / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / f"{name}.exe"
    if local.exists():
        return str(local)
    return None


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def ffprobe_json(path: Path) -> dict[str, Any]:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found")
    completed = run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(completed.stdout)


def video_metadata(path: Path) -> dict[str, Any]:
    data = ffprobe_json(path)
    metadata: dict[str, Any] = {}
    fmt = data.get("format") or {}
    if "duration" in fmt:
        metadata["duration_seconds"] = float(fmt["duration"])
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            metadata["width"] = int(stream.get("width") or 0)
            metadata["height"] = int(stream.get("height") or 0)
            break
    return metadata


def load_timeline(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else []


def collect_timestamps(duration: float, timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[tuple[float, str]] = []
    if duration > 2:
        candidates.append((2.0, "first_2s"))
    for seconds in range(8, int(math.floor(duration)), 8):
        candidates.append((float(seconds), "interval_8s"))
    if duration > 4:
        candidates.append((max(0.0, duration - 2.0), "final_2s"))

    for index, entry in enumerate(timeline):
        start = float(entry.get("start_time", 0.0))
        end = float(entry.get("end_time", start))
        middle = start + max(0.0, end - start) / 2
        candidates.append((min(max(start + 0.2, 0.0), max(duration - 0.1, 0.0)), f"segment_{index:02d}_start"))
        candidates.append((min(max(middle, 0.0), max(duration - 0.1, 0.0)), f"segment_{index:02d}_middle"))
        if entry.get("type") in {"PIP", "TEXT"} or entry.get("caption_text"):
            candidates.append((min(max(middle, 0.0), max(duration - 0.1, 0.0)), f"{entry.get('type')}_review"))

    seen: set[float] = set()
    timestamps = []
    for seconds, reason in sorted(candidates, key=lambda item: item[0]):
        rounded = round(seconds, 2)
        if rounded in seen:
            continue
        seen.add(rounded)
        timestamps.append({"seconds": rounded, "reason": reason})
    return timestamps


def extract_frame(video: Path, output: Path, seconds: float) -> None:
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg,
            "-y",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(output),
        ]
    )


def analyze_frame(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return {"auto_checks": {"available": False, "warnings": ["Pillow not installed"]}}

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        stat = ImageStat.Stat(rgb)
        mean = sum(stat.mean) / 3
        extrema = rgb.getextrema()
        contrast_span = sum(high - low for low, high in extrema) / 3
    warnings: list[str] = []
    if mean < 8:
        warnings.append("very dark or blank-looking frame")
    if contrast_span < 15:
        warnings.append("low contrast or blank-looking frame")
    return {
        "auto_checks": {
            "available": True,
            "mean_luma_estimate": round(mean, 2),
            "contrast_span_estimate": round(contrast_span, 2),
            "warnings": warnings,
        }
    }


def make_contact_sheet(frame_paths: list[Path], output: Path) -> str | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    if not frame_paths:
        return None

    thumbs = []
    for path in frame_paths:
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((240, 426))
            canvas = Image.new("RGB", (240, 456), "white")
            x = int((240 - thumb.width) / 2)
            canvas.paste(thumb, (x, 0))
            draw = ImageDraw.Draw(canvas)
            draw.text((8, 432), path.stem, fill=(0, 0, 0))
            thumbs.append(canvas)

    columns = 4
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 240, rows * 456), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 240, (index // columns) * 456))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return str(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create final-render visual QA frames and manifest.")
    parser.add_argument("--project-dir", required=True, help="Project directory.")
    parser.add_argument("--video", help="Rendered MP4. Defaults to <project-dir>/final_output.mp4")
    parser.add_argument("--timeline", help="Timeline JSON. Defaults to <project-dir>/timeline.json when present")
    parser.add_argument("--output", help="QA manifest path. Defaults to <project-dir>/manifests/visual-qa.json")
    parser.add_argument("--status", choices=("pass", "fail", "needs_review"), default="needs_review")
    parser.add_argument("--notes", default="", help="Human visual QA notes to record.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    video = Path(args.video).resolve() if args.video else project_dir / "final_output.mp4"
    timeline_path = Path(args.timeline).resolve() if args.timeline else project_dir / "timeline.json"
    output = Path(args.output).resolve() if args.output else project_dir / "manifests" / "visual-qa.json"
    qa_stem = video.stem
    frames_dir = project_dir / "qa" / "final-frames" / qa_stem
    contact_sheet = project_dir / "qa" / f"contact-sheet-{qa_stem}.jpg"

    if not video.exists():
        raise FileNotFoundError(f"video not found: {video}")

    metadata = video_metadata(video)
    duration = float(metadata.get("duration_seconds") or 0.0)
    timeline = load_timeline(timeline_path)
    timestamps = collect_timestamps(duration, timeline)
    frame_entries: list[dict[str, Any]] = []
    frame_paths: list[Path] = []

    for index, item in enumerate(timestamps):
        seconds = float(item["seconds"])
        frame_path = frames_dir / f"frame_{index:02d}_{seconds:06.2f}s.png"
        extract_frame(video, frame_path, seconds)
        frame_paths.append(frame_path)
        frame_entries.append(
            {
                "seconds": seconds,
                "reason": item["reason"],
                "path": str(frame_path),
                **analyze_frame(frame_path),
            }
        )

    sheet_path = make_contact_sheet(frame_paths, contact_sheet)
    manifest = {
        "video": str(video),
        "timeline": str(timeline_path) if timeline_path.exists() else None,
        "metadata": metadata,
        "status": args.status,
        "notes": args.notes,
        "frames": frame_entries,
        "contact_sheet": sheet_path,
        "manual_acceptance_required": True,
        "acceptance_criteria": [
            "9:16 render at 1080x1920 for reels",
            "clear hook and visual change in the opening seconds",
            "readable captions or text without overlap",
            "circular PiP when presenter overlay is used",
            "no blank, loading, error, or unfinished-looking frames",
            "no accidental real credentials or unintended brand endorsement",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote visual QA manifest: {output}")
    print(f"Extracted frames: {len(frame_entries)}")
    if sheet_path:
        print(f"Contact sheet: {sheet_path}")
    return 0 if args.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
