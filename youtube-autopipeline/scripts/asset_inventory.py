#!/usr/bin/env python3
"""Classify local media assets for a YouTube autopipeline project manifest."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".srt", ".vtt"}


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    local = Path.home() / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / f"{name}.exe"
    if local.exists():
        return str(local)
    return None


def run_json(command: list[str]) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def probe_media(path: Path) -> dict[str, Any]:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return {}
    data = run_json(
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
    if not data:
        return {}

    result: dict[str, Any] = {}
    fmt = data.get("format") or {}
    if "duration" in fmt:
        try:
            result["duration_seconds"] = round(float(fmt["duration"]), 3)
        except (TypeError, ValueError):
            pass
    if "size" in fmt:
        try:
            result["size_bytes"] = int(fmt["size"])
        except (TypeError, ValueError):
            pass

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and "width" in stream and "height" in stream:
            width = int(stream["width"])
            height = int(stream["height"])
            result.update(
                {
                    "width": width,
                    "height": height,
                    "orientation": orientation(width, height),
                    "codec": stream.get("codec_name"),
                }
            )
            break
        if stream.get("codec_type") == "audio" and "sample_rate" in stream:
            result["sample_rate"] = int(stream["sample_rate"])
            result["channels"] = int(stream.get("channels") or 0)
    return result


def orientation(width: int, height: int) -> str:
    ratio = width / height
    if ratio > 1.2:
        return "landscape"
    if ratio < 0.83:
        return "portrait"
    return "square"


def classify_path(path: Path, root: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    name = path.name.lower()
    relative = str(path.relative_to(root))
    item: dict[str, Any] = {
        "path": str(path),
        "relative_path": relative,
        "name": path.name,
        "extension": suffix,
        "size_bytes": path.stat().st_size,
    }

    if suffix in VIDEO_EXTENSIONS:
        item["media_type"] = "video"
        item.update(probe_media(path))
        item["role"] = classify_video_role(name, item)
        item["usable"] = item["role"] != "previous_output"
        item["reason"] = video_reason(item)
    elif suffix in AUDIO_EXTENSIONS:
        item["media_type"] = "audio"
        item.update(probe_media(path))
        item["role"] = classify_audio_role(name)
        item["usable"] = item["role"] in {"voice_sample", "music", "narration_candidate"}
        item["reason"] = "usable audio candidate" if item["usable"] else "audio type not selected for default pipeline"
    elif suffix in IMAGE_EXTENSIONS:
        item["media_type"] = "image"
        item["role"] = classify_image_role(name)
        item["usable"] = True
        item["reason"] = "usable still or overlay candidate"
    elif suffix in TEXT_EXTENSIONS:
        item["media_type"] = "text"
        item["role"] = "transcript" if "transcript" in name or "script" in name else "text"
        item["usable"] = item["role"] == "transcript"
        item["reason"] = "voice clone transcript candidate" if item["usable"] else "supporting text"
    else:
        item["media_type"] = "other"
        item["role"] = "unknown"
        item["usable"] = False
        item["reason"] = "unsupported extension"
    return item


def classify_video_role(name: str, item: dict[str, Any]) -> str:
    if "final" in name or "output" in name or "reel" in name:
        return "previous_output"
    if "profile" in name:
        return "presenter_profile"
    if "front" in name or "presenter" in name:
        return "presenter_front"
    if item.get("orientation") == "portrait":
        return "presenter_or_vertical_broll"
    return "broll_or_presenter"


def classify_audio_role(name: str) -> str:
    if "voice_sample" in name or "speech-sample" in name:
        return "voice_sample"
    if "music" in name or "soundtrack" in name or "neon nights" in name:
        return "music"
    if "clean" in name or "audio" in name or "voice" in name:
        return "narration_candidate"
    return "audio"


def classify_image_role(name: str) -> str:
    if "presenter" in name and "profile" in name:
        return "presenter_profile_still"
    if "presenter" in name or "front" in name:
        return "presenter_front_still"
    if "logo" in name or "overlay" in name:
        return "overlay"
    return "still"


def video_reason(item: dict[str, Any]) -> str:
    if item["role"] == "previous_output":
        return "previous render; keep for comparison, not source selection"
    if item.get("duration_seconds", 0) <= 0:
        return "duration unavailable"
    if item["role"].startswith("presenter"):
        return "presenter plate candidate"
    return "B-roll or alternate presenter candidate"


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    roles: dict[str, int] = {}
    for item in items:
        counts[item["media_type"]] = counts.get(item["media_type"], 0) + 1
        roles[item["role"]] = roles.get(item["role"], 0) + 1
    selected = [item for item in items if item.get("usable")]
    rejected = [item for item in items if not item.get("usable")]
    return {
        "total_files": len(items),
        "counts_by_media_type": counts,
        "counts_by_role": roles,
        "selected_count": len(selected),
        "rejected_count": len(rejected),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect and classify local video pipeline assets.")
    parser.add_argument("--asset-root", required=True, help="Folder containing source assets to classify.")
    parser.add_argument("--output", required=True, help="Manifest JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.asset_root).resolve()
    output = Path(args.output).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"asset root not found: {root}")

    items = [classify_path(path, root) for path in sorted(root.rglob("*")) if path.is_file()]
    manifest = {
        "asset_root": str(root),
        "summary": summarize(items),
        "assets": items,
        "selected_assets": [item for item in items if item.get("usable")],
        "rejected_assets": [item for item in items if not item.get("usable")],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote asset manifest: {output}")
    print(json.dumps(manifest["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
