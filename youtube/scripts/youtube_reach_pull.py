#!/usr/bin/env python3
"""Export thumbnail reach reports without changing channel content."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse


REPORT_TYPES = ("channel_reach_basic_a1", "channel_reach_combined_a1")
DAILY_HEADERS = [
    "date", "channel_id", "video_id", "video_thumbnail_impressions",
    "video_thumbnail_impressions_ctr",
]
SUMMARY_HEADERS = [
    "video", "video_thumbnail_impressions", "video_thumbnail_impressions_ctr",
    "reach_start_date", "reach_end_date", "reach_days",
]


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def list_pages(method, key: str, **params) -> list[dict]:
    items = []
    while True:
        page = method(**params).execute()
        items.extend(page.get(key, []))
        token = page.get("nextPageToken")
        if not token:
            return items
        params["pageToken"] = token


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def report_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    return date.fromisoformat(value).isoformat()


def newest_reports(reports: list[dict]) -> list[dict]:
    """Backfills replace an entire period, including a replacement with no rows."""
    selected = {}
    for report in reports:
        period = (timestamp(report["startTime"]), timestamp(report["endTime"]))
        previous = selected.get(period)
        if previous is None or timestamp(report["createTime"]) > timestamp(previous["createTime"]):
            selected[period] = report
    return [selected[period] for period in sorted(selected)]


def download_report(session, report: dict, cache_dir: Path) -> Path:
    # IDs are opaque; hash them rather than allowing them to form file paths.
    path = cache_dir / (hashlib.sha256(report["id"].encode()).hexdigest() + ".csv")
    if path.is_file():
        return path
    url = report["downloadUrl"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".googleapis.com"):
        raise ValueError("Unexpected report download host; credentials were not sent.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    response = session.get(url, timeout=60, stream=True)
    temp_path = None
    try:
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(dir=cache_dir, delete=False) as handle:
            temp_path = Path(handle.name)
            for block in response.iter_content(chunk_size=1024 * 1024):
                if block:
                    handle.write(block)
        # A failed or HTML download must never become a successful cached CSV.
        with temp_path.open(newline="", encoding="utf-8-sig") as handle:
            headers = csv.DictReader(handle).fieldnames or []
        if not set(DAILY_HEADERS).issubset(headers):
            raise ValueError("Reach report is missing required CSV columns.")
        os.replace(temp_path, path)
        temp_path = None
    finally:
        response.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path


def aggregate_reach(rows: list[dict]) -> list[dict]:
    """Keep the API's CTR scale and weight it by impressions, never by rows."""
    groups = {}
    for row in rows:
        video = row["video_id"]
        group = groups.setdefault(video, {"impressions": 0, "weighted_ctr": Decimal(0),
                                          "complete_ctr": True, "dates": set()})
        impressions = int(row["video_thumbnail_impressions"])
        if impressions < 0:
            raise ValueError("Reach report contains negative impressions.")
        group["impressions"] += impressions
        group["dates"].add(row["date"])
        ctr = row.get("video_thumbnail_impressions_ctr", "").strip()
        if impressions:
            if ctr and ctr.upper() != "NULL":
                value = Decimal(ctr)
                if not value.is_finite() or value < 0:
                    raise ValueError("Reach report contains an invalid CTR.")
                group["weighted_ctr"] += impressions * value
            else:
                group["complete_ctr"] = False
    output = []
    for video, group in sorted(groups.items()):
        impressions = group["impressions"]
        ctr = ""
        if impressions and group["complete_ctr"]:
            ctr = format(group["weighted_ctr"] / impressions, "f")
        output.append({"video": video, "video_thumbnail_impressions": impressions,
                       "video_thumbnail_impressions_ctr": ctr,
                       "reach_start_date": min(group["dates"]),
                       "reach_end_date": max(group["dates"]),
                       "reach_days": len(group["dates"])})
    return output


def api_error(exc: Exception) -> dict:
    code = getattr(getattr(exc, "resp", None), "status", None)
    detail = {}
    try:
        detail = json.loads(getattr(exc, "content", b"{}")).get("error", {})
    except (TypeError, ValueError, AttributeError):
        pass
    message = detail.get("message", str(exc)) if isinstance(detail, dict) else str(detail)
    lower = message.lower()
    if code == 403 and any(text in lower for text in ("disabled", "has not been used", "not enabled")):
        status = "api_disabled"
        message = "Enable YouTube Reporting API in the existing OAuth client's Google Cloud project. OAuth scopes need not change."
    elif code == 403 and any(text in lower for text in ("scope", "insufficient permission")):
        status = "insufficient_scope"
        message = "This saved authorization lacks yt-analytics.readonly. Reuse another existing valid token before requesting OAuth consent."
    else:
        status = "error"
    return {"status": status, "http_status": code, "message": message}


def export_reach(reporting, youtube, session, *, channel_id: str, start_date: str,
                 end_date: str, output_dir: Path, cache_dir: Path,
                 report_type: str = REPORT_TYPES[0], create_job: bool = False) -> dict:
    result = {"report_type": report_type, "requested_start_date": start_date,
              "requested_end_date": end_date,
              "checked_at": datetime.now(timezone.utc).isoformat(),
              "job_created": False}
    rows = []
    headers = list(DAILY_HEADERS)
    summary = []
    try:
        if report_type not in REPORT_TYPES:
            raise ValueError("Unsupported reach report type.")
        if start_date > end_date:
            raise ValueError("Start date must not follow end date.")
        channels = list_pages(youtube.channels().list, "items", part="snippet", mine=True)
        # Reporting API uses the current authorization's channel, not an arbitrary channel ID.
        if len(channels) != 1 or channel_id not in ("MINE", channels[0]["id"]):
            result.update(status="channel_mismatch", message="Reporting API requires the single channel exposed by this OAuth authorization. No report job was created.")
        else:
            actual_channel = channels[0]["id"]
            result["channel_id"] = actual_channel
            now = datetime.now(timezone.utc)
            jobs = [job for job in list_pages(reporting.jobs().list, "jobs")
                    if job.get("reportTypeId") == report_type
                    and (not job.get("expireTime") or timestamp(job["expireTime"]) > now)]
            if not jobs and create_job:
                available = list_pages(reporting.reportTypes().list, "reportTypes")
                if report_type not in {item["id"] for item in available}:
                    raise ValueError("The authorized channel does not expose this reach report type.")
                # No retry on POST. A rerun lists existing jobs before considering creation.
                job = reporting.jobs().create(body={"reportTypeId": report_type,
                    "name": "YouTube Analytics reach export"}).execute(num_retries=0)
                confirmed = reporting.jobs().get(jobId=job["id"]).execute()
                if confirmed.get("reportTypeId") != report_type:
                    raise ValueError("The created reporting job could not be verified.")
                jobs = [confirmed]
                result["job_created"] = True
            result["jobs"] = [{key: job[key] for key in ("id", "reportTypeId", "createTime") if key in job} for job in jobs]
            if not jobs:
                result.update(status="job_missing", message="No reach reporting job exists. Use --create-job (standalone) or --create-reach-job (main export) after Reporting setup is authorized.")
            else:
                reports = []
                # Overfetch the UTC boundaries, then filter actual CSV calendar dates.
                lower = (date.fromisoformat(start_date) - timedelta(days=1)).isoformat() + "T00:00:00Z"
                upper = (date.fromisoformat(end_date) + timedelta(days=2)).isoformat() + "T00:00:00Z"
                for job in jobs:
                    reports.extend(list_pages(reporting.jobs().reports().list, "reports",
                        jobId=job["id"], startTimeAtOrAfter=lower, startTimeBefore=upper))
                selected = newest_reports(reports)
                result["reports"] = [{key: report[key] for key in ("id", "startTime", "endTime", "createTime")} for report in selected]
                if not selected:
                    result.update(status="pending", message="No reports are available for this period yet. New jobs normally need up to 48 hours; historical reports may take a couple of days. This does not mean zero impressions.")
                else:
                    for report in selected:
                        path = download_report(session, report, cache_dir / actual_channel / report_type)
                        with path.open(newline="", encoding="utf-8-sig") as handle:
                            reader = csv.DictReader(handle)
                            for column in reader.fieldnames or []:
                                if column not in headers:
                                    headers.append(column)
                            for row in reader:
                                day = report_date(row["date"])
                                if not start_date <= day <= end_date:
                                    continue
                                if row["channel_id"] != actual_channel:
                                    raise ValueError("Downloaded report contains a different channel ID.")
                                row["date"] = day
                                rows.append(row)
                    summary = aggregate_reach(rows)
                    result.update(status="ok" if rows else "no_data_in_period",
                                  rows=len(rows), reports_downloaded_or_cached=len(selected),
                                  available_dates=sorted({row["date"] for row in rows}),
                                  ctr_unit="API native scale, unchanged; summary is impression-weighted")
    except Exception as exc:
        result.update(api_error(exc))
        rows, summary, headers = [], [], list(DAILY_HEADERS)
    # Always publish an explicit status and replace stale exports with headers when unavailable.
    write_csv(output_dir / "reach_daily.csv", headers, rows)
    write_csv(output_dir / "reach_by_video.csv", SUMMARY_HEADERS, summary)
    (output_dir / "reach_manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    from youtube_analytics_pull import default_base_dir, load_credentials, local_path, parse_date

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-secrets", type=local_path, default=default_base_dir() / "secrets/youtube_oauth_client.json")
    parser.add_argument("--token", type=local_path, default=default_base_dir() / "secrets/youtube_token.json")
    parser.add_argument("--output-dir", type=local_path, default=default_base_dir() / "data")
    parser.add_argument("--cache-dir", type=local_path, default=default_base_dir() / "reporting")
    parser.add_argument("--channel-id", default="MINE")
    parser.add_argument("--start-date", default=(date.today() - timedelta(days=30)).isoformat())
    parser.add_argument("--end-date", default="today")
    parser.add_argument("--report-type", choices=REPORT_TYPES, default=REPORT_TYPES[0])
    parser.add_argument("--create-job", action="store_true", help="Create a daily reach reporting job only when none exists.")
    parser.add_argument("--no-browser-login", action="store_true", help="Reuse/refresh saved credentials; never open OAuth in a browser.")
    args = parser.parse_args()
    start, end = parse_date(args.start_date), parse_date(args.end_date)
    if start > end:
        parser.error("--start-date must not follow --end-date")
    from google.auth.transport.requests import AuthorizedSession
    from googleapiclient.discovery import build

    creds = load_credentials(args.client_secrets, args.token, allow_login=not args.no_browser_login)
    with AuthorizedSession(creds) as session:
        result = export_reach(build("youtubereporting", "v1", credentials=creds),
            build("youtube", "v3", credentials=creds), session,
            channel_id=args.channel_id, start_date=start, end_date=end,
            output_dir=args.output_dir, cache_dir=args.cache_dir,
            report_type=args.report_type, create_job=args.create_job)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in ("ok", "pending", "no_data_in_period") else 1


if __name__ == "__main__":
    raise SystemExit(main())
