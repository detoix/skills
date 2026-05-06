#!/usr/bin/env python3
"""Preflight and contract validation for the local YouTube autopipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_VISUALS = {
    "landscape": {"A_ROLL", "B_ROLL", "PUNCH_IN", "TEXT_GRAPHIC", "PIP"},
    "vertical": {"A_ROLL", "B_ROLL", "PUNCH_IN", "TEXT", "TEXT_GRAPHIC", "PIP", "STACK_2", "STACK_3", "SPLIT_2", "GRID_4", "STILL_MOTION"},
}
TIMELINE_TYPES = {"A-ROLL", "B-ROLL", "PIP", "TEXT", "STACK_2", "STACK_3", "SPLIT_2", "GRID_4", "STILL_MOTION"}
LOOP_POLICIES = {"loop", "error"}
SPLIT_AXES = {"horizontal", "vertical"}
STILL_MOTION_TYPES = {"push-in", "pull-back", "pan-left", "pan-right", "pan-up", "pan-down", "diagonal-drift", "swipe-in"}
CAPTION_POSITIONS = {"top", "center", "bottom"}
PRESENTER_TYPES = {"A-ROLL", "PIP"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
BROLL_SOURCE_TYPES = {"webpage", "stock", "screen-record", "generated-image", "manual", "local-html", "motion-graphic", "animated-board"}
GRAPHIC_TARGETS = {"TEXT", "B_ROLL", "PIP", "manual"}
ASSEMBLY_RISKS = {"none", "fallback", "manual-review"}
SECTION_PATTERNS = {
    "fullscreen-stock",
    "fullscreen-manual",
    "fullscreen-webpage",
    "fullscreen-generated-motion",
    "pip-presenter-broll",
    "pip-presenter-screen",
    "split-presenter-demo",
    "split-comparison",
    "stack-2",
    "stack-3",
    "grid-4",
    "custom-html-capture",
    "animated-board-capture",
    "pip-presenter-over-animated-board",
    "receipt-highlight",
    "kinetic-text",
    "before-after",
    "this-vs-that",
    "myth-fact",
    "mistake-fix",
    "step-by-step",
    "checklist",
    "countdown",
    "map-path",
    "timeline",
    "zoomed-detail",
    "product-in-use",
    "reaction-reference",
    "seamless-loop",
}
REQUIRED_SKILLS = (
    "youtube-scriptwriter",
    "tts",
    "latentsync",
    "animated-broll-boards",
    "playwright-broll-recorder",
    "moviepy-video-composer",
)
OPTIONAL_SKILLS = ("codeformer-postprocess", "pexels-stock-downloader")


@dataclass
class Finding:
    severity: str
    code: str
    message: str


class Report:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def error(self, code: str, message: str) -> None:
        self.findings.append(Finding("ERROR", code, message))

    def warn(self, code: str, message: str) -> None:
        self.findings.append(Finding("WARN", code, message))

    def info(self, code: str, message: str) -> None:
        self.findings.append(Finding("INFO", code, message))

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "ERROR" for item in self.findings)


def load_json(path: Path, report: Report, label: str) -> Any | None:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        report.error("missing-file", f"{label} not found: {path}")
    except json.JSONDecodeError as exc:
        report.error("invalid-json", f"{label} is not valid JSON: {path} ({exc})")
    return None


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def require_keys(item: dict[str, Any], keys: tuple[str, ...], report: Report, context: str) -> None:
    for key in keys:
        if key not in item:
            report.error("missing-key", f"{context} is missing required key {key!r}")


def validate_script(script: Any, report: Report, format_mode: str | None = None) -> None:
    if not isinstance(script, dict):
        report.error("script-shape", "script JSON must be an object")
        return

    require_keys(
        script,
        ("metadata", "segments", "tts_chunks", "broll_queries", "graphics", "assembly_notes"),
        report,
        "script",
    )
    metadata = script.get("metadata")
    segments = script.get("segments")
    tts_chunks = script.get("tts_chunks")
    broll_queries = script.get("broll_queries")
    graphics = script.get("graphics")
    assembly_notes = script.get("assembly_notes")

    if not isinstance(metadata, dict):
        report.error("script-metadata", "metadata must be an object")
        return

    require_keys(
        metadata,
        (
            "topic",
            "target_audience",
            "tone",
            "language",
            "format_mode",
            "target_duration_seconds",
            "estimated_duration_seconds",
            "estimated_word_count",
            "pattern_interrupt_interval_seconds",
            "max_static_aroll_seconds",
        ),
        report,
        "metadata",
    )

    detected_format = metadata.get("format_mode")
    if detected_format not in SCRIPT_VISUALS:
        report.error("script-format", "metadata.format_mode must be 'landscape' or 'vertical'")
        detected_format = format_mode
    if format_mode and detected_format and format_mode != detected_format:
        report.error("format-mismatch", f"script format {detected_format!r} does not match requested {format_mode!r}")

    if not isinstance(segments, list) or not segments:
        report.error("script-segments", "segments must be a non-empty array")
        return
    if not isinstance(tts_chunks, list) or not tts_chunks:
        report.error("script-tts", "tts_chunks must be a non-empty array")
        tts_chunks = []
    if not isinstance(broll_queries, list):
        report.error("script-broll", "broll_queries must be an array")
        broll_queries = []
    if not isinstance(graphics, list):
        report.error("script-graphics", "graphics must be an array")
        graphics = []
    if not isinstance(assembly_notes, list):
        report.error("script-assembly-notes", "assembly_notes must be an array")

    previous_end = 0.0
    last_interrupt: float | None = None
    segment_ids: set[str] = set()
    allowed_visuals = SCRIPT_VISUALS.get(str(detected_format), SCRIPT_VISUALS["landscape"])

    for index, segment in enumerate(segments):
        context = f"segments[{index}]"
        if not isinstance(segment, dict):
            report.error("segment-shape", f"{context} must be an object")
            continue
        require_keys(
            segment,
            (
                "segment_id",
                "start_seconds",
                "end_seconds",
                "duration_seconds",
                "primary_visual",
                "pattern_interrupt",
                "pattern_interrupt_type",
                "narration",
                "on_screen_text",
                "visual_direction",
                "broll_search_query",
                "avatar_direction",
                "editor_notes",
            ),
            report,
            context,
        )

        segment_id = segment.get("segment_id")
        if isinstance(segment_id, str):
            if segment_id in segment_ids:
                report.error("duplicate-segment", f"duplicate segment_id {segment_id!r}")
            segment_ids.add(segment_id)
        else:
            report.error("segment-id", f"{context}.segment_id must be a string")

        start = as_number(segment.get("start_seconds"))
        end = as_number(segment.get("end_seconds"))
        duration = as_number(segment.get("duration_seconds"))
        if start is None or end is None or duration is None:
            report.error("segment-timing", f"{context} must include numeric start/end/duration")
            continue
        if end <= start:
            report.error("segment-duration", f"{context} has non-positive duration")
        if abs(start - previous_end) > 0.01:
            report.error("segment-sequence", f"{context}.start_seconds expected {previous_end}, got {start}")
        if abs((end - start) - duration) > 0.05:
            report.error("segment-duration", f"{context}.duration_seconds does not match end-start")
        previous_end = end

        visual = segment.get("primary_visual")
        if visual not in allowed_visuals:
            report.error("segment-visual", f"{context}.primary_visual {visual!r} is not allowed for {detected_format}")
        if visual == "A_ROLL" and duration > 20.0:
            report.error("aroll-too-long", f"{context} A_ROLL duration exceeds 20 seconds")

        if segment.get("pattern_interrupt") is True:
            if last_interrupt is not None and start - last_interrupt > 15.0:
                report.error("interrupt-gap", f"{context} starts {start - last_interrupt:.2f}s after previous interrupt")
            last_interrupt = start
        elif last_interrupt is None and start >= 15.0:
            report.error("interrupt-missing", f"{context} has no pattern interrupt in first 15 seconds")
        elif last_interrupt is not None and start - last_interrupt > 15.0:
            report.error("interrupt-gap", f"{context} exceeds 15 seconds since previous interrupt")

    for index, chunk in enumerate(tts_chunks):
        context = f"tts_chunks[{index}]"
        if not isinstance(chunk, dict):
            report.error("tts-shape", f"{context} must be an object")
            continue
        require_keys(chunk, ("chunk_id", "segment_ids", "voice_text", "delivery_style", "estimated_seconds"), report, context)
        if not isinstance(chunk.get("voice_text"), str) or not chunk.get("voice_text", "").strip():
            report.error("tts-empty", f"{context}.voice_text must be non-empty")
        refs = chunk.get("segment_ids")
        if not isinstance(refs, list) or not refs:
            report.error("tts-segments", f"{context}.segment_ids must be a non-empty array")
            continue
        for ref in refs:
            if ref not in segment_ids:
                report.error("tts-segment-ref", f"{context} references unknown segment {ref!r}")

    for index, item in enumerate(broll_queries):
        if not isinstance(item, dict):
            report.error("broll_queries-shape", f"broll_queries[{index}] must be an object")
            continue
        ref = item.get("segment_id")
        if ref not in segment_ids:
            report.error("broll_queries-ref", f"broll_queries[{index}] references unknown segment {ref!r}")
        require_keys(
            item,
            ("segment_id", "query", "source_type", "must_include", "avoid", "orientation_preference"),
            report,
            f"broll_queries[{index}]",
        )
        source_type = item.get("source_type")
        if source_type not in BROLL_SOURCE_TYPES:
            report.error(
                "broll-source-type",
                f"broll_queries[{index}].source_type must be one of {sorted(BROLL_SOURCE_TYPES)}",
            )
        if source_type == "generated-image" and detected_format == "vertical":
            orientation = item.get("orientation_preference")
            if orientation not in {"vertical", "either"}:
                report.warn("generated-orientation", f"broll_queries[{index}] generated image should prefer vertical or either")

    for index, item in enumerate(graphics):
        if not isinstance(item, dict):
            report.error("graphics-shape", f"graphics[{index}] must be an object")
            continue
        ref = item.get("segment_id")
        if ref not in segment_ids:
            report.error("graphics-ref", f"graphics[{index}] references unknown segment {ref!r}")
        require_keys(item, ("segment_id", "graphic_type", "copy", "composer_target"), report, f"graphics[{index}]")
        if item.get("composer_target") not in GRAPHIC_TARGETS:
            report.error("graphics-target", f"graphics[{index}].composer_target must be one of {sorted(GRAPHIC_TARGETS)}")

    for index, item in enumerate(assembly_notes):
        if not isinstance(item, dict):
            report.error("assembly-notes-shape", f"assembly_notes[{index}] must be an object")
            continue
        ref = item.get("segment_id")
        if ref not in segment_ids:
            report.error("assembly-notes-ref", f"assembly_notes[{index}] references unknown segment {ref!r}")
        require_keys(item, ("segment_id", "note", "risk"), report, f"assembly_notes[{index}]")
        if item.get("risk") not in ASSEMBLY_RISKS:
            report.error("assembly-risk", f"assembly_notes[{index}].risk must be one of {sorted(ASSEMBLY_RISKS)}")

    generated_refs = {
        item.get("segment_id")
        for item in broll_queries
        if isinstance(item, dict) and item.get("source_type") == "generated-image"
    }
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        if segment.get("primary_visual") in {"TEXT_GRAPHIC", "PUNCH_IN"}:
            segment_id = segment.get("segment_id")
            has_graphic = any(isinstance(item, dict) and item.get("segment_id") == segment_id for item in graphics)
            has_generated = segment_id in generated_refs
            if not has_graphic and not has_generated:
                report.warn(
                    "visual-plan-weak",
                    f"segments[{index}] {segment_id!r} uses {segment.get('primary_visual')} without graphics or generated-image plan",
                )


def resolve_path(project_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else project_dir / path


def find_ffprobe() -> str | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        candidate = Path(ffmpeg).with_name("ffprobe.exe")
        if candidate.exists():
            return str(candidate)
    local = Path.home() / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffprobe.exe"
    if local.exists():
        return str(local)
    return None


def media_duration(path: Path, report: Report) -> float | None:
    ffprobe = find_ffprobe()
    if not ffprobe:
        report.warn("ffprobe-missing", "ffprobe not found; media durations could not be checked")
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return float(completed.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as exc:
        report.warn("duration-unavailable", f"could not read duration for {path}: {exc}")
        return None


def probe_audio(path: Path, report: Report) -> dict[str, Any] | None:
    ffprobe = find_ffprobe()
    if not ffprobe:
        report.warn("ffprobe-missing", "ffprobe not found; audio streams could not be checked")
        return None
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
        report.warn("audio-probe-unavailable", f"could not probe audio for {path}: {exc}")
        return None
    audio_stream = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"), None)
    if not audio_stream:
        report.error("audio-stream-missing", f"no audio stream found in {path}")
        return None
    fmt = data.get("format") or {}
    try:
        duration = float(fmt.get("duration") or audio_stream.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration_seconds": duration,
        "codec": audio_stream.get("codec_name"),
        "sample_rate": int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
        "channels": int(audio_stream.get("channels") or 0),
    }


def validate_loop_policy(value: Any, report: Report, context: str) -> str:
    if value is None:
        return "loop"
    if value not in LOOP_POLICIES:
        report.error("loop-policy", f"{context} must be one of {sorted(LOOP_POLICIES)}")
        return "loop"
    return str(value)


def path_looks_like_presenter(path: Path) -> bool:
    lowered = str(path).lower()
    return any(marker in lowered for marker in ("synced", "presenter", "avatar", "profile", "a-roll", "aroll"))


def validate_timeline(timeline: Any, project_dir: Path, report: Report, audio_path: Path | None = None) -> None:
    if not isinstance(timeline, list) or not timeline:
        report.error("timeline-shape", "timeline must be a non-empty JSON array")
        return

    previous_end = 0.0
    final_end = 0.0
    for index, entry in enumerate(timeline):
        context = f"timeline[{index}]"
        if not isinstance(entry, dict):
            report.error("timeline-entry", f"{context} must be an object")
            continue
        entry_type = entry.get("type")
        if entry_type not in TIMELINE_TYPES:
            report.error("timeline-type", f"{context}.type {entry_type!r} is unsupported")
            continue
        start = as_number(entry.get("start_time"))
        end = as_number(entry.get("end_time"))
        if start is None or end is None:
            report.error("timeline-timing", f"{context} must include numeric start_time and end_time")
            continue
        if end <= start:
            report.error("timeline-duration", f"{context} has non-positive duration")
            continue
        if abs(start - previous_end) > 0.01:
            report.error("timeline-sequence", f"{context}.start_time expected {previous_end}, got {start}")
        previous_end = end
        final_end = end
        duration = end - start

        loop_policy = validate_loop_policy(entry.get("loop_policy"), report, f"{context}.loop_policy")
        background_loop = validate_loop_policy(
            entry.get("background_loop_policy", loop_policy), report, f"{context}.background_loop_policy"
        )
        overlay_loop = validate_loop_policy(
            entry.get("overlay_loop_policy", loop_policy), report, f"{context}.overlay_loop_policy"
        )

        media_fields: list[tuple[str, str, float, str]] = []
        clip_start = as_number(entry.get("clip_start")) or 0.0
        if entry_type in {"A-ROLL", "B-ROLL"}:
            media_fields.append(("clip_path", "primary clip", clip_start, loop_policy))
        elif entry_type == "PIP":
            background_start = as_number(entry.get("background_clip_start"))
            overlay_start = as_number(entry.get("overlay_clip_start"))
            media_fields.append(("background_path", "PIP background", background_start if background_start is not None else clip_start, background_loop))
            media_fields.append(("overlay_path", "PIP overlay", overlay_start if overlay_start is not None else clip_start, overlay_loop))
        elif entry_type == "TEXT":
            media_fields.append(("background_path", "TEXT background", clip_start, background_loop))
            if not isinstance(entry.get("text"), str) or not entry.get("text", "").strip():
                report.error("text-empty", f"{context}.text must be non-empty")
        elif entry_type == "STACK_2":
            media_fields.append(("clip_path_top", "STACK_2 top", as_number(entry.get("clip_start_top")) or clip_start, loop_policy))
            media_fields.append(("clip_path_bot", "STACK_2 bottom", as_number(entry.get("clip_start_bot")) or clip_start, loop_policy))
        elif entry_type == "STACK_3":
            media_fields.append(("clip_path_top", "STACK_3 top", as_number(entry.get("clip_start_top")) or clip_start, loop_policy))
            media_fields.append(("clip_path_mid", "STACK_3 mid", as_number(entry.get("clip_start_mid")) or clip_start, loop_policy))
            media_fields.append(("clip_path_bot", "STACK_3 bot", as_number(entry.get("clip_start_bot")) or clip_start, loop_policy))
        elif entry_type == "SPLIT_2":
            if entry.get("split_axis", "vertical") not in SPLIT_AXES:
                report.error("split-axis", f"{context}.split_axis must be one of {sorted(SPLIT_AXES)}")
            media_fields.append(("clip_path_a", "SPLIT_2 panel A", as_number(entry.get("clip_start_a")) or clip_start, loop_policy))
            media_fields.append(("clip_path_b", "SPLIT_2 panel B", as_number(entry.get("clip_start_b")) or clip_start, loop_policy))
        elif entry_type == "GRID_4":
            media_fields.append(("clip_path_1", "GRID_4 clip 1", as_number(entry.get("clip_start_1")) or clip_start, loop_policy))
            media_fields.append(("clip_path_2", "GRID_4 clip 2", as_number(entry.get("clip_start_2")) or clip_start, loop_policy))
            media_fields.append(("clip_path_3", "GRID_4 clip 3", as_number(entry.get("clip_start_3")) or clip_start, loop_policy))
            media_fields.append(("clip_path_4", "GRID_4 clip 4", as_number(entry.get("clip_start_4")) or clip_start, loop_policy))
        elif entry_type == "STILL_MOTION":
            if entry.get("motion_type", "push-in") not in STILL_MOTION_TYPES:
                report.error("still-motion-type", f"{context}.motion_type must be one of {sorted(STILL_MOTION_TYPES)}")
            media_fields.append(("clip_path", "STILL_MOTION clip", clip_start, loop_policy))

        caption = entry.get("caption_text")
        if caption is not None:
            if not isinstance(caption, str) or not caption.strip():
                report.error("caption-empty", f"{context}.caption_text must be non-empty when provided")
            elif len(caption.strip()) > 84:
                report.warn("caption-long", f"{context}.caption_text is long; keep captions short enough for phone viewing")
            position = entry.get("caption_position")
            if position is not None and position not in CAPTION_POSITIONS:
                report.error("caption-position", f"{context}.caption_position must be one of {sorted(CAPTION_POSITIONS)}")
            caption_y = as_number(entry.get("caption_y"))
            if "caption_y" in entry and caption_y is None:
                report.error("caption-y", f"{context}.caption_y must be numeric when provided")
            elif caption_y is not None and caption_y < 0:
                report.error("caption-y", f"{context}.caption_y must be non-negative")

        for field, label, start_offset, policy in media_fields:
            path = resolve_path(project_dir, entry.get(field))
            if path is None:
                report.error("media-field", f"{context} missing {field}")
                continue
            if not path.exists() or not path.is_file():
                report.error("media-missing", f"{context} {label} not found: {path}")
                continue
            if path_looks_like_presenter(path) and policy != "error":
                report.error("presenter-loop-policy", f"{context} {field} looks like presenter media and must use loop_policy/error")
            if start_offset < 0:
                report.error("clip-start", f"{context} {field} start offset must be non-negative")
                continue
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                if start_offset:
                    report.error("clip-start", f"{context} {field} is a still image and cannot use clip_start")
                continue
            source_duration = media_duration(path, report)
            if source_duration is None:
                continue
            available = source_duration - start_offset
            if available <= 0:
                report.error("clip-start", f"{context} {field} start offset exceeds source duration")
            elif available + 0.05 < duration:
                if policy == "error" or (entry_type in PRESENTER_TYPES and field in {"clip_path", "overlay_path"}):
                    report.error(
                        "clip-too-short",
                        f"{context} {field} has {available:.2f}s available for {duration:.2f}s segment",
                    )
                else:
                    report.warn(
                        "clip-will-loop",
                        f"{context} {field} has {available:.2f}s available for {duration:.2f}s segment and will loop",
                    )

    if audio_path:
        if not audio_path.exists() or not audio_path.is_file():
            report.error("audio-missing", f"audio file not found: {audio_path}")
        else:
            duration = media_duration(audio_path, report)
            if duration is not None and duration + 0.1 < final_end:
                report.error("audio-too-short", f"audio is {duration:.2f}s but timeline ends at {final_end:.2f}s")
            elif duration is not None and duration - final_end > 1.0:
                report.warn("audio-extra", f"audio is {duration:.2f}s but timeline ends at {final_end:.2f}s")


def env_file_has_key(path: Path, key: str) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{key}=") and stripped.split("=", 1)[1].strip():
                return True
    except OSError:
        return False
    return False


def run_python_import(python_exe: Path, module: str) -> bool:
    if not python_exe.exists():
        return False
    command = [str(python_exe), "-c", f"import {module}"]
    return subprocess.run(command, capture_output=True, text=True).returncode == 0


def preflight(project_dir: Path, report: Report, require_pexels: bool) -> None:
    skills_root = Path(__file__).resolve().parents[2]
    for name in REQUIRED_SKILLS:
        path = skills_root / name / "SKILL.md"
        if path.exists():
            report.info("skill-found", f"{name}: {path}")
        else:
            report.error("skill-missing", f"required skill missing: {path}")
    for name in OPTIONAL_SKILLS:
        path = skills_root / name / "SKILL.md"
        if path.exists():
            report.info("skill-found", f"{name}: {path}")
        else:
            report.warn("skill-missing", f"optional skill missing: {path}")

    ffmpeg_dir = Path.home() / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
    ffmpeg = shutil.which("ffmpeg") or str(ffmpeg_dir / "ffmpeg.exe")
    if Path(ffmpeg).exists():
        report.info("ffmpeg-found", f"ffmpeg: {ffmpeg}")
    else:
        report.error("ffmpeg-missing", f"ffmpeg not found; expected {ffmpeg_dir}")

    tts_python = Path.home() / "Downloads" / "speech-gen" / "venv" / "Scripts" / "python.exe"
    if tts_python.exists():
        report.info("tts-env-found", f"TTS Python: {tts_python}")
    else:
        report.error("tts-env-missing", f"TTS environment missing: {tts_python}")

    composer_python = skills_root / "moviepy-video-composer" / ".venv" / "Scripts" / "python.exe"
    if run_python_import(composer_python, "moviepy"):
        report.info("composer-ok", f"moviepy import works in {composer_python}")
    else:
        report.error("composer-import", f"moviepy import failed in {composer_python}")

    latentsync_root = os.environ.get("LATENTSYNC_ROOT")
    candidates = []
    if latentsync_root:
        candidates.append(Path(latentsync_root))
    candidates.extend(
        (
            project_dir / "official-latentsync",
            Path.home() / "Downloads" / "official-latentsync",
            Path.home() / "Downloads" / "speech-gen" / "official-latentsync",
        )
    )
    latent_root = next((path for path in candidates if (path / ".venv" / "Scripts" / "python.exe").exists()), None)
    if latent_root:
        checkpoint = latent_root / "checkpoints" / "latentsync_unet.pt"
        if checkpoint.exists():
            report.info("latentsync-ok", f"LatentSync root: {latent_root}")
        else:
            report.error("latentsync-checkpoint", f"LatentSync checkpoint missing: {checkpoint}")
    else:
        report.error("latentsync-missing", "LatentSync runtime missing; set LATENTSYNC_ROOT or place official-latentsync in the project")

    if require_pexels:
        api_key_present = bool(os.environ.get("PEXELS_API_KEY"))
        api_key_present = api_key_present or env_file_has_key(skills_root / "pexels-stock-downloader" / ".env", "PEXELS_API_KEY")
        api_key_present = api_key_present or env_file_has_key(project_dir / ".env", "PEXELS_API_KEY")
        if api_key_present:
            report.info("pexels-ok", "PEXELS_API_KEY is configured")
        else:
            report.error("pexels-key", "PEXELS_API_KEY missing")


def validate_asset_manifest(manifest: Any, report: Report, format_mode: str | None, allow_test_input: bool) -> None:
    if not isinstance(manifest, dict):
        report.error("asset-manifest-shape", "asset manifest must be an object")
        return
    asset_set_type = manifest.get("asset_set_type")
    if asset_set_type == "test_input" and not allow_test_input:
        report.error(
            "test-input-assets",
            "asset manifest is marked test_input; production runs require user-provided assets",
        )
    groups = manifest.get("groups")
    if not isinstance(groups, dict):
        report.error("asset-groups", "asset manifest must include grouped asset categories")
        return

    presenter_plates = groups.get("usable_presenter_plates")
    voice_samples = groups.get("voice_samples")
    transcripts = groups.get("transcripts")
    if not isinstance(presenter_plates, list) or not presenter_plates:
        report.error("asset-presenter", "no usable presenter plates found")
    if not isinstance(voice_samples, list) or not voice_samples:
        report.error("asset-voice", "no voice sample found")
    if not isinstance(transcripts, list) or not transcripts:
        report.error("asset-transcript", "no voice sample transcript found")

    if isinstance(presenter_plates, list) and format_mode == "vertical":
        portrait_front = [
            item
            for item in presenter_plates
            if isinstance(item, dict)
            and item.get("role") == "presenter_front"
            and item.get("orientation") == "portrait"
        ]
        if not portrait_front:
            report.warn("asset-front-portrait", "no portrait front presenter plate found for vertical mode")
    if isinstance(presenter_plates, list) and format_mode == "landscape":
        landscape_front = [
            item
            for item in presenter_plates
            if isinstance(item, dict)
            and item.get("role") == "presenter_front"
            and item.get("orientation") == "landscape"
        ]
        landscape_profile = [
            item
            for item in presenter_plates
            if isinstance(item, dict)
            and item.get("role") == "presenter_profile"
            and item.get("orientation") == "landscape"
        ]
        if not landscape_front:
            report.error("asset-front-landscape", "landscape mode requires a landscape front presenter plate")
        if not landscape_profile:
            report.error("asset-profile-landscape", "landscape mode requires a landscape profile presenter plate")


def validate_music_manifest(manifest: Any, project_dir: Path, report: Report) -> None:
    if not isinstance(manifest, dict):
        report.error("music-manifest-shape", "music manifest must be an object")
        return
    enabled = manifest.get("enabled")
    if not isinstance(enabled, bool):
        report.error("music-enabled", "music manifest enabled must be true or false")
        return
    if enabled is False:
        return

    require_keys(
        manifest,
        (
            "original_path",
            "project_path",
            "sha256",
            "duration_seconds",
            "codec",
            "sample_rate",
            "channels",
            "size_bytes",
        ),
        report,
        "music manifest",
    )
    project_path = resolve_path(project_dir, manifest.get("project_path"))
    if project_path is None:
        report.error("music-path", "music manifest project_path must be non-empty")
        return
    if project_path.suffix.lower() not in AUDIO_EXTENSIONS:
        report.error("music-extension", f"music file extension must be one of {sorted(AUDIO_EXTENSIONS)}")
    if not project_path.exists() or not project_path.is_file():
        report.error("music-missing", f"music file not found: {project_path}")
        return

    duration = as_number(manifest.get("duration_seconds"))
    if duration is None or duration <= 0:
        report.error("music-duration", "music manifest duration_seconds must be positive")
    channels = as_number(manifest.get("channels"))
    if channels is None or channels <= 0:
        report.error("music-channels", "music manifest channels must be positive")
    sample_rate = as_number(manifest.get("sample_rate"))
    if sample_rate is None or sample_rate <= 0:
        report.error("music-sample-rate", "music manifest sample_rate must be positive")
    if not isinstance(manifest.get("sha256"), str) or len(manifest.get("sha256", "")) != 64:
        report.error("music-sha256", "music manifest sha256 must be a 64-character hex digest")

    probe = probe_audio(project_path, report)
    if probe and probe["duration_seconds"] <= 0:
        report.error("music-duration", f"music file has non-positive probed duration: {project_path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_sha(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if len(lowered) == 64 and all(char in "0123456789abcdef" for char in lowered):
        return lowered
    return None


def validate_presenter_plan(manifest: Any, project_dir: Path, report: Report) -> None:
    if not isinstance(manifest, dict):
        report.error("presenter-plan-shape", "presenter plan must be an object")
        return
    assignments = manifest.get("assignments")
    if not isinstance(assignments, list):
        report.error("presenter-plan-assignments", "presenter plan must include assignments array")
        return

    repeated_decisions = manifest.get("repeat_decisions", [])
    if repeated_decisions is None:
        repeated_decisions = []
    if not isinstance(repeated_decisions, list):
        report.error("presenter-repeat-decisions", "presenter plan repeat_decisions must be an array when present")
        repeated_decisions = []
    decisions_by_sha: dict[str, dict[str, Any]] = {}
    for index, decision in enumerate(repeated_decisions):
        context = f"repeat_decisions[{index}]"
        if not isinstance(decision, dict):
            report.error("presenter-repeat-decision-shape", f"{context} must be an object")
            continue
        sha = normalize_sha(decision.get("sha256"))
        if sha is None:
            report.error("presenter-repeat-decision-sha", f"{context}.sha256 must be a 64-character hex digest")
            continue
        decisions_by_sha[sha] = decision

    uses_by_sha: dict[str, list[dict[str, Any]]] = {}
    for index, assignment in enumerate(assignments):
        context = f"assignments[{index}]"
        if not isinstance(assignment, dict):
            report.error("presenter-assignment-shape", f"{context} must be an object")
            continue
        source = assignment.get("source")
        if not isinstance(source, str) or not source.strip():
            report.error("presenter-assignment-source", f"{context}.source must be a non-empty path")
            continue
        source_path = resolve_path(project_dir, source)
        if source_path is None or not source_path.exists() or not source_path.is_file():
            report.error("presenter-assignment-missing", f"{context}.source not found: {source}")
            continue
        sha = normalize_sha(assignment.get("sha256")) or sha256_file(source_path)
        uses_by_sha.setdefault(sha, []).append(
            {
                "index": index,
                "source": source,
                "chunk_id": assignment.get("chunk_id"),
                "segment_id": assignment.get("segment_id"),
            }
        )

    for sha, uses in sorted(uses_by_sha.items()):
        if len(uses) <= 1:
            continue
        decision = decisions_by_sha.get(sha)
        if not decision:
            used = ", ".join(str(use.get("source")) for use in uses)
            report.error(
                "presenter-repeat-undecided",
                f"presenter source sha256 {sha} is used {len(uses)} times without repeat_decisions entry; sources: {used}",
            )
            continue
        reason = str(decision.get("reason", "")).strip()
        if len(reason) < 20:
            report.error("presenter-repeat-reason", f"repeat_decisions entry for sha256 {sha} needs a concrete reason")
        selected_uses = decision.get("uses")
        if not isinstance(selected_uses, list) or len(selected_uses) < len(uses):
            report.warn(
                "presenter-repeat-uses",
                f"repeat_decisions entry for sha256 {sha} should list all repeated uses for review",
            )

def validate_selected_visuals_manifest(manifest: Any, report: Report) -> None:
    if not isinstance(manifest, dict):
        report.error("selected-visuals-shape", "selected visuals manifest must be an object")
        return
    items = manifest.get("items")
    if not isinstance(items, list):
        report.error("selected-visuals-items", "selected visuals manifest must include an items array")
        return
    accepted_patterns: set[str] = set()
    accepted_canonicals: dict[str, int] = {}
    source_type_durations: dict[str, float] = {}
    accepted_source_types: set[str] = set()
    for index, item in enumerate(items):
        context = f"selected_visuals.items[{index}]"
        if not isinstance(item, dict):
            report.error("selected-visuals-item", f"{context} must be an object")
            continue
        require_keys(item, ("segment_id", "section_pattern", "source_type", "canonical_id", "accepted", "reason", "risk"), report, context)
        pattern = item.get("section_pattern")
        source_type = item.get("source_type")
        canonical_id = item.get("canonical_id")
        if pattern not in SECTION_PATTERNS:
            report.error("section-pattern", f"{context}.section_pattern must be one of {sorted(SECTION_PATTERNS)}")
        if source_type not in BROLL_SOURCE_TYPES:
            report.error("visual-source-type", f"{context}.source_type must be one of {sorted(BROLL_SOURCE_TYPES)}")
        if not isinstance(canonical_id, str) or not canonical_id.strip():
            report.error("canonical-id", f"{context}.canonical_id must be non-empty")
        if source_type == "animated-board":
            for field in ("creative_concept", "visual_metaphor", "motion_summary"):
                if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                    report.error("animated-board-creative-metadata", f"{context}.{field} is required for animated-board visuals")
            concept = str(item.get("creative_concept", "")).strip().lower()
            if concept in {"checklist", "timeline", "process-flow", "bar-comparison", "risk-matrix", "myth-fact", "template"}:
                report.error(
                    "animated-board-template-concept",
                    f"{context}.creative_concept must describe a custom visual metaphor, not a template type",
                )
        if item.get("accepted") is True:
            accepted_patterns.add(str(pattern))
            if isinstance(source_type, str) and source_type in BROLL_SOURCE_TYPES:
                accepted_source_types.add(source_type)
            if isinstance(canonical_id, str) and canonical_id:
                accepted_canonicals[canonical_id] = accepted_canonicals.get(canonical_id, 0) + 1
            duration = as_number(item.get("duration_seconds"))
            if duration is None:
                report.error("visual-duration", f"{context}.duration_seconds is required for accepted visuals")
            elif duration <= 0:
                report.error("visual-duration", f"{context}.duration_seconds must be positive")
            elif isinstance(source_type, str) and source_type in BROLL_SOURCE_TYPES:
                source_type_durations[source_type] = source_type_durations.get(source_type, 0.0) + duration
            if not str(item.get("reason", "")).strip():
                report.error("visual-reason", f"{context}.reason must explain why the visual fits")

    reuse_decisions = manifest.get("reuse_decisions", [])
    if reuse_decisions is None:
        reuse_decisions = []
    if not isinstance(reuse_decisions, list):
        report.error("visual-reuse-decisions", "selected visuals reuse_decisions must be an array when present")
        reuse_decisions = []
    reuse_by_id: dict[str, dict[str, Any]] = {}
    for index, decision in enumerate(reuse_decisions):
        context = f"reuse_decisions[{index}]"
        if not isinstance(decision, dict):
            report.error("visual-reuse-decision-shape", f"{context} must be an object")
            continue
        canonical_id = decision.get("canonical_id")
        if not isinstance(canonical_id, str) or not canonical_id.strip():
            report.error("visual-reuse-decision-id", f"{context}.canonical_id must be non-empty")
            continue
        reuse_by_id[canonical_id] = decision

    repeated = sorted(key for key, count in accepted_canonicals.items() if count > 2)
    for canonical_id in repeated:
        decision = reuse_by_id.get(canonical_id)
        if not decision:
            report.error(
                "visual-reuse-undecided",
                f"accepted selected visuals reuse canonical_id {canonical_id!r} more than twice without reuse_decisions entry",
            )
            continue
        if len(str(decision.get("reason", "")).strip()) < 20:
            report.error("visual-reuse-reason", f"reuse_decisions entry for {canonical_id!r} needs a concrete reason")

    broll_duration = sum(source_type_durations.values())
    if broll_duration > 0:
        required_source_types = int(math.ceil(broll_duration / 20.0))
        if len(accepted_source_types) < required_source_types:
            report.error(
                "low-source-type-variety",
                f"selected visuals use {len(accepted_source_types)} source_type values for {broll_duration:.2f}s of B-roll; "
                f"required at least {required_source_types} (one per started 20 seconds)",
            )
    target_duration = as_number(manifest.get("target_duration_seconds"))
    creative_reason = str(manifest.get("single_pattern_reason", "")).strip()
    if target_duration is not None and target_duration > 45 and len(accepted_patterns) < 3 and not creative_reason:
        report.error(
            "low-section-variety",
            "selected visuals for reels over 45 seconds require at least three section patterns or single_pattern_reason",
        )


def validate_z_image_plan(plan: Any, report: Report, require_review: bool) -> None:
    if not isinstance(plan, dict):
        report.error("z-image-plan-shape", "z-image plan must be an object")
        return
    if plan.get("source") != "z-image-turbo":
        report.error("z-image-source", "z-image plan source must be z-image-turbo")
    items = plan.get("items")
    if not isinstance(items, list):
        report.error("z-image-items", "z-image plan must include an items array")
        return
    if not items:
        report.warn("z-image-empty", "z-image plan contains no candidate images")
    for index, item in enumerate(items):
        context = f"z-image.items[{index}]"
        if not isinstance(item, dict):
            report.error("z-image-item-shape", f"{context} must be an object")
            continue
        require_keys(item, ("segment_id", "prompt", "output", "status", "review", "command"), report, context)
        prompt = item.get("prompt")
        if not isinstance(prompt, str) or len(prompt.strip()) < 40:
            report.error("z-image-prompt", f"{context}.prompt is missing or too weak")
        output = item.get("output")
        if not isinstance(output, str) or not output:
            report.error("z-image-output", f"{context}.output must be a non-empty path")
        elif Path(output).suffix.lower() not in IMAGE_EXTENSIONS:
            report.error("z-image-output", f"{context}.output must be an image path")
        review = item.get("review")
        if not isinstance(review, dict):
            report.error("z-image-review", f"{context}.review must be an object")
            continue
        accepted = review.get("accepted")
        if require_review and accepted is None:
            report.error("z-image-review-required", f"{context} has not been reviewed")
        if accepted is True and not str(review.get("notes", "")).strip():
            report.error("z-image-review-notes", f"{context} accepted image requires review notes")
        if accepted is False and not str(review.get("rejection_reason", "")).strip():
            report.error("z-image-rejection-reason", f"{context} rejected image requires a rejection reason")


def print_report(report: Report, json_output: bool) -> None:
    if json_output:
        print(json.dumps([item.__dict__ for item in report.findings], indent=2))
        return
    for item in report.findings:
        print(f"{item.severity}: {item.code}: {item.message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local YouTube autopipeline preflight and JSON contracts.")
    parser.add_argument("--project-dir", default=".", help="Project directory for relative timeline/media paths.")
    parser.add_argument("--script", help="Path to script.json to validate.")
    parser.add_argument("--timeline", help="Path to timeline.json to validate.")
    parser.add_argument("--asset-manifest", help="Path to assets-manifest.json to validate.")
    parser.add_argument("--music-manifest", help="Path to music-manifest.json to validate.")
    parser.add_argument("--presenter-plan", help="Path to presenter-plan.json to validate.")
    parser.add_argument("--selected-visuals", help="Path to selected-visuals manifest to validate.")
    parser.add_argument("--z-image-plan", help="Path to z-image-plan.json to validate.")
    parser.add_argument("--audio", help="Path to final narration audio for duration validation.")
    parser.add_argument("--format", choices=("landscape", "vertical"), help="Expected output format.")
    parser.add_argument(
        "--mode",
        choices=("all", "preflight", "script", "timeline", "assets"),
        default="all",
        help="Validation scope.",
    )
    parser.add_argument("--require-pexels", action="store_true", help="Fail preflight if PEXELS_API_KEY is missing.")
    parser.add_argument(
        "--allow-test-input",
        action="store_true",
        help="Allow asset manifests marked as test_input. Use only for tests, never production runs.",
    )
    parser.add_argument("--require-z-image-review", action="store_true", help="Fail if z-image candidates lack review status.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = Report()
    project_dir = Path(args.project_dir).resolve()

    if args.mode in {"all", "preflight"}:
        preflight(project_dir, report, args.require_pexels)

    if args.mode in {"all", "script"}:
        script_path = Path(args.script).resolve() if args.script else project_dir / "script.json"
        script = load_json(script_path, report, "script")
        if script is not None:
            validate_script(script, report, args.format)

    if args.mode in {"all", "timeline"}:
        timeline_path = Path(args.timeline).resolve() if args.timeline else project_dir / "timeline.json"
        timeline = load_json(timeline_path, report, "timeline")
        audio_path = Path(args.audio).resolve() if args.audio else None
        if timeline is not None:
            validate_timeline(timeline, project_dir, report, audio_path)

    asset_manifest_path = Path(args.asset_manifest).resolve() if args.asset_manifest else None
    if asset_manifest_path and args.mode in {"all", "preflight", "assets"}:
        manifest = load_json(asset_manifest_path, report, "asset manifest")
        if manifest is not None:
            validate_asset_manifest(manifest, report, args.format, args.allow_test_input)

    music_manifest_path = Path(args.music_manifest).resolve() if args.music_manifest else None
    if music_manifest_path and args.mode in {"all", "preflight", "assets"}:
        manifest = load_json(music_manifest_path, report, "music manifest")
        if manifest is not None:
            validate_music_manifest(manifest, project_dir, report)

    presenter_plan_path = Path(args.presenter_plan).resolve() if args.presenter_plan else None
    if presenter_plan_path and args.mode in {"all", "preflight", "assets"}:
        manifest = load_json(presenter_plan_path, report, "presenter plan")
        if manifest is not None:
            validate_presenter_plan(manifest, project_dir, report)

    selected_visuals_path = Path(args.selected_visuals).resolve() if args.selected_visuals else None
    if selected_visuals_path and args.mode in {"all", "preflight", "assets"}:
        manifest = load_json(selected_visuals_path, report, "selected visuals manifest")
        if manifest is not None:
            validate_selected_visuals_manifest(manifest, report)

    z_image_plan_path = Path(args.z_image_plan).resolve() if args.z_image_plan else None
    if z_image_plan_path and args.mode in {"all", "preflight", "assets"}:
        plan = load_json(z_image_plan_path, report, "z-image plan")
        if plan is not None:
            validate_z_image_plan(plan, report, args.require_z_image_review)

    print_report(report, args.json)
    return 1 if report.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
