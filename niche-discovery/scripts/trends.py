#!/usr/bin/env python3
"""
Google Trends miner via pytrends.

Usage: python scripts/trends.py <keyword> [options]
"""

import sys
import json
import time
import argparse

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import dry_run_check, output_result, output_error


def compute_trend_direction(values: list) -> str:
    """Determine if interest is rising, stable, declining, or seasonal."""
    if len(values) < 4:
        return "unknown"
    peak = max(values) if values else 0
    if peak == 0:
        return "unknown"
    # Seasonal: many near-zero weeks interspersed with clear spikes
    near_zero = sum(1 for v in values if v < peak * 0.2)
    if near_zero / len(values) > 0.4 and peak >= 50:
        return "seasonal"
    first_quarter = sum(values[:len(values)//4]) / max(len(values)//4, 1)
    last_quarter = sum(values[-len(values)//4:]) / max(len(values)//4, 1)
    if first_quarter == 0:
        return "rising" if last_quarter > 0 else "unknown"
    pct_change = (last_quarter - first_quarter) / first_quarter * 100
    if pct_change > 10:
        return "rising"
    elif pct_change < -10:
        return "declining"
    return "stable"


def derive_broad_keyword(kw: str) -> str:
    """
    Strip low-signal trailing words (app, software, tool, platform) and
    return a shorter keyword more likely to have Trends volume.
    Falls back to first 3 words if the result would be empty.
    """
    noise_suffixes = {"app", "apps", "software", "tool", "tools", "platform",
                      "application", "applications", "program", "programs"}
    words = kw.split()
    trimmed = [w for w in words if w.lower() not in noise_suffixes]
    if not trimmed:
        trimmed = words
    # Also cap at 4 words to stay within Trends' sweet spot
    broad = " ".join(trimmed[:4])
    return broad if broad != kw else kw


def main():
    parser = argparse.ArgumentParser(description="Mine Google Trends for keyword interest and related queries")
    parser.add_argument("keyword", help="Niche keyword to research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    parser.add_argument("--timeframe", default="today 12-m", help="Trends timeframe (default: 'today 12-m')")
    parser.add_argument("--geo", default="", help="Country code (default: worldwide)")
    parser.add_argument("--broad-keyword", help="Override the broad keyword used for Trends (default: auto-derived)")
    args = parser.parse_args()

    kw = args.keyword
    broad_kw = args.broad_keyword or derive_broad_keyword(kw)
    if broad_kw != kw:
        print(f"Trends: using broader keyword '{broad_kw}' (derived from '{kw}')", file=sys.stderr)

    dry_run_check(args, f"Fetch Google Trends for '{broad_kw}'", [
        f"pytrends interest_over_time: {broad_kw} [{args.timeframe}]",
        f"pytrends related_queries: {broad_kw}",
        f"pytrends related_topics: {broad_kw}",
    ])

    try:
        from pytrends.request import TrendReq
    except ImportError:
        output_error("google_trends", "pytrends not installed. Run: pip install pytrends", keyword=kw)
        sys.exit(1)

    print(f"Connecting to Google Trends for: {broad_kw}", file=sys.stderr)
    pytrends = TrendReq(hl="en-US", tz=360)

    try:
        pytrends.build_payload([broad_kw], timeframe=args.timeframe, geo=args.geo)
    except Exception as e:
        output_error("google_trends", f"Failed to build payload: {e}", keyword=kw)
        sys.exit(1)

    # Interest over time
    print("Fetching interest over time...", file=sys.stderr)
    try:
        iot_df = pytrends.interest_over_time()
        time.sleep(2)
    except Exception as e:
        output_error("google_trends", f"Failed to fetch interest over time: {e}", keyword=kw)
        sys.exit(1)

    interest_over_time = []
    values = []
    if not iot_df.empty and broad_kw in iot_df.columns:
        for date, row in iot_df.iterrows():
            v = int(row[broad_kw])
            values.append(v)
            interest_over_time.append({"date": str(date)[:10], "value": v})

    trend_direction = compute_trend_direction(values)
    avg_interest = int(sum(values) / len(values)) if values else 0
    peak_interest = max(values) if values else 0

    # Related queries
    print("Fetching related queries...", file=sys.stderr)
    related_rising = []
    related_top = []
    try:
        rq = pytrends.related_queries()
        time.sleep(2)
        if rq and broad_kw in rq:
            if rq[broad_kw].get("rising") is not None:
                related_rising = rq[broad_kw]["rising"]["query"].tolist()[:20]
            if rq[broad_kw].get("top") is not None:
                related_top = rq[broad_kw]["top"]["query"].tolist()[:20]
    except Exception as e:
        print(f"Warning: related_queries failed: {e}", file=sys.stderr)

    # Related topics
    print("Fetching related topics...", file=sys.stderr)
    related_topics = []
    try:
        rt = pytrends.related_topics()
        time.sleep(2)
        if rt and broad_kw in rt:
            if rt[broad_kw].get("rising") is not None:
                related_topics = rt[broad_kw]["rising"]["topic_title"].tolist()[:10]
    except Exception as e:
        print(f"Warning: related_topics failed: {e}", file=sys.stderr)

    output_result({
        "source": "google_trends",
        "keyword": kw,
        "broad_keyword_used": broad_kw,
        "trend_direction": trend_direction,
        "interest_over_time": interest_over_time,
        "avg_interest": avg_interest,
        "peak_interest": peak_interest,
        "related_queries_rising": related_rising,
        "related_queries_top": related_top,
        "related_topics": related_topics,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_error("google_trends", str(e))
        sys.exit(1)
