#!/usr/bin/env python3
"""
Pre-flight token check — run this before a research session to confirm
which API keys are loaded. Exits 0 if all required keys are present.

Usage: python scripts/check_tokens.py
"""

import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from utils import load_env_key

TOKENS = [
    ("YOUTUBE_API_KEY",    "required", "youtube_comments.py, youtube_transcripts.py"),
    ("APIFY_TOKEN",        "required", "apify_scrape.py (Google Search SERP via Apify actor)"),
    ("REDDIT_CLIENT_ID",   "optional", "reddit.py (6x rate limit boost)"),
    ("GITHUB_TOKEN",       "optional", "github_issues.py (5000 req/hr vs 60)"),
    ("STACKEXCHANGE_KEY",  "optional", "stackoverflow.py (10k req/day vs 300)"),
]

missing_required = []
print("Token status:")
for name, level, used_by in TOKENS:
    val = load_env_key(name)
    status = "SET" if val else ("MISSING" if level == "required" else "not set")
    marker = "OK" if val else ("!!" if level == "required" else "--")
    print(f"  [{marker}] {name:<25} {status:<10}  ({used_by})")
    if not val and level == "required":
        missing_required.append(name)

print()
if missing_required:
    print(f"WARNING: {len(missing_required)} required token(s) missing: {', '.join(missing_required)}")
    print("Add them to: .env (in the niche-discovery skill root)")
    sys.exit(1)
else:
    print("All required tokens are set. Ready to run.")
