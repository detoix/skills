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
IDENTITY_FIELDS = {"source_type", "canonical_id", "sha256", "provenance"}


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


def source_type_for_item(item: dict[str, Any], rel_path: str | None, source_url: str | None) -> str:
    rel = normalize_rel_path(rel_path or "").lower()
    if rel.startswith("broll/boards/"):
        return "synthetic-motion"
    if rel.startswith("broll/generated/"):
        return "generated-image"
    if rel.startswith("broll/html/") or rel.endswith(".html"):
        return "synthetic-motion"
    if rel.startswith("broll/screen/") or "screen" in rel:
        return "screen-record"
    if rel.startswith("broll/stock/"):
        return "stock"
    if rel.startswith("broll/motion/") or item.get("motion_graphic") is True:
        return "synthetic-motion"
    if source_url:
        provider = provider_from_url(source_url)
        return "stock" if provider else "webpage"
    return "manual"


def validate_intent_item(item: dict[str, Any], index: int, errors: list[str]) -> None:
    forbidden = sorted(field for field in IDENTITY_FIELDS if field in item)
    if forbidden:
        errors.append(f"items[{index}] contains resolver-owned fields: {', '.join(forbidden)}")
    if "local_path" not in item and "source_url" not in item:
        errors.append(f"items[{index}] must include local_path or source_url")


def resolve_item(project_dir: Path, item: dict[str, Any], index: int, errors: list[str]) -> dict[str, Any] | None:
    validate_intent_item(item, index, errors)
    local_path = item.get("local_path")
    source_url = item.get("source_url")
    if local_path is not None and not isinstance(local_path, str):
        errors.append(f"items[{index}].local_path must be a string")
        return None
    if source_url is not None and not isinstance(source_url, str):
        errors.append(f"items[{index}].source_url must be a string")
        return None

    resolved = dict(item)
    source_type = source_type_for_item(item, local_path, source_url)
    resolved["source_type"] = source_type

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

    return resolved


def resolve_manifest(project_dir: Path, input_path: Path, manifest: Any) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {}, ["selected visuals intent manifest must be an object"]
    if "resolver" in manifest:
        errors.append("input already contains resolver metadata; pass the intent manifest, not a resolved manifest")
    items = manifest.get("items")
    if not isinstance(items, list):
        return {}, ["selected visuals intent manifest must include an items array"]

    resolved_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object")
            continue
        resolved = resolve_item(project_dir, item, index, errors)
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
