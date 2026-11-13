#!/usr/bin/env python3
"""Generate a compact local growth report from YouTube analytics CSV exports."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_optional_csv(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    return read_csv(path)


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
    engaged_views = int(as_float(row.get("engagedViews")))
    avg_pct = as_float(row.get("averageViewPercentage"))
    avg_duration = as_float(row.get("averageViewDuration"))
    gained = int(as_float(row.get("subscribersGained")) - as_float(row.get("subscribersLost")))
    engaged_part = (
        f", engaged_views={engaged_views}, engaged_rate={percent(engaged_views, views):.1f}%"
        if "engagedViews" in row
        else ""
    )
    return (
        f"- {title}: views={views}, avg_view_pct={avg_pct:.1f}, "
        f"avg_view_duration_sec={avg_duration:.1f}{engaged_part}, "
        f"net_subs={gained}, score={score(row):.2f}"
    )


def percent(value: float, total: float) -> float:
    return value / max(total, 1.0) * 100.0


def supplemental_table(
    title: str,
    rows: list[dict[str, str]],
    label_key: str | list[str],
    value_key: str = "views",
    extra_key: str | None = "averageViewPercentage",
    limit: int = 10,
) -> list[str]:
    if not rows:
        return []
    total = sum(as_float(row.get(value_key)) for row in rows)
    lines = ["", f"## {title}"]
    for row in sorted(rows, key=lambda item: as_float(item.get(value_key)), reverse=True)[:limit]:
        if isinstance(label_key, list):
            label = " / ".join(row.get(key) or "<unknown>" for key in label_key)
        else:
            label = row.get(label_key) or "<unknown>"
        value = as_float(row.get(value_key))
        line = f"- {label}: {value_key}={value:.0f}, share={percent(value, total):.1f}%"
        if extra_key and extra_key in row:
            line += f", avg_view_pct={as_float(row.get(extra_key)):.1f}"
        lines.append(line)
    return lines


def diagnostics(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    view_values = [as_float(row.get("views")) for row in rows]
    retention_values = [as_float(row.get("averageViewPercentage")) for row in rows]
    low_retention = [
        row for row in rows if as_float(row.get("averageViewPercentage")) < 35.0
    ]
    high_retention_low_views = [
        row
        for row in rows
        if as_float(row.get("averageViewPercentage")) >= 45.0
        and as_float(row.get("views")) < statistics.median(view_values)
    ]
    lines = [
        "",
        "## Diagnostics",
        f"- Median views per video: {statistics.median(view_values):.0f}",
        f"- Mean views per video: {statistics.mean(view_values):.1f}",
        f"- Median average view percentage: {statistics.median(retention_values):.1f}",
        f"- Videos below 35% average view percentage: {len(low_retention)}",
        f"- Videos with >=45% average view percentage but below median views: {len(high_retention_low_views)}",
    ]
    if "engagedViews" in rows[0]:
        total_views = sum(as_float(row.get("views")) for row in rows)
        total_engaged = sum(as_float(row.get("engagedViews")) for row in rows)
        lines.append(
            f"- Engaged views / views proxy: {total_engaged:.0f}/{total_views:.0f} ({percent(total_engaged, total_views):.1f}%)"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analytics-csv", type=Path, required=True)
    parser.add_argument("--metadata-csv", type=Path)
    parser.add_argument("--traffic-source-csv", type=Path)
    parser.add_argument("--device-type-csv", type=Path)
    parser.add_argument("--subscribed-status-csv", type=Path)
    parser.add_argument("--creator-content-type-csv", type=Path)
    parser.add_argument("--country-csv", type=Path)
    parser.add_argument("--age-gender-csv", type=Path)
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
        *diagnostics(rows),
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
        *supplemental_table(
            "Traffic Sources",
            read_optional_csv(args.traffic_source_csv),
            "insightTrafficSourceType",
        ),
        *supplemental_table(
            "Creator Content Type",
            read_optional_csv(args.creator_content_type_csv),
            "creatorContentType",
        ),
        *supplemental_table(
            "Subscribed Status",
            read_optional_csv(args.subscribed_status_csv),
            "subscribedStatus",
        ),
        *supplemental_table(
            "Device Type",
            read_optional_csv(args.device_type_csv),
            "deviceType",
        ),
        *supplemental_table("Countries", read_optional_csv(args.country_csv), "country"),
        *supplemental_table(
            "Age And Gender",
            read_optional_csv(args.age_gender_csv),
            ["ageGroup", "gender"],
            value_key="viewerPercentage",
            extra_key=None,
        ),
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
