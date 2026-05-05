#!/usr/bin/env python3
"""Search and download stock videos from Pexels."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_URL = "https://api.pexels.com/v1/videos/search"
DEFAULT_COUNT = 3
DEFAULT_TIMEOUT = 60
DEFAULT_PER_PAGE = 20
ALLOWED_ORIENTATIONS = {"landscape", "portrait", "square", "vertical", "either"}
ORIENTATION_ALIASES = {
    "vertical": "portrait",
    "either": None,
}
SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.pexels.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
}


def load_dotenv() -> None:
    candidates = [
        SKILL_ROOT / ".env",
        Path.cwd() / ".env",
    ]
    for dotenv_path in candidates:
        if not dotenv_path.exists():
            continue
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
        break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search and download stock videos from Pexels.")
    parser.add_argument("--query", required=True, help="Pexels search query.")
    parser.add_argument("--output-dir", required=True, help="Directory for downloaded clips.")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="How many clips to download.")
    parser.add_argument(
        "--orientation",
        choices=sorted(ALLOWED_ORIENTATIONS),
        help="Optional orientation filter. Accepts vertical as an alias for portrait; either disables the filter.",
    )
    parser.add_argument("--min-duration", type=int, help="Optional minimum duration in seconds.")
    parser.add_argument("--max-duration", type=int, help="Optional maximum duration in seconds.")
    parser.add_argument("--page", type=int, default=1, help="Results page number.")
    parser.add_argument("--manifest", help="Optional manifest output path.")
    parser.add_argument("--dry-run", action="store_true", help="Search and score results without downloading.")
    args = parser.parse_args()

    if args.count <= 0:
        parser.error("--count must be positive")
    if args.page <= 0:
        parser.error("--page must be positive")
    if args.min_duration is not None and args.min_duration < 0:
        parser.error("--min-duration must be zero or greater")
    if args.max_duration is not None and args.max_duration < 0:
        parser.error("--max-duration must be zero or greater")
    if (
        args.min_duration is not None
        and args.max_duration is not None
        and args.max_duration < args.min_duration
    ):
        parser.error("--max-duration must be greater than or equal to --min-duration")

    return args


def require_api_key() -> str:
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing PEXELS_API_KEY in the environment.")
    return api_key


def build_url(args: argparse.Namespace) -> str:
    params = {
        "query": args.query,
        "per_page": max(DEFAULT_PER_PAGE, args.count * 3),
        "page": args.page,
    }
    orientation = ORIENTATION_ALIASES.get(args.orientation, args.orientation)
    if orientation:
        params["orientation"] = orientation
    if args.min_duration is not None:
        params["min_duration"] = args.min_duration
    if args.max_duration is not None:
        params["max_duration"] = args.max_duration
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def api_get_json(url: str, api_key: str) -> dict:
    headers = dict(DEFAULT_HEADERS)
    headers["Authorization"] = api_key
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def sanitize_filename(value: str) -> str:
    collapsed = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return collapsed or "clip"


def orientation_of(video: dict) -> str:
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def choose_video_file(video: dict) -> dict | None:
    candidates = [item for item in video.get("video_files", []) if item.get("file_type") == "video/mp4" and item.get("link")]
    if not candidates:
        return None

    def quality_rank(item: dict) -> tuple[int, int, int]:
        quality = str(item.get("quality") or "")
        quality_score = 2 if quality == "hd" else 1 if quality == "sd" else 0
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        return quality_score, width * height, width

    return sorted(candidates, key=quality_rank, reverse=True)[0]


def score_video(video: dict, desired_orientation: str | None) -> tuple[int, int, int]:
    duration = int(video.get("duration") or 0)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    orientation_bonus = 2 if desired_orientation and orientation_of(video) == desired_orientation else 0
    return orientation_bonus, width * height, duration


def select_videos(payload: dict, desired_orientation: str | None, count: int) -> list[dict]:
    videos = payload.get("videos")
    if not isinstance(videos, list):
        raise SystemExit("Unexpected Pexels response: missing 'videos' array.")

    prepared: list[tuple[tuple[int, int, int], dict, dict]] = []
    for video in videos:
        if not isinstance(video, dict):
            continue
        chosen_file = choose_video_file(video)
        if not chosen_file:
            continue
        prepared.append((score_video(video, desired_orientation), video, chosen_file))

    prepared.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for _, video, chosen_file in prepared[:count]:
        merged = dict(video)
        merged["selected_file"] = chosen_file
        selected.append(merged)
    return selected


def download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        destination.write_bytes(response.read())


def manifest_entry(video: dict, downloaded_path: str | None) -> dict:
    selected_file = video["selected_file"]
    return {
        "id": video.get("id"),
        "duration": video.get("duration"),
        "width": video.get("width"),
        "height": video.get("height"),
        "orientation": orientation_of(video),
        "url": video.get("url"),
        "video_file_url": selected_file.get("link"),
        "video_file_quality": selected_file.get("quality"),
        "video_file_width": selected_file.get("width"),
        "video_file_height": selected_file.get("height"),
        "downloaded_path": downloaded_path,
        "user": {
            "id": (video.get("user") or {}).get("id"),
            "name": (video.get("user") or {}).get("name"),
            "url": (video.get("user") or {}).get("url"),
        },
    }


def main() -> int:
    args = parse_args()
    load_dotenv()
    api_key = require_api_key()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest).resolve() if args.manifest else output_dir / "pexels_manifest.json"

    url = build_url(args)
    try:
        payload = api_get_json(url, api_key)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Pexels API request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Pexels API request failed: {exc.reason}") from exc

    selected = select_videos(payload, args.orientation, args.count)
    if not selected:
        raise SystemExit("No downloadable Pexels videos matched the query.")

    manifest = {
        "query": args.query,
        "requested_count": args.count,
        "downloaded_count": 0 if args.dry_run else len(selected),
        "page": args.page,
        "generated_at_unix": int(time.time()),
        "items": [],
    }

    for index, video in enumerate(selected, start=1):
        selected_file = video["selected_file"]
        suffix = Path(urllib.parse.urlparse(selected_file["link"]).path).suffix or ".mp4"
        stem = sanitize_filename(f"{index:02d}-{args.query}-{video.get('id')}")
        destination = output_dir / f"{stem}{suffix}"

        if not args.dry_run:
            download_file(selected_file["link"], destination)
            downloaded_path = str(destination)
        else:
            downloaded_path = None

        manifest["items"].append(manifest_entry(video, downloaded_path))

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.dry_run:
        print(f"Dry run complete. Wrote manifest: {manifest_path}")
    else:
        print(f"Downloaded {len(selected)} clip(s) to: {output_dir}")
        print(f"Wrote manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
