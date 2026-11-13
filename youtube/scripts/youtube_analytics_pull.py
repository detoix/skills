#!/usr/bin/env python3
"""Export YouTube viewing metrics, metadata, and thumbnail reach to local CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
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
        "engagedViews",
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

SUPPLEMENTAL_REPORTS = [
    {
        "name": "traffic_source",
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
        "dimensions": "insightTrafficSourceType",
        "sort": "-views",
    },
    {
        "name": "day_traffic_source",
        "metrics": "views,averageViewPercentage",
        "dimensions": "day,insightTrafficSourceType",
        "sort": "day",
    },
    {
        "name": "device_type",
        "metrics": "views,averageViewPercentage",
        "dimensions": "deviceType",
        "sort": "-views",
    },
    {
        "name": "operating_system",
        "metrics": "views,averageViewPercentage",
        "dimensions": "operatingSystem",
        "sort": "-views",
    },
    {
        "name": "subscribed_status",
        "metrics": "views,averageViewPercentage",
        "dimensions": "subscribedStatus",
        "sort": "-views",
    },
    {
        "name": "creator_content_type",
        "metrics": "views,averageViewPercentage",
        "dimensions": "creatorContentType",
        "sort": "-views",
    },
    {
        "name": "country",
        "metrics": "views,averageViewPercentage",
        "dimensions": "country",
        "sort": "-views",
    },
    {
        "name": "age_gender",
        "metrics": "viewerPercentage",
        "dimensions": "ageGroup,gender",
        "sort": "-viewerPercentage",
    },
]


def default_base_dir() -> Path:
    configured = os.environ.get("YOUTUBE_ANALYTICS_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".youtube"


def local_path(value: str) -> Path:
    return Path(value).expanduser()


def parse_date(value: str) -> str:
    if value == "today":
        return date.today().isoformat()
    if value == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    date.fromisoformat(value)
    return value


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_credentials(token_path: Path, serialized: str) -> None:
    token_path = token_path.resolve()
    ensure_parent(token_path)
    temp_path = None
    try:
        # Use the same directory for atomic replacement and inherit its Windows ACL.
        # NamedTemporaryFile creates the file with mode 0600 on POSIX.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=token_path.parent,
            prefix=".youtube-token-", suffix=".json", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, token_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_credentials(client_secrets: Path, token_path: Path, *, allow_login: bool = True):
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
        creds = Credentials.from_authorized_user_file(str(token_path))

    needs_save = False
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        needs_save = True

    if not creds or not creds.valid or not creds.has_scopes(SCOPES):
        if not allow_login:
            raise SystemExit(
                "No usable saved authorization with youtube.readonly and yt-analytics.readonly. "
                "Pass an existing valid token with --token; browser OAuth is disabled."
            )
        if not client_secrets.is_file():
            raise SystemExit(
                f"OAuth login requires the existing Desktop app client JSON: {client_secrets}. "
                "Pass its local path with --client-secrets. Existing Google projects "
                "and enabled APIs do not need to be recreated."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets), SCOPES, autogenerate_code_verifier=True
        )
        creds = flow.run_local_server(port=0)
        needs_save = True

    if needs_save:
        save_credentials(token_path, creds.to_json())
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


def fetch_supplemental_reports(
    analytics,
    *,
    channel_id: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    max_results: int,
) -> list[dict[str, object]]:
    statuses = []
    for report in SUPPLEMENTAL_REPORTS:
        name = str(report["name"])
        try:
            headers, rows = query_analytics(
                analytics,
                channel_id=channel_id,
                start_date=start_date,
                end_date=end_date,
                metrics=str(report["metrics"]),
                dimensions=str(report["dimensions"]),
                sort=str(report["sort"]),
                max_results=max_results,
            )
            write_csv(output_dir / f"{name}.csv", headers, rows)
            statuses.append({"name": name, "status": "ok", "rows": len(rows)})
        except Exception as exc:  # Keep the main export usable if a report is unavailable.
            statuses.append({"name": name, "status": "error", "error": str(exc)})
    return statuses


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
    from youtube_reach_pull import REPORT_TYPES

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--client-secrets",
        type=local_path,
        default=default_base_dir() / "secrets" / "youtube_oauth_client.json",
    )
    parser.add_argument(
        "--token",
        type=local_path,
        default=default_base_dir() / "secrets" / "youtube_token.json",
    )
    parser.add_argument("--output-dir", type=local_path, default=default_base_dir() / "data")
    parser.add_argument("--channel-id", default="MINE")
    parser.add_argument("--start-date", default=(date.today() - timedelta(days=30)).isoformat())
    parser.add_argument("--end-date", default="today")
    parser.add_argument("--metrics", default=DEFAULT_METRICS)
    parser.add_argument("--max-results", type=int, default=200)
    parser.add_argument("--skip-metadata", action="store_true")
    parser.add_argument("--skip-supplemental", action="store_true")
    parser.add_argument("--no-browser-login", action="store_true")
    parser.add_argument("--skip-reach", action="store_true", help="Skip Reporting API reach export.")
    parser.add_argument("--create-reach-job", action="store_true", help="Create a reach report job if none exists (one-time Reporting setup).")
    parser.add_argument("--reach-report-type", choices=REPORT_TYPES, default=REPORT_TYPES[0])
    parser.add_argument("--reach-cache-dir", type=local_path, default=default_base_dir() / "reporting")
    args = parser.parse_args()

    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "Missing Google API dependencies. Install with: "
            "python -m pip install -r scripts/requirements.txt"
        ) from exc

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if start_date > end_date:
        parser.error("--start-date must not follow --end-date")
    if args.skip_reach and args.create_reach_job:
        parser.error("--skip-reach and --create-reach-job cannot be combined")
    creds = load_credentials(args.client_secrets, args.token, allow_login=not args.no_browser_login)
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

    supplemental_reports = []
    if not args.skip_supplemental:
        supplemental_reports = fetch_supplemental_reports(
            analytics,
            channel_id=args.channel_id,
            start_date=start_date,
            end_date=end_date,
            output_dir=args.output_dir,
            max_results=args.max_results,
        )

    reach = {"status": "skipped"}
    if not args.skip_reach:
        from google.auth.transport.requests import AuthorizedSession
        from youtube_reach_pull import export_reach

        with AuthorizedSession(creds) as session:
            reach = export_reach(
                build("youtubereporting", "v1", credentials=creds), youtube, session,
                channel_id=args.channel_id, start_date=start_date, end_date=end_date,
                output_dir=args.output_dir, cache_dir=args.reach_cache_dir,
                report_type=args.reach_report_type, create_job=args.create_reach_job,
            )
        print(f"Thumbnail reach: {reach['status']}. {reach.get('message', '')}".rstrip())

    manifest = {
        "start_date": start_date,
        "end_date": end_date,
        "channel_id": args.channel_id,
        "metrics": args.metrics.split(","),
        "analytics_by_video_rows": len(video_rows),
        "analytics_by_day_rows": len(day_rows),
        "analytics_available_through": max((str(row["day"]) for row in day_rows), default=None),
        "supplemental_reports": supplemental_reports,
        "reach": reach,
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
