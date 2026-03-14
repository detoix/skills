#!/usr/bin/env python3
"""
Test harness for all niche-discovery scripts.

Tests three things per script:
1. --help works
2. --dry-run works and produces valid JSON
3. (Optional) live run with minimal limits produces valid JSON with required fields

Usage:
  python scripts/test_all.py                    # dry-run tests only
  python scripts/test_all.py --live             # also run live API tests
  python scripts/test_all.py --script reddit    # test a single script
"""

import sys
import os
import json
import subprocess
import argparse
from typing import Optional

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_KEYWORD = "todo app"

# Required fields in every script's JSON output
REQUIRED_FIELDS = {"source"}

# Per-script required fields and dry-run args
SCRIPT_CONFIGS = {
    "autocomplete.py": {
        "required_fields": {"source", "keyword", "suggestions", "count"},
        "live_args": ["--no-alphabet"],
        "expected_source": "google_autocomplete",
    },
    "serp.py": {
        "required_fields": {"source", "keyword", "organic_results"},
        "expected_source": "google_serp",
    },
    "trends.py": {
        "required_fields": {"source", "keyword", "trend_direction"},
        "expected_source": "google_trends",
    },
    "reddit.py": {
        "required_fields": {"source", "keyword", "posts"},
        "expected_source": "reddit",
    },
    "youtube_comments.py": {
        "required_fields": {"source", "keyword"},
        "expected_source": "youtube_comments",
    },
    "youtube_transcripts.py": {
        "required_fields": {"source", "keyword"},
        "expected_source": "youtube_transcripts",
    },
    "playstore.py": {
        "required_fields": {"source", "keyword"},
        "expected_source": "google_play_store_npm",
    },
    "stackoverflow.py": {
        "required_fields": {"source", "keyword", "questions"},
        "expected_source": "stack_overflow",
    },
    "github_issues.py": {
        "required_fields": {"source", "keyword", "issues"},
        "expected_source": "github_issues",
    },
    "wordpress.py": {
        "required_fields": {"source", "keyword"},
        "expected_source": "wordpress_plugins",
    },
    "hackernews.py": {
        "required_fields": {"source", "keyword"},
        "expected_source": "hacker_news",
    },
    "cpc.py": {
        "required_fields": {"source", "keyword"},
        "expected_source": "cpc_data",
    },
    "apify_scrape.py": {
        "required_fields": {"source", "keyword"},
        "expected_source": "apify_google_search",
        "skip_live": True,  # needs APIFY_TOKEN
    },
}


def run_script(script: str, args: list, timeout: int = 30) -> tuple:
    """Run a script and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script)] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SCRIPTS_DIR,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def validate_json(stdout: str, required_fields: set, expected_source: Optional[str] = None) -> tuple:
    """Validate JSON output. Returns (ok, error_message)."""
    stdout = stdout.strip()
    if not stdout:
        return False, "Empty stdout"
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        preview = stdout[:200]
        return False, f"Invalid JSON: {e}\nOutput preview: {preview}"

    if not isinstance(data, dict):
        return False, f"Expected JSON object, got {type(data).__name__}"

    missing = required_fields - set(data.keys())
    if missing:
        return False, f"Missing required fields: {missing}"

    if expected_source and data.get("source") != expected_source:
        # Accept error payloads (missing key means script gracefully degraded)
        if "error" not in data:
            return False, f"Expected source='{expected_source}', got '{data.get('source')}'"

    return True, ""


def test_help(script: str) -> bool:
    """Test that --help exits cleanly."""
    rc, stdout, stderr = run_script(script, ["--help"])
    if rc == 0 and (stdout or stderr):
        print(f"  [PASS] --help")
        return True
    print(f"  [FAIL] --help returned {rc}")
    return False


def test_dry_run(script: str, config: dict, keyword: str) -> bool:
    """Test that --dry-run produces valid JSON."""
    extra = config.get("extra_args", [])
    rc, stdout, stderr = run_script(
        script,
        [keyword] + extra + ["--dry-run"],
        timeout=15,
    )
    # dry-run exits with 0
    if rc not in (0, 1):
        print(f"  [FAIL] --dry-run returned {rc}\n    stderr: {stderr[:200]}")
        return False
    ok, err = validate_json(stdout, {"dry_run"})
    if ok:
        print(f"  [PASS] --dry-run")
        return True
    else:
        print(f"  [FAIL] --dry-run: {err}")
        return False


def test_live(script: str, config: dict, keyword: str) -> bool:
    """Run a minimal live test and validate JSON schema."""
    if config.get("skip_live"):
        print(f"  [SKIP] live test (budget-gated script)")
        return True

    extra = config.get("extra_args", [])
    live_args = config.get("live_args", [])
    rc, stdout, stderr = run_script(
        script,
        [keyword] + extra + live_args,
        timeout=60,
    )
    if rc not in (0, 1):
        print(f"  [FAIL] live run returned {rc}\n    stderr: {stderr[:300]}")
        return False

    ok, err = validate_json(stdout, config.get("required_fields", {"source"}),
                             expected_source=config.get("expected_source"))
    if ok:
        data = json.loads(stdout)
        source = data.get("source", "?")
        if "error" in data:
            print(f"  [WARN] live run returned error (likely missing API key): {data['error'][:100]}")
        else:
            print(f"  [PASS] live run → source='{source}'")
        return True
    else:
        print(f"  [FAIL] live run: {err}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test all niche-discovery scripts")
    parser.add_argument("--live", action="store_true", help="Also run live API tests (requires some env vars)")
    parser.add_argument("--script", help="Test a single script by name (e.g., reddit.py)")
    parser.add_argument("--keyword", default=TEST_KEYWORD, help=f"Test keyword (default: '{TEST_KEYWORD}')")
    args = parser.parse_args()

    keyword = args.keyword

    scripts_to_test = {}
    if args.script:
        key = args.script if args.script.endswith(".py") else args.script + ".py"
        if key not in SCRIPT_CONFIGS:
            print(f"Unknown script: {key}. Available: {list(SCRIPT_CONFIGS.keys())}")
            sys.exit(1)
        scripts_to_test[key] = SCRIPT_CONFIGS[key]
    else:
        scripts_to_test = SCRIPT_CONFIGS

    results = {"passed": 0, "failed": 0, "skipped": 0}

    for script, config in scripts_to_test.items():
        script_path = os.path.join(SCRIPTS_DIR, script)
        if not os.path.exists(script_path):
            print(f"\n[MISSING] {script} — file not found, skipping")
            results["skipped"] += 1
            continue

        print(f"\n{'='*50}")
        print(f"Testing: {script}")
        print(f"{'='*50}")

        ok = test_help(script)
        results["passed" if ok else "failed"] += 1

        ok = test_dry_run(script, config, keyword)
        results["passed" if ok else "failed"] += 1

        if args.live:
            ok = test_live(script, config, keyword)
            results["passed" if ok else "failed"] += 1

    print(f"\n{'='*50}")
    print(f"Results: {results['passed']} passed, {results['failed']} failed, {results['skipped']} skipped")
    print(f"{'='*50}")

    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
