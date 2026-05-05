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

import numpy as np
from moviepy import ColorClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips, TextClip


SUPPORTED_TYPES = {"A-ROLL", "B-ROLL", "PIP", "TEXT", "STACK_3"}
LOOP_POLICIES = {"loop", "error"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_FPS = 30
DEFAULT_CODEC = "libx264"
DEFAULT_AUDIO_CODEC = "aac"
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
DEFAULT_OVERLAY_SCALE = 0.3
DEFAULT_OVERLAY_POSITION = ("right", "bottom")
OVERLAY_PADDING = 20
PIP_CORNER_RADIUS = 28
PIP_OVERLAY_SHAPE = "circle"
DEFAULT_FONT = "C:\\Windows\\Fonts\\arialbd.ttf"
DEFAULT_TEXT_COLOR = "#fad617"
DEFAULT_AUDIO_CANDIDATES = ("final_audio.mp3", "final_audio.wav")
DEFAULT_MUSIC_CANDIDATES = (
    "source-assets/soundtrack.mp3",
    "source-assets/soundtrack.wav",
    "soundtrack.mp3",
    "soundtrack.wav",
)
VOICE_LOUDNORM = "loudnorm=I=-16:LRA=11:TP=-1.5"
MUSIC_BASE_GAIN = 0.14
DUCK_THRESHOLD = 0.015
DUCK_RATIO = 10
DUCK_ATTACK_MS = 15
DUCK_RELEASE_MS = 300
FINAL_PEAK_LIMIT = 0.95


def configure_output_format(format_name: str) -> None:
    global OUTPUT_WIDTH
    global OUTPUT_HEIGHT
    global DEFAULT_OVERLAY_SCALE
    global DEFAULT_OVERLAY_POSITION
    global OVERLAY_PADDING
    global PIP_CORNER_RADIUS
    global PIP_OVERLAY_SHAPE

    normalized = format_name.lower()
    if normalized in {"landscape", "16:9", "16x9"}:
        OUTPUT_WIDTH = 1920
        OUTPUT_HEIGHT = 1080
        DEFAULT_OVERLAY_SCALE = 0.3
        DEFAULT_OVERLAY_POSITION = ("right", "bottom")
        OVERLAY_PADDING = 20
        PIP_CORNER_RADIUS = 10_000
        PIP_OVERLAY_SHAPE = "circle"
        return

    if normalized in {"vertical", "9:16", "9x16", "portrait"}:
        OUTPUT_WIDTH = 1080
        OUTPUT_HEIGHT = 1920
        DEFAULT_OVERLAY_SCALE = 0.34
        DEFAULT_OVERLAY_POSITION = ("center", "bottom")
        OVERLAY_PADDING = 36
        PIP_CORNER_RADIUS = 10_000
        PIP_OVERLAY_SHAPE = "circle"
        return

    raise ValueError(f"Unsupported output format: {format_name!r}")


@dataclass(frozen=True)
class TimelineEntry:
    type: str
    start_time: float
    end_time: float
    clip_path: str | None = None
    clip_path_top: str | None = None
    clip_path_mid: str | None = None
    clip_path_bot: str | None = None
    background_path: str | None = None
    overlay_path: str | None = None
    overlay_scale: float | None = None
    overlay_position: tuple[str | int, str | int] | None = None
    overlay_crop_x: int | None = None
    overlay_crop_y: int | None = None
    overlay_crop_size: int | None = None
    text: str | None = None
    text_color: str | None = None
    font: str | None = None
    caption_text: str | None = None
    caption_color: str | None = None
    caption_position: str | None = None
    caption_y: int | None = None
    clip_start: float = 0.0
    background_clip_start: float | None = None
    overlay_clip_start: float | None = None
    clip_start_top: float | None = None
    clip_start_mid: float | None = None
    clip_start_bot: float | None = None
    loop_policy: str = "loop"
    background_loop_policy: str | None = None
    overlay_loop_policy: str | None = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def clip_offset(self, field: str) -> float:
        value = getattr(self, field)
        return self.clip_start if value is None else value

    def resolved_loop_policy(self, field: str | None = None) -> str:
        if field:
            value = getattr(self, field)
            if value:
                return value
        return self.loop_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose a final video from a timeline JSON and local assets.")
    parser.add_argument("--project-dir", default=".", help="Base directory for timeline, audio, and relative asset paths.")
    parser.add_argument("--timeline", help="Path to timeline.json. Defaults to <project-dir>/timeline.json")
    parser.add_argument("--audio", help="Path to the master narration track. Defaults to a common final_audio file.")
    parser.add_argument("--music", help="Optional path to background music. Defaults to a common soundtrack file if present.")
    parser.add_argument("--output", help="Output MP4 path. Defaults to <project-dir>/final_output.mp4")
    parser.add_argument(
        "--format",
        default="landscape",
        choices=("landscape", "vertical", "16:9", "9:16", "16x9", "9x16", "portrait"),
        help="Output format. landscape/16:9 renders 1920x1080; vertical/9:16 renders 1080x1920.",
    )
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
    if args.music and args.music.upper() == "NONE":
        music_path = None
    else:
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
    with timeline_path.open("r", encoding="utf-8-sig") as handle:
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

        loop_policy = item.get("loop_policy", "loop")
        background_loop_policy = item.get("background_loop_policy")
        overlay_loop_policy = item.get("overlay_loop_policy")
        for field_name, policy in (
            ("loop_policy", loop_policy),
            ("background_loop_policy", background_loop_policy),
            ("overlay_loop_policy", overlay_loop_policy),
        ):
            if policy is not None and policy not in LOOP_POLICIES:
                raise ValueError(f"Timeline entry {index} has invalid {field_name}: {policy!r}")

        entries.append(
            TimelineEntry(
                type=entry_type,
                start_time=float(start_time),
                end_time=float(end_time),
                clip_path=item.get("clip_path"),
                clip_path_top=item.get("clip_path_top"),
                clip_path_mid=item.get("clip_path_mid"),
                clip_path_bot=item.get("clip_path_bot"),
                background_path=item.get("background_path"),
                overlay_path=item.get("overlay_path"),
                overlay_scale=float(item["overlay_scale"]) if "overlay_scale" in item else None,
                overlay_position=parsed_position,
                overlay_crop_x=int(item["overlay_crop_x"]) if "overlay_crop_x" in item else None,
                overlay_crop_y=int(item["overlay_crop_y"]) if "overlay_crop_y" in item else None,
                overlay_crop_size=int(item["overlay_crop_size"]) if "overlay_crop_size" in item else None,
                text=item.get("text"),
                text_color=item.get("text_color"),
                font=item.get("font"),
                caption_text=item.get("caption_text"),
                caption_color=item.get("caption_color"),
                caption_position=item.get("caption_position"),
                caption_y=int(item["caption_y"]) if "caption_y" in item else None,
                clip_start=float(item.get("clip_start", 0.0)),
                background_clip_start=float(item["background_clip_start"]) if "background_clip_start" in item else None,
                overlay_clip_start=float(item["overlay_clip_start"]) if "overlay_clip_start" in item else None,
                clip_start_top=float(item["clip_start_top"]) if "clip_start_top" in item else None,
                clip_start_mid=float(item["clip_start_mid"]) if "clip_start_mid" in item else None,
                clip_start_bot=float(item["clip_start_bot"]) if "clip_start_bot" in item else None,
                loop_policy=loop_policy,
                background_loop_policy=background_loop_policy,
                overlay_loop_policy=overlay_loop_policy,
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
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError(
                "ffmpeg is required for final audio normalization, ducking, and muxing. "
                "Install ffmpeg or install imageio-ffmpeg in the active Python environment."
            )
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
    try:
        run_ffmpeg(command)
    except RuntimeError:
        # Fallback: if sidechain ducking fails in ffmpeg, keep the music bed quiet
        # and produce a safe final mix rather than failing the entire render.
        fallback_filter_complex = (
            f"[1:a]atrim=0:{duration},asetpts=N/SR/TB,volume={MUSIC_BASE_GAIN}[musicbed];"
            f"[2:a]{VOICE_LOUDNORM}[voice];"
            f"[musicbed][voice]amix=inputs=2:normalize=0,"
            f"alimiter=limit={FINAL_PEAK_LIMIT}[mix]"
        )
        fallback_command = [
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
            fallback_filter_complex,
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
        run_ffmpeg(fallback_command)


def trim_or_loop_clip(clip: VideoFileClip, target_duration: float, loop_policy: str, label: str):
    if clip.duration <= 0:
        raise ValueError(f"{label} has zero duration.")
    if clip.duration >= target_duration:
        return clip.subclipped(0, target_duration)
    if loop_policy == "error":
        raise ValueError(
            f"{label} is too short for the requested segment: "
            f"{clip.duration:.3f}s available, {target_duration:.3f}s required."
        )

    loops: list[VideoFileClip] = []
    remaining = target_duration
    while remaining > 0.01:
        piece_duration = min(clip.duration, remaining)
        loops.append(clip.subclipped(0, piece_duration))
        remaining -= piece_duration
    return concatenate_videoclips(loops, method="compose")


def normalize_video_clip(
    path: Path,
    target_duration: float,
    start_offset: float = 0.0,
    loop_policy: str = "loop",
    label: str = "clip",
):
    if loop_policy not in LOOP_POLICIES:
        raise ValueError(f"Unsupported loop policy: {loop_policy!r}")
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        if start_offset:
            raise ValueError(f"{label} clip_start is not valid for still images.")
        return ImageClip(str(path)).with_duration(target_duration), None

    source = VideoFileClip(str(path))
    try:
        if start_offset < 0:
            raise ValueError(f"{label} clip_start must be zero or positive.")
        if start_offset >= source.duration:
            raise ValueError(
                f"{label} clip_start {start_offset:.3f}s exceeds source duration {source.duration:.3f}s."
            )
        clip_end = min(source.duration, start_offset + target_duration)
        trimmed = source.subclipped(start_offset, clip_end)

        working = trim_or_loop_clip(trimmed, target_duration, loop_policy, label)
        return working.with_duration(target_duration), source
    except Exception:
        source.close()
        raise


def scale_clip_to_canvas(clip, canvas_size: tuple[int, int], policy: str):
    canvas_w, canvas_h = canvas_size
    if policy not in {"fit", "cover"}:
        raise ValueError(f"Unsupported canvas scaling policy: {policy!r}")

    if policy == "fit":
        scale = min(canvas_w / clip.w, canvas_h / clip.h)
        resized = clip.resized(width=max(1, int(clip.w * scale)))
        if resized.h > canvas_h:
            resized = clip.resized(height=max(1, int(clip.h * scale)))
        background = ColorClip(size=canvas_size, color=(0, 0, 0)).with_duration(clip.duration)
        composed = CompositeVideoClip(
            [background, resized.with_position(("center", "center"))],
            size=canvas_size,
        ).with_duration(clip.duration)
        return composed, [background, resized, composed]

    scale = max(canvas_w / clip.w, canvas_h / clip.h)
    resized = clip.resized(width=max(1, int(clip.w * scale)))
    if resized.h < canvas_h:
        resized = clip.resized(height=max(1, int(clip.h * scale)))

    x = int((canvas_w - resized.w) / 2)
    y = int((canvas_h - resized.h) / 2)
    composed = CompositeVideoClip(
        [resized.with_position((x, y))],
        size=canvas_size,
    ).with_duration(clip.duration)
    return composed, [resized, composed]


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


def build_rounded_mask(size: tuple[int, int], radius: int, duration: float):
    width, height = size
    radius = max(0, min(radius, width // 2, height // 2))
    if radius == 0:
        mask = np.ones((height, width), dtype=float)
        return ImageClip(mask, is_mask=True).with_duration(duration)

    mask = np.ones((height, width), dtype=float)
    y = np.arange(radius)[:, None]
    x = np.arange(radius)[None, :]
    distance_from_corner = np.sqrt((radius - 1 - y) ** 2 + (radius - 1 - x) ** 2)
    corner = (distance_from_corner <= (radius - 1)).astype(float)

    mask[0:radius, 0:radius] = corner
    mask[0:radius, width - radius : width] = np.fliplr(corner)
    mask[height - radius : height, 0:radius] = np.flipud(corner)
    mask[height - radius : height, width - radius : width] = np.flipud(np.fliplr(corner))

    return ImageClip(mask, is_mask=True).with_duration(duration)


def build_text_clip(project_dir: Path, entry: TimelineEntry):
    if not entry.text:
        raise ValueError("TEXT entry must include text.")

    background_path = resolve_media_path(project_dir, entry.background_path, "background_path")
    background_clip, background_source = normalize_video_clip(
        background_path,
        entry.duration,
        entry.clip_offset("background_clip_start"),
        entry.resolved_loop_policy("background_loop_policy"),
        "TEXT background",
    )
    fitted_background, background_handles = scale_clip_to_canvas(
        background_clip,
        (OUTPUT_WIDTH, OUTPUT_HEIGHT),
        "cover",
    )

    text_box_height = int(OUTPUT_HEIGHT * 0.18)
    font_size = max(48, min(86, int(OUTPUT_WIDTH / max(10, len(entry.text)) * 1.12)))
    text_backdrop = (
        ColorClip(size=(OUTPUT_WIDTH, text_box_height), color=(0, 0, 0))
        .with_opacity(0.46)
        .with_duration(entry.duration)
        .with_position(("center", "center"))
    )
    text_clip = TextClip(
        text=entry.text,
        font=entry.font or DEFAULT_FONT,
        font_size=font_size,
        color=entry.text_color or DEFAULT_TEXT_COLOR,
        method="caption",
        size=(OUTPUT_WIDTH, text_box_height),
        text_align="center",
        vertical_align="center",
    ).with_duration(entry.duration).with_position(("center", "center"))

    composite = CompositeVideoClip(
        [fitted_background, text_backdrop, text_clip],
        size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
    ).with_duration(entry.duration)
    return composite, [composite, text_clip, text_backdrop, background_clip, background_source, fitted_background, *background_handles]


def caption_y_position(entry: TimelineEntry, caption_height: int) -> int:
    if entry.caption_y is not None:
        return max(0, min(entry.caption_y, OUTPUT_HEIGHT - caption_height))

    position = entry.caption_position
    normalized = (position or "top").lower()
    top_safe = int(OUTPUT_HEIGHT * 0.10)
    center_y = int((OUTPUT_HEIGHT - caption_height) / 2)
    bottom_safe = int(OUTPUT_HEIGHT - caption_height - OUTPUT_HEIGHT * 0.16)
    if normalized == "top":
        return top_safe
    if normalized == "center":
        return center_y
    if normalized == "bottom":
        return bottom_safe
    raise ValueError("caption_position must be one of: top, center, bottom")


def add_caption_overlay(segment, entry: TimelineEntry):
    if not entry.caption_text:
        return segment, []

    caption = entry.caption_text.strip()
    if not caption:
        return segment, []

    max_width = int(OUTPUT_WIDTH * 0.84)
    box_height = int(OUTPUT_HEIGHT * 0.16)
    font_size = 58 if OUTPUT_HEIGHT > OUTPUT_WIDTH else 44
    caption_clip = TextClip(
        text=caption,
        font=entry.font or DEFAULT_FONT,
        font_size=font_size,
        color=entry.caption_color or "#ffffff",
        stroke_color="#000000",
        stroke_width=3,
        method="caption",
        size=(max_width, box_height),
        text_align="center",
        vertical_align="center",
    ).with_duration(entry.duration)
    y = caption_y_position(entry, box_height)
    composite = CompositeVideoClip(
        [segment, caption_clip.with_position(("center", y))],
        size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
    ).with_duration(entry.duration)
    return composite, [composite, caption_clip]


def build_stack_3_clip(project_dir: Path, entry: TimelineEntry):
    top_path = resolve_media_path(project_dir, entry.clip_path_top, "clip_path_top")
    mid_path = resolve_media_path(project_dir, entry.clip_path_mid, "clip_path_mid")
    bot_path = resolve_media_path(project_dir, entry.clip_path_bot, "clip_path_bot")

    top_clip, top_source = normalize_video_clip(
        top_path,
        entry.duration,
        entry.clip_offset("clip_start_top"),
        entry.loop_policy,
        "STACK_3 top clip",
    )
    mid_clip, mid_source = normalize_video_clip(
        mid_path,
        entry.duration,
        entry.clip_offset("clip_start_mid"),
        entry.loop_policy,
        "STACK_3 middle clip",
    )
    bot_clip, bot_source = normalize_video_clip(
        bot_path,
        entry.duration,
        entry.clip_offset("clip_start_bot"),
        entry.loop_policy,
        "STACK_3 bottom clip",
    )

    top_resized = top_clip.resized(width=OUTPUT_WIDTH)
    mid_resized = mid_clip.resized(width=OUTPUT_WIDTH)
    bot_resized = bot_clip.resized(width=OUTPUT_WIDTH)

    total_height = top_resized.h + mid_resized.h + bot_resized.h
    y_start = int((OUTPUT_HEIGHT - total_height) / 2)
    background = ColorClip(size=(OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(0, 0, 0)).with_duration(entry.duration)
    composite = CompositeVideoClip(
        [
            background,
            top_resized.with_position((0, y_start)),
            mid_resized.with_position((0, y_start + top_resized.h)),
            bot_resized.with_position((0, y_start + top_resized.h + mid_resized.h)),
        ],
        size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
    ).with_duration(entry.duration)

    return composite, [
        composite,
        background,
        top_clip,
        top_source,
        top_resized,
        mid_clip,
        mid_source,
        mid_resized,
        bot_clip,
        bot_source,
        bot_resized,
    ]


def crop_to_square(clip, crop_x: int, crop_y: int, crop_size: int | None = None):
    width, height = clip.size
    if crop_size is None:
        crop_size = min(width, height)
    crop_size = max(1, min(crop_size, width, height))
    x1 = max(0, min(crop_x, width - crop_size))
    y1 = max(0, min(crop_y, height - crop_size))
    return clip.cropped(x1=x1, y1=y1, width=crop_size, height=crop_size)


def center_crop_to_square(clip):
    width, height = clip.size
    crop_size = min(width, height)
    x1 = max(0, int((width - crop_size) / 2))
    y1 = max(0, int((height - crop_size) / 2))
    return clip.cropped(x1=x1, y1=y1, width=crop_size, height=crop_size)


def build_standard_clip(project_dir: Path, entry: TimelineEntry):
    clip_path = resolve_media_path(project_dir, entry.clip_path, "clip_path")
    clip, source = normalize_video_clip(
        clip_path,
        entry.duration,
        entry.clip_start,
        entry.loop_policy,
        f"{entry.type} clip",
    )
    framed, framed_handles = scale_clip_to_canvas(clip, (OUTPUT_WIDTH, OUTPUT_HEIGHT), "cover")
    return framed, [framed, clip, source, *framed_handles]


def build_pip_clip(project_dir: Path, entry: TimelineEntry):
    background_path = resolve_media_path(project_dir, entry.background_path, "background_path")
    overlay_path = resolve_media_path(project_dir, entry.overlay_path, "overlay_path")

    background_clip, background_source = normalize_video_clip(
        background_path,
        entry.duration,
        entry.clip_offset("background_clip_start"),
        entry.resolved_loop_policy("background_loop_policy"),
        "PIP background",
    )
    overlay_clip, overlay_source = normalize_video_clip(
        overlay_path,
        entry.duration,
        entry.clip_offset("overlay_clip_start"),
        entry.resolved_loop_policy("overlay_loop_policy"),
        "PIP overlay",
    )
    cropped_overlay = None
    if entry.overlay_crop_x is not None and entry.overlay_crop_y is not None:
        cropped_overlay = crop_to_square(
            overlay_clip,
            entry.overlay_crop_x,
            entry.overlay_crop_y,
            entry.overlay_crop_size,
        )
        overlay_clip = cropped_overlay
    elif PIP_OVERLAY_SHAPE == "circle":
        cropped_overlay = center_crop_to_square(overlay_clip)
        overlay_clip = cropped_overlay
    fitted_background, background_handles = scale_clip_to_canvas(
        background_clip,
        (OUTPUT_WIDTH, OUTPUT_HEIGHT),
        "cover",
    )

    overlay_scale = entry.overlay_scale if entry.overlay_scale is not None else DEFAULT_OVERLAY_SCALE
    if overlay_scale <= 0:
        raise ValueError("overlay_scale must be positive.")

    resized_overlay = overlay_clip.resized(height=int(OUTPUT_HEIGHT * overlay_scale))
    overlay_mask = build_rounded_mask((resized_overlay.w, resized_overlay.h), PIP_CORNER_RADIUS, entry.duration)
    masked_overlay = resized_overlay.with_mask(overlay_mask)
    requested_position = entry.overlay_position or DEFAULT_OVERLAY_POSITION
    overlay_position = compute_overlay_position(
        (OUTPUT_WIDTH, OUTPUT_HEIGHT),
        (masked_overlay.w, masked_overlay.h),
        requested_position,
    )

    background_layer = fitted_background.with_duration(entry.duration)
    composite = CompositeVideoClip(
        [
            background_layer,
            masked_overlay.with_position(overlay_position),
        ],
        size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
    ).with_duration(entry.duration)
    return composite, [
        composite,
        background_clip,
        overlay_clip,
        background_source,
        overlay_source,
        fitted_background,
        *background_handles,
        resized_overlay,
        overlay_mask,
        masked_overlay,
        background_layer,
        cropped_overlay,
    ]


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
            elif entry.type == "TEXT":
                segment, handles = build_text_clip(project_dir, entry)
            elif entry.type == "STACK_3":
                segment, handles = build_stack_3_clip(project_dir, entry)
            else:
                raise ValueError(f"Unsupported timeline type: {entry.type}")
            segment, caption_handles = add_caption_overlay(segment, entry)
            visual_segments.append(segment)
            opened.extend([*handles, *caption_handles])

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
    configure_output_format(args.format)
    project_dir, timeline_path, audio_path, music_path, output_path = resolve_project_paths(args)

    ensure_file(timeline_path, "Timeline file")
    result = compose_video(project_dir, timeline_path, audio_path, music_path, output_path)
    print(f"Saved final video: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
