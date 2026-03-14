#!/usr/bin/env python3
"""
Google Autocomplete miner — extracts suggestion patterns for a keyword.

Usage: python scripts/autocomplete.py <keyword> [options]
"""

import sys
import json
import time
import argparse

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import make_session, safe_get, dry_run_check, output_result, output_error


ENDPOINT = "https://suggestqueries.google.com/complete/search"

QUERY_TEMPLATES = [
    "{kw}",
    "{kw} app",
    "{kw} software",
    "{kw} tool",
    "best {kw}",
    "{kw} alternative",
    "why is {kw}",
    "{kw} problem",
    "I wish {kw}",
    "{kw} sucks",
    "{kw} review",
    "{kw} free",
    "{kw} vs",
    "how to {kw}",
    "{kw} tutorial",
]


def fetch_suggestions(session, query: str) -> list:
    """Fetch autocomplete suggestions for a single query string."""
    resp = safe_get(session, ENDPOINT, params={"client": "firefox", "q": query})
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
        # Response format: [query, [suggestions, ...]]
        return data[1] if isinstance(data, list) and len(data) > 1 else []
    except Exception:
        return []


def fetch_alphabet_drilldown(session, keyword: str) -> list:
    """Append a-z to get deeper suggestions."""
    results = []
    for letter in "abcdefghijklmnopqrstuvwxyz":
        query = f"{keyword} {letter}"
        suggestions = fetch_suggestions(session, query)
        results.extend(suggestions)
        time.sleep(0.1)  # gentle rate limit
    return results


def main():
    parser = argparse.ArgumentParser(description="Mine Google Autocomplete for niche keyword patterns")
    parser.add_argument("keyword", help="Niche keyword to research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched without making requests")
    parser.add_argument("--no-alphabet", action="store_true", help="Skip a-z drilldown (faster)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between requests (default: 0.5)")
    parser.add_argument("--query-templates", nargs="+", help="Dynamic list of query templates containing {kw}")
    args = parser.parse_args()

    kw = args.keyword
    
    templates = list(QUERY_TEMPLATES)
    if getattr(args, "query_templates", None):
        # Add user/agent provided templates, ensuring they are unique
        for qt in args.query_templates:
            if qt not in templates:
                templates.insert(0, qt) # Prioritize custom templates
                
    queries = [t.format(kw=kw) for t in templates]
    would_fetch = [f"GET {ENDPOINT}?q={q}" for q in queries]
    if not args.no_alphabet:
        would_fetch.append(f"GET {ENDPOINT}?q={kw} [a-z] (26 requests)")

    dry_run_check(args, f"Fetch Google Autocomplete for '{kw}'", would_fetch)

    session = make_session()
    all_suggestions = set()
    queries_used = 0

    print(f"Fetching autocomplete for: {kw}", file=sys.stderr)

    for query in queries:
        suggestions = fetch_suggestions(session, query)
        all_suggestions.update(suggestions)
        queries_used += 1
        time.sleep(args.delay)

    if not args.no_alphabet:
        print("Running alphabet drilldown...", file=sys.stderr)
        alpha_suggestions = fetch_alphabet_drilldown(session, kw)
        all_suggestions.update(alpha_suggestions)
        queries_used += 26

    # Filter out the base keyword itself
    suggestions_list = sorted(s for s in all_suggestions if s.lower() != kw.lower())

    # Low signal: automatically try keyword expansions and suggest reframes
    reframes = []
    if len(suggestions_list) < 3:
        print(f"Low signal ({len(suggestions_list)} suggestions). Trying keyword expansions...", file=sys.stderr)
        expansion_candidates = [
            f"{kw} software", f"{kw} tool", f"{kw} platform", f"best {kw}",
        ]
        # Also try dropping the last word (e.g. "3d map configurator" → "3d map")
        words = kw.split()
        if len(words) > 2:
            expansion_candidates.append(" ".join(words[:-1]))
        # And replacing the first word (e.g. "3d map configurator" → "interactive map configurator")
        # Just try without the first word
        if len(words) > 2:
            expansion_candidates.append(" ".join(words[1:]))

        for candidate in expansion_candidates:
            if candidate == kw:
                continue
            exp_suggestions = set()
            for tmpl in templates[:6]:
                q = tmpl.format(kw=candidate)
                exp_suggestions.update(fetch_suggestions(session, q))
                time.sleep(0.3)
            count = len([s for s in exp_suggestions if s.lower() != candidate.lower()])
            if count >= 3:
                reframes.append({
                    "keyword": candidate,
                    "suggestion_count": count,
                    "sample": sorted(s for s in exp_suggestions if s.lower() != candidate.lower())[:3],
                })

        if reframes:
            best = max(reframes, key=lambda r: r["suggestion_count"])
            print(f"Suggested reframe: '{best['keyword']}' ({best['suggestion_count']} suggestions)", file=sys.stderr)

    output_result({
        "source": "google_autocomplete",
        "keyword": kw,
        "suggestions": suggestions_list,
        "count": len(suggestions_list),
        "query_variations_used": queries_used,
        "low_signal_reframes": reframes,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_error("google_autocomplete", str(e))
        sys.exit(1)
