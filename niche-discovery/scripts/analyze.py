#!/usr/bin/env python3
"""
Pain point synthesis and ranking engine.

Reads JSON output from all other scripts and produces a ranked list of
validated pain points with cross-source evidence and an opportunity verdict.

Usage:
  python scripts/analyze.py --input-dir ./results/
  cat results/*.json | python scripts/analyze.py --stdin
"""

import sys
import json
import os
import re
import argparse
from collections import defaultdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Scoring weights (must sum to 1.0)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "frequency": 0.25,          # How many times complaint appears total
    "cross_source_count": 0.30, # Biggest multiplier: N different sources
    "intensity": 0.20,          # Avg upvotes/reactions/thumbs
    "recency": 0.10,            # Recent complaints score higher
    "commercial_intent": 0.15,  # Context suggests willingness to pay
}

MAX_SCORE = 100.0
CROSS_SOURCE_MAX = 8  # Normalize cross_source_count to this ceiling


# ---------------------------------------------------------------------------
# Pain point extraction per source type
# ---------------------------------------------------------------------------

def extract_pain_points(record: dict) -> list:
    """Extract a list of (text, intensity, date, commercial_intent) from a source record."""
    source = record.get("source", "unknown")
    points = []

    def add(text, intensity=0, date="", commercial=False):
        if text and len(text.strip()) > 10:
            points.append({
                "text": text.strip()[:500],
                "intensity": intensity,
                "date": date,
                "commercial_intent": commercial,
                "source": source,
                "url": record.get("url", ""),
            })

    if source == "reddit":
        for post in record.get("posts", []):
            if post.get("frustration_matches"):
                add(
                    post.get("title", "") + " " + post.get("selftext_preview", ""),
                    intensity=post.get("score", 0),
                    date=post.get("created_utc", ""),
                )

    elif source in ("google_play_store", "apple_app_store"):
        for r in record.get("frustration_reviews", []):
            add(r.get("review_text", ""),
                intensity=r.get("thumbs_up", 0),
                commercial=True)  # App stores = paying customers

    elif source == "stack_overflow":
        for q in record.get("questions", []):
            add(q.get("title", "") + " " + q.get("body_preview", ""),
                intensity=q.get("score", 0) + q.get("view_count", 0) // 100,
                date=str(q.get("creation_date", "")))

    elif source == "github_issues":
        for issue in record.get("issues", []):
            add(issue.get("title", "") + " " + issue.get("body_preview", ""),
                intensity=issue.get("reactions_total", 0) + issue.get("comments", 0),
                date=issue.get("created_at", ""))

    elif source == "hacker_news":
        for c in record.get("frustration_comments", []):
            add(c.get("text", ""), intensity=c.get("points", 0),
                date=c.get("created_at", ""))
        for s in record.get("stories", []):
            if s.get("type") == "ask_hn":
                add(s.get("title", ""), intensity=s.get("points", 0))

    elif source == "youtube_comments":
        for c in record.get("frustration_comments", []):
            add(c.get("comment_text", ""), intensity=c.get("like_count", 0))

    elif source == "youtube_transcripts":
        for seg in record.get("pain_segments", []):
            add(seg.get("text", ""))

    elif source == "wordpress_plugins":
        for r in record.get("frustration_reviews", []):
            add(r.get("review_text", ""), commercial=True)

    elif source == "product_hunt":
        for p in record.get("products", []):
            for c in p.get("frustration_comments", []):
                add(c.get("body", ""), intensity=c.get("votes", 0))

    elif source == "apify_google_search":
        for r in record.get("frustration_results", []):
            add(r.get("title", "") + " " + r.get("snippet", ""))
        for q in record.get("people_also_ask", []):
            add(q)

    elif source == "google_news":
        for a in record.get("frustration_articles", []):
            add(a.get("title", "") + " " + a.get("snippet", ""),
                date=a.get("published", ""))

    elif source == "google_serp":
        for paa in record.get("people_also_ask", []):
            add(paa, commercial=False)

    elif source == "google_autocomplete":
        for s in record.get("suggestions", []):
            add(s)

    return points


# ---------------------------------------------------------------------------
# Clustering (keyword overlap — no ML needed)
# ---------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for", "of", "and",
    "or", "with", "this", "that", "can", "do", "i", "my", "we", "be", "are",
    "was", "not", "no", "how", "what", "why", "when", "there", "have", "has",
}


def tokenize(text: str) -> set:
    """Extract meaningful words from text."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return {w for w in words if w not in STOPWORDS}


def jaccard_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_points(points: list, threshold: float = 0.25) -> list:
    """Group similar pain points by keyword overlap. Returns list of clusters."""
    clusters = []
    point_tokens = [tokenize(p["text"]) for p in points]

    assigned = [False] * len(points)
    for i, pt in enumerate(points):
        if assigned[i]:
            continue
        cluster = [i]
        assigned[i] = True
        for j in range(i + 1, len(points)):
            if assigned[j]:
                continue
            sim = jaccard_similarity(point_tokens[i], point_tokens[j])
            if sim >= threshold:
                cluster.append(j)
                assigned[j] = True
        clusters.append(cluster)

    return clusters


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_cluster(cluster_indices: list, points: list) -> dict:
    """Compute composite score for a cluster of pain points."""
    cluster_points = [points[i] for i in cluster_indices]
    sources = list({p["source"] for p in cluster_points})
    frequency = len(cluster_points)
    cross_source_count = len(sources)
    intensities = [p["intensity"] for p in cluster_points if (p["intensity"] or 0) > 0]
    avg_intensity = sum(intensities) / len(intensities) if intensities else 0.0
    has_commercial = any(p["commercial_intent"] for p in cluster_points)

    # Recency: score 1.0 if any mention in last 12 months, 0.5 otherwise
    recency_score = 0.5
    now_year = datetime.now().year
    for p in cluster_points:
        date_str = p.get("date", "")
        if date_str and str(now_year) in date_str:
            recency_score = 1.0
            break
        if date_str and str(now_year - 1) in date_str:
            recency_score = 0.8

    # Normalize components to 0-1
    freq_norm = min(frequency / 50, 1.0)
    cross_norm = min(cross_source_count / CROSS_SOURCE_MAX, 1.0)
    intensity_norm = min(avg_intensity / 200, 1.0)
    commercial_norm = 1.0 if has_commercial else 0.4

    composite = (
        WEIGHTS["frequency"] * freq_norm +
        WEIGHTS["cross_source_count"] * cross_norm +
        WEIGHTS["intensity"] * intensity_norm +
        WEIGHTS["recency"] * recency_score +
        WEIGHTS["commercial_intent"] * commercial_norm
    ) * MAX_SCORE

    # Representative summary: pick the shortest, most representative text
    best_text = min(cluster_points, key=lambda p: len(p["text"]))["text"]

    # Top evidence per source (up to 2 per source)
    evidence = []
    seen_sources = defaultdict(int)
    for p in sorted(cluster_points, key=lambda x: x["intensity"] or 0, reverse=True):
        src = p["source"]
        if seen_sources[src] < 2:
            evidence.append({
                "source": src,
                "text": p["text"][:300],
                "url": p.get("url", ""),
                "score": p["intensity"],
            })
            seen_sources[src] += 1
        if len(evidence) >= 6:
            break

    return {
        "summary": best_text[:200],
        "composite_score": round(composite, 1),
        "frequency": frequency,
        "cross_source_count": cross_source_count,
        "sources": sources,
        "evidence": evidence,
        "intensity_avg": round(avg_intensity, 1),
        "has_existing_solution": False,  # Enriched by analyze workflow, not automated
    }


# ---------------------------------------------------------------------------
# Opportunity gap detection
# ---------------------------------------------------------------------------

OPPORTUNITY_PHRASES = [
    "i wish", "why can't", "there's no way to", "no way to",
    "need a way to", "should be able to", "is there a",
    "does anyone know how to", "missing feature", "please add",
]


def find_opportunity_gaps(points: list) -> list:
    """Find pain points that express desired-but-missing features."""
    gaps = []
    for p in points:
        text_lower = p["text"].lower()
        matches = [phrase for phrase in OPPORTUNITY_PHRASES if phrase in text_lower]
        if matches:
            gaps.append({
                "description": p["text"][:200],
                "source": p["source"],
                "phrases_matched": matches,
                "supporting_evidence_count": 1,
                "competitor_gap": False,
            })
    return gaps[:20]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Synthesize and rank pain points from all data sources")
    parser.add_argument("--input-dir", help="Directory containing JSON result files")
    parser.add_argument("--stdin", action="store_true", help="Read JSON records from stdin (newline or array)")
    parser.add_argument("--keyword", default="", help="Keyword being researched (for output labeling)")
    parser.add_argument("--cluster-threshold", type=float, default=0.25,
                        help="Jaccard similarity threshold for clustering (default: 0.25)")
    args = parser.parse_args()

    records = []

    # Load from directory
    if args.input_dir:
        if not os.path.isdir(args.input_dir):
            print(f"ERROR: {args.input_dir} is not a directory", file=sys.stderr)
            sys.exit(1)
        for fname in os.listdir(args.input_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(args.input_dir, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    records.extend(data)
                else:
                    records.append(data)
                print(f"Loaded: {fname}", file=sys.stderr)
            except Exception as e:
                print(f"Failed to load {fname}: {e}", file=sys.stderr)

    # Load from stdin
    if args.stdin or not args.input_dir:
        raw = sys.stdin.read().strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    records.extend(parsed)
                else:
                    records.append(parsed)
            except json.JSONDecodeError:
                # Try line-by-line
                for line in raw.splitlines():
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            pass

    if not records:
        print("No data to analyze. Provide --input-dir or pipe JSON via stdin.", file=sys.stderr)
        sys.exit(1)

    # Determine keyword from data if not provided
    keyword = args.keyword
    if not keyword:
        for r in records:
            if r.get("keyword"):
                keyword = r["keyword"]
                break

    print(f"Analyzing {len(records)} source records for: '{keyword}'", file=sys.stderr)

    # Extract all pain points
    all_points = []
    sources_used = set()
    for record in records:
        if "error" in record:
            continue
        pts = extract_pain_points(record)
        all_points.extend(pts)
        if pts:
            sources_used.add(record.get("source", "unknown"))

    print(f"Extracted {len(all_points)} raw data points from {len(sources_used)} sources", file=sys.stderr)

    if not all_points:
        print(json.dumps({
            "source": "analysis",
            "keyword": keyword,
            "total_data_points": 0,
            "sources_used": 0,
            "pain_points": [],
            "opportunity_gaps": []
        }, indent=2))
        return

    # Cluster
    print("Clustering similar pain points...", file=sys.stderr)
    clusters = cluster_points(all_points, threshold=args.cluster_threshold)
    print(f"Found {len(clusters)} clusters", file=sys.stderr)

    # Score and rank
    scored = [score_cluster(c, all_points) for c in clusters]
    scored.sort(key=lambda x: x["composite_score"], reverse=True)

    # Add rank
    for i, item in enumerate(scored):
        item["rank"] = i + 1

    # Opportunity gaps
    gaps = find_opportunity_gaps(all_points)

    # Deduplicate gaps by text similarity
    seen_gap_tokens = []
    unique_gaps = []
    for gap in gaps:
        tokens = tokenize(gap["description"])
        is_dup = any(jaccard_similarity(tokens, seen) > 0.5 for seen in seen_gap_tokens)
        if not is_dup:
            unique_gaps.append(gap)
            seen_gap_tokens.append(tokens)

    # Verdict
    top_pain_points = scored

    print(json.dumps({
        "source": "analysis",
        "keyword": keyword,
        "total_data_points": len(all_points),
        "sources_used": len(sources_used),
        "pain_points": top_pain_points,
        "opportunity_gaps": unique_gaps[:10]
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e), "source": "analysis"}, indent=2))
        sys.exit(1)
