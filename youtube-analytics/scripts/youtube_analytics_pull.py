#!/usr/bin/env python3
"""Pull read-only YouTube Analytics and Data API exports to local CSV files."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable


SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DEFAULT_METRICS = ",".join(
    [
        "views",
        "estimatedMinutesWatched",
        "averageViewDuration",
        "averageViewPercentage",
        "likes",
        "comments",
        "shares",
        "subscribersGained",
        "subscribersLost",
    ]
)


def default_base_dir() -> Path:
    return Path.home() / ".youtube-analytics"


def parse_date(value: str) -> str:
    if value == "today":
        return date.today().isoformat()
    if value == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    date.fromisoformat(value)
    return value


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_credentials(client_secrets: Path, token_path: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise SystemExit(
            "Missing Google API dependencies. Install with: "
            "python -m pip install -r scripts/requirements.txt"
        ) from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
        creds = flow.run_local_server(port=0)

    ensure_parent(token_path)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def write_csv(path: Path, headers: list[str], rows: Iterable[dict[str, object]]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def analytics_rows(response: dict) -> tuple[list[str], list[dict[str, object]]]:
    headers = [col["name"] for col in response.get("columnHeaders", [])]
    rows = [dict(zip(headers, values)) for values in response.get("rows", [])]
    return headers, rows


def query_analytics(
    analytics,
    *,
    channel_id: str,
    start_date: str,
    end_date: str,
    metrics: str,
    dimensions: str,
    sort: str | None = None,
    max_results: int | None = None,
) -> tuple[list[str], list[dict[str, object]]]:
    request = {
        "ids": f"channel=={channel_id}",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": metrics,
        "dimensions": dimensions,
    }
    if sort:
        request["sort"] = sort
    if max_results:
        request["maxResults"] = max_results
    return analytics_rows(analytics.reports().query(**request).execute())


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_video_metadata(youtube, video_ids: list[str]) -> list[dict[str, object]]:
    output = []
    for batch in chunks(video_ids, 50):
        response = (
            youtube.videos()
            .list(
                part="snippet,contentDetails,statistics,status",
                id=",".join(batch),
                maxResults=50,
            )
            .execute()
        )
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            status = item.get("status", {})
            output.append(
                {
                    "video": item.get("id"),
                    "title": snippet.get("title"),
                    "publishedAt": snippet.get("publishedAt"),
                    "channelTitle": snippet.get("channelTitle"),
                    "categoryId": snippet.get("categoryId"),
                    "duration": item.get("contentDetails", {}).get("duration"),
                    "privacyStatus": status.get("privacyStatus"),
                    "publicViewCount": stats.get("viewCount"),
                    "publicLikeCount": stats.get("likeCount"),
                    "publicCommentCount": stats.get("commentCount"),
                    "tags": json.dumps(snippet.get("tags", []), ensure_ascii=False),
                }
            )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=default_base_dir() / "secrets" / "youtube_oauth_client.json",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=default_base_dir() / "secrets" / "youtube_token.json",
    )
    parser.add_argument("--output-dir", type=Path, default=default_base_dir() / "data")
    parser.add_argument("--channel-id", default="MINE")
    parser.add_argument("--start-date", default=(date.today() - timedelta(days=30)).isoformat())
    parser.add_argument("--end-date", default="today")
    parser.add_argument("--metrics", default=DEFAULT_METRICS)
    parser.add_argument("--max-results", type=int, default=200)
    parser.add_argument("--skip-metadata", action="store_true")
    args = parser.parse_args()

    if not args.client_secrets.exists():
        raise SystemExit(f"OAuth client secrets file not found: {args.client_secrets}")

    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "Missing Google API dependencies. Install with: "
            "python -m pip install -r scripts/requirements.txt"
        ) from exc

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    creds = load_credentials(args.client_secrets, args.token)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    youtube = build("youtube", "v3", credentials=creds)

    video_headers, video_rows = query_analytics(
        analytics,
        channel_id=args.channel_id,
        start_date=start_date,
        end_date=end_date,
        metrics=args.metrics,
        dimensions="video",
        sort="-views",
        max_results=args.max_results,
    )
    write_csv(args.output_dir / "analytics_by_video.csv", video_headers, video_rows)

    day_headers, day_rows = query_analytics(
        analytics,
        channel_id=args.channel_id,
        start_date=start_date,
        end_date=end_date,
        metrics=args.metrics,
        dimensions="day",
        sort="day",
    )
    write_csv(args.output_dir / "analytics_by_day.csv", day_headers, day_rows)

    if not args.skip_metadata:
        video_ids = [str(row["video"]) for row in video_rows if row.get("video")]
        metadata_rows = fetch_video_metadata(youtube, video_ids)
        metadata_headers = [
            "video",
            "title",
            "publishedAt",
            "channelTitle",
            "categoryId",
            "duration",
            "privacyStatus",
            "publicViewCount",
            "publicLikeCount",
            "publicCommentCount",
            "tags",
        ]
        write_csv(args.output_dir / "video_metadata.csv", metadata_headers, metadata_rows)

    manifest = {
        "start_date": start_date,
        "end_date": end_date,
        "channel_id": args.channel_id,
        "metrics": args.metrics.split(","),
        "analytics_by_video_rows": len(video_rows),
        "analytics_by_day_rows": len(day_rows),
    }
    ensure_parent(args.output_dir / "manifest.json")
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote YouTube analytics exports to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
