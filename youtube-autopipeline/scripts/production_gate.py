#!/usr/bin/env python3
"""Hard production gates for the local YouTube autopipeline."""

from __future__ import annotations

import argparse
import json
import math
import re
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
SCRIPT_RELATIVE_PATH = Path("script.json")
VISUAL_PLAN_RELATIVE_PATH = Path("manifests") / "visual-plan.json"
APPROVAL_RELATIVE_PATH = Path("manifests") / "creative-approval.json"
REVIEW_REQUEST_RELATIVE_PATH = Path("manifests") / "creative-review-request.json"
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


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
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


def write_pipeline_state(project_dir: Path, findings: list[GateFinding]) -> None:
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if not errors:
        return
    state_path = project_dir / PIPELINE_STATE_RELATIVE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "blocked",
        "gate": "creative-gate",
        "blocked_stage": "production",
        "reason": "Creative gate failed",
        "required_artifact": str(project_dir / APPROVAL_RELATIVE_PATH),
        "findings": [finding.__dict__ for finding in findings],
        "recovery": "Fix script.json, manifests/visual-plan.json, then regenerate manifests/creative-approval.json with approve_creative_plan.py.",
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
        write_pipeline_state(project_dir, findings)
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
    parser.add_argument("--require-broll-source", choices=sorted(ALLOWED_SOURCE_STRATEGIES), help="Require an approved visual-plan scene with this B-roll panel source.")
    parser.add_argument("--scene-id", help="Scene id to match in visual-plan.")
    parser.add_argument("--segment-id", help="Segment id to match in visual-plan.")
    parser.add_argument("--board-id", help="Board id to match in visual-plan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
