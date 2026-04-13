#!/usr/bin/env python3
"""Assemble a final MP4 from a JSON timeline, local video assets, and mixed audio."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from moviepy import CompositeVideoClip, VideoFileClip, concatenate_videoclips


SUPPORTED_TYPES = {"A-ROLL", "B-ROLL", "PIP"}
DEFAULT_FPS = 30
DEFAULT_CODEC = "libx264"
DEFAULT_AUDIO_CODEC = "aac"
DEFAULT_OVERLAY_SCALE = 0.3
DEFAULT_OVERLAY_POSITION = ("right", "bottom")
OVERLAY_PADDING = 20
DEFAULT_AUDIO_CANDIDATES = ("final_audio.mp3", "final_audio.wav")
DEFAULT_MUSIC_CANDIDATES = (
    "source-assets/soundtrack.mp3",
    "source-assets/soundtrack.wav",
    "soundtrack.mp3",
    "soundtrack.wav",
)
VOICE_LOUDNORM = "loudnorm=I=-16:LRA=11:TP=-1.5"
MUSIC_BASE_GAIN = 0.22
DUCK_THRESHOLD = 0.015
DUCK_RATIO = 10
DUCK_ATTACK_MS = 15
DUCK_RELEASE_MS = 300
FINAL_PEAK_LIMIT = 0.95


@dataclass(frozen=True)
class TimelineEntry:
    type: str
    start_time: float
    end_time: float
    clip_path: str | None = None
    background_path: str | None = None
    overlay_path: str | None = None
    overlay_scale: float | None = None
    overlay_position: tuple[str | int, str | int] | None = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose a final video from a timeline JSON and local assets.")
    parser.add_argument("--project-dir", default=".", help="Base directory for timeline, audio, and relative asset paths.")
    parser.add_argument("--timeline", help="Path to timeline.json. Defaults to <project-dir>/timeline.json")
    parser.add_argument("--audio", help="Path to the master narration track. Defaults to a common final_audio file.")
    parser.add_argument("--music", help="Optional path to background music. Defaults to a common soundtrack file if present.")
    parser.add_argument("--output", help="Output MP4 path. Defaults to <project-dir>/final_output.mp4")
    return parser.parse_args()


def resolve_default_file(project_dir: Path, candidates: tuple[str, ...], label: str, required: bool) -> Path | None:
    for relative in candidates:
        candidate = (project_dir / relative).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    if required:
        expected = ", ".join(str(project_dir / name) for name in candidates)
        raise FileNotFoundError(f"{label} not found. Checked: {expected}")
    return None


def resolve_project_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path | None, Path]:
    project_dir = Path(args.project_dir).resolve()
    timeline_path = Path(args.timeline).resolve() if args.timeline else project_dir / "timeline.json"
    audio_path = Path(args.audio).resolve() if args.audio else resolve_default_file(
        project_dir, DEFAULT_AUDIO_CANDIDATES, "Audio file", required=True
    )
    music_path = Path(args.music).resolve() if args.music else resolve_default_file(
        project_dir, DEFAULT_MUSIC_CANDIDATES, "Music file", required=False
    )
    output_path = Path(args.output).resolve() if args.output else project_dir / "final_output.mp4"
    return project_dir, timeline_path, audio_path, music_path, output_path


def ensure_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"{label} is not a file: {path}")


def load_timeline(timeline_path: Path) -> list[TimelineEntry]:
    with timeline_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if not isinstance(raw, list) or not raw:
        raise ValueError("timeline.json must contain a non-empty JSON array.")

    entries: list[TimelineEntry] = []
    previous_end = 0.0

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Timeline entry {index} must be an object.")

        entry_type = item.get("type")
        start_time = item.get("start_time")
        end_time = item.get("end_time")

        if entry_type not in SUPPORTED_TYPES:
            raise ValueError(f"Timeline entry {index} has unsupported type: {entry_type!r}")
        if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
            raise ValueError(f"Timeline entry {index} must include numeric start_time and end_time.")
        if end_time <= start_time:
            raise ValueError(f"Timeline entry {index} has non-positive duration.")
        if abs(float(start_time) - previous_end) > 0.01:
            raise ValueError(
                f"Timeline entry {index} is not sequential. Expected start_time {previous_end}, got {start_time}."
            )

        overlay_position = item.get("overlay_position")
        parsed_position: tuple[str | int, str | int] | None = None
        if overlay_position is not None:
            if (
                not isinstance(overlay_position, list)
                or len(overlay_position) != 2
                or not all(isinstance(part, (str, int, float)) for part in overlay_position)
            ):
                raise ValueError(f"Timeline entry {index} has invalid overlay_position.")
            parsed_position = (overlay_position[0], overlay_position[1])

        entries.append(
            TimelineEntry(
                type=entry_type,
                start_time=float(start_time),
                end_time=float(end_time),
                clip_path=item.get("clip_path"),
                background_path=item.get("background_path"),
                overlay_path=item.get("overlay_path"),
                overlay_scale=float(item["overlay_scale"]) if "overlay_scale" in item else None,
                overlay_position=parsed_position,
            )
        )
        previous_end = float(end_time)

    return entries


def resolve_media_path(project_dir: Path, raw_path: str | None, label: str) -> Path:
    if not raw_path:
        raise ValueError(f"Missing required field: {label}")
    candidate = Path(raw_path)
    path = candidate.resolve() if candidate.is_absolute() else (project_dir / candidate).resolve()
    ensure_file(path, label)
    return path


def require_ffmpeg() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg is required for final audio normalization, ducking, and muxing.")
    return ffmpeg_path


def run_ffmpeg(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "unknown ffmpeg failure"
        raise RuntimeError(f"ffmpeg command failed: {message}") from exc


def mux_with_processed_audio(
    video_path: Path,
    audio_path: Path,
    music_path: Path | None,
    output_path: Path,
    target_duration: float,
) -> None:
    ffmpeg = require_ffmpeg()
    duration = f"{target_duration:.3f}"

    if music_path is None:
        filter_complex = f"[1:a]{VOICE_LOUDNORM},alimiter=limit={FINAL_PEAK_LIMIT}[mix]"
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[mix]",
            "-c:v",
            "copy",
            "-c:a",
            DEFAULT_AUDIO_CODEC,
            "-shortest",
            str(output_path),
        ]
        run_ffmpeg(command)
        return

    filter_complex = (
        f"[1:a]atrim=0:{duration},asetpts=N/SR/TB,volume={MUSIC_BASE_GAIN}[musicbed];"
        f"[2:a]{VOICE_LOUDNORM}[voice];"
        f"[musicbed][voice]sidechaincompress="
        f"threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}[ducked];"
        f"[ducked][voice]amix=inputs=2:normalize=0,"
        f"alimiter=limit={FINAL_PEAK_LIMIT}[mix]"
    )
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-stream_loop",
        "-1",
        "-i",
        str(music_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "[mix]",
        "-c:v",
        "copy",
        "-c:a",
        DEFAULT_AUDIO_CODEC,
        "-shortest",
        str(output_path),
    ]
    run_ffmpeg(command)


def trim_or_loop_clip(clip: VideoFileClip, target_duration: float):
    if clip.duration <= 0:
        raise ValueError("Input clip has zero duration.")
    if clip.duration >= target_duration:
        return clip.subclipped(0, target_duration)

    loops: list[VideoFileClip] = []
    remaining = target_duration
    while remaining > 0.01:
        piece_duration = min(clip.duration, remaining)
        loops.append(clip.subclipped(0, piece_duration))
        remaining -= piece_duration
    return concatenate_videoclips(loops, method="compose")


def normalize_video_clip(path: Path, target_duration: float):
    source = VideoFileClip(str(path))
    try:
        working = trim_or_loop_clip(source, target_duration)
        return working.with_duration(target_duration), source
    except Exception:
        source.close()
        raise


def compute_overlay_position(
    background_size: tuple[int, int],
    overlay_size: tuple[int, int],
    requested: tuple[str | int, str | int],
) -> tuple[int, int]:
    bg_w, bg_h = background_size
    ov_w, ov_h = overlay_size
    x_raw, y_raw = requested

    def convert_axis(raw: str | int, axis_size: int, item_size: int) -> int:
        if isinstance(raw, (int, float)):
            return int(raw)
        if raw == "left" or raw == "top":
            return OVERLAY_PADDING
        if raw == "right" or raw == "bottom":
            return max(OVERLAY_PADDING, axis_size - item_size - OVERLAY_PADDING)
        if raw == "center":
            return max(0, int((axis_size - item_size) / 2))
        raise ValueError(f"Unsupported overlay position value: {raw!r}")

    return (
        convert_axis(x_raw, bg_w, ov_w),
        convert_axis(y_raw, bg_h, ov_h),
    )


def build_standard_clip(project_dir: Path, entry: TimelineEntry):
    clip_path = resolve_media_path(project_dir, entry.clip_path, "clip_path")
    clip, source = normalize_video_clip(clip_path, entry.duration)
    return clip, [clip, source]


def build_pip_clip(project_dir: Path, entry: TimelineEntry):
    background_path = resolve_media_path(project_dir, entry.background_path, "background_path")
    overlay_path = resolve_media_path(project_dir, entry.overlay_path, "overlay_path")

    background_clip, background_source = normalize_video_clip(background_path, entry.duration)
    overlay_clip, overlay_source = normalize_video_clip(overlay_path, entry.duration)

    overlay_scale = entry.overlay_scale if entry.overlay_scale is not None else DEFAULT_OVERLAY_SCALE
    if overlay_scale <= 0:
        raise ValueError("overlay_scale must be positive.")

    resized_overlay = overlay_clip.resized(height=int(background_clip.h * overlay_scale))
    requested_position = entry.overlay_position or DEFAULT_OVERLAY_POSITION
    overlay_position = compute_overlay_position(
        (background_clip.w, background_clip.h),
        (resized_overlay.w, resized_overlay.h),
        requested_position,
    )

    composite = CompositeVideoClip(
        [
            background_clip,
            resized_overlay.with_position(overlay_position),
        ],
        size=(background_clip.w, background_clip.h),
    ).with_duration(entry.duration)
    return composite, [composite, background_clip, overlay_clip, background_source, overlay_source]


def close_all(clips: Iterable[Any]) -> None:
    seen: set[int] = set()
    for clip in clips:
        if clip is None or id(clip) in seen:
            continue
        seen.add(id(clip))
        close = getattr(clip, "close", None)
        if callable(close):
            close()


def compose_video(
    project_dir: Path,
    timeline_path: Path,
    audio_path: Path,
    music_path: Path | None,
    output_path: Path,
) -> Path:
    entries = load_timeline(timeline_path)
    ensure_file(audio_path, "Audio file")
    if music_path is not None:
        ensure_file(music_path, "Music file")

    opened: list[Any] = []
    visual_segments = []
    final_video = None
    temp_video_path = None

    try:
        for entry in entries:
            if entry.type in {"A-ROLL", "B-ROLL"}:
                segment, handles = build_standard_clip(project_dir, entry)
            elif entry.type == "PIP":
                segment, handles = build_pip_clip(project_dir, entry)
            else:
                raise ValueError(f"Unsupported timeline type: {entry.type}")
            visual_segments.append(segment)
            opened.extend(handles)

        final_video = concatenate_videoclips(visual_segments, method="compose")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(prefix="compose_video_", suffix=".mp4", delete=False) as handle:
            temp_video_path = Path(handle.name)

        final_video.write_videofile(
            str(temp_video_path),
            fps=DEFAULT_FPS,
            codec=DEFAULT_CODEC,
            audio=False,
        )
        mux_with_processed_audio(temp_video_path, audio_path, music_path, output_path, entries[-1].end_time)
        return output_path
    finally:
        close_all([final_video, *visual_segments, *opened])
        if temp_video_path is not None and temp_video_path.exists():
            temp_video_path.unlink()


def main() -> int:
    args = parse_args()
    project_dir, timeline_path, audio_path, music_path, output_path = resolve_project_paths(args)

    ensure_file(timeline_path, "Timeline file")
    result = compose_video(project_dir, timeline_path, audio_path, music_path, output_path)
    print(f"Saved final video: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
