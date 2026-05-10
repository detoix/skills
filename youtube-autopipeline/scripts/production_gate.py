#!/usr/bin/env python3
"""Hard production gates for the local YouTube autopipeline."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_SOURCE_STRATEGIES = {
    "stock",
    "manual",
    "generated-image",
    "webpage",
    "screen-record",
    "synthetic-motion",
}
SEGMENT_TYPES = {"A_ROLL", "B_ROLL"}
LEGACY_TOP_LEVEL_TYPES = {"A-ROLL", "B-ROLL", "PIP", "TEXT", "TEXT_GRAPHIC", "STACK_2", "STACK_3", "SPLIT_2", "GRID_4", "STILL_MOTION", "PUNCH_IN"}
BROLL_LAYOUTS = {"fullscreen", "stack2", "stack3", "grid4"}
BROLL_LAYOUT_PANEL_COUNTS = {"stack2": 2, "stack3": 3, "grid4": 4}
PANEL_KINDS = {"broll", "presenter"}
BROLL_PRESENTER_PANEL_TARGET_RATIO = 0.5
BROLL_PRESENTER_PANEL_MIN_RATIO = 0.4
BROLL_PRESENTER_PANEL_MAX_RATIO = 0.7
SCRIPT_RELATIVE_PATH = Path("script.json")
VISUAL_PLAN_RELATIVE_PATH = Path("manifests") / "visual-plan.json"
APPROVAL_RELATIVE_PATH = Path("manifests") / "creative-approval.json"
REVIEW_REQUEST_RELATIVE_PATH = Path("manifests") / "creative-review-request.json"
PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH = Path("manifests") / "prototype-review-request.json"
PROTOTYPE_APPROVAL_RELATIVE_PATH = Path("manifests") / "prototype-approval.json"
PROTOTYPE_MANIFEST_RELATIVE_PATH = Path("manifests") / "prototype-manifest.json"
TTS_PROTOTYPE_MANIFEST_RELATIVE_PATH = Path("manifests") / "tts-prototype-manifest.json"
TTS_PRONUNCIATION_QA_RELATIVE_PATH = Path("manifests") / "tts-pronunciation-qa.json"
FINAL_AUDIO_MANIFEST_RELATIVE_PATH = Path("manifests") / "final-audio-manifest.json"
FINAL_AUDIO_RELATIVE_PATH = Path("final_audio.wav")
TIMELINE_PROTOTYPE_RELATIVE_PATH = Path("timeline.prototype.json")
PROTOTYPE_OUTPUT_RELATIVE_PATH = Path("outputs") / "prototype.mp4"
PIPELINE_STATE_RELATIVE_PATH = Path("manifests") / "pipeline-state.json"


@dataclass
class GateFinding:
    severity: str
    code: str
    message: str


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, findings: list[GateFinding], label: str) -> Any | None:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        findings.append(GateFinding("ERROR", "missing-file", f"{label} not found: {path}"))
    except json.JSONDecodeError as exc:
        findings.append(GateFinding("ERROR", "invalid-json", f"{label} is not valid JSON: {path} ({exc})"))
    return None


def normalize_rel_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def is_portable_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    raw = value.strip()
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        return False
    if raw.startswith(("/", "\\\\")):
        return False
    path = Path(raw)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def project_file(project_dir: Path, relative_path: Path | str) -> Path:
    return project_dir / Path(str(relative_path))


def artifact_record(project_dir: Path, relative_path: Path) -> dict[str, str]:
    path = project_file(project_dir, relative_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Missing artifact: {path}")
    return {
        "path": normalize_rel_path(relative_path),
        "sha256": sha256_file(path),
    }


def validate_sha256(value: Any, findings: list[GateFinding], code: str, message: str) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        findings.append(GateFinding("ERROR", code, message))
        return None
    return value.lower()


def validate_portable_artifact(
    artifact: Any,
    project_dir: Path,
    findings: list[GateFinding],
    *,
    context: str,
    required: bool = True,
) -> dict[str, Any] | None:
    if artifact is None and not required:
        return None
    if not isinstance(artifact, dict):
        findings.append(GateFinding("ERROR", "prototype-artifact-shape", f"{context} must be an object"))
        return None
    path_value = artifact.get("path")
    if not is_portable_relative_path(path_value):
        findings.append(GateFinding("ERROR", "prototype-artifact-path", f"{context}.path must be relative to the project and portable"))
        return None
    expected_hash = validate_sha256(
        artifact.get("sha256"),
        findings,
        "prototype-artifact-sha256",
        f"{context}.sha256 must be a 64-character hex digest",
    )
    full_path = project_file(project_dir, Path(str(path_value)))
    if not full_path.exists() or not full_path.is_file():
        findings.append(GateFinding("ERROR", "prototype-artifact-missing", f"{context} file not found: {full_path}"))
        return None
    if expected_hash:
        actual_hash = sha256_file(full_path)
        if actual_hash != expected_hash:
            findings.append(
                GateFinding(
                    "ERROR",
                    "prototype-artifact-stale",
                    f"{context} sha256 is stale: expected {expected_hash}, current {actual_hash}",
                )
            )
    return artifact


def text_sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


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


def media_duration(path: Path, findings: list[GateFinding], *, required: bool = False) -> float | None:
    ffprobe = find_ffprobe()
    if not ffprobe:
        severity = "ERROR" if required else "WARN"
        findings.append(GateFinding(severity, "ffprobe-missing", "ffprobe not found; prototype presenter durations could not be checked"))
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
        severity = "ERROR" if required else "WARN"
        findings.append(GateFinding(severity, "duration-unavailable", f"could not read duration for {path}: {exc}"))
        return None


def broll_panel_sources(item: dict[str, Any], findings: list[GateFinding], context: str) -> list[str]:
    if "primary_visual" in item:
        findings.append(GateFinding("ERROR", "legacy-visual-field", f"{context}.primary_visual is not supported; use type A_ROLL or B_ROLL"))
    segment_type = item.get("type")
    if segment_type in LEGACY_TOP_LEVEL_TYPES - SEGMENT_TYPES:
        findings.append(GateFinding("ERROR", "legacy-segment-type", f"{context}.type {segment_type!r} is a layout/treatment, not a segment type"))
        return []
    if segment_type not in SEGMENT_TYPES:
        findings.append(GateFinding("ERROR", "segment-type", f"{context}.type must be one of {sorted(SEGMENT_TYPES)}"))
        return []
    if segment_type == "A_ROLL":
        for field in ("layout", "panels", "source", "source_strategy"):
            if field in item:
                findings.append(GateFinding("ERROR", "aroll-broll-field", f"{context}.{field} is only valid for B_ROLL"))
        return []

    layout = item.get("layout")
    if layout not in BROLL_LAYOUTS:
        findings.append(GateFinding("ERROR", "broll-layout", f"{context}.layout must be one of {sorted(BROLL_LAYOUTS)}"))
    panels = item.get("panels")
    if not isinstance(panels, list) or not panels:
        findings.append(GateFinding("ERROR", "broll-panels", f"{context}.panels must be a non-empty array"))
        return []
    expected_count = BROLL_LAYOUT_PANEL_COUNTS.get(str(layout))
    if expected_count is not None and len(panels) != expected_count:
        findings.append(GateFinding("ERROR", "broll-panel-count", f"{context}.layout {layout!r} requires exactly {expected_count} panels"))

    sources: list[str] = []
    broll_count = 0
    presenter_count = 0
    for panel_index, panel in enumerate(panels):
        panel_context = f"{context}.panels[{panel_index}]"
        if not isinstance(panel, dict):
            findings.append(GateFinding("ERROR", "broll-panel-shape", f"{panel_context} must be an object"))
            continue
        kind = panel.get("kind")
        if kind not in PANEL_KINDS:
            findings.append(GateFinding("ERROR", "broll-panel-kind", f"{panel_context}.kind must be one of {sorted(PANEL_KINDS)}"))
            continue
        if kind == "broll":
            broll_count += 1
            source = panel.get("source")
            if source not in ALLOWED_SOURCE_STRATEGIES:
                findings.append(GateFinding("ERROR", "broll-panel-source", f"{panel_context}.source must be one of {sorted(ALLOWED_SOURCE_STRATEGIES)}"))
            else:
                sources.append(str(source))
        else:
            presenter_count += 1
            if "source" in panel or "source_strategy" in panel:
                findings.append(GateFinding("ERROR", "presenter-source", f"{panel_context} is presenter media and must not define source fields"))
    if broll_count == 0:
        findings.append(GateFinding("ERROR", "broll-panel-missing", f"{context}.panels must include at least one kind='broll' panel"))
    if layout == "fullscreen":
        if broll_count != 1:
            findings.append(GateFinding("ERROR", "fullscreen-broll-count", f"{context}.layout 'fullscreen' requires exactly one broll panel"))
        if presenter_count > 1:
            findings.append(GateFinding("ERROR", "fullscreen-presenter-count", f"{context}.layout 'fullscreen' allows at most one presenter overlay"))
    return sources


def has_presenter_panel(item: dict[str, Any]) -> bool:
    panels = item.get("panels")
    if not isinstance(panels, list):
        return False
    return any(isinstance(panel, dict) and panel.get("kind") == "presenter" for panel in panels)


def validate_visual_plan(plan: Any, findings: list[GateFinding]) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        findings.append(GateFinding("ERROR", "visual-plan-shape", "visual-plan.json must be an object"))
        return []
    for key in ("schema_version", "metadata", "scenes"):
        if key not in plan:
            findings.append(GateFinding("ERROR", "visual-plan-missing-key", f"visual-plan.json is missing {key!r}"))
    if not isinstance(plan.get("metadata"), dict):
        findings.append(GateFinding("ERROR", "visual-plan-metadata", "visual-plan.metadata must be an object"))
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        findings.append(GateFinding("ERROR", "visual-plan-scenes", "visual-plan.scenes must be a non-empty array"))
        return []

    seen_scene_ids: set[str] = set()
    valid_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        context = f"visual-plan.scenes[{index}]"
        if not isinstance(scene, dict):
            findings.append(GateFinding("ERROR", "visual-plan-scene-shape", f"{context} must be an object"))
            continue
        for field in ("scene_id", "segment_id", "type", "purpose", "visual_idea", "fallback_strategy", "acceptance_criteria"):
            if field not in scene:
                findings.append(GateFinding("ERROR", "visual-plan-scene-missing-key", f"{context} is missing {field!r}"))
        for field in ("scene_id", "segment_id", "purpose", "visual_idea", "fallback_strategy"):
            if field in scene and not is_non_empty_string(scene.get(field)):
                findings.append(GateFinding("ERROR", "visual-plan-scene-field", f"{context}.{field} must be a non-empty string"))
        broll_panel_sources(scene, findings, context)
        acceptance = scene.get("acceptance_criteria")
        if isinstance(acceptance, str):
            if not acceptance.strip():
                findings.append(GateFinding("ERROR", "visual-plan-acceptance", f"{context}.acceptance_criteria must be non-empty"))
        elif isinstance(acceptance, list):
            if not acceptance or any(not is_non_empty_string(item) for item in acceptance):
                findings.append(GateFinding("ERROR", "visual-plan-acceptance", f"{context}.acceptance_criteria list must contain non-empty strings"))
        elif "acceptance_criteria" in scene:
            findings.append(GateFinding("ERROR", "visual-plan-acceptance", f"{context}.acceptance_criteria must be a string or array of strings"))
        scene_id = scene.get("scene_id")
        if isinstance(scene_id, str) and scene_id.strip():
            if scene_id in seen_scene_ids:
                findings.append(GateFinding("ERROR", "visual-plan-duplicate-scene", f"duplicate visual-plan scene_id: {scene_id}"))
            seen_scene_ids.add(scene_id)
        valid_scenes.append(scene)
    return valid_scenes


def validate_prototype_presenter_media(
    project_dir: Path,
    findings: list[GateFinding],
    *,
    path_value: Any,
    loop_policy: Any,
    clip_start: Any,
    segment_duration: float,
    context: str,
) -> None:
    if loop_policy != "error":
        findings.append(GateFinding("ERROR", "prototype-presenter-loop-policy", f"{context}.loop_policy must be 'error'"))
    if not is_portable_relative_path(path_value):
        findings.append(GateFinding("ERROR", "prototype-presenter-path", f"{context}.path must be relative to the project and portable"))
        return
    path = project_file(project_dir, Path(str(path_value)))
    if not path.exists() or not path.is_file():
        findings.append(GateFinding("ERROR", "prototype-presenter-missing", f"{context}.path file not found: {path}"))
        return
    start_offset = as_number(clip_start) or 0.0
    if start_offset < 0:
        findings.append(GateFinding("ERROR", "prototype-presenter-clip-start", f"{context}.clip_start must be non-negative"))
        return
    source_duration = media_duration(path, findings, required=True)
    if source_duration is None:
        return
    available = source_duration - start_offset
    if available <= 0:
        findings.append(GateFinding("ERROR", "prototype-presenter-clip-start", f"{context}.clip_start exceeds source duration"))
    elif available + 0.05 < segment_duration:
        findings.append(
            GateFinding(
                "ERROR",
                "prototype-presenter-too-short",
                f"{context} has {available:.2f}s available for {segment_duration:.2f}s segment",
            )
        )


def validate_prototype_timeline_presenter_policy(project_dir: Path, findings: list[GateFinding]) -> None:
    timeline = load_json(project_dir / TIMELINE_PROTOTYPE_RELATIVE_PATH, findings, "prototype timeline")
    if not isinstance(timeline, list):
        findings.append(GateFinding("ERROR", "prototype-timeline-shape", "timeline.prototype.json must be an array"))
        return
    for index, entry in enumerate(timeline):
        context = f"timeline.prototype[{index}]"
        if not isinstance(entry, dict):
            findings.append(GateFinding("ERROR", "prototype-timeline-entry", f"{context} must be an object"))
            continue
        start = as_number(entry.get("start_time"))
        end = as_number(entry.get("end_time"))
        if start is None or end is None or end <= start:
            findings.append(GateFinding("ERROR", "prototype-timeline-timing", f"{context} must include valid numeric start_time and end_time"))
            continue
        duration = end - start
        entry_clip_start = entry.get("clip_start")
        if entry.get("type") == "A_ROLL":
            validate_prototype_presenter_media(
                project_dir,
                findings,
                path_value=entry.get("clip_path"),
                loop_policy=entry.get("loop_policy"),
                clip_start=entry_clip_start,
                segment_duration=duration,
                context=f"{context}.clip_path",
            )
        if entry.get("type") != "B_ROLL":
            continue
        panels = entry.get("panels")
        if not isinstance(panels, list):
            continue
        for panel_index, panel in enumerate(panels):
            if not isinstance(panel, dict) or panel.get("kind") != "presenter":
                continue
            validate_prototype_presenter_media(
                project_dir,
                findings,
                path_value=panel.get("path"),
                loop_policy=panel.get("loop_policy"),
                clip_start=panel.get("clip_start", entry_clip_start),
                segment_duration=duration,
                context=f"{context}.panels[{panel_index}]",
            )


def validate_script_contract(script: Any, findings: list[GateFinding]) -> None:
    if not isinstance(script, dict):
        findings.append(GateFinding("ERROR", "script-shape", "script.json must be an object"))
        return
    for key in ("metadata", "segments", "tts_chunks", "broll_queries", "graphics", "assembly_notes"):
        if key not in script:
            findings.append(GateFinding("ERROR", "script-missing-key", f"script.json is missing {key!r}"))
    if not isinstance(script.get("metadata"), dict):
        findings.append(GateFinding("ERROR", "script-metadata", "script.metadata must be an object"))
    for key in ("segments", "tts_chunks", "broll_queries", "graphics", "assembly_notes"):
        if key in script and not isinstance(script.get(key), list):
            findings.append(GateFinding("ERROR", "script-list", f"script.{key} must be an array"))
    segments = script.get("segments")
    if isinstance(segments, list) and not segments:
        findings.append(GateFinding("ERROR", "script-segments-empty", "script.segments must not be empty before creative approval"))
    if isinstance(segments, list):
        for index, segment in enumerate(segments):
            if isinstance(segment, dict):
                broll_panel_sources(segment, findings, f"script.segments[{index}]")
    tts_chunks = script.get("tts_chunks")
    if isinstance(tts_chunks, list) and not tts_chunks:
        findings.append(GateFinding("ERROR", "script-tts-empty", "script.tts_chunks must not be empty before creative approval"))


def validate_visual_plan_source_mix(script: Any, visual_plan: Any, scenes: list[dict[str, Any]], findings: list[GateFinding]) -> None:
    if not isinstance(script, dict) or not isinstance(visual_plan, dict) or not scenes:
        return
    script_segments = script.get("segments")
    if not isinstance(script_segments, list):
        return
    segment_by_id: dict[str, dict[str, Any]] = {}
    for segment in script_segments:
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")
        if isinstance(segment_id, str) and segment_id.strip():
            segment_by_id[segment_id.strip()] = segment

    source_strategies: set[str] = set()
    broll_duration = 0.0
    presenter_panel_broll_duration = 0.0
    scene_segment_ids = {
        str(scene.get("segment_id", "")).strip()
        for scene in scenes
        if isinstance(scene.get("segment_id"), str) and str(scene.get("segment_id", "")).strip()
    }

    for scene in scenes:
        segment_id = scene.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            continue
        segment = segment_by_id.get(segment_id.strip())
        if segment is None:
            findings.append(
                GateFinding(
                    "ERROR",
                    "visual-plan-segment-not-found",
                    f"visual-plan scene {scene.get('scene_id')!r} references segment_id {segment_id!r}, but script.json has no matching segment",
                )
            )
            continue
        if scene.get("type") != segment.get("type"):
            findings.append(
                GateFinding(
                    "ERROR",
                    "visual-plan-segment-type-mismatch",
                    f"visual-plan scene {scene.get('scene_id')!r} type {scene.get('type')!r} does not match script segment {segment_id!r} type {segment.get('type')!r}",
                )
            )
            continue
        if segment.get("type") == "A_ROLL":
            continue
        if segment.get("type") != "B_ROLL":
            continue
        scene_sources = broll_panel_sources(scene, findings, f"visual-plan scene {scene.get('scene_id')!r}")
        if not scene_sources:
            continue
        duration = as_number(segment.get("duration_seconds"))
        if duration is None:
            findings.append(
                GateFinding(
                    "ERROR",
                    "visual-plan-segment-duration",
                    f"script segment {segment_id!r} must have numeric duration_seconds for visual-plan source mix validation",
                )
            )
            continue
        if duration <= 0:
            continue
        broll_duration += duration
        if has_presenter_panel(scene):
            presenter_panel_broll_duration += duration
        source_strategies.update(scene_sources)

    for segment_id, segment in segment_by_id.items():
        if segment.get("type") != "B_ROLL":
            continue
        if segment_id not in scene_segment_ids:
            findings.append(
                GateFinding(
                    "ERROR",
                    "visual-plan-broll-source-missing",
                    f"script segment {segment_id!r} uses B_ROLL and must have a visual-plan scene with B-roll panel sources",
                )
            )

    if broll_duration > 0:
        presenter_ratio = presenter_panel_broll_duration / broll_duration
        if presenter_ratio + 1e-9 < BROLL_PRESENTER_PANEL_MIN_RATIO or presenter_ratio - 1e-9 > BROLL_PRESENTER_PANEL_MAX_RATIO:
            findings.append(
                GateFinding(
                    "ERROR",
                    "broll-presenter-panel-ratio",
                    f"{presenter_ratio * 100:.1f}% of B-roll duration has presenter panels; "
                    f"target is about {BROLL_PRESENTER_PANEL_TARGET_RATIO * 100:.1f}% "
                    f"(accepted range {BROLL_PRESENTER_PANEL_MIN_RATIO * 100:.1f}%"
                    f"-{BROLL_PRESENTER_PANEL_MAX_RATIO * 100:.1f}%)",
                )
            )
        required_source_strategies = int(math.ceil(broll_duration / 20.0))
        if len(source_strategies) < required_source_strategies:
            findings.append(
                GateFinding(
                    "ERROR",
                    "visual-plan-low-source-strategy-variety",
                    f"visual-plan uses {len(source_strategies)} broll panel source values for {broll_duration:.2f}s of planned B-roll; "
                    f"required at least {required_source_strategies} (one per started 20 seconds)",
                )
            )


def approval_artifact(approval: dict[str, Any], key: str) -> dict[str, Any] | None:
    artifacts = approval.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    artifact = artifacts.get(key)
    return artifact if isinstance(artifact, dict) else None


def validate_approval(approval: Any, project_dir: Path, findings: list[GateFinding]) -> None:
    if not isinstance(approval, dict):
        findings.append(GateFinding("ERROR", "approval-shape", "creative-approval.json must be an object"))
        return
    if approval.get("status") != "approved":
        findings.append(GateFinding("ERROR", "approval-status", "creative-approval.status must be 'approved'"))
    if approval.get("approval_type") != "human":
        findings.append(GateFinding("ERROR", "approval-type", "creative-approval.approval_type must be 'human'"))
    approved_items = approval.get("approved_items")
    if not isinstance(approved_items, list):
        findings.append(GateFinding("ERROR", "approval-items", "creative-approval.approved_items must be an array"))
    else:
        for required in ("script", "visual_plan"):
            if required not in approved_items:
                findings.append(GateFinding("ERROR", "approval-items", f"creative-approval.approved_items must include {required!r}"))
    approved_at = approval.get("approved_at")
    if not is_non_empty_string(approved_at):
        findings.append(GateFinding("ERROR", "approval-time", "creative-approval.approved_at must be a non-empty timestamp"))
    review_request = approval.get("review_request")
    request_payload: dict[str, Any] | None = None
    if not isinstance(review_request, dict):
        findings.append(GateFinding("ERROR", "approval-review-request", "creative-approval.review_request is required"))
    else:
        request_path_value = review_request.get("path")
        request_sha = review_request.get("sha256")
        if not is_non_empty_string(request_path_value):
            findings.append(GateFinding("ERROR", "approval-review-request-path", "creative-approval.review_request.path must be non-empty"))
            request_path = project_dir / REVIEW_REQUEST_RELATIVE_PATH
        else:
            request_path_raw = Path(str(request_path_value))
            request_path = request_path_raw if request_path_raw.is_absolute() else project_dir / request_path_raw
        if not isinstance(request_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", request_sha):
            findings.append(GateFinding("ERROR", "approval-review-request-sha256", "creative-approval.review_request.sha256 must be a 64-character hex digest"))
        elif not request_path.exists() or not request_path.is_file():
            findings.append(GateFinding("ERROR", "approval-review-request-missing", f"creative review request not found: {request_path}"))
        elif sha256_file(request_path) != request_sha.lower():
            findings.append(GateFinding("ERROR", "approval-review-request-stale", "creative-approval.review_request.sha256 does not match current creative-review-request.json"))
        else:
            loaded_request = load_json(request_path, findings, "creative review request")
            if isinstance(loaded_request, dict):
                request_payload = loaded_request

    expected = {
        "script": SCRIPT_RELATIVE_PATH,
        "visual_plan": VISUAL_PLAN_RELATIVE_PATH,
    }
    for key, default_rel_path in expected.items():
        artifact = approval_artifact(approval, key)
        if artifact is None:
            findings.append(GateFinding("ERROR", "approval-artifact", f"creative-approval.artifacts.{key} is required"))
            continue
        artifact_path = artifact.get("path")
        if not is_non_empty_string(artifact_path):
            findings.append(GateFinding("ERROR", "approval-artifact-path", f"creative-approval.artifacts.{key}.path must be non-empty"))
            rel_path = default_rel_path
        else:
            rel_path = Path(str(artifact_path))
        full_path = rel_path if rel_path.is_absolute() else project_dir / rel_path
        if not full_path.exists() or not full_path.is_file():
            findings.append(GateFinding("ERROR", "approval-artifact-missing", f"approved artifact not found: {full_path}"))
            continue
        expected_hash = artifact.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            findings.append(GateFinding("ERROR", "approval-artifact-sha256", f"creative-approval.artifacts.{key}.sha256 must be a 64-character hex digest"))
            continue
        actual_hash = sha256_file(full_path)
        if actual_hash.lower() != expected_hash.lower():
            findings.append(
                GateFinding(
                    "ERROR",
                    "approval-stale",
                    f"creative approval is stale for {key}: expected {expected_hash.lower()}, current {actual_hash}",
                )
            )
        request_artifact = approval_artifact(request_payload, key) if request_payload else None
        request_hash = request_artifact.get("sha256") if request_artifact else None
        if isinstance(request_hash, str) and request_hash.lower() != expected_hash.lower():
            findings.append(
                GateFinding(
                    "ERROR",
                    "approval-request-mismatch",
                    f"creative approval for {key} does not match the human review request hash",
                )
            )


def scene_matches_identifier(scene: dict[str, Any], *, scene_id: str | None, segment_id: str | None, board_id: str | None) -> bool:
    candidates = {
        str(scene.get("scene_id", "")).strip(),
        str(scene.get("segment_id", "")).strip(),
        str(scene.get("board_id", "")).strip(),
    }
    board_ids = scene.get("board_ids")
    if isinstance(board_ids, list):
        candidates.update(str(item).strip() for item in board_ids if str(item).strip())
    wanted = {value for value in (scene_id, segment_id, board_id) if value}
    return bool(wanted & candidates)


def require_broll_source(
    scenes: list[dict[str, Any]],
    findings: list[GateFinding],
    source: str | None,
    *,
    scene_id: str | None = None,
    segment_id: str | None = None,
    board_id: str | None = None,
) -> None:
    if not source:
        return
    if source not in ALLOWED_SOURCE_STRATEGIES:
        findings.append(GateFinding("ERROR", "required-broll-source", f"unknown required B-roll source: {source}"))
        return
    matches = [
        scene
        for scene in scenes
        if source in broll_panel_sources(scene, findings, f"visual-plan scene {scene.get('scene_id')!r}")
        and scene_matches_identifier(scene, scene_id=scene_id, segment_id=segment_id, board_id=board_id)
    ]
    if not matches:
        identifiers = ", ".join(f"{key}={value}" for key, value in (("scene_id", scene_id), ("segment_id", segment_id), ("board_id", board_id)) if value)
        findings.append(
            GateFinding(
                "ERROR",
                "broll-source-not-approved",
                f"visual-plan has no approved B-roll panel source={source!r} matching {identifiers or 'the requested item'}",
            )
        )


def visual_plan_requires_generated_images(visual_plan: Any) -> bool:
    if not isinstance(visual_plan, dict):
        return False
    scenes = visual_plan.get("scenes")
    if not isinstance(scenes, list):
        return False
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        panels = scene.get("panels")
        if not isinstance(panels, list):
            continue
        for panel in panels:
            if isinstance(panel, dict) and panel.get("kind") == "broll" and panel.get("source") == "generated-image":
                return True
    return False


def validate_path_like_fields(value: Any, findings: list[GateFinding], context: str = "prototype-manifest") -> None:
    path_keys = {
        "path",
        "local_path",
        "source_path",
        "file_path",
        "audio_path",
        "video_path",
        "placeholder_path",
        "prompt_audio_path",
        "reference_audio_path",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            child_context = f"{context}.{key}"
            if key in path_keys and child is not None and not is_portable_relative_path(child):
                findings.append(GateFinding("ERROR", "prototype-portable-path", f"{child_context} must be relative to the project and portable"))
            validate_path_like_fields(child, findings, child_context)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_path_like_fields(child, findings, f"{context}[{index}]")


def validate_tts_prototype_contract(manifest: dict[str, Any], project_dir: Path, findings: list[GateFinding]) -> None:
    tts = manifest.get("tts")
    if not isinstance(tts, dict):
        findings.append(GateFinding("ERROR", "prototype-tts", "prototype-manifest.tts must be an object"))
        return
    if not any(is_non_empty_string(tts.get(field)) for field in ("engine", "model_id", "model_snapshot")):
        findings.append(GateFinding("ERROR", "prototype-tts-model", "prototype-manifest.tts needs engine, model_id, or model_snapshot"))
    run_seed = tts.get("run_seed")
    if run_seed is not None and (not isinstance(run_seed, int) or isinstance(run_seed, bool)):
        findings.append(GateFinding("ERROR", "prototype-tts-run-seed", "prototype-manifest.tts.run_seed must be an integer when present"))
    if tts.get("prototype_inference_timesteps") != 10:
        findings.append(GateFinding("ERROR", "prototype-tts-steps", "prototype-manifest.tts.prototype_inference_timesteps must be 10"))
    if tts.get("production_inference_timesteps") != 10:
        findings.append(GateFinding("ERROR", "prototype-tts-production-steps", "prototype-manifest.tts.production_inference_timesteps must be 10"))
    if as_number(tts.get("cfg_value")) is None:
        findings.append(GateFinding("ERROR", "prototype-tts-cfg", "prototype-manifest.tts.cfg_value must be numeric"))
    for flag in ("normalize", "denoise"):
        if not isinstance(tts.get(flag), bool):
            findings.append(GateFinding("ERROR", "prototype-tts-flag", f"prototype-manifest.tts.{flag} must be boolean"))
    chunks = tts.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        findings.append(GateFinding("ERROR", "prototype-tts-chunks", "prototype-manifest.tts.chunks must be a non-empty array"))
        chunks = []
    for index, chunk in enumerate(chunks):
        context = f"prototype-manifest.tts.chunks[{index}]"
        if not isinstance(chunk, dict):
            findings.append(GateFinding("ERROR", "prototype-tts-chunk-shape", f"{context} must be an object"))
            continue
        if not is_non_empty_string(chunk.get("chunk_id")):
            findings.append(GateFinding("ERROR", "prototype-tts-chunk-id", f"{context}.chunk_id must be non-empty"))
        if not is_non_empty_string(chunk.get("voice_text")):
            findings.append(GateFinding("ERROR", "prototype-tts-chunk-text", f"{context}.voice_text must be non-empty"))
        if not isinstance(chunk.get("seed"), int) or isinstance(chunk.get("seed"), bool):
            findings.append(GateFinding("ERROR", "prototype-tts-chunk-seed", f"{context}.seed must be an integer"))
        if chunk.get("seed_mode") not in {"applied", "recorded_only"}:
            findings.append(GateFinding("ERROR", "prototype-tts-seed-mode", f"{context}.seed_mode must be 'applied' or 'recorded_only'"))
        audio_path = chunk.get("audio_path")
        if not is_portable_relative_path(audio_path):
            findings.append(GateFinding("ERROR", "prototype-tts-chunk-audio-path", f"{context}.audio_path must be relative to the project and portable"))
            continue
        expected_hash = validate_sha256(
            chunk.get("sha256"),
            findings,
            "prototype-tts-chunk-sha256",
            f"{context}.sha256 must be a 64-character hex digest",
        )
        full_path = project_file(project_dir, Path(str(audio_path)))
        if not full_path.exists() or not full_path.is_file():
            findings.append(GateFinding("ERROR", "prototype-tts-chunk-audio-missing", f"{context}.audio_path file not found: {full_path}"))
            continue
        if expected_hash:
            actual_hash = sha256_file(full_path)
            if actual_hash != expected_hash:
                findings.append(GateFinding("ERROR", "prototype-tts-chunk-audio-stale", f"{context}.sha256 does not match audio_path bytes"))
    for field in ("prompt_audio", "reference_audio"):
        audio = tts.get(field)
        if not isinstance(audio, dict):
            findings.append(GateFinding("ERROR", "prototype-tts-audio", f"prototype-manifest.tts.{field} must be an object"))
            continue
        validate_sha256(
            audio.get("sha256"),
            findings,
            "prototype-tts-audio-sha256",
            f"prototype-manifest.tts.{field}.sha256 must be a 64-character hex digest",
        )


ALLOWED_PROTOTYPE_PRESENTER_MODES = {"raw_muted_video"}


def validate_presenter_prototype_contract(manifest: dict[str, Any], findings: list[GateFinding]) -> None:
    presenter = manifest.get("presenter")
    if not isinstance(presenter, dict):
        findings.append(GateFinding("ERROR", "prototype-presenter", "prototype-manifest.presenter must be an object"))
        return
    if presenter.get("latentsync") != "skipped":
        findings.append(GateFinding("ERROR", "prototype-latentsync", "prototype-manifest.presenter.latentsync must be 'skipped'"))
    if presenter.get("presenter_mode") not in ALLOWED_PROTOTYPE_PRESENTER_MODES:
        allowed = ", ".join(sorted(ALLOWED_PROTOTYPE_PRESENTER_MODES))
        findings.append(GateFinding("ERROR", "prototype-presenter-mode", f"prototype-manifest.presenter.presenter_mode must be one of: {allowed}"))
    assets = presenter.get("assets")
    if assets is not None and not isinstance(assets, list):
        findings.append(GateFinding("ERROR", "prototype-presenter-assets", "prototype-manifest.presenter.assets must be an array when present"))
        return
    for index, asset in enumerate(assets or []):
        if not isinstance(asset, dict):
            findings.append(GateFinding("ERROR", "prototype-presenter-asset", f"prototype-manifest.presenter.assets[{index}] must be an object"))
            continue
        if "path" in asset and not is_portable_relative_path(asset.get("path")):
            findings.append(GateFinding("ERROR", "prototype-presenter-asset-path", f"prototype-manifest.presenter.assets[{index}].path must be portable"))
        validate_sha256(
            asset.get("sha256"),
            findings,
            "prototype-presenter-asset-sha256",
            f"prototype-manifest.presenter.assets[{index}].sha256 must be a 64-character hex digest",
        )


def validate_generated_image_placeholders(
    manifest: dict[str, Any],
    project_dir: Path,
    visual_plan: Any,
    findings: list[GateFinding],
) -> None:
    placeholders = manifest.get("generated_image_placeholders")
    if placeholders is None:
        placeholders = []
    if not isinstance(placeholders, list):
        findings.append(GateFinding("ERROR", "prototype-placeholders", "prototype-manifest.generated_image_placeholders must be an array"))
        return
    if visual_plan_requires_generated_images(visual_plan) and not placeholders:
        findings.append(GateFinding("ERROR", "prototype-placeholders-missing", "visual-plan uses generated-image but prototype manifest has no placeholders"))
    for index, placeholder in enumerate(placeholders):
        context = f"prototype-manifest.generated_image_placeholders[{index}]"
        if not isinstance(placeholder, dict):
            findings.append(GateFinding("ERROR", "prototype-placeholder-shape", f"{context} must be an object"))
            continue
        text = (
            placeholder.get("placeholder_text")
            or placeholder.get("prompt")
            or placeholder.get("visual_brief")
        )
        if not is_non_empty_string(text):
            findings.append(GateFinding("ERROR", "prototype-placeholder-text", f"{context} needs prompt, visual_brief, or placeholder_text"))
        expected_hash = validate_sha256(
            placeholder.get("sha256"),
            findings,
            "prototype-placeholder-sha256",
            f"{context}.sha256 must be a 64-character hex digest",
        )
        placeholder_path = placeholder.get("placeholder_path")
        if placeholder_path is not None:
            if not is_portable_relative_path(placeholder_path):
                findings.append(GateFinding("ERROR", "prototype-placeholder-path", f"{context}.placeholder_path must be portable"))
            else:
                placeholder_file = project_file(project_dir, Path(str(placeholder_path)))
                if not placeholder_file.exists() or not placeholder_file.is_file():
                    findings.append(GateFinding("ERROR", "prototype-placeholder-missing", f"{context}.placeholder_path file not found: {placeholder_file}"))
                file_hash = placeholder.get("placeholder_file_sha256")
                if file_hash is not None:
                    expected_file_hash = validate_sha256(
                        file_hash,
                        findings,
                        "prototype-placeholder-file-sha256",
                        f"{context}.placeholder_file_sha256 must be a 64-character hex digest",
                    )
                    if expected_file_hash and placeholder_file.exists() and placeholder_file.is_file() and sha256_file(placeholder_file) != expected_file_hash:
                        findings.append(GateFinding("ERROR", "prototype-placeholder-file-stale", f"{context}.placeholder_file_sha256 does not match placeholder_path bytes"))
        if expected_hash and is_non_empty_string(text) and text_sha256(str(text)) != expected_hash:
            findings.append(GateFinding("ERROR", "prototype-placeholder-stale", f"{context}.sha256 must match placeholder text"))


def validate_prototype_manifest(manifest: Any, project_dir: Path, findings: list[GateFinding], visual_plan: Any = None) -> None:
    if not isinstance(manifest, dict):
        findings.append(GateFinding("ERROR", "prototype-manifest-shape", "prototype-manifest.json must be an object"))
        return
    validate_path_like_fields(manifest, findings)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        findings.append(GateFinding("ERROR", "prototype-artifacts", "prototype-manifest.artifacts must be an object"))
        artifacts = {}
    required_artifacts = {
        "script": SCRIPT_RELATIVE_PATH,
        "visual_plan": VISUAL_PLAN_RELATIVE_PATH,
        "timeline_prototype": TIMELINE_PROTOTYPE_RELATIVE_PATH,
        "prototype_video": PROTOTYPE_OUTPUT_RELATIVE_PATH,
        "tts_prototype_manifest": TTS_PROTOTYPE_MANIFEST_RELATIVE_PATH,
        "tts_pronunciation_qa": TTS_PRONUNCIATION_QA_RELATIVE_PATH,
        "final_audio_manifest": FINAL_AUDIO_MANIFEST_RELATIVE_PATH,
        "final_audio": FINAL_AUDIO_RELATIVE_PATH,
    }
    for key in required_artifacts:
        validate_portable_artifact(artifacts.get(key), project_dir, findings, context=f"prototype-manifest.artifacts.{key}")
    validate_tts_pronunciation_qa(project_dir, findings)
    validate_final_audio_manifest_contract(project_dir, findings)
    validate_tts_prototype_contract(manifest, project_dir, findings)
    validate_presenter_prototype_contract(manifest, findings)
    validate_generated_image_placeholders(manifest, project_dir, visual_plan, findings)


def validate_final_audio_manifest_contract(project_dir: Path, findings: list[GateFinding]) -> None:
    manifest_path = project_dir / FINAL_AUDIO_MANIFEST_RELATIVE_PATH
    if not manifest_path.exists():
        return
    manifest = load_json(manifest_path, findings, "final audio manifest")
    if not isinstance(manifest, dict):
        findings.append(GateFinding("ERROR", "prototype-final-audio-manifest", "final-audio-manifest.json must be an object"))
        return
    duration = manifest.get("duration_seconds")
    if duration is not None and (as_number(duration) is None or as_number(duration) <= 0):
        findings.append(GateFinding("ERROR", "prototype-final-audio-manifest", "final-audio-manifest.duration_seconds must be positive when present"))
    chunks = manifest.get("tts_chunks")
    if not isinstance(chunks, list) or not chunks:
        findings.append(GateFinding("ERROR", "prototype-final-audio-manifest", "final-audio-manifest.tts_chunks must be a non-empty array"))
        return
    for index, chunk in enumerate(chunks):
        context = f"final-audio-manifest.tts_chunks[{index}]"
        if not isinstance(chunk, dict):
            findings.append(GateFinding("ERROR", "prototype-final-audio-manifest", f"{context} must be an object"))
            continue
        if not is_non_empty_string(chunk.get("chunk")):
            findings.append(GateFinding("ERROR", "prototype-final-audio-manifest", f"{context}.chunk must be non-empty"))
        if as_number(chunk.get("timeline_start_seconds")) is None:
            findings.append(GateFinding("ERROR", "prototype-final-audio-manifest", f"{context}.timeline_start_seconds must be numeric"))
        chunk_duration = chunk.get("duration_seconds")
        if chunk_duration is not None and (as_number(chunk_duration) is None or as_number(chunk_duration) <= 0):
            findings.append(GateFinding("ERROR", "prototype-final-audio-manifest", f"{context}.duration_seconds must be positive when present"))


def validate_tts_pronunciation_qa(project_dir: Path, findings: list[GateFinding]) -> None:
    report_path = project_dir / TTS_PRONUNCIATION_QA_RELATIVE_PATH
    if not report_path.exists():
        return
    report = load_json(report_path, findings, "TTS pronunciation QA")
    if not isinstance(report, dict):
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "tts-pronunciation-qa.json must be an object"))
        return
    if report.get("status") != "pass":
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "tts-pronunciation-qa.json status must be 'pass'"))
        return
    if report.get("qa_method") == "asr_with_user_approved_override":
        validate_tts_pronunciation_override(report, findings)
    elif report.get("qa_method") is not None:
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "tts-pronunciation-qa.json has unsupported qa_method"))
    else:
        validate_tts_pronunciation_automatic_pass(report, findings)


def validate_tts_pronunciation_automatic_pass(report: dict[str, Any], findings: list[GateFinding]) -> None:
    if not is_non_empty_string(report.get("backend")):
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "automatic TTS pronunciation QA pass needs backend"))
    if not isinstance(report.get("thresholds"), dict):
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "automatic TTS pronunciation QA pass needs thresholds"))
    if report.get("errors") != []:
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "automatic TTS pronunciation QA pass must have no errors"))
    chunks = report.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "automatic TTS pronunciation QA pass needs non-empty chunks"))
        return
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or chunk.get("passed") is not True:
            findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", f"automatic TTS pronunciation QA chunks[{index}].passed must be true"))


def validate_tts_pronunciation_override(report: dict[str, Any], findings: list[GateFinding]) -> None:
    if report.get("asr_status") != "fail":
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override needs asr_status 'fail'"))
    if report.get("manual_review_status") != "approved":
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override needs manual_review_status 'approved'"))
    if report.get("accepted_by") != "user":
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override needs accepted_by 'user'"))
    accepted_at = report.get("accepted_at")
    if not is_non_empty_string(accepted_at):
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override needs accepted_at"))
    else:
        try:
            datetime.fromisoformat(str(accepted_at).replace("Z", "+00:00"))
        except ValueError:
            findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override accepted_at must be an ISO timestamp"))
    if report.get("errors") != []:
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override must have no runtime errors"))
    chunks = report.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override must retain non-empty ASR chunks"))
    overrides = report.get("overrides")
    if not isinstance(overrides, list) or not overrides:
        findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", "TTS QA override needs non-empty overrides"))
        return
    for index, override in enumerate(overrides):
        context = f"TTS QA override overrides[{index}]"
        if not isinstance(override, dict):
            findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", f"{context} must be an object"))
            continue
        for field in ("chunk_id", "reason", "expected", "asr_transcript"):
            if not is_non_empty_string(override.get(field)):
                findings.append(GateFinding("ERROR", "prototype-tts-pronunciation-qa", f"{context}.{field} must be non-empty"))


def validate_prototype_approval(approval: Any, project_dir: Path, findings: list[GateFinding]) -> None:
    if not isinstance(approval, dict):
        findings.append(GateFinding("ERROR", "prototype-approval-shape", "prototype-approval.json must be an object"))
        return
    if approval.get("status") != "approved":
        findings.append(GateFinding("ERROR", "prototype-approval-status", "prototype-approval.status must be 'approved'"))
    if approval.get("approval_type") != "human":
        findings.append(GateFinding("ERROR", "prototype-approval-type", "prototype-approval.approval_type must be 'human'"))
    approved_items = approval.get("approved_items")
    required_items = {"prototype_manifest", "prototype_video", "timeline_prototype", "tts_prototype_manifest", "tts_pronunciation_qa", "final_audio_manifest", "final_audio"}
    if not isinstance(approved_items, list):
        findings.append(GateFinding("ERROR", "prototype-approval-items", "prototype-approval.approved_items must be an array"))
    else:
        missing = sorted(required_items - set(approved_items))
        for item in missing:
            findings.append(GateFinding("ERROR", "prototype-approval-items", f"prototype-approval.approved_items must include {item!r}"))

    review_request = approval.get("review_request")
    request_payload: dict[str, Any] | None = None
    if not isinstance(review_request, dict):
        findings.append(GateFinding("ERROR", "prototype-approval-review-request", "prototype-approval.review_request is required"))
    else:
        request_path_value = review_request.get("path")
        request_sha = review_request.get("sha256")
        if not is_portable_relative_path(request_path_value):
            findings.append(GateFinding("ERROR", "prototype-approval-review-request-path", "prototype-approval.review_request.path must be portable"))
            request_path = project_dir / PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH
        else:
            request_path = project_file(project_dir, Path(str(request_path_value)))
        expected_hash = validate_sha256(
            request_sha,
            findings,
            "prototype-approval-review-request-sha256",
            "prototype-approval.review_request.sha256 must be a 64-character hex digest",
        )
        if not request_path.exists() or not request_path.is_file():
            findings.append(GateFinding("ERROR", "prototype-approval-review-request-missing", f"prototype review request not found: {request_path}"))
        elif expected_hash and sha256_file(request_path) != expected_hash:
            findings.append(GateFinding("ERROR", "prototype-approval-review-request-stale", "prototype-approval.review_request.sha256 does not match current prototype-review-request.json"))
        else:
            loaded_request = load_json(request_path, findings, "prototype review request")
            if isinstance(loaded_request, dict):
                request_payload = loaded_request

    artifacts = approval.get("artifacts")
    if not isinstance(artifacts, dict):
        findings.append(GateFinding("ERROR", "prototype-approval-artifacts", "prototype-approval.artifacts must be an object"))
        artifacts = {}
    for key in ("script", "visual_plan", "prototype_manifest", "timeline_prototype", "prototype_video", "tts_prototype_manifest", "tts_pronunciation_qa", "final_audio_manifest", "final_audio"):
        artifact = validate_portable_artifact(artifacts.get(key), project_dir, findings, context=f"prototype-approval.artifacts.{key}")
        request_artifact = approval_artifact(request_payload, key) if request_payload else None
        if artifact and request_artifact:
            approval_hash = artifact.get("sha256")
            request_hash = request_artifact.get("sha256")
            if isinstance(approval_hash, str) and isinstance(request_hash, str) and approval_hash.lower() != request_hash.lower():
                findings.append(GateFinding("ERROR", "prototype-approval-request-mismatch", f"prototype approval for {key} does not match the human review request hash"))


def write_pipeline_state(project_dir: Path, findings: list[GateFinding], *, gate: str = "creative-gate", blocked_stage: str = "production") -> None:
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if not errors:
        return
    state_path = project_dir / PIPELINE_STATE_RELATIVE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    required_artifact = PROTOTYPE_APPROVAL_RELATIVE_PATH if gate == "prototype-gate" else APPROVAL_RELATIVE_PATH
    recovery = (
        "Fix prototype artifacts, regenerate manifests/prototype-review-request.json, then regenerate manifests/prototype-approval.json with approve_prototype.py."
        if gate == "prototype-gate"
        else "Fix script.json, manifests/visual-plan.json, then regenerate manifests/creative-approval.json with approve_creative_plan.py."
    )
    payload = {
        "status": "blocked",
        "gate": gate,
        "blocked_stage": blocked_stage,
        "reason": f"{gate} failed",
        "required_artifact": str(project_dir / required_artifact),
        "findings": [finding.__dict__ for finding in findings],
        "recovery": recovery,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_creative_gate(
    project_dir: Path,
    *,
    require_source: str | None = None,
    scene_id: str | None = None,
    segment_id: str | None = None,
    board_id: str | None = None,
    write_state: bool = True,
) -> list[GateFinding]:
    project_dir = project_dir.resolve()
    findings: list[GateFinding] = []
    script = load_json(project_dir / SCRIPT_RELATIVE_PATH, findings, "script")
    visual_plan = load_json(project_dir / VISUAL_PLAN_RELATIVE_PATH, findings, "visual plan")
    approval = load_json(project_dir / APPROVAL_RELATIVE_PATH, findings, "creative approval")

    if script is not None:
        validate_script_contract(script, findings)

    scenes: list[dict[str, Any]] = []
    if visual_plan is not None:
        scenes = validate_visual_plan(visual_plan, findings)
        validate_visual_plan_source_mix(script, visual_plan, scenes, findings)

    if approval is not None:
        validate_approval(approval, project_dir, findings)

    require_broll_source(scenes, findings, require_source, scene_id=scene_id, segment_id=segment_id, board_id=board_id)

    if write_state:
        write_pipeline_state(project_dir, findings, gate="creative-gate", blocked_stage="production")
    return findings


def run_prototype_gate(project_dir: Path, *, write_state: bool = True) -> list[GateFinding]:
    project_dir = project_dir.resolve()
    findings = run_creative_gate(project_dir, write_state=False)
    visual_plan = load_json(project_dir / VISUAL_PLAN_RELATIVE_PATH, findings, "visual plan")
    prototype_manifest = load_json(project_dir / PROTOTYPE_MANIFEST_RELATIVE_PATH, findings, "prototype manifest")
    prototype_approval = load_json(project_dir / PROTOTYPE_APPROVAL_RELATIVE_PATH, findings, "prototype approval")

    if prototype_manifest is not None:
        validate_prototype_manifest(prototype_manifest, project_dir, findings, visual_plan)
    validate_prototype_timeline_presenter_policy(project_dir, findings)
    if prototype_approval is not None:
        validate_prototype_approval(prototype_approval, project_dir, findings)

    if write_state:
        write_pipeline_state(project_dir, findings, gate="prototype-gate", blocked_stage="final-production")
    return findings


def create_approval(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    script_path = project_dir / SCRIPT_RELATIVE_PATH
    visual_plan_path = project_dir / VISUAL_PLAN_RELATIVE_PATH
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")
    if not visual_plan_path.exists():
        raise FileNotFoundError(f"Missing visual plan: {visual_plan_path}")
    review_request_path = project_dir / REVIEW_REQUEST_RELATIVE_PATH
    if not review_request_path.exists():
        raise FileNotFoundError(f"Missing creative review request: {review_request_path}")
    request = json.loads(review_request_path.read_text(encoding="utf-8-sig"))
    if not isinstance(request, dict) or request.get("status") != "awaiting_human_review":
        raise ValueError("creative-review-request.json must have status awaiting_human_review")
    request_artifacts = request.get("artifacts")
    if not isinstance(request_artifacts, dict):
        raise ValueError("creative-review-request.json is missing artifacts")
    current_script_sha = sha256_file(script_path)
    current_visual_plan_sha = sha256_file(visual_plan_path)
    if (request_artifacts.get("script") or {}).get("sha256") != current_script_sha:
        raise ValueError("script.json changed after creative-review-request.json was created")
    if (request_artifacts.get("visual_plan") or {}).get("sha256") != current_visual_plan_sha:
        raise ValueError("manifests/visual-plan.json changed after creative-review-request.json was created")
    return {
        "schema_version": 1,
        "status": "approved",
        "approval_type": "human",
        "approved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "approved_items": ["script", "visual_plan"],
        "review_request": {
            "path": str(REVIEW_REQUEST_RELATIVE_PATH).replace("\\", "/"),
            "sha256": sha256_file(review_request_path),
        },
        "artifacts": {
            "script": {
                "path": str(SCRIPT_RELATIVE_PATH).replace("\\", "/"),
                "sha256": current_script_sha,
            },
            "visual_plan": {
                "path": str(VISUAL_PLAN_RELATIVE_PATH).replace("\\", "/"),
                "sha256": current_visual_plan_sha,
            },
        },
    }


def prototype_artifact_records(project_dir: Path) -> dict[str, dict[str, str]]:
    return {
        "script": artifact_record(project_dir, SCRIPT_RELATIVE_PATH),
        "visual_plan": artifact_record(project_dir, VISUAL_PLAN_RELATIVE_PATH),
        "prototype_manifest": artifact_record(project_dir, PROTOTYPE_MANIFEST_RELATIVE_PATH),
        "timeline_prototype": artifact_record(project_dir, TIMELINE_PROTOTYPE_RELATIVE_PATH),
        "prototype_video": artifact_record(project_dir, PROTOTYPE_OUTPUT_RELATIVE_PATH),
        "tts_prototype_manifest": artifact_record(project_dir, TTS_PROTOTYPE_MANIFEST_RELATIVE_PATH),
        "tts_pronunciation_qa": artifact_record(project_dir, TTS_PRONUNCIATION_QA_RELATIVE_PATH),
        "final_audio_manifest": artifact_record(project_dir, FINAL_AUDIO_MANIFEST_RELATIVE_PATH),
        "final_audio": artifact_record(project_dir, FINAL_AUDIO_RELATIVE_PATH),
    }


def create_prototype_review_request(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    findings = run_creative_gate(project_dir, write_state=False)
    visual_plan = load_json(project_dir / VISUAL_PLAN_RELATIVE_PATH, findings, "visual plan")
    prototype_manifest = load_json(project_dir / PROTOTYPE_MANIFEST_RELATIVE_PATH, findings, "prototype manifest")
    if prototype_manifest is not None:
        validate_prototype_manifest(prototype_manifest, project_dir, findings, visual_plan)
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        messages = "; ".join(f"{finding.code}: {finding.message}" for finding in errors)
        raise ValueError(f"Cannot create prototype review request: {messages}")
    return {
        "schema_version": 1,
        "status": "awaiting_human_review",
        "checkpoint_type": "human-verify-prototype",
        "resume_signal": "approved",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifacts": prototype_artifact_records(project_dir),
    }


def create_prototype_approval(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    review_request_path = project_dir / PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH
    if not review_request_path.exists():
        raise FileNotFoundError(f"Missing prototype review request: {review_request_path}")
    request = json.loads(review_request_path.read_text(encoding="utf-8-sig"))
    if not isinstance(request, dict) or request.get("status") != "awaiting_human_review":
        raise ValueError("prototype-review-request.json must have status awaiting_human_review")
    request_artifacts = request.get("artifacts")
    if not isinstance(request_artifacts, dict):
        raise ValueError("prototype-review-request.json is missing artifacts")
    current_artifacts = prototype_artifact_records(project_dir)
    for key, artifact in current_artifacts.items():
        request_hash = (request_artifacts.get(key) or {}).get("sha256")
        if request_hash != artifact["sha256"]:
            raise ValueError(f"{artifact['path']} changed after prototype-review-request.json was created")
    return {
        "schema_version": 1,
        "status": "approved",
        "approval_type": "human",
        "approved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "approved_items": [
            "script",
            "visual_plan",
            "prototype_manifest",
            "timeline_prototype",
            "prototype_video",
            "tts_prototype_manifest",
            "tts_pronunciation_qa",
            "final_audio_manifest",
            "final_audio",
        ],
        "review_request": {
            "path": normalize_rel_path(PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH),
            "sha256": sha256_file(review_request_path),
        },
        "artifacts": current_artifacts,
    }


def create_review_request(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    script_path = project_dir / SCRIPT_RELATIVE_PATH
    visual_plan_path = project_dir / VISUAL_PLAN_RELATIVE_PATH
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")
    if not visual_plan_path.exists():
        raise FileNotFoundError(f"Missing visual plan: {visual_plan_path}")
    findings: list[GateFinding] = []
    script = load_json(script_path, findings, "script")
    visual_plan = load_json(visual_plan_path, findings, "visual plan")
    validate_script_contract(script, findings)
    scenes = validate_visual_plan(visual_plan, findings)
    validate_visual_plan_source_mix(script, visual_plan, scenes, findings)
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        messages = "; ".join(f"{finding.code}: {finding.message}" for finding in errors)
        raise ValueError(f"Cannot create creative review request: {messages}")
    return {
        "schema_version": 1,
        "status": "awaiting_human_review",
        "checkpoint_type": "human-verify",
        "resume_signal": "approved",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifacts": {
            "script": {
                "path": str(SCRIPT_RELATIVE_PATH).replace("\\", "/"),
                "sha256": sha256_file(script_path),
            },
            "visual_plan": {
                "path": str(VISUAL_PLAN_RELATIVE_PATH).replace("\\", "/"),
                "sha256": sha256_file(visual_plan_path),
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the YouTube autopipeline creative production gate.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    parser.add_argument("--gate", choices=("creative", "prototype"), default="creative", help="Gate to validate.")
    parser.add_argument("--require-broll-source", choices=sorted(ALLOWED_SOURCE_STRATEGIES), help="Require an approved visual-plan scene with this B-roll panel source.")
    parser.add_argument("--scene-id", help="Scene id to match in visual-plan.")
    parser.add_argument("--segment-id", help="Segment id to match in visual-plan.")
    parser.add_argument("--board-id", help="Board id to match in visual-plan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.gate == "prototype":
        if any((args.require_broll_source, args.scene_id, args.segment_id, args.board_id)):
            raise SystemExit("--require-broll-source/--scene-id/--segment-id/--board-id are only valid for the creative gate")
        findings = run_prototype_gate(Path(args.project_dir))
    else:
        findings = run_creative_gate(
            Path(args.project_dir),
            require_source=args.require_broll_source,
            scene_id=args.scene_id,
            segment_id=args.segment_id,
            board_id=args.board_id,
        )
    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], indent=2, ensure_ascii=False))
    else:
        for finding in findings:
            print(f"{finding.severity}: {finding.code}: {finding.message}")
    return 1 if any(finding.severity == "ERROR" for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
