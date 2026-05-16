#!/usr/bin/env python3
"""Resolve selected-visuals intent manifests into validation manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


RESOLVER_NAME = "youtube-autopipeline-selected-visuals-resolver"
RESOLVER_VERSION = "1.0.0"
BROLL_SOURCE_TYPES = {"webpage", "stock", "screen-record", "generated-image", "manual", "synthetic-motion"}
IDENTITY_FIELDS = {"canonical_id", "sha256", "provenance"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_rel_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def resolve_local_path(project_dir: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, netloc, path, query, ""))


def provider_from_url(url: str) -> str | None:
    host = urlsplit(url).netloc.lower()
    if "pexels.com" in host:
        return "pexels"
    return None


def script_sources(script: Any) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    if not isinstance(script, dict) or not isinstance(script.get("segments"), list):
        return sources
    for segment in script["segments"]:
        if not isinstance(segment, dict) or segment.get("type") != "B_ROLL":
            continue
        segment_id = segment.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            continue
        segment_sources: set[str] = set()
        panels = segment.get("panels")
        if isinstance(panels, list):
            for panel in panels:
                if isinstance(panel, dict) and panel.get("kind") == "broll" and panel.get("source_type") in BROLL_SOURCE_TYPES:
                    segment_sources.add(str(panel["source_type"]))
        if segment_sources:
            sources[segment_id.strip()] = segment_sources
    return sources


def planned_sources_for_item(item: dict[str, Any], planned_sources: dict[str, set[str]]) -> set[str]:
    segment_id = item.get("segment_id") if isinstance(item.get("segment_id"), str) else None
    if segment_id:
        return planned_sources.get(segment_id, set())
    return set()


def relative_media_ref(project_dir: Path, value: str) -> str:
    path = Path(value)
    resolved = path if path.is_absolute() else project_dir / path
    try:
        return str(resolved.resolve().relative_to(project_dir.resolve())).replace("/", "\\")
    except ValueError:
        return str(resolved.resolve())


def accepted_z_image_outputs(project_dir: Path) -> set[str]:
    plan_path = project_dir / "manifests" / "z-image-plan.json"
    if not plan_path.exists():
        return set()
    plan = load_json(plan_path)
    accepted: set[str] = set()
    if isinstance(plan, dict) and isinstance(plan.get("items"), list):
        for item in plan["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("output"), str):
                continue
            review = item.get("review") if isinstance(item.get("review"), dict) else {}
            if review.get("accepted") is True:
                accepted.add(relative_media_ref(project_dir, item["output"]))
    return accepted


def has_board_proof(local_file: Path) -> bool:
    directory = local_file.parent
    manifest_path = directory / "board-manifest.json"
    qa_path = directory / "board-qa.json"
    if manifest_path.exists() and manifest_path.is_file():
        return True
    if not qa_path.exists() or not qa_path.is_file():
        return False
    try:
        qa = load_json(qa_path)
    except Exception:
        return False
    if not isinstance(qa, dict):
        return False
    return qa.get("status") == "pass" or qa.get("passed") is True


def validate_source_type_proof(
    project_dir: Path,
    item: dict[str, Any],
    source_type: str,
    file_path: Path | None,
    source_url: str | None,
    accepted_z_outputs: set[str],
    index: int,
    errors: list[str],
) -> None:
    context = f"items[{index}]"
    if source_type == "generated-image":
        if file_path is None:
            errors.append(f"{context}.local_path is required for generated-image")
            return
        if relative_media_ref(project_dir, str(file_path)) not in accepted_z_outputs:
            errors.append(f"{context}.local_path is not an accepted output in manifests/z-image-plan.json")
    elif source_type == "synthetic-motion":
        if file_path is None:
            errors.append(f"{context}.local_path is required for synthetic-motion")
        elif not has_board_proof(file_path):
            errors.append(f"{context}.local_path has no board-manifest.json or passing board-qa.json proof")
    elif source_type == "webpage":
        if not (isinstance(source_url, str) and source_url.strip()) and not isinstance(item.get("capture_source_url"), str):
            errors.append(f"{context}.source_url or capture_source_url is required for webpage")
    elif source_type == "stock":
        provider = item.get("provider")
        if provider != "pexels" and not (isinstance(source_url, str) and provider_from_url(source_url) == "pexels"):
            errors.append(f"{context}.provider='pexels' or a Pexels source_url is required for stock")


def validate_intent_item(item: dict[str, Any], index: int, errors: list[str]) -> None:
    forbidden = sorted(field for field in IDENTITY_FIELDS if field in item)
    if forbidden:
        errors.append(f"items[{index}] contains resolver-owned fields: {', '.join(forbidden)}")
    if "local_path" not in item and "source_url" not in item:
        errors.append(f"items[{index}] must include local_path or source_url")
    source_type = item.get("source_type")
    if source_type not in BROLL_SOURCE_TYPES:
        errors.append(f"items[{index}].source_type must be one of {sorted(BROLL_SOURCE_TYPES)}")


def resolve_item(
    project_dir: Path,
    item: dict[str, Any],
    index: int,
    planned_sources: dict[str, set[str]],
    accepted_z_outputs: set[str],
    errors: list[str],
) -> dict[str, Any] | None:
    validate_intent_item(item, index, errors)
    local_path = item.get("local_path")
    source_url = item.get("source_url")
    source_type = item.get("source_type")
    if local_path is not None and not isinstance(local_path, str):
        errors.append(f"items[{index}].local_path must be a string")
        return None
    if source_url is not None and not isinstance(source_url, str):
        errors.append(f"items[{index}].source_url must be a string")
        return None

    if source_type not in BROLL_SOURCE_TYPES:
        return None
    planned = planned_sources_for_item(item, planned_sources)
    if not planned:
        errors.append(f"items[{index}] does not match any B-roll source_type in script.json")
    elif source_type not in planned:
        errors.append(f"items[{index}].source_type {source_type!r} does not match script sources {sorted(planned)}")

    resolved = dict(item)
    file_path: Path | None = None

    if local_path:
        file_path = resolve_local_path(project_dir, local_path)
        if not file_path.exists() or not file_path.is_file():
            errors.append(f"items[{index}].local_path not found: {file_path}")
            return None
        digest = sha256_file(file_path)
        resolved["sha256"] = digest
        resolved["canonical_id"] = f"sha256:{digest}"
        resolved["provenance"] = {
            "kind": "local_file",
            "resolved_path": str(file_path),
            "project_relative_path": normalize_rel_path(local_path),
            "sha256": digest,
        }
    elif source_url:
        normalized_url = canonical_url(source_url)
        provider = provider_from_url(normalized_url)
        if provider:
            resolved["canonical_id"] = f"{provider}:{normalized_url}"
        else:
            resolved["canonical_id"] = f"url:{normalized_url}"
        provenance: dict[str, Any] = {
            "kind": "remote",
            "source_url": normalized_url,
        }
        if provider:
            provenance["provider"] = provider
        resolved["provenance"] = provenance

    validate_source_type_proof(project_dir, item, source_type, file_path, source_url, accepted_z_outputs, index, errors)

    return resolved


def resolve_manifest(project_dir: Path, input_path: Path, manifest: Any) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {}, ["selected visuals intent manifest must be an object"]
    if "resolver" in manifest:
        errors.append("input already contains resolver metadata; pass the intent manifest, not a resolved manifest")
    script = load_json(project_dir / "script.json")
    planned_sources = script_sources(script)
    if not planned_sources:
        errors.append("script.json contains no B-roll source_type declarations")
    accepted_z_outputs = accepted_z_image_outputs(project_dir)
    items = manifest.get("items")
    if not isinstance(items, list):
        return {}, ["selected visuals intent manifest must include an items array"]

    resolved_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object")
            continue
        resolved = resolve_item(project_dir, item, index, planned_sources, accepted_z_outputs, errors)
        if resolved is not None:
            resolved_items.append(resolved)

    output = {
        "resolver": {
            "name": RESOLVER_NAME,
            "version": RESOLVER_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "source_manifest": {
            "path": str(input_path.resolve()),
            "sha256": sha256_file(input_path) if input_path.exists() else None,
        },
        "target_duration_seconds": manifest.get("target_duration_seconds"),
        "single_pattern_reason": manifest.get("single_pattern_reason"),
        "items": resolved_items,
    }
    return output, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve selected-visuals intent manifest into validation manifest.")
    parser.add_argument("--project-dir", required=True, help="Project directory.")
    parser.add_argument("--input", required=True, help="Input selected-visuals intent manifest.")
    parser.add_argument("--output", required=True, help="Output selected-visuals resolved manifest.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    try:
        manifest = load_json(input_path)
        resolved, errors = resolve_manifest(project_dir, input_path, manifest)
        if errors:
            print("selected visuals resolver failed:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        write_json(output_path, resolved)
        print(f"Wrote resolved selected visuals: {output_path}")
        return 0
    except Exception as exc:
        print(f"selected visuals resolver failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
