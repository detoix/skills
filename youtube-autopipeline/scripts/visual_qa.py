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


EXPECTED_FORMATS = {
    "vertical": {"width": 1080, "height": 1920, "ratio": "9:16"},
    "landscape": {"width": 1920, "height": 1080, "ratio": "16:9"},
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


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


def load_json_object(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def relative_media_ref(project_dir: Path, value: str) -> str:
    path = Path(value)
    resolved = path if path.is_absolute() else project_dir / path
    try:
        return str(resolved.resolve().relative_to(project_dir.resolve())).replace("/", "\\")
    except ValueError:
        return str(resolved.resolve())


def z_image_audit(project_dir: Path, timeline: list[dict[str, Any]], z_image_plan: dict[str, Any] | None) -> dict[str, Any]:
    generated_refs: set[str] = set()
    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        for field in ("clip_path", "background_path", "clip_path_top", "clip_path_mid", "clip_path_bot"):
            value = entry.get(field)
            if isinstance(value, str) and Path(value).suffix.lower() in IMAGE_EXTENSIONS:
                ref = relative_media_ref(project_dir, value)
                if "\\generated\\" in f"\\{ref}" or "z-image" in ref.lower():
                    generated_refs.add(ref)

    plan_items = {}
    if z_image_plan and isinstance(z_image_plan.get("items"), list):
        for item in z_image_plan["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("output"), str):
                continue
            plan_items[relative_media_ref(project_dir, item["output"])] = item

    missing_plan = []
    unreviewed = []
    rejected = []
    accepted = []
    for ref in sorted(generated_refs):
        item = plan_items.get(ref)
        if not item:
            missing_plan.append(ref)
            continue
        review = item.get("review") if isinstance(item.get("review"), dict) else {}
        if review.get("accepted") is True:
            accepted.append(ref)
        elif review.get("accepted") is False:
            rejected.append(ref)
        else:
            unreviewed.append(ref)

    return {
        "plan_present": z_image_plan is not None,
        "generated_refs_in_timeline": sorted(generated_refs),
        "accepted_refs": accepted,
        "missing_plan_refs": missing_plan,
        "unreviewed_refs": unreviewed,
        "rejected_refs": rejected,
    }


def timeline_asset_categories(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    categories: set[str] = set()
    media_refs: set[str] = set()
    type_counts: dict[str, int] = {}
    caption_entries = []
    pip_entries = []
    text_entries = []
    segment_durations = []

    for index, entry in enumerate(timeline):
        entry_type = str(entry.get("type", "UNKNOWN"))
        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
        start = float(entry.get("start_time", 0.0))
        end = float(entry.get("end_time", start))
        segment_durations.append({"index": index, "type": entry_type, "duration_seconds": round(end - start, 3)})

        for field in ("clip_path", "background_path", "overlay_path", "clip_path_top", "clip_path_mid", "clip_path_bot"):
            value = entry.get(field)
            if isinstance(value, str) and value:
                media_refs.add(value)

        if entry_type == "A-ROLL":
            categories.add("presenter_fullscreen")
        elif entry_type == "PIP":
            categories.update({"pip_presenter", "background_broll"})
            pip_entries.append(
                {
                    "index": index,
                    "overlay_path": entry.get("overlay_path"),
                    "overlay_scale": entry.get("overlay_scale"),
                    "overlay_position": entry.get("overlay_position"),
                    "shape_expected": "circle",
                    "crop_override": all(key in entry for key in ("overlay_crop_x", "overlay_crop_y")),
                }
            )
        elif entry_type == "B-ROLL":
            categories.add("fullscreen_broll")
        elif entry_type == "TEXT":
            categories.add("text_beat")
            text_value = str(entry.get("text", "")).strip()
            text_entries.append(
                {
                    "index": index,
                    "text": text_value,
                    "characters": len(text_value),
                    "background_path": entry.get("background_path"),
                }
            )
        elif entry_type == "STACK_3":
            categories.add("stacked_broll")

        caption = entry.get("caption_text")
        if isinstance(caption, str) and caption.strip():
            categories.add("captions")
            caption_entries.append(
                {
                    "index": index,
                    "text": caption.strip(),
                    "characters": len(caption.strip()),
                    "position": entry.get("caption_position") or "top",
                    "caption_y": entry.get("caption_y"),
                }
            )

    return {
        "type_counts": type_counts,
        "asset_categories_used": sorted(categories),
        "distinct_media_reference_count": len(media_refs),
        "caption_entries": caption_entries,
        "pip_entries": pip_entries,
        "text_entries": text_entries,
        "segment_durations": segment_durations,
    }


def tts_prefix_audit(tts_manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not tts_manifest:
        return {
            "manifest_present": False,
            "prompt_prefix_absent": None,
            "warnings": ["tts manifest not found; prefix absence could not be verified"],
            "chunks_checked": 0,
        }
    warnings = []
    chunks = tts_manifest.get("chunks")
    if not isinstance(chunks, list):
        return {
            "manifest_present": True,
            "prompt_prefix_absent": False,
            "warnings": ["tts manifest has no chunks array"],
            "chunks_checked": 0,
        }

    checked = 0
    prefix_absent = True
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        checked += 1
        if chunk.get("prompt_prefix_absent") is False or chunk.get("prefix_present") is True:
            prefix_absent = False
            warnings.append(f"{chunk.get('chunk_id', 'unknown')} reports prompt prefix contamination")
        trim_mode = chunk.get("trim_mode")
        if trim_mode == "manual_review":
            prefix_absent = False
            warnings.append(f"{chunk.get('chunk_id', 'unknown')} requires manual prefix review")
        if trim_mode not in {None, "target_only", "trimmed_prefix", "not_applicable"}:
            warnings.append(f"{chunk.get('chunk_id', 'unknown')} has unrecognized trim_mode {trim_mode!r}")

    return {
        "manifest_present": True,
        "prompt_prefix_absent": prefix_absent,
        "warnings": warnings,
        "chunks_checked": checked,
    }


def build_findings(
    metadata: dict[str, Any],
    frame_entries: list[dict[str, Any]],
    timeline_summary: dict[str, Any],
    prefix_audit: dict[str, Any],
    generated_audit: dict[str, Any],
    format_name: str | None,
    min_duration: float | None,
    max_duration: float | None,
    human_aesthetic_pass: bool,
    aesthetic_notes: str,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(severity: str, code: str, message: str) -> None:
        findings.append({"severity": severity, "code": code, "message": message})

    duration = float(metadata.get("duration_seconds") or 0.0)
    if min_duration is not None and duration + 0.05 < min_duration:
        add("ERROR", "duration-too-short", f"duration {duration:.2f}s is below minimum {min_duration:.2f}s")
    if max_duration is not None and duration - 0.05 > max_duration:
        add("ERROR", "duration-too-long", f"duration {duration:.2f}s is above maximum {max_duration:.2f}s")

    if format_name:
        expected = EXPECTED_FORMATS[format_name]
        if metadata.get("width") != expected["width"] or metadata.get("height") != expected["height"]:
            add(
                "ERROR",
                "resolution-mismatch",
                f"expected {expected['width']}x{expected['height']} {expected['ratio']}, got {metadata.get('width')}x{metadata.get('height')}",
            )

    categories = set(timeline_summary.get("asset_categories_used", []))
    if len(categories) < 4:
        add("WARN", "low-visual-variety", f"only {len(categories)} visual categories used: {sorted(categories)}")
    if timeline_summary.get("distinct_media_reference_count", 0) < 4:
        add("WARN", "low-asset-variety", "timeline uses fewer than four distinct media references")

    for item in timeline_summary.get("caption_entries", []):
        if item["characters"] > 64:
            add("WARN", "caption-long", f"caption at timeline[{item['index']}] has {item['characters']} characters")
        if item["position"] == "bottom":
            add("WARN", "caption-bottom", f"caption at timeline[{item['index']}] is in bottom band")
        caption_y = item.get("caption_y")
        if format_name == "vertical" and isinstance(caption_y, (int, float)):
            if caption_y < 192 or caption_y > 1152:
                add("WARN", "caption-safe-zone", f"caption at timeline[{item['index']}] is outside preferred vertical title-safe band")

    for item in timeline_summary.get("text_entries", []):
        if item["characters"] > 28:
            add("WARN", "text-beat-long", f"TEXT beat at timeline[{item['index']}] has {item['characters']} characters")

    for item in timeline_summary.get("pip_entries", []):
        if item.get("overlay_position") not in (["center", "bottom"], ("center", "bottom"), None):
            add("WARN", "pip-position", f"PIP at timeline[{item['index']}] is not centered bottom for vertical review")
        if item.get("overlay_scale") is None:
            add("WARN", "pip-scale", f"PIP at timeline[{item['index']}] relies on default overlay scale")

    for frame in frame_entries:
        for warning in frame.get("auto_checks", {}).get("warnings", []):
            add("ERROR", "frame-auto-check", f"{Path(frame['path']).name}: {warning}")

    if prefix_audit.get("prompt_prefix_absent") is False:
        add("ERROR", "tts-prefix", "tts manifest reports prompt prefix risk")
    elif prefix_audit.get("prompt_prefix_absent") is None:
        add("WARN", "tts-prefix-unverified", "tts prompt prefix absence was not verified")

    if not human_aesthetic_pass:
        add("ERROR", "aesthetic-review-required", "human/aesthetic QA pass is required before a reel can pass")
    if human_aesthetic_pass and len(aesthetic_notes.strip()) < 80:
        add("ERROR", "aesthetic-notes-missing", "human/aesthetic QA pass requires concrete notes, not a one-line approval")

    for ref in generated_audit.get("missing_plan_refs", []):
        add("ERROR", "generated-image-unplanned", f"generated timeline image has no z-image plan entry: {ref}")
    for ref in generated_audit.get("unreviewed_refs", []):
        add("ERROR", "generated-image-unreviewed", f"generated timeline image has not been reviewed: {ref}")
    for ref in generated_audit.get("rejected_refs", []):
        add("ERROR", "generated-image-rejected", f"timeline uses rejected generated image: {ref}")

    return findings


def write_markdown_report(
    output: Path,
    manifest: dict[str, Any],
    timeline_summary: dict[str, Any],
    prefix_audit: dict[str, Any],
    generated_audit: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    lines = [
        "# Reel QA Report",
        "",
        f"- Video: `{manifest['video']}`",
        f"- Duration: {manifest['metadata'].get('duration_seconds')}s",
        f"- Resolution: {manifest['metadata'].get('width')}x{manifest['metadata'].get('height')}",
        f"- Status: {manifest['status']}",
        f"- Contact sheet: `{manifest.get('contact_sheet')}`",
        "",
        "## Timeline",
        "",
        f"- Type counts: `{timeline_summary.get('type_counts')}`",
        f"- Asset categories used: `{', '.join(timeline_summary.get('asset_categories_used', []))}`",
        f"- Distinct media references: {timeline_summary.get('distinct_media_reference_count')}",
        f"- Captions checked: {len(timeline_summary.get('caption_entries', []))}",
        f"- PiP entries checked: {len(timeline_summary.get('pip_entries', []))}",
        f"- TEXT entries checked: {len(timeline_summary.get('text_entries', []))}",
        f"- Generated image refs: {len(generated_audit.get('generated_refs_in_timeline', []))}",
        "",
        "## TTS Prefix",
        "",
        f"- Manifest present: {prefix_audit.get('manifest_present')}",
        f"- Chunks checked: {prefix_audit.get('chunks_checked')}",
        f"- Prompt prefix absent: {prefix_audit.get('prompt_prefix_absent')}",
        f"- Human/aesthetic pass: {manifest.get('human_aesthetic_pass')}",
        f"- Aesthetic notes: {manifest.get('aesthetic_notes')}",
        "",
        "## Findings",
        "",
    ]
    if findings:
        for finding in findings:
            lines.append(f"- {finding['severity']}: {finding['code']}: {finding['message']}")
    else:
        lines.append("- No automated QA findings.")
    lines.extend(
        [
            "",
            "## Frame Coverage",
            "",
            f"- Frames extracted: {len(manifest.get('frames', []))}",
            f"- Manual acceptance required: {manifest.get('manual_acceptance_required')}",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser.add_argument("--format", choices=("vertical", "landscape"), help="Expected render format for resolution checks.")
    parser.add_argument("--min-duration", type=float, help="Minimum acceptable duration in seconds.")
    parser.add_argument("--max-duration", type=float, help="Maximum acceptable duration in seconds.")
    parser.add_argument("--tts-manifest", help="Optional TTS manifest path. Defaults to <project-dir>/manifests/tts-manifest.json")
    parser.add_argument("--z-image-plan", help="Optional z-image plan path. Defaults to <project-dir>/manifests/z-image-plan.json when present")
    parser.add_argument("--report-md", help="Optional Markdown QA report path.")
    parser.add_argument(
        "--human-aesthetic-pass",
        action="store_true",
        help="Mark the render as passing human/aesthetic review. Required for final pass status.",
    )
    parser.add_argument("--aesthetic-notes", default="", help="Concrete notes from manual visual/aesthetic review.")
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
    tts_manifest_path = Path(args.tts_manifest).resolve() if args.tts_manifest else project_dir / "manifests" / "tts-manifest.json"
    tts_manifest = load_json_object(tts_manifest_path)
    z_image_plan_path = Path(args.z_image_plan).resolve() if args.z_image_plan else project_dir / "manifests" / "z-image-plan.json"
    z_image_plan = load_json_object(z_image_plan_path)
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
    timeline_summary = timeline_asset_categories(timeline)
    prefix_audit = tts_prefix_audit(tts_manifest)
    generated_audit = z_image_audit(project_dir, timeline, z_image_plan)
    findings = build_findings(
        metadata,
        frame_entries,
        timeline_summary,
        prefix_audit,
        generated_audit,
        args.format,
        args.min_duration,
        args.max_duration,
        args.human_aesthetic_pass,
        args.aesthetic_notes,
    )
    computed_status = "fail" if any(item["severity"] == "ERROR" for item in findings) else "pass"
    final_status = "fail" if computed_status == "fail" else args.status
    manifest = {
        "video": str(video),
        "timeline": str(timeline_path) if timeline_path.exists() else None,
        "metadata": metadata,
        "status": final_status,
        "computed_status": computed_status,
        "notes": args.notes,
        "human_aesthetic_pass": args.human_aesthetic_pass,
        "aesthetic_notes": args.aesthetic_notes,
        "timeline_summary": timeline_summary,
        "tts_prefix_audit": prefix_audit,
        "generated_image_audit": generated_audit,
        "findings": findings,
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
    report_md = Path(args.report_md).resolve() if args.report_md else output.with_suffix(".md")
    write_markdown_report(report_md, manifest, timeline_summary, prefix_audit, generated_audit, findings)
    print(f"Wrote visual QA manifest: {output}")
    print(f"Wrote visual QA report: {report_md}")
    print(f"Extracted frames: {len(frame_entries)}")
    if sheet_path:
        print(f"Contact sheet: {sheet_path}")
    return 0 if final_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
