#!/usr/bin/env python3
"""Generate a compact local growth report from YouTube analytics CSV exports."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def merge_metadata(rows: list[dict[str, str]], metadata_path: Path | None) -> list[dict[str, str]]:
    if not metadata_path or not metadata_path.exists():
        return rows
    metadata = {row.get("video"): row for row in read_csv(metadata_path)}
    merged = []
    for row in rows:
        item = dict(row)
        item.update({f"meta_{key}": value for key, value in metadata.get(row.get("video"), {}).items()})
        merged.append(item)
    return merged


def score(row: dict[str, str]) -> float:
    views = as_float(row.get("views"))
    avg_pct = as_float(row.get("averageViewPercentage"))
    likes = as_float(row.get("likes"))
    shares = as_float(row.get("shares"))
    subscribers = as_float(row.get("subscribersGained")) - as_float(row.get("subscribersLost"))
    engagement = (likes + shares + max(subscribers, 0.0)) / max(views, 1.0)
    return (avg_pct * 0.65) + (engagement * 100.0 * 0.35)


def line_for(row: dict[str, str]) -> str:
    title = row.get("meta_title") or row.get("video") or "<unknown>"
    views = int(as_float(row.get("views")))
    avg_pct = as_float(row.get("averageViewPercentage"))
    avg_duration = as_float(row.get("averageViewDuration"))
    gained = int(as_float(row.get("subscribersGained")) - as_float(row.get("subscribersLost")))
    return (
        f"- {title}: views={views}, avg_view_pct={avg_pct:.1f}, "
        f"avg_view_duration_sec={avg_duration:.1f}, net_subs={gained}, score={score(row):.2f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analytics-csv", type=Path, required=True)
    parser.add_argument("--metadata-csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    rows = merge_metadata(read_csv(args.analytics_csv), args.metadata_csv)
    ranked = sorted(rows, key=score, reverse=True)
    by_views = sorted(rows, key=lambda row: as_float(row.get("views")), reverse=True)

    total_views = sum(as_float(row.get("views")) for row in rows)
    total_subs = sum(
        as_float(row.get("subscribersGained")) - as_float(row.get("subscribersLost"))
        for row in rows
    )
    weighted_retention = sum(
        as_float(row.get("averageViewPercentage")) * as_float(row.get("views")) for row in rows
    ) / max(total_views, 1.0)

    sections = [
        "# YouTube Growth Report",
        "",
        f"Videos analyzed: {len(rows)}",
        f"Total views: {int(total_views)}",
        f"Net subscribers: {int(total_subs)}",
        f"View-weighted average view percentage: {weighted_retention:.1f}",
        "",
        "## Best Overall",
        *[line_for(row) for row in ranked[: args.top]],
        "",
        "## Most Viewed",
        *[line_for(row) for row in by_views[: args.top]],
        "",
        "## Interpretation Rules",
        "- Treat high retention with low views as a format candidate that needs better packaging or distribution.",
        "- Treat high views with low retention as a hook/topic candidate that needs tighter pacing.",
        "- Treat high shares and subscriber gain as stronger growth signals than likes alone.",
    ]
    report = "\n".join(sections) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
