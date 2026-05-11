#!/usr/bin/env python3
"""Assemble a final MP4 from a JSON timeline, local video assets, and mixed audio."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import sys

import numpy as np
from moviepy import ColorClip, CompositeVideoClip, ImageClip, VideoClip, VideoFileClip, concatenate_videoclips, TextClip

AUTOPIPELINE_SCRIPTS = Path(__file__).resolve().parents[2] / "youtube-autopipeline" / "scripts"
sys.path.insert(0, str(AUTOPIPELINE_SCRIPTS))
from production_gate import run_creative_gate  # noqa: E402
from production_metrics import end_stage, start_stage  # noqa: E402


SUPPORTED_TYPES = {"A_ROLL", "B_ROLL"}
LEGACY_TOP_LEVEL_TYPES = {"A-ROLL", "B-ROLL", "PIP", "TEXT", "TEXT_GRAPHIC", "STACK_2", "STACK_3", "SPLIT_2", "GRID_4", "STILL_MOTION", "PUNCH_IN"}
BROLL_LAYOUTS = {"fullscreen", "stack2", "stack3", "grid4"}
BROLL_LAYOUT_PANEL_COUNTS = {"stack2": 2, "stack3": 3, "grid4": 4}
PANEL_KINDS = {"broll", "presenter"}
BROLL_SOURCE_TYPES = {"webpage", "stock", "screen-record", "generated-image", "manual", "synthetic-motion"}
LOOP_POLICIES = {"loop", "error"}
SPLIT_AXES = {"horizontal", "vertical"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
STILL_MOTION_TYPES = {"push-in", "pull-back", "pan-left", "pan-right", "pan-up", "pan-down", "diagonal-drift", "swipe-in"}
DEFAULT_FPS = 30
DEFAULT_CODEC = "libx264"
DEFAULT_AUDIO_CODEC = "aac"
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
DEFAULT_OVERLAY_SCALE = 0.3
DEFAULT_OVERLAY_POSITION: tuple[str, str] | None = ("right", "bottom")
OVERLAY_PADDING = 20
PIP_CORNER_RADIUS = 28
PIP_OVERLAY_SHAPE = "circle"
DEFAULT_FONT = "C:\\Windows\\Fonts\\arialbd.ttf"
DEFAULT_TEXT_COLOR = "#fad617"
DEFAULT_AUDIO_CANDIDATES = ("final_audio.mp3", "final_audio.wav")
DEFAULT_MUSIC_CANDIDATES = (
    "source-assets/soundtrack.mp3",
    "source-assets/soundtrack.wav",
    "source-assets/soundtrack.m4a",
    "source-assets/soundtrack.aac",
    "source-assets/soundtrack.flac",
    "source-assets/soundtrack.ogg",
    "soundtrack.mp3",
    "soundtrack.wav",
    "soundtrack.m4a",
    "soundtrack.aac",
    "soundtrack.flac",
    "soundtrack.ogg",
)
FRONT_STACK_CROP_Y_FRACTION = 1 / 8
FRONT_STACK_CROP_HEIGHT_FRACTION = 1 / 2
VOICE_LOUDNORM = "loudnorm=I=-16:LRA=11:TP=-1.5"
MUSIC_BASE_GAIN = 0.30
DUCK_THRESHOLD = 0.015
DUCK_RATIO = 5
DUCK_ATTACK_MS = 5
DUCK_RELEASE_MS = 220
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
        DEFAULT_OVERLAY_POSITION = None
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
    layout: str | None = None
    panels: list[dict[str, Any]] | None = None
    clip_path: str | None = None
    clip_path_top: str | None = None
    clip_path_mid: str | None = None
    clip_path_bot: str | None = None
    clip_path_a: str | None = None
    clip_path_b: str | None = None
    clip_path_1: str | None = None
    clip_path_2: str | None = None
    clip_path_3: str | None = None
    clip_path_4: str | None = None
    background_path: str | None = None
    overlay_path: str | None = None
    treatment: str | None = None
    split_axis: str = "vertical"
    motion_type: str = "push-in"
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
    clip_start_a: float | None = None
    clip_start_b: float | None = None
    clip_start_1: float | None = None
    clip_start_2: float | None = None
    clip_start_3: float | None = None
    clip_start_4: float | None = None
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
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel segment render workers. Default: 4. Use 1 for sequential.",
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


def validate_and_expand_entry(item: dict[str, Any], index: int) -> dict[str, Any]:
    expanded = dict(item)
    entry_type = item.get("type")
    if "primary_visual" in item:
        raise ValueError(f"Timeline entry {index} uses unsupported primary_visual; use type A_ROLL or B_ROLL.")
    if entry_type in LEGACY_TOP_LEVEL_TYPES - SUPPORTED_TYPES:
        raise ValueError(f"Timeline entry {index} uses layout/treatment as type: {entry_type!r}")
    if entry_type not in SUPPORTED_TYPES:
        raise ValueError(f"Timeline entry {index} has unsupported type: {entry_type!r}")

    if entry_type == "A_ROLL":
        for field in ("layout", "panels", "source", "source_strategy"):
            if field in item:
                raise ValueError(f"Timeline entry {index} field {field!r} is only valid for B_ROLL.")
        if not isinstance(item.get("clip_path"), str) or not item.get("clip_path", "").strip():
            raise ValueError(f"Timeline entry {index} A_ROLL requires clip_path.")
        return expanded

    layout = item.get("layout")
    if layout not in BROLL_LAYOUTS:
        raise ValueError(f"Timeline entry {index} B_ROLL layout must be one of {sorted(BROLL_LAYOUTS)}.")
    panels = item.get("panels")
    if not isinstance(panels, list) or not panels:
        raise ValueError(f"Timeline entry {index} B_ROLL requires non-empty panels.")
    expected_count = BROLL_LAYOUT_PANEL_COUNTS.get(str(layout))
    if expected_count is not None and len(panels) != expected_count:
        raise ValueError(f"Timeline entry {index} layout {layout!r} requires exactly {expected_count} panels.")

    broll_panels: list[dict[str, Any]] = []
    presenter_panels: list[dict[str, Any]] = []
    for panel_index, panel in enumerate(panels):
        if not isinstance(panel, dict):
            raise ValueError(f"Timeline entry {index} panels[{panel_index}] must be an object.")
        kind = panel.get("kind")
        if kind not in PANEL_KINDS:
            raise ValueError(f"Timeline entry {index} panels[{panel_index}].kind must be one of {sorted(PANEL_KINDS)}.")
        if not isinstance(panel.get("path"), str) or not panel.get("path", "").strip():
            raise ValueError(f"Timeline entry {index} panels[{panel_index}].path must be a non-empty media path.")
        if kind == "broll":
            if panel.get("source") not in BROLL_SOURCE_TYPES:
                raise ValueError(f"Timeline entry {index} panels[{panel_index}].source must be one of {sorted(BROLL_SOURCE_TYPES)}.")
            broll_panels.append(panel)
        else:
            if "source" in panel or "source_strategy" in panel:
                raise ValueError(f"Timeline entry {index} panels[{panel_index}] is presenter media and cannot define source fields.")
            if layout == "fullscreen" and DEFAULT_OVERLAY_POSITION is None:
                overlay_position = panel.get("overlay_position")
                if (
                    not isinstance(overlay_position, list)
                    or len(overlay_position) != 2
                    or not all(isinstance(part, (str, int, float)) for part in overlay_position)
                ):
                    raise ValueError(
                        f"Timeline entry {index} panels[{panel_index}].overlay_position is required for vertical fullscreen presenter overlays."
                    )
            presenter_panels.append(panel)
    if not broll_panels:
        raise ValueError(f"Timeline entry {index} B_ROLL must include at least one broll panel.")
    if presenter_panels and "loop_policy" not in expanded:
        expanded["loop_policy"] = "error"

    if layout == "fullscreen":
        if len(broll_panels) != 1:
            raise ValueError(f"Timeline entry {index} fullscreen B_ROLL requires exactly one broll panel.")
        if len(presenter_panels) > 1:
            raise ValueError(f"Timeline entry {index} fullscreen B_ROLL allows at most one presenter overlay.")
        expanded["clip_path"] = broll_panels[0]["path"]
        if "clip_start" in broll_panels[0]:
            expanded["clip_start"] = broll_panels[0]["clip_start"]
        for field in ("treatment", "motion_type", "loop_policy"):
            if field in broll_panels[0]:
                expanded[field] = broll_panels[0][field]
        if presenter_panels:
            presenter = presenter_panels[0]
            expanded["background_path"] = broll_panels[0]["path"]
            expanded["overlay_path"] = presenter["path"]
            if "clip_start" in broll_panels[0]:
                expanded["background_clip_start"] = broll_panels[0]["clip_start"]
            if "clip_start" in presenter:
                expanded["overlay_clip_start"] = presenter["clip_start"]
            if "loop_policy" in presenter:
                expanded["overlay_loop_policy"] = presenter["loop_policy"]
            for field in ("overlay_scale", "overlay_position", "overlay_crop_x", "overlay_crop_y", "overlay_crop_size"):
                if field in presenter:
                    expanded[field] = presenter[field]
    elif layout == "stack2":
        expanded["clip_path_top"] = panels[0]["path"]
        expanded["clip_path_bot"] = panels[1]["path"]
        for field_name, panel in (("clip_start_top", panels[0]), ("clip_start_bot", panels[1])):
            if "clip_start" in panel:
                expanded[field_name] = panel["clip_start"]
    elif layout == "stack3":
        expanded["clip_path_top"] = panels[0]["path"]
        expanded["clip_path_mid"] = panels[1]["path"]
        expanded["clip_path_bot"] = panels[2]["path"]
        for field_name, panel in (("clip_start_top", panels[0]), ("clip_start_mid", panels[1]), ("clip_start_bot", panels[2])):
            if "clip_start" in panel:
                expanded[field_name] = panel["clip_start"]
    elif layout == "grid4":
        for panel_index, panel in enumerate(panels, start=1):
            expanded[f"clip_path_{panel_index}"] = panel["path"]
            if "clip_start" in panel:
                expanded[f"clip_start_{panel_index}"] = panel["clip_start"]
    return expanded


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
        item = validate_and_expand_entry(item, index)

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
        split_axis = item.get("split_axis", "vertical")
        if split_axis not in SPLIT_AXES:
            raise ValueError(f"Timeline entry {index} has invalid split_axis: {split_axis!r}")
        motion_type = item.get("motion_type", "push-in")
        if motion_type not in STILL_MOTION_TYPES:
            raise ValueError(f"Timeline entry {index} has invalid motion_type: {motion_type!r}")

        entries.append(
            TimelineEntry(
                type=entry_type,
                start_time=float(start_time),
                end_time=float(end_time),
                layout=item.get("layout"),
                panels=item.get("panels"),
                clip_path=item.get("clip_path"),
                clip_path_top=item.get("clip_path_top"),
                clip_path_mid=item.get("clip_path_mid"),
                clip_path_bot=item.get("clip_path_bot"),
                clip_path_a=item.get("clip_path_a"),
                clip_path_b=item.get("clip_path_b"),
                clip_path_1=item.get("clip_path_1"),
                clip_path_2=item.get("clip_path_2"),
                clip_path_3=item.get("clip_path_3"),
                clip_path_4=item.get("clip_path_4"),
                background_path=item.get("background_path"),
                overlay_path=item.get("overlay_path"),
                treatment=item.get("treatment"),
                split_axis=split_axis,
                motion_type=motion_type,
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
                clip_start_a=float(item["clip_start_a"]) if "clip_start_a" in item else None,
                clip_start_b=float(item["clip_start_b"]) if "clip_start_b" in item else None,
                clip_start_1=float(item["clip_start_1"]) if "clip_start_1" in item else None,
                clip_start_2=float(item["clip_start_2"]) if "clip_start_2" in item else None,
                clip_start_3=float(item["clip_start_3"]) if "clip_start_3" in item else None,
                clip_start_4=float(item["clip_start_4"]) if "clip_start_4" in item else None,
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


def require_ffprobe() -> str:
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        return ffprobe_path
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        candidate = Path(ffmpeg_path).with_name("ffprobe.exe")
        if candidate.exists():
            return str(candidate)
    local = Path.home() / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffprobe.exe"
    if local.exists():
        return str(local)
    raise RuntimeError("ffprobe is required to validate narration and soundtrack audio streams.")


def run_ffmpeg(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "unknown ffmpeg failure"
        raise RuntimeError(f"ffmpeg command failed: {message}") from exc


def probe_audio_file(path: Path, label: str) -> dict[str, Any]:
    ffprobe = require_ffprobe()
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads(completed.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not probe {label}: {path}") from exc
    audio_stream = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"), None)
    if not audio_stream:
        raise ValueError(f"{label} has no audio stream: {path}")
    fmt = data.get("format") or {}
    try:
        duration = float(fmt.get("duration") or audio_stream.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise ValueError(f"{label} has non-positive duration: {path}")
    return {
        "path": str(path),
        "duration_seconds": round(duration, 3),
        "codec": audio_stream.get("codec_name"),
        "sample_rate": int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
        "channels": int(audio_stream.get("channels") or 0),
    }


def write_audio_mix_manifest(
    project_dir: Path,
    output_path: Path,
    target_duration: float,
    narration_probe: dict[str, Any],
    music_probe: dict[str, Any] | None,
    mix_mode: str,
) -> Path:
    manifest = {
        "output_path": str(output_path),
        "target_duration_seconds": round(target_duration, 3),
        "narration": narration_probe,
        "music": {
            "enabled": music_probe is not None,
            "probe": music_probe,
            "base_gain": MUSIC_BASE_GAIN if music_probe is not None else None,
            "ducking": {
                "enabled": music_probe is not None and mix_mode == "sidechain",
                "threshold": DUCK_THRESHOLD,
                "ratio": DUCK_RATIO,
                "attack_ms": DUCK_ATTACK_MS,
                "release_ms": DUCK_RELEASE_MS,
            },
        },
        "voice_loudnorm": VOICE_LOUDNORM,
        "final_peak_limit": FINAL_PEAK_LIMIT,
        "mix_mode": mix_mode,
        "audio_codec": DEFAULT_AUDIO_CODEC,
    }
    output = project_dir / "manifests" / "audio-mix-manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def mux_with_processed_audio(
    video_path: Path,
    audio_path: Path,
    music_path: Path | None,
    output_path: Path,
    target_duration: float,
) -> str:
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
        return "narration_only"

    filter_complex = (
        f"[1:a]atrim=0:{duration},asetpts=N/SR/TB,volume={MUSIC_BASE_GAIN}[musicbed];"
        f"[2:a]{VOICE_LOUDNORM},asplit=2[voice_sc][voice_mix];"
        f"[musicbed][voice_sc]sidechaincompress="
        f"threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}[ducked];"
        f"[ducked][voice_mix]amix=inputs=2:normalize=0,"
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
        return "sidechain"
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
        return "fallback_quiet_mix"


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


def path_has_segment(raw_path: str | None, segment: str) -> bool:
    if not raw_path:
        return False
    normalized = raw_path.replace("\\", "/")
    return segment.lower() in {part.lower() for part in normalized.split("/") if part}


def is_front_presenter_panel(panel: dict[str, Any] | None, raw_path: str | None) -> bool:
    if not isinstance(panel, dict):
        return False
    if panel.get("kind") != "presenter":
        return False
    return path_has_segment(str(panel.get("path") or raw_path or ""), "front")


def front_stack_presenter_crop_box(source_size: tuple[int, int], panel_size: tuple[int, int]) -> tuple[int, int, int, int]:
    source_w, source_h = source_size
    panel_w, panel_h = panel_size
    if source_w <= 0 or source_h <= 0:
        raise ValueError("source_size must be positive.")
    if panel_w <= 0 or panel_h <= 0:
        raise ValueError("panel_size must be positive.")

    crop_x = 0
    crop_y = int(round(source_h * FRONT_STACK_CROP_Y_FRACTION))
    crop_w = source_w
    crop_h = min(source_h, max(1, int(round(source_h * FRONT_STACK_CROP_HEIGHT_FRACTION))))

    crop_x = max(0, min(crop_x, source_w - crop_w))
    crop_y = max(0, min(crop_y, source_h - crop_h))
    return crop_x, crop_y, crop_w, crop_h


def maybe_crop_front_stack_presenter(clip, panel: dict[str, Any] | None, raw_path: str | None, panel_size: tuple[int, int]):
    if not is_front_presenter_panel(panel, raw_path):
        return clip, None
    if clip.h <= clip.w:
        return clip, None
    crop_x, crop_y, crop_w, crop_h = front_stack_presenter_crop_box((clip.w, clip.h), panel_size)
    return clip.cropped(x1=crop_x, y1=crop_y, width=crop_w, height=crop_h), (crop_x, crop_y, crop_w, crop_h)


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


def build_panel_clip(
    project_dir: Path,
    raw_path: str | None,
    duration: float,
    start_offset: float,
    loop_policy: str,
    label: str,
    size: tuple[int, int],
    panel: dict[str, Any] | None = None,
):
    path = resolve_media_path(project_dir, raw_path, label)
    if (
        isinstance(panel, dict)
        and panel.get("kind") == "broll"
        and panel.get("treatment") == "still_motion"
        and path.suffix.lower() in IMAGE_EXTENSIONS
    ):
        if start_offset:
            raise ValueError(f"{label} clip_start is not valid for still images.")
        motion_type = str(panel.get("motion_type") or "push-in")
        return build_still_motion_image_clip(path, duration, size, motion_type, label)

    clip, source = normalize_video_clip(path, duration, start_offset, loop_policy, label)
    stack_crop, crop_box = maybe_crop_front_stack_presenter(clip, panel, raw_path, size)
    if crop_box is not None:
        clip = stack_crop
    fitted, handles = scale_clip_to_canvas(clip, size, "cover")
    return fitted, [clip, source, stack_crop, fitted, *handles]


def build_stack_2_clip(project_dir: Path, entry: TimelineEntry):
    panel_h = OUTPUT_HEIGHT // 2
    panels = entry.panels if isinstance(entry.panels, list) else []
    top_panel = panels[0] if len(panels) > 0 and isinstance(panels[0], dict) else None
    bot_panel = panels[1] if len(panels) > 1 and isinstance(panels[1], dict) else None
    top, top_handles = build_panel_clip(
        project_dir,
        entry.clip_path_top,
        entry.duration,
        entry.clip_offset("clip_start_top"),
        entry.loop_policy,
        "STACK_2 top clip",
        (OUTPUT_WIDTH, panel_h),
        top_panel,
    )
    bot, bot_handles = build_panel_clip(
        project_dir,
        entry.clip_path_bot,
        entry.duration,
        entry.clip_offset("clip_start_bot"),
        entry.loop_policy,
        "STACK_2 bottom clip",
        (OUTPUT_WIDTH, OUTPUT_HEIGHT - panel_h),
        bot_panel,
    )
    background = ColorClip(size=(OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(0, 0, 0)).with_duration(entry.duration)
    composite = CompositeVideoClip(
        [background, top.with_position((0, 0)), bot.with_position((0, panel_h))],
        size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
    ).with_duration(entry.duration)
    return composite, [composite, background, *top_handles, *bot_handles]


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


def build_split_2_clip(project_dir: Path, entry: TimelineEntry):
    if entry.split_axis == "horizontal":
        panel_h = OUTPUT_HEIGHT // 2
        size_a = (OUTPUT_WIDTH, panel_h)
        size_b = (OUTPUT_WIDTH, OUTPUT_HEIGHT - panel_h)
        pos_a = (0, 0)
        pos_b = (0, panel_h)
    else:
        panel_w = OUTPUT_WIDTH // 2
        size_a = (panel_w, OUTPUT_HEIGHT)
        size_b = (OUTPUT_WIDTH - panel_w, OUTPUT_HEIGHT)
        pos_a = (0, 0)
        pos_b = (panel_w, 0)

    panel_a, handles_a = build_panel_clip(
        project_dir,
        entry.clip_path_a,
        entry.duration,
        entry.clip_offset("clip_start_a"),
        entry.loop_policy,
        "SPLIT_2 panel A",
        size_a,
    )
    panel_b, handles_b = build_panel_clip(
        project_dir,
        entry.clip_path_b,
        entry.duration,
        entry.clip_offset("clip_start_b"),
        entry.loop_policy,
        "SPLIT_2 panel B",
        size_b,
    )
    background = ColorClip(size=(OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(0, 0, 0)).with_duration(entry.duration)
    composite = CompositeVideoClip(
        [background, panel_a.with_position(pos_a), panel_b.with_position(pos_b)],
        size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
    ).with_duration(entry.duration)
    return composite, [composite, background, *handles_a, *handles_b]


def build_grid_4_clip(project_dir: Path, entry: TimelineEntry):
    panel_w = OUTPUT_WIDTH // 2
    panel_h = OUTPUT_HEIGHT // 2
    panel_specs = [
        ("clip_path_1", "clip_start_1", (0, 0), (panel_w, panel_h), "GRID_4 clip 1"),
        ("clip_path_2", "clip_start_2", (panel_w, 0), (OUTPUT_WIDTH - panel_w, panel_h), "GRID_4 clip 2"),
        ("clip_path_3", "clip_start_3", (0, panel_h), (panel_w, OUTPUT_HEIGHT - panel_h), "GRID_4 clip 3"),
        ("clip_path_4", "clip_start_4", (panel_w, panel_h), (OUTPUT_WIDTH - panel_w, OUTPUT_HEIGHT - panel_h), "GRID_4 clip 4"),
    ]
    layers = []
    handles = []
    for path_field, start_field, position, size, label in panel_specs:
        panel, panel_handles = build_panel_clip(
            project_dir,
            getattr(entry, path_field),
            entry.duration,
            entry.clip_offset(start_field),
            entry.loop_policy,
            label,
            size,
        )
        layers.append(panel.with_position(position))
        handles.extend(panel_handles)
    background = ColorClip(size=(OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(0, 0, 0)).with_duration(entry.duration)
    composite = CompositeVideoClip([background, *layers], size=(OUTPUT_WIDTH, OUTPUT_HEIGHT)).with_duration(entry.duration)
    return composite, [composite, background, *handles, *layers]


def cover_crop_box(image_size: tuple[int, int], output_size: tuple[int, int], scale: float) -> tuple[float, float, float, float]:
    width, height = image_size
    out_w, out_h = output_size
    aspect = out_w / out_h
    if width / height > aspect:
        crop_h = height * scale
        crop_w = crop_h * aspect
    else:
        crop_w = width * scale
        crop_h = crop_w / aspect
    if crop_w > width or crop_h > height:
        raise ValueError("requested still-motion crop exceeds image bounds")
    x = (width - crop_w) / 2
    y = (height - crop_h) / 2
    return (x, y, crop_w, crop_h)


def motion_crop_boxes(image_size: tuple[int, int], output_size: tuple[int, int], motion_type: str) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    base = cover_crop_box(image_size, output_size, 1.0)
    moving = cover_crop_box(image_size, output_size, 0.84)
    width, height = image_size
    x, y, w, h = moving
    max_x = width - w
    max_y = height - h

    if motion_type == "push-in":
        return base, moving
    if motion_type == "pull-back":
        return moving, base
    if motion_type == "pan-left":
        return (max_x, y, w, h), (0, y, w, h)
    if motion_type == "pan-right":
        return (0, y, w, h), (max_x, y, w, h)
    if motion_type == "pan-up":
        return (x, max_y, w, h), (x, 0, w, h)
    if motion_type == "pan-down":
        return (x, 0, w, h), (x, max_y, w, h)
    if motion_type == "diagonal-drift":
        return (0, 0, w, h), (max_x, max_y, w, h)
    if motion_type == "swipe-in":
        return (0, y, w, h), (max_x, y, w, h)
    raise ValueError(f"Unsupported still motion type: {motion_type!r}")


def build_still_motion_image_clip(
    path: Path,
    duration: float,
    output_size: tuple[int, int],
    motion_type: str,
    label: str,
):
    if motion_type not in STILL_MOTION_TYPES:
        raise ValueError(f"{label} has unsupported still motion type: {motion_type!r}")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for direct STILL_MOTION image rendering.") from exc

    image = Image.open(path).convert("RGB")
    start_box, end_box = motion_crop_boxes(image.size, output_size, motion_type)

    def make_frame(t: float):
        progress = 0.0 if duration <= 0 else max(0.0, min(1.0, t / duration))
        eased = progress * progress * (3 - 2 * progress)
        box = tuple(start_box[i] + (end_box[i] - start_box[i]) * eased for i in range(4))
        left, top, width, height = box
        crop = image.crop((int(round(left)), int(round(top)), int(round(left + width)), int(round(top + height))))
        resized = crop.resize(output_size, Image.Resampling.LANCZOS)
        return np.array(resized)

    clip = VideoClip(make_frame, duration=duration)
    return clip, [clip]


def build_still_motion_clip(project_dir: Path, entry: TimelineEntry):
    path = resolve_media_path(project_dir, entry.clip_path, "STILL_MOTION clip_path")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return build_standard_clip(project_dir, entry)

    return build_still_motion_image_clip(
        path,
        entry.duration,
        (OUTPUT_WIDTH, OUTPUT_HEIGHT),
        entry.motion_type,
        "STILL_MOTION clip_path",
    )


def build_camera_motion_clip(project_dir: Path, entry: TimelineEntry):
    clip_path = resolve_media_path(project_dir, entry.clip_path, "clip_path")
    clip, source = normalize_video_clip(
        clip_path,
        entry.duration,
        entry.clip_start,
        entry.loop_policy,
        f"{entry.type} clip",
    )

    try:
        from PIL import Image
    except ImportError as exc:
        close_all([clip, source])
        raise RuntimeError("Pillow is required for A_ROLL camera motion rendering.") from exc

    start_box, end_box = motion_crop_boxes((clip.w, clip.h), (OUTPUT_WIDTH, OUTPUT_HEIGHT), entry.motion_type)

    def make_frame(t: float):
        progress = 0.0 if entry.duration <= 0 else max(0.0, min(1.0, t / entry.duration))
        eased = progress * progress * (3 - 2 * progress)
        box = tuple(start_box[i] + (end_box[i] - start_box[i]) * eased for i in range(4))
        left, top, width, height = box
        frame = clip.get_frame(t)
        image = Image.fromarray(frame).convert("RGB")
        crop = image.crop((int(round(left)), int(round(top)), int(round(left + width)), int(round(top + height))))
        resized = crop.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)
        return np.array(resized)

    motion_clip = VideoClip(make_frame, duration=entry.duration)
    return motion_clip, [motion_clip, clip, source]


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
    masked_overlay = resized_overlay.with_mask(overlay_mask).with_duration(entry.duration)
    requested_position = entry.overlay_position or DEFAULT_OVERLAY_POSITION
    if requested_position is None:
        raise ValueError("Vertical presenter overlays require explicit overlay_position.")
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


def _render_segment_worker(
    index: int,
    entry: TimelineEntry,
    project_dir: Path,
    format_name: str,
    n_frames: int,
    seg_path: Path,
) -> Path:
    configure_output_format(format_name)

    if entry.type == "A_ROLL":
        if entry.treatment == "camera_motion":
            segment, handles = build_camera_motion_clip(project_dir, entry)
        else:
            segment, handles = build_standard_clip(project_dir, entry)
    elif entry.type == "B_ROLL":
        if entry.layout == "fullscreen" and entry.overlay_path:
            segment, handles = build_pip_clip(project_dir, entry)
        elif entry.layout == "fullscreen":
            if (entry.panels or [{}])[0].get("treatment") == "still_motion":
                segment, handles = build_still_motion_clip(project_dir, entry)
            else:
                segment, handles = build_standard_clip(project_dir, entry)
        elif entry.layout == "stack2":
            segment, handles = build_stack_2_clip(project_dir, entry)
        elif entry.layout == "stack3":
            segment, handles = build_stack_3_clip(project_dir, entry)
        elif entry.layout == "grid4":
            segment, handles = build_grid_4_clip(project_dir, entry)
        else:
            raise ValueError(f"Unsupported B_ROLL layout: {entry.layout}")
    else:
        raise ValueError(f"Unsupported timeline type: {entry.type}")

    segment, caption_handles = add_caption_overlay(segment, entry)
    adjusted_duration = n_frames / DEFAULT_FPS
    segment = segment.with_duration(adjusted_duration)

    segment.write_videofile(
        str(seg_path),
        fps=DEFAULT_FPS,
        codec=DEFAULT_CODEC,
        audio=False,
        logger=None,
    )
    close_all([segment, *handles, *caption_handles])
    return seg_path


def compose_video(
    project_dir: Path,
    timeline_path: Path,
    audio_path: Path,
    music_path: Path | None,
    output_path: Path,
    format_name: str = "landscape",
    max_workers: int = 4,
) -> Path:
    entries = load_timeline(timeline_path)
    ensure_file(audio_path, "Audio file")
    narration_probe = probe_audio_file(audio_path, "Audio file")
    music_probe = None
    if music_path is not None:
        ensure_file(music_path, "Music file")
        music_probe = probe_audio_file(music_path, "Music file")

    temp_dir = Path(tempfile.mkdtemp(prefix="compose_segments_"))
    segment_paths: list[Path] = []

    try:
        total_frames = round(entries[-1].end_time * DEFAULT_FPS)
        segment_frame_counts = [round(entry.duration * DEFAULT_FPS) for entry in entries]
        frame_diff = total_frames - sum(segment_frame_counts)
        if frame_diff != 0:
            segment_frame_counts[-1] += frame_diff

        workers = max(1, min(max_workers, len(entries)))
        seg_paths = [temp_dir / f"seg_{i:03d}.mp4" for i in range(len(entries))]
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for i, entry in enumerate(entries):
                future = executor.submit(
                    _render_segment_worker,
                    i, entry, project_dir, format_name,
                    segment_frame_counts[i], seg_paths[i],
                )
                futures[future] = i
            for future in concurrent.futures.as_completed(futures):
                future.result()
        segment_paths = seg_paths

        concat_list_path = temp_dir / "concat_list.txt"
        with concat_list_path.open("w", encoding="utf-8") as f:
            for j in range(len(segment_paths)):
                f.write(f"file 'seg_{j:03d}.mp4'\n")

        temp_concat_path = temp_dir / "concat.mp4"
        ffmpeg_bin = require_ffmpeg()
        run_ffmpeg([
            ffmpeg_bin, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            str(temp_concat_path),
        ])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        mix_mode = mux_with_processed_audio(temp_concat_path, audio_path, music_path, output_path, entries[-1].end_time)
        write_audio_mix_manifest(project_dir, output_path, entries[-1].end_time, narration_probe, music_probe, mix_mode)
        return output_path
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


def main() -> int:
    args = parse_args()
    configure_output_format(args.format)
    project_dir, timeline_path, audio_path, music_path, output_path = resolve_project_paths(args)
    gate_record = start_stage(project_dir, "creative_gate", command=["production_gate.py", "--project-dir", str(project_dir)])
    gate_findings = run_creative_gate(project_dir)
    gate_errors = [finding for finding in gate_findings if finding.severity == "ERROR"]
    if gate_errors:
        for finding in gate_findings:
            print(f"{finding.severity}: {finding.code}: {finding.message}", file=sys.stderr)
        end_stage(project_dir, gate_record, status="fail", return_code=1, metadata={"errors": len(gate_errors)})
        return 1
    end_stage(project_dir, gate_record, status="pass", return_code=0)

    ensure_file(timeline_path, "Timeline file")
    render_record = start_stage(
        project_dir,
        "base_render",
        command=["compose_video.py", "--format", args.format],
        metadata={"timeline": str(timeline_path), "output": str(output_path), "music": str(music_path) if music_path else None},
    )
    try:
        result = compose_video(project_dir, timeline_path, audio_path, music_path, output_path, format_name=args.format, max_workers=args.workers)
    except Exception as exc:
        end_stage(project_dir, render_record, status="error", error=str(exc))
        raise
    end_stage(project_dir, render_record, status="pass", return_code=0, metadata={"output": str(result)})
    print(f"Saved final video: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
