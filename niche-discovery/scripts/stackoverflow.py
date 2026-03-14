#!/usr/bin/env python3
"""
Stack Exchange API miner — finds unanswered questions and high-vote unsolved problems.

Usage: python scripts/stackoverflow.py <keyword> [options]
"""

import sys
import json
import time
import argparse

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import make_session, safe_get, load_env_key, dry_run_check, output_result, output_error


BASE_URL = "https://api.stackexchange.com/2.3"


def search_questions(session, keyword: str, site: str, key: str = None,
                     page_size: int = 100, max_pages: int = 3) -> list:
    """Search Stack Exchange for questions matching keyword."""
    params = {
        "order": "desc",
        "sort": "votes",
        "q": keyword,
        "site": site,
        "pagesize": page_size,
        "filter": "withbody",
    }
    if key:
        params["key"] = key

    all_questions = []
    for page in range(1, max_pages + 1):
        params["page"] = page
        resp = safe_get(session, f"{BASE_URL}/search/advanced", params=params)
        if resp is None or resp.status_code != 200:
            break
        try:
            data = resp.json()
            items = data.get("items", [])
            all_questions.extend(items)
            if not data.get("has_more", False):
                break
            # Respect backoff if provided
            backoff = data.get("backoff", 0)
            if backoff:
                print(f"Stack Exchange backoff: waiting {backoff}s", file=sys.stderr)
                time.sleep(backoff)
        except Exception as e:
            print(f"SE parse error: {e}", file=sys.stderr)
            break
        time.sleep(0.5)

    return all_questions


def main():
    parser = argparse.ArgumentParser(description="Mine Stack Exchange for unanswered questions and pain points")
    parser.add_argument("keyword", help="Niche keyword to research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    parser.add_argument("--site", default="stackoverflow",
                        help="Stack Exchange site (default: stackoverflow). Others: softwareengineering, ux, etc.")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages to fetch (default: 3, 100 items each)")
    parser.add_argument("--queries", nargs="+", help="Ignored by this script (for compatibility)")
    parser.add_argument("--query-templates", nargs="+", help="Ignored by this script (for compatibility)")
    parser.add_argument("--subreddits", nargs="+", help="Ignored by this script (for compatibility)")
    args = parser.parse_args()

    kw = args.keyword
    dry_run_check(args, f"Search Stack Exchange ({args.site}) for '{kw}'", [
        f"GET {BASE_URL}/search/advanced?q={kw}&site={args.site}&sort=votes (up to {args.max_pages} pages)",
    ])

    key = load_env_key("STACKEXCHANGE_KEY")
    session = make_session()

    print(f"Searching {args.site} for: {kw}", file=sys.stderr)
    if not key:
        print("Tip: Set STACKEXCHANGE_KEY for 10,000 req/day (vs 300/day without)", file=sys.stderr)

    questions = search_questions(session, kw, args.site, key=key, max_pages=args.max_pages)
    print(f"Found {len(questions)} questions", file=sys.stderr)

    formatted = []
    tag_counts = {}
    unanswered_count = 0

    for q in questions:
        is_answered = q.get("is_answered", False)
        answer_count = q.get("answer_count", 0)
        if not is_answered:
            unanswered_count += 1
        tags = q.get("tags", [])
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        body = q.get("body", "") or ""
        formatted.append({
            "title": q.get("title", ""),
            "body_preview": body[:500],
            "score": q.get("score", 0),
            "answer_count": answer_count,
            "view_count": q.get("view_count", 0),
            "tags": tags,
            "is_answered": is_answered,
            "link": q.get("link", ""),
            "creation_date": q.get("creation_date", 0),
        })

    top_tags = sorted(
        [{"tag": k, "count": v} for k, v in tag_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:20]

    output_result({
        "source": "stack_overflow",
        "keyword": kw,
        "site": args.site,
        "total_questions": len(formatted),
        "unanswered_count": unanswered_count,
        "questions": formatted,
        "top_tags": top_tags,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_error("stack_overflow", str(e))
        sys.exit(1)
