#!/usr/bin/env python3
"""Preflight and contract validation for the local YouTube autopipeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_VISUALS = {
    "landscape": {"A_ROLL", "B_ROLL", "PUNCH_IN", "TEXT_GRAPHIC", "PIP"},
    "vertical": {"A_ROLL", "B_ROLL", "PUNCH_IN", "TEXT", "TEXT_GRAPHIC", "PIP", "STACK_3"},
}
TIMELINE_TYPES = {"A-ROLL", "B-ROLL", "PIP", "TEXT", "STACK_3"}
LOOP_POLICIES = {"loop", "error"}
PRESENTER_TYPES = {"A-ROLL", "PIP"}
REQUIRED_SKILLS = (
    "youtube-scriptwriter",
    "tts",
    "latentsync",
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

    for collection_name, collection in (("broll_queries", broll_queries), ("graphics", graphics)):
        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                report.error(f"{collection_name}-shape", f"{collection_name}[{index}] must be an object")
                continue
            ref = item.get("segment_id")
            if ref not in segment_ids:
                report.error(f"{collection_name}-ref", f"{collection_name}[{index}] references unknown segment {ref!r}")


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


def validate_loop_policy(value: Any, report: Report, context: str) -> str:
    if value is None:
        return "loop"
    if value not in LOOP_POLICIES:
        report.error("loop-policy", f"{context} must be one of {sorted(LOOP_POLICIES)}")
        return "loop"
    return str(value)


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
        elif entry_type == "STACK_3":
            media_fields.append(("clip_path_top", "STACK_3 top", as_number(entry.get("clip_start_top")) or clip_start, loop_policy))
            media_fields.append(("clip_path_mid", "STACK_3 mid", as_number(entry.get("clip_start_mid")) or clip_start, loop_policy))
            media_fields.append(("clip_path_bot", "STACK_3 bot", as_number(entry.get("clip_start_bot")) or clip_start, loop_policy))

        for field, label, start_offset, policy in media_fields:
            path = resolve_path(project_dir, entry.get(field))
            if path is None:
                report.error("media-field", f"{context} missing {field}")
                continue
            if not path.exists() or not path.is_file():
                report.error("media-missing", f"{context} {label} not found: {path}")
                continue
            if start_offset < 0:
                report.error("clip-start", f"{context} {field} start offset must be non-negative")
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
    parser.add_argument("--audio", help="Path to final narration audio for duration validation.")
    parser.add_argument("--format", choices=("landscape", "vertical"), help="Expected output format.")
    parser.add_argument(
        "--mode",
        choices=("all", "preflight", "script", "timeline"),
        default="all",
        help="Validation scope.",
    )
    parser.add_argument("--require-pexels", action="store_true", help="Fail preflight if PEXELS_API_KEY is missing.")
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

    print_report(report, args.json)
    return 1 if report.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
