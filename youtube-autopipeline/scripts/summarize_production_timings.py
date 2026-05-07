#!/usr/bin/env python3
"""Summarize production-timings.jsonl for a local video project."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    if not path.exists():
        raise FileNotFoundError(f"timings log not found: {path}")
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(event, dict):
                events.append(event)
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage: dict[str, dict[str, Any]] = defaultdict(lambda: {"runs": 0, "total_seconds": 0.0, "failures": 0})
    completed = [event for event in events if event.get("event") == "stage_end"]
    for event in completed:
        stage = str(event.get("stage") or "unknown")
        duration = float(event.get("duration_seconds") or 0.0)
        item = by_stage[stage]
        item["runs"] += 1
        item["total_seconds"] += duration
        if event.get("status") not in {"pass", "needs_review"}:
            item["failures"] += 1

    stages = []
    for stage, item in by_stage.items():
        total = float(item["total_seconds"])
        runs = int(item["runs"])
        stages.append(
            {
                "stage": stage,
                "runs": runs,
                "total_seconds": round(total, 3),
                "avg_seconds": round(total / runs, 3) if runs else 0,
                "failures": item["failures"],
            }
        )
    stages.sort(key=lambda item: item["total_seconds"], reverse=True)
    return {
        "total_completed_stage_seconds": round(sum(item["total_seconds"] for item in stages), 3),
        "completed_stage_count": len(completed),
        "stages": stages,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize local video production timing logs.")
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON summary path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    timings_path = project_dir / "manifests" / "production-timings.jsonl"
    summary = summarize(load_events(timings_path))
    output_path = args.output.resolve() if args.output else project_dir / "manifests" / "production-timings-summary.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote timing summary: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
