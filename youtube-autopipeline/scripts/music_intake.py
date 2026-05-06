#!/usr/bin/env python3
"""Copy and validate a user-provided local music bed for a reel project."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    local = Path.home() / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / f"{name}.exe"
    if local.exists():
        return str(local)
    return None


def run_json(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "unknown ffprobe failure"
        raise RuntimeError(message) from exc
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe returned invalid JSON") from exc


def probe_audio(path: Path) -> dict[str, Any]:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required for music intake")
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
    audio_stream = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"), None)
    if not audio_stream:
        raise ValueError(f"music file has no audio stream: {path}")

    fmt = data.get("format") or {}
    try:
        duration = float(fmt.get("duration") or audio_stream.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise ValueError(f"music file has non-positive duration: {path}")

    return {
        "duration_seconds": round(duration, 3),
        "codec": audio_stream.get("codec_name"),
        "sample_rate": int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
        "channels": int(audio_stream.get("channels") or 0),
        "size_bytes": int(fmt.get("size") or path.stat().st_size),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(project_dir: Path, manifest: dict[str, Any]) -> Path:
    output = project_dir / "manifests" / "music-manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and ingest a local background music file.")
    parser.add_argument("--project-dir", required=True, help="Video project directory.")
    parser.add_argument("--music", required=True, help="Local audio path, or NONE to disable background music.")
    parser.add_argument("--title", help="Optional user-provided track title.")
    parser.add_argument("--artist", help="Optional user-provided artist/source label.")
    parser.add_argument("--notes", help="Optional user-provided usage notes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    if args.music.upper() == "NONE":
        manifest = {
            "enabled": False,
            "original_path": None,
            "project_path": None,
            "user_metadata": {
                "title": args.title,
                "artist": args.artist,
                "notes": args.notes,
            },
        }
        output = write_manifest(project_dir, manifest)
        print(f"Wrote disabled music manifest: {output}")
        return 0

    source = Path(args.music).resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"music file not found: {source}")
    if source.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise ValueError(f"unsupported music extension {source.suffix!r}; expected one of {supported}")

    media = probe_audio(source)
    destination = project_dir / "source-assets" / f"soundtrack{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source != destination.resolve():
        shutil.copy2(source, destination)

    copied_media = probe_audio(destination)
    manifest = {
        "enabled": True,
        "original_path": str(source),
        "project_path": str(destination.resolve()),
        "relative_project_path": str(destination.relative_to(project_dir)),
        "sha256": sha256_file(destination),
        "duration_seconds": copied_media["duration_seconds"],
        "codec": copied_media["codec"],
        "sample_rate": copied_media["sample_rate"],
        "channels": copied_media["channels"],
        "size_bytes": copied_media["size_bytes"],
        "user_metadata": {
            "title": args.title,
            "artist": args.artist,
            "notes": args.notes,
        },
    }
    if abs(float(media["duration_seconds"]) - float(copied_media["duration_seconds"])) > 0.01:
        manifest["copy_warning"] = "Copied file duration differs from source probe."

    output = write_manifest(project_dir, manifest)
    print(f"Ingested music: {destination}")
    print(f"Wrote music manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
