#!/usr/bin/env python3
"""
SERP miner — organic results and related searches via DuckDuckGo.

Free, no API key, no account required.

Usage: python scripts/serp.py <keyword> [options]
"""

import sys
import json
import argparse

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import make_session, dry_run_check, output_result, output_error

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


def fetch_duckduckgo(session, keyword: str) -> dict:
    """Scrape DuckDuckGo HTML results."""
    if not BS4_AVAILABLE:
        return None

    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        import requests as req
        resp = req.post(url, data={"q": keyword, "kl": "us-en"}, headers=headers, timeout=15)
    except Exception as e:
        print(f"DuckDuckGo request failed: {e}", file=sys.stderr)
        return None

    if resp.status_code != 200:
        print(f"DuckDuckGo error {resp.status_code}", file=sys.stderr)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    organic = []
    for result in soup.select(".result__body"):
        title_el = result.select_one(".result__title")
        url_el = result.select_one(".result__url")
        snippet_el = result.select_one(".result__snippet")
        if not title_el:
            continue
        organic.append({
            "title": title_el.get_text(strip=True),
            "url": url_el.get_text(strip=True) if url_el else "",
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })

    if not organic:
        print("DuckDuckGo returned no results (may be temporarily rate-limited, try again in a minute)", file=sys.stderr)
        return None

    related = [a.get_text(strip=True) for a in soup.select(".related-searches__item a")][:10]

    return {
        "provider_used": "duckduckgo",
        "organic_results": organic[:10],
        "people_also_ask": [],
        "related_searches": related,
        "total_results_estimate": 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Mine DuckDuckGo SERP for competitor and market signals")
    parser.add_argument("keyword", help="Niche keyword to research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    args = parser.parse_args()

    kw = args.keyword
    dry_run_check(args, f"Fetch DuckDuckGo SERP for '{kw}'", [
        f"POST https://html.duckduckgo.com/html/ q={kw}",
    ])

    if not BS4_AVAILABLE:
        output_error("google_serp", "beautifulsoup4 not installed. Run: pip install beautifulsoup4", keyword=kw)
        sys.exit(1)

    session = make_session()
    print(f"Fetching DuckDuckGo results for: {kw}", file=sys.stderr)
    result = fetch_duckduckgo(session, kw)

    if result is None:
        output_error("google_serp", "DuckDuckGo returned no results. Wait a moment and retry.", keyword=kw)
        sys.exit(1)

    result.update({"source": "google_serp", "keyword": kw})
    output_result(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output_error("google_serp", str(e))
        sys.exit(1)
