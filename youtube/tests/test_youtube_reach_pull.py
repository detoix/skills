"""Offline behavior checks for report generation, replacement, and reach math."""

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import youtube_reach_pull as reach


class Request:
    def __init__(self, value):
        self.value = value

    def execute(self, **kwargs):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value() if callable(self.value) else self.value


class ApiError(Exception):
    def __init__(self, message, status=403):
        super().__init__(message)
        self.resp = SimpleNamespace(status=status)
        self.content = json.dumps({"error": {"message": message}}).encode()


def job(identifier="job-1"):
    return {"id": identifier, "reportTypeId": reach.REPORT_TYPES[0], "createTime": "2026-11-04T08:00:00Z"}


def report(identifier, day="2026-11-01", created="2026-11-03T08:00:00Z"):
    from datetime import date, timedelta
    end = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    return {"id": identifier, "startTime": day + "T08:00:00Z", "endTime": end + "T08:00:00Z",
            "createTime": created, "downloadUrl": "https://youtubereporting.googleapis.com/v1/media/" + identifier}


class Reporting:
    def __init__(self, jobs=None, reports=None, error=None):
        self.saved_jobs = list(jobs or [])
        self.saved_reports = list(reports or [])
        self.error = error
        self.creates = 0
        self.report_pages = 0

    def jobs(self):
        owner = self

        class Jobs:
            def list(self, **params):
                if owner.error:
                    return Request(owner.error)
                index = int(params.get("pageToken", "0"))
                result = {"jobs": owner.saved_jobs[index:index + 1]}
                if index + 1 < len(owner.saved_jobs):
                    result["nextPageToken"] = str(index + 1)
                return Request(result)

            def create(self, body):
                def create():
                    owner.creates += 1
                    value = job("created-job")
                    owner.saved_jobs.append(value)
                    return value
                return Request(create)

            def get(self, jobId):
                return Request(next(value for value in owner.saved_jobs if value["id"] == jobId))

            def reports(self):
                class Reports:
                    def list(self, **params):
                        owner.report_pages += 1
                        index = int(params.get("pageToken", "0"))
                        result = {"reports": owner.saved_reports[index:index + 1]}
                        if index + 1 < len(owner.saved_reports):
                            result["nextPageToken"] = str(index + 1)
                        return Request(result)
                return Reports()
        return Jobs()

    def reportTypes(self):
        return SimpleNamespace(list=lambda **kwargs: Request({"reportTypes": [{"id": reach.REPORT_TYPES[0]}]}))


class Session:
    def __init__(self, bodies):
        self.bodies = bodies
        self.downloads = []

    def get(self, url, **kwargs):
        identifier = url.rsplit("/", 1)[-1]
        self.downloads.append(identifier)
        return SimpleNamespace(raise_for_status=lambda: None, close=lambda: None,
                               iter_content=lambda **kwargs: iter([self.bodies[identifier].encode()]))


def csv_body(rows):
    handle = io.StringIO()
    # Deliberately reordered columns plus a future field.
    headers = ["video_id", "date", "channel_id", "video_thumbnail_impressions_ctr",
               "video_thumbnail_impressions", "future_column"]
    writer = csv.DictWriter(handle, headers)
    writer.writeheader()
    for day, impressions, ctr in rows:
        writer.writerow({"video_id": "video-1", "date": day, "channel_id": "channel-1",
                         "video_thumbnail_impressions": impressions,
                         "video_thumbnail_impressions_ctr": ctr, "future_column": "kept"})
    return "\ufeff" + handle.getvalue()


class ReachTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.youtube = SimpleNamespace(channels=lambda: SimpleNamespace(
            list=lambda **kwargs: Request({"items": [{"id": "channel-1"}]})))

    def tearDown(self):
        self.temp.cleanup()

    def export(self, reporting, session=None, **kwargs):
        return reach.export_reach(reporting, self.youtube, session or Session({}),
            channel_id=kwargs.pop("channel_id", "MINE"), start_date="2026-10-31", end_date="2026-11-02",
            output_dir=self.root / "out", cache_dir=self.root / "cache", **kwargs)

    def rows(self, name):
        with (self.root / "out" / name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_no_implicit_job_creation(self):
        api = Reporting()
        result = self.export(api)
        self.assertEqual(result["status"], "job_missing")
        self.assertEqual(api.creates, 0)
        self.assertEqual(self.rows("reach_by_video.csv"), [])

    def test_explicit_setup_is_reused_and_pending_is_not_zero(self):
        api = Reporting()
        first = self.export(api, create_job=True)
        second = self.export(api, create_job=True)
        self.assertEqual((first["status"], second["status"]), ("pending", "pending"))
        self.assertTrue(first["job_created"])
        self.assertFalse(second["job_created"])
        self.assertEqual(api.creates, 1)
        self.assertEqual(self.rows("reach_daily.csv"), [])

    def test_wrong_channel_cannot_create_job(self):
        api = Reporting()
        self.assertEqual(self.export(api, channel_id="another-channel", create_job=True)["status"], "channel_mismatch")
        self.assertEqual(api.creates, 0)

    def test_pagination_duplicate_jobs_and_backfill_do_not_double_count(self):
        old = report("old")
        new = report("new", created="2026-11-04T08:00:00Z")
        api = Reporting([job(), job("duplicate")], [old, new])
        session = Session({"old": csv_body([("20261101", 50, "0.02")]),
                           "new": csv_body([("20261101", 100, "0.044")])})
        result = self.export(api, session)
        self.assertEqual(result["status"], "ok")
        self.assertGreater(api.report_pages, 1)
        self.assertEqual(session.downloads, ["new"])
        self.assertEqual(self.rows("reach_by_video.csv")[0]["video_thumbnail_impressions"], "100")
        self.export(api, session)
        self.assertEqual(session.downloads, ["new"])
        # A newer, empty correction replaces the earlier nonempty dataset.
        api.saved_reports.append(report("empty", created="2026-11-05T08:00:00Z"))
        session.bodies["empty"] = csv_body([])
        self.assertEqual(self.export(api, session)["status"], "no_data_in_period")
        self.assertEqual(self.rows("reach_by_video.csv"), [])

    def test_weighted_ctr_date_filter_and_extra_columns(self):
        api = Reporting([job()], [report("data")])
        session = Session({"data": csv_body([("20261030", 999, "0.9"),
            ("20261031", 100, "0.04"), ("2026-11-02", 900, "0.10"), ("20261103", 999, "0.9")])})
        result = self.export(api, session)
        self.assertEqual(result["available_dates"], ["2026-10-31", "2026-11-02"])
        row = self.rows("reach_by_video.csv")[0]
        self.assertEqual(row["video_thumbnail_impressions"], "1000")
        self.assertEqual(row["video_thumbnail_impressions_ctr"], "0.094")
        self.assertEqual(self.rows("reach_daily.csv")[0]["future_column"], "kept")

    def test_missing_or_zero_impression_ctr_is_not_fabricated(self):
        for impressions, ctr in [(0, ""), (100, ""), (100, "NULL")]:
            with self.subTest(impressions=impressions, ctr=ctr):
                rows = [{"video_id": "v", "date": "2026-11-01",
                         "video_thumbnail_impressions": str(impressions),
                         "video_thumbnail_impressions_ctr": ctr}]
                self.assertEqual(reach.aggregate_reach(rows)[0]["video_thumbnail_impressions_ctr"], "")

    def test_access_errors_are_distinct_and_clear_stale_exports(self):
        valid = Reporting([job()], [report("data")])
        self.export(valid, Session({"data": csv_body([("20261101", 100, "4.4")])}))
        for message, status in [("API has not been used or is disabled", "api_disabled"),
                                ("Request had insufficient authentication scopes", "insufficient_scope")]:
            with self.subTest(status=status):
                result = self.export(Reporting(error=ApiError(message)))
                self.assertEqual(result["status"], status)
                self.assertEqual(self.rows("reach_by_video.csv"), [])
                saved = json.loads((self.root / "out/reach_manifest.json").read_text())
                self.assertEqual(saved["status"], status)

    def test_invalid_download_is_not_cached(self):
        api = Reporting([job()], [report("bad")])
        self.assertEqual(self.export(api, Session({"bad": "<html>Error</html>"}))["status"], "error")
        self.assertEqual(list((self.root / "cache").rglob("*.csv")), [])

    def test_unexpected_host_does_not_receive_authorization(self):
        value = report("outside")
        value["downloadUrl"] = "https://example.org/report.csv"
        session = Session({})
        self.assertEqual(self.export(Reporting([job()], [value]), session)["status"], "error")
        self.assertEqual(session.downloads, [])


if __name__ == "__main__":
    unittest.main()
