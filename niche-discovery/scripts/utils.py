#!/usr/bin/env python3
"""Shared utilities for niche-discovery scripts."""

import os
import re
import sys
import time
import json

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = os.path.join(SKILL_ROOT, "results")

# ---------------------------------------------------------------------------
# Frustration signal keywords
# ---------------------------------------------------------------------------

FRUSTRATION_KEYWORDS = [
    "i wish", "why can't", "is there a", "does anyone know",
    "frustrated", "frustrating", "annoying", "annoyed",
    "hate", "sucks", "terrible", "horrible", "worst",
    "problem with", "issue with", "bug", "broken",
    "looking for alternative", "alternative to",
    "doesn't work", "stopped working", "can't believe",
    "waste of time", "waste of money", "ripoff", "rip off",
    "missing feature", "need a way to", "should be able to",
    "used to work", "please fix", "when will", "still waiting",
    "no way to", "why is there no", "can't figure out",
    "so hard to", "impossible to", "nightmare",
    "spreadsheet", "excel", "google sheets", "manually", "manual process",
    "so slow", "too slow", "bloated", "overpriced", "expensive",
    "workflow", "workaround", "automation", "zapier", "make.com",
]


def match_frustration(text: str, dynamic_filters: list = None, keyword: str = None) -> list:
    """Return frustration keywords found in text.

    If dynamic_filters is provided, they are merged with the baseline FRUSTRATION_KEYWORDS.
    If keyword is provided, posts where the keyword doesn't appear at all
    are filtered to only high-confidence frustration signals, reducing noise
    from off-topic results (e.g. gaming posts matching 'bug' or 'hate').
    """
    text_lower = text.lower()
    search_terms = list(FRUSTRATION_KEYWORDS)
    if dynamic_filters:
        # Since dynamic_filters are now full queries, we probably won't find exact match of the query string in text often.
        # But we'll add them to the search terms anyway to prioritize exact matches if they do occur.
        search_terms.extend([f.lower() for f in dynamic_filters])

    matches = [kw for kw in search_terms if kw in text_lower]

    if keyword and matches:
        keyword_lower = keyword.lower()
        if keyword_lower not in text_lower:
            # Off-topic post: keep only unambiguous signals
            HIGH_CONFIDENCE = {
                "i wish", "why can't", "frustrated", "frustrating",
                "looking for alternative", "alternative to",
                "missing feature", "need a way to", "should be able to",
                "no way to", "why is there no", "nightmare", "impossible to",
                "used to work", "please fix", "still waiting",
            }
            if dynamic_filters:
                HIGH_CONFIDENCE.update([f.lower() for f in dynamic_filters])
            
            matches = [m for m in matches if m in HIGH_CONFIDENCE]

    return matches


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def rate_limit_sleep(seconds: float):
    """Sleep with stderr notification."""
    print(f"Rate limiting: waiting {seconds}s...", file=sys.stderr)
    time.sleep(seconds)


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

def load_env_key(name: str, required: bool = False):
    """Load API key from environment variable. Exits if required and missing."""
    val = os.environ.get(name)
    if not val:
        # Also check .env file in the skill root (two directories up from scripts/)
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{name}="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if required and not val:
        print(f"ERROR: Required env var {name} not set", file=sys.stderr)
        sys.exit(1)
    return val or None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def output_error(source: str, message: str, **extra):
    """Print a standard error JSON object to stdout."""
    result = {"error": message, "source": source}
    result.update(extra)
    print(json.dumps(result, indent=2))


def save_result(data: dict):
    """Save result JSON to ./results/ so analyze.py can read it."""
    try:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        source = str(data.get("source", "unknown")).replace("/", "_")
        keyword = str(data.get("keyword", "unknown"))
        keyword_slug = re.sub(r"[^a-z0-9]+", "_", keyword.lower()).strip("_")[:40]
        filename = f"{source}_{keyword_slug}_{int(time.time())}.json"
        filepath = os.path.join(RESULTS_DIR, filename)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Saved: results/{filename}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: could not save result: {e}", file=sys.stderr)


def output_result(data: dict):
    """Print result JSON to stdout and auto-save to results/."""
    print(json.dumps(data, indent=2, default=str))
    save_result(data)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session(user_agent: str = "niche-discovery/1.0"):
    """Create a requests.Session with a sensible default User-Agent."""
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests", file=sys.stderr)
        sys.exit(1)
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    return s


def safe_get(session, url: str, params: dict = None, timeout: int = 15, retries: int = 3):
    """GET with retries and exponential backoff. Returns Response or None."""
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"Rate limited (429). Waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            return resp
        except Exception as e:
            if attempt == retries - 1:
                print(f"Request failed after {retries} attempts: {e}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Dry-run decorator
# ---------------------------------------------------------------------------

def dry_run_check(args, description: str, would_fetch: list):
    """If --dry-run is set, print what would be fetched and exit."""
    if getattr(args, "dry_run", False):
        print(f"DRY RUN: {description}", file=sys.stderr)
        for item in would_fetch:
            print(f"  Would fetch: {item}", file=sys.stderr)
        print(json.dumps({"dry_run": True, "would_fetch": would_fetch}))
        sys.exit(0)
