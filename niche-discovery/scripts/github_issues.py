#!/usr/bin/env python3
"""
GitHub Issues miner — finds open issues and feature requests with high community pain.

Usage: python scripts/github_issues.py <keyword> [options]
"""

import sys
import json
import time
import argparse

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import make_session, safe_get, load_env_key, dry_run_check, output_result, output_error


SEARCH_URL = "https://api.github.com/search/issues"


def search_issues(session, query: str, per_page: int = 30, page: int = 1) -> dict:
    """Search GitHub issues API."""
    resp = safe_get(session, SEARCH_URL, params={
        "q": query,
        "per_page": per_page,
        "page": page,
        "sort": "reactions",
        "order": "desc",
    })
    if resp is None:
        return {}
    if resp.status_code == 403:
        print("GitHub rate limit hit. Set GITHUB_TOKEN for 5,000 req/hr.", file=sys.stderr)
        return {}
    if resp.status_code != 200:
        print(f"GitHub API error {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        return {}
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Mine GitHub Issues for shared pain points and feature requests")
    parser.add_argument("keyword", help="Niche keyword to research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    parser.add_argument("--max-results", type=int, default=100, help="Max issues to retrieve (default: 100)")
    parser.add_argument("--labels", nargs="+",
                        default=["bug", "feature-request", "enhancement", "help wanted"],
                        help="Issue labels to target")
    parser.add_argument("--queries", nargs="+", help="Ignored by this script (for compatibility)")
    parser.add_argument("--query-templates", nargs="+", help="Ignored by this script (for compatibility)")
    parser.add_argument("--subreddits", nargs="+", help="Ignored by this script (for compatibility)")
    args = parser.parse_args()

    kw = args.keyword
    dry_run_check(args, f"Search GitHub Issues for '{kw}'", [
        f"GET {SEARCH_URL}?q={kw}+type:issue+state:open",
        f"GET {SEARCH_URL}?q={kw}+type:issue+label:bug",
        f"... (one query per label: {args.labels})",
    ])

    token = load_env_key("GITHUB_TOKEN")
    session = make_session()
    if token:
        session.headers.update({"Authorization": f"token {token}"})
        print("Using GitHub token (5,000 req/hr)", file=sys.stderr)
    else:
        print("No GITHUB_TOKEN set (60 req/hr limit applies)", file=sys.stderr)

    all_issues = {}
    per_page = min(args.max_results, 30)

    # Base query
    queries = [f"{kw} type:issue state:open"]
    # Label-specific queries
    for label in args.labels:
        queries.append(f"{kw} type:issue state:open label:\"{label}\"")

    print(f"Searching GitHub Issues for: {kw}", file=sys.stderr)
    for q in queries:
        print(f"  Query: {q}", file=sys.stderr)
        data = search_issues(session, q, per_page=per_page)
        items = data.get("items", [])
        for item in items:
            issue_id = item.get("id", "")
            if issue_id and issue_id not in all_issues:
                all_issues[issue_id] = item
        time.sleep(1)

    print(f"Total unique issues: {len(all_issues)}", file=sys.stderr)

    formatted = []
    repo_counts = {}

    for item in all_issues.values():
        body = item.get("body", "") or ""
        reactions = item.get("reactions", {})
        total_reactions = sum(
            v for k, v in reactions.items()
            if k not in ("url", "total_count") and isinstance(v, int)
        ) if reactions else 0
        repo_url = item.get("repository_url", "")
        repo = repo_url.replace("https://api.github.com/repos/", "") if repo_url else ""
        labels = [l.get("name", "") for l in item.get("labels", [])]
        repo_counts[repo] = repo_counts.get(repo, 0) + 1

        formatted.append({
            "title": item.get("title", ""),
            "body_preview": body[:500],
            "reactions_total": total_reactions,
            "comments": item.get("comments", 0),
            "repo": repo,
            "labels": labels,
            "url": item.get("html_url", ""),
            "created_at": item.get("created_at", ""),
        })

    # Sort by reactions + comments
    formatted.sort(key=lambda x: (x["reactions_total"] + x["comments"]), reverse=True)

    top_repos = sorted(
        [{"repo": k, "issue_count": v} for k, v in repo_counts.items()],
        key=lambda x: x["issue_count"],
        reverse=True,
    )[:10]

    output_result({
        "source": "github_issues",
        "keyword": kw,
        "total_issues": len(formatted),
        "issues": formatted[:args.max_results],
        "top_repos": top_repos,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_error("github_issues", str(e))
        sys.exit(1)
