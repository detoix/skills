#!/usr/bin/env python3
"""
Apify Google Search Scraper — mines SERP results for niche pain point research.

Runs multiple complaint/alternative/problem-framed queries against Google Search
via Apify's official google-search-scraper actor. Extracts organic results,
People Also Ask, and related queries.

$5/month free credit on Apify — covers 1,000+ results (~10 sessions at default settings).

Usage: python scripts/apify_scrape.py <keyword> [options]
"""

import sys
import json
import time
import argparse

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import (make_session, safe_get, load_env_key,
                   match_frustration, dry_run_check, output_result, output_error)


APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "apify/google-search-scraper"

SEARCH_TEMPLATES = [
    "{keyword} problems",
    "{keyword} alternatives",
    "{keyword} complaints",
    "best {keyword} software",
    "{keyword} not working",
]

COST_ESTIMATE = 0.50  # ~$0.50 per typical run (5 queries × 2 pages × 10 results)


def build_actor_input(keyword: str, max_pages: int = 2) -> dict:
    queries = [t.format(keyword=keyword) for t in SEARCH_TEMPLATES]
    return {
        "queries": "\n".join(queries),
        "maxPagesPerQuery": max_pages,
        "countryCode": "us",
        "languageCode": "en",
    }


def run_actor(session, token: str, actor_input: dict, budget_limit: float) -> dict:
    """Start an Apify actor run and poll for completion."""
    actor_path = ACTOR_ID.replace("/", "~")
    start_url = f"{APIFY_BASE}/acts/{actor_path}/runs?token={token}"
    print(f"Starting Apify actor: {ACTOR_ID}", file=sys.stderr)
    try:
        import requests
        resp = requests.post(start_url, json=actor_input, timeout=30)
    except Exception as e:
        return {"error": f"Failed to start actor: {e}"}

    if resp.status_code not in (200, 201):
        return {"error": f"Actor start failed: {resp.status_code} {resp.text[:200]}"}

    run_data = resp.json().get("data", {})
    run_id = run_data.get("id")
    if not run_id:
        return {"error": "No run ID returned from Apify"}

    print(f"Run started: {run_id}. Polling for completion...", file=sys.stderr)

    for attempt in range(60):
        time.sleep(5)
        status_resp = safe_get(session, f"{APIFY_BASE}/actor-runs/{run_id}",
                               params={"token": token})
        if status_resp is None:
            continue
        status_data = status_resp.json().get("data", {})
        run_status = status_data.get("status", "")
        usage = status_data.get("usageTotalUsd", 0) or 0

        print(f"  Status: {run_status} | Cost so far: ${usage:.4f}", file=sys.stderr)

        if usage > budget_limit:
            print(f"Budget limit ${budget_limit} exceeded. Aborting.", file=sys.stderr)
            safe_get(session, f"{APIFY_BASE}/actor-runs/{run_id}/abort",
                     params={"token": token})
            return {"error": f"Budget limit exceeded: ${usage:.4f} > ${budget_limit}",
                    "actual_cost": usage}

        if run_status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            if run_status != "SUCCEEDED":
                return {"error": f"Actor run ended with status: {run_status}",
                        "actual_cost": usage}
            return {"dataset_id": status_data.get("defaultDatasetId"), "actual_cost": usage}

    return {"error": "Actor timed out after 5 minutes"}


def fetch_dataset(session, token: str, dataset_id: str) -> list:
    resp = safe_get(session, f"{APIFY_BASE}/datasets/{dataset_id}/items",
                    params={"token": token, "limit": 1000})
    if resp is None or resp.status_code != 200:
        return []
    return resp.json() if isinstance(resp.json(), list) else resp.json().get("items", [])


def format_results(items: list, keyword: str, dynamic_filters: list = None) -> tuple:
    """Parse dataset items into organic results, PAA questions, and related queries."""
    organic = []
    people_also_ask = []
    related = []
    seen_urls = set()

    for page in items:
        sq = page.get("searchQuery", {})
        query = sq.get("term", "") if isinstance(sq, dict) else str(sq)

        for r in page.get("organicResults", []):
            url = r.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title = r.get("title", "") or ""
            snippet = (r.get("description", "") or "")[:400]
            text = title + " " + snippet
            organic.append({
                "query": query,
                "title": title,
                "url": url,
                "snippet": snippet,
                "frustration_matches": match_frustration(text, dynamic_filters=dynamic_filters, keyword=keyword),
            })

        for paa in page.get("peopleAlsoAsk", []):
            q = paa.get("question", "") if isinstance(paa, dict) else str(paa)
            if q and q not in people_also_ask:
                people_also_ask.append(q)

        for rq in page.get("relatedQueries", []):
            q = rq.get("query", "") if isinstance(rq, dict) else str(rq)
            if q and q not in related:
                related.append(q)

    frustration_results = [r for r in organic if r["frustration_matches"]]
    return organic, frustration_results, people_also_ask, related


def main():
    parser = argparse.ArgumentParser(
        description="Mine Google Search results for niche pain points via Apify. "
                    "Runs complaint/alternative/problem queries and extracts SERP signals."
    )
    parser.add_argument("keyword", help="Niche keyword to research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    parser.add_argument("--budget-limit", type=float, default=1.00,
                        help="Max USD to spend on this run (default: $1.00)")
    parser.add_argument("--max-pages", type=int, default=2,
                        help="Pages per query (default: 2, ~20 results per query)")
    parser.add_argument("--queries", nargs="+", help="Dynamic list of full search queries generated by the agent")
    parser.add_argument("--query-templates", nargs="+", help="Ignored by this script (for compatibility)")
    parser.add_argument("--subreddits", nargs="+", help="Ignored by this script (for compatibility)")
    args = parser.parse_args()

    kw = args.keyword
    queries = [t.format(keyword=kw) for t in SEARCH_TEMPLATES]

    dry_run_check(args, f"Run Apify Google Search Scraper for '{kw}'", [
        f"Actor: {ACTOR_ID}",
        f"Queries: {queries}",
        f"Pages per query: {args.max_pages}",
        f"Estimated cost: ~${COST_ESTIMATE:.2f} of your $5/mo free credit",
        f"Budget limit: ${args.budget_limit:.2f}",
    ])

    token = load_env_key("APIFY_TOKEN")
    if not token:
        output_error("apify_google_search",
                     "APIFY_TOKEN not set. Get your free token at apify.com (no credit card required).",
                     keyword=kw)
        sys.exit(1)

    print(f"Running Apify Google Search for: {kw} (est. ~${COST_ESTIMATE:.2f} of $5/mo free credit)",
          file=sys.stderr)

    session = make_session()
    actor_input = build_actor_input(kw, max_pages=args.max_pages)
    run_result = run_actor(session, token, actor_input, args.budget_limit)

    if "error" in run_result:
        output_error("apify_google_search", run_result["error"],
                     keyword=kw, actor_used=ACTOR_ID,
                     actual_cost=run_result.get("actual_cost", 0))
        sys.exit(1)

    items = fetch_dataset(session, token, run_result["dataset_id"])
    organic, frustration_results, people_also_ask, related = format_results(items, kw, dynamic_filters=getattr(args, "queries", None))

    output_result({
        "source": "apify_google_search",
        "keyword": kw,
        "actor_used": ACTOR_ID,
        "actual_cost": run_result.get("actual_cost", 0),
        "queries_run": queries,
        "organic_results_count": len(organic),
        "frustration_results_count": len(frustration_results),
        "organic_results": organic,
        "frustration_results": frustration_results,
        "people_also_ask": people_also_ask,
        "related_queries": related,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_error("apify_google_search", str(e))
        sys.exit(1)
