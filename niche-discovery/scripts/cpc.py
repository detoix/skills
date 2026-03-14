#!/usr/bin/env python3
"""
CPC / keyword volume estimator.

No free API exists for accurate CPC data. This script provides a
heuristic estimate based on Google Autocomplete suggestion count
as a proxy for search demand.

For real CPC data, check manually: Google Keyword Planner (free with
a Google Ads account), or Ubersuggest (3 free lookups/day at app.neilpatel.com).

Usage: python scripts/cpc.py <keyword> [options]
"""

import sys
import json
import subprocess
import argparse
import os

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import dry_run_check, output_result, output_error


def estimate_from_autocomplete(keyword: str, scripts_dir: str) -> dict:
    """Run autocomplete.py and use suggestion count as a demand proxy."""
    autocomplete_script = os.path.join(scripts_dir, "autocomplete.py")
    try:
        result = subprocess.run(
            [sys.executable, autocomplete_script, keyword, "--no-alphabet"],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        count = data.get("count", 0)
    except Exception:
        count = 0

    if count > 30:
        volume_estimate = "1,000–10,000/mo"
        demand = "moderate-high"
    elif count > 15:
        volume_estimate = "100–1,000/mo"
        demand = "moderate"
    elif count > 5:
        volume_estimate = "10–100/mo"
        demand = "low-moderate"
    elif count > 0:
        volume_estimate = "1–10/mo"
        demand = "low"
    else:
        volume_estimate = "~0"
        demand = "very low or too niche to measure"

    return {
        "provider": "autocomplete_heuristic",
        "autocomplete_suggestion_count": count,
        "monthly_search_volume_estimate": volume_estimate,
        "demand_signal": demand,
        "cpc": "unknown — check Google Keyword Planner manually",
        "competition": "unknown",
        "note": (
            "No free CPC API is available. Suggestion count is a rough demand proxy. "
            "For real numbers: https://ads.google.com/aw/keywordplanner (free, requires Google Ads account)"
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Estimate keyword demand via autocomplete count (no paid API)"
    )
    parser.add_argument("keyword", help="Niche keyword to research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    args = parser.parse_args()

    kw = args.keyword
    scripts_dir = os.path.dirname(os.path.abspath(__file__))

    dry_run_check(args, f"Estimate demand for '{kw}' via autocomplete count", [
        f"Run autocomplete.py '{kw}' --no-alphabet and count suggestions",
    ])

    print(f"Estimating demand for: {kw}", file=sys.stderr)
    result = estimate_from_autocomplete(kw, scripts_dir)
    result.update({"source": "cpc_data", "keyword": kw})
    output_result(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_error("cpc_data", str(e))
        sys.exit(1)
