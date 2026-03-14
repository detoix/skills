#!/usr/bin/env python3
"""
Google Play Store review miner using NPM google-play-scraper.
"""

import sys
import json
import subprocess
import argparse
import os

sys.path.insert(0, os.path.dirname(__file__))
from utils import match_frustration, dry_run_check, output_result, output_error

def main():
    parser = argparse.ArgumentParser(description="Mine Google Play Store reviews for pain points (NPM version)")
    parser.add_argument("keyword", help="Niche keyword to search in Play Store")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    parser.add_argument("--max-apps", type=int, default=5, help="Number of apps to analyze (default: 5)")
    parser.add_argument("--reviews-per-app", type=int, default=100, help="Reviews per app (default: 100)")
    parser.add_argument("--queries", nargs="+", help="Ignored by this script (for compatibility)")
    parser.add_argument("--query-templates", nargs="+", help="Ignored by this script (for compatibility)")
    parser.add_argument("--subreddits", nargs="+", help="Ignored by this script (for compatibility)")
    args = parser.parse_args()

    kw = args.keyword
    dry_run_check(args, f"Search Google Play Store (NPM) for '{kw}'", [
        f"npx google-play-scraper search: {kw} (top {args.max_apps} apps)",
        f"npx google-play-scraper reviews: {args.reviews_per_app} reviews per app",
    ])

    print(f"Searching Play Store (NPM) for: {kw}", file=sys.stderr)
    
    script_path = os.path.join(os.path.dirname(__file__), "gplay_npm.js")
    # Run node script directly
    cmd = [
        "node", script_path, 
        kw, str(args.max_apps), str(args.reviews_per_app)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        # Apply frustration matching to the reviews
        for review in data.get("frustration_reviews", []):
            text = review.get("review_text", "")
            review["frustration_matches"] = match_frustration(text, dynamic_filters=getattr(args, "queries", None), keyword=kw)
            
        output_result(data)
        
    except subprocess.CalledProcessError as e:
        output_error("google_play_store_npm", f"NPM script failed: {e.stderr}", keyword=kw)
        sys.exit(1)
    except json.JSONDecodeError as e:
        output_error("google_play_store_npm", f"Failed to parse NPM output: {str(e)}", keyword=kw)
        sys.exit(1)
    except Exception as e:
        output_error("google_play_store_npm", str(e), keyword=kw)
        sys.exit(1)

if __name__ == "__main__":
    main()
