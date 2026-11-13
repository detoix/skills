---
name: youtube
description: Export and analyze YouTube channel viewing metrics, thumbnail impressions, and CTR using local OAuth credentials and the official Analytics, Reporting, and Data APIs. Use for channel/video performance, CSV/JSON exports, OAuth setup, reach reporting setup, and growth reports.
---

# YouTube

Use the bundled scripts for API-based analytics exports before considering YouTube Studio. Channel content is not modified. Reach report generation is configured separately with an explicit setup flag; routine reads reuse existing jobs.

## Paths and runtime

Resolve `scripts/` relative to this skill's directory, not the conversation's working directory. Run the examples below from that directory using an available Python interpreter (`python` or `python3`). If a virtual environment is used, select its interpreter for the current operating system; do not assume a particular username, drive, checkout location, or installed environment.

The export script resolves storage independently of the skill's installation location:

- Base directory: `Path.home() / ".youtube"` by default; override with `YOUTUBE_ANALYTICS_HOME`.
- OAuth client: `<base>/secrets/youtube_oauth_client.json`.
- Saved authorization: `<base>/secrets/youtube_token.json`.
- Exports: `<base>/data/`.
- Downloaded reach report cache: `<base>/reporting/<authorized-channel>/<report-type>/`.

`Path.home()` resolves the current user's home on Windows, macOS, and Linux. `--client-secrets`, `--token`, and `--output-dir` override their individual paths; `~` is expanded. Use `--reach-cache-dir` in the main exporter or `--cache-dir` in the reach-only exporter to override cached report storage. A custom `YOUTUBE_ANALYTICS_HOME` should be an absolute path so scheduled runs do not depend on their working directory.

Keep machine-specific paths and account/channel identifiers in local runtime configuration, never in this skill's instructions or source.

## Authorization

Reuse existing credentials first. A valid saved token or one that can be refreshed is sufficient; the client JSON is only needed for interactive OAuth login. If multiple saved authorizations exist, pass the known working one with `--token` rather than assuming the default is usable. `--no-browser-login` permits saved-token reuse and refresh but prevents an interactive browser login. Reauthorizing an existing Google app does not require creating a new Cloud project, reenabling its APIs, or creating another client.

YouTube Reporting API uses the same `yt-analytics.readonly` scope already needed for viewing analytics. Enabling Reporting API in the existing Google Cloud project does not itself require new OAuth consent. Distinguish a disabled API from insufficient OAuth scopes; test existing authorization first.

When login is needed:

1. Locate the user's existing OAuth **Desktop app** client JSON. Ask for its local path, not its contents.
2. Install dependencies with `python -m pip install -r scripts/requirements.txt` in the selected environment if needed.
3. Run the export script with `--client-secrets "<local-client-json>"`, or place the client JSON at its default private storage path. The OAuth flow opens the system browser; the user selects the Google account/channel and grants read-only access.
4. The script saves authorization at the resolved token path after login or refresh, replacing the previous file only after the new one has been written. Report where authorization was saved without displaying its contents.

Do not infer that an OAuth login includes all channels managed by a Google account. To identify the channel(s) exposed by the current authorization, use YouTube Data API `channels.list(part="snippet", mine=True)` with the same credentials. `--channel-id` selects a report target; it does not grant access to another channel.

Keep OAuth client JSON, saved tokens, and analytics private and outside version control. If storage is inside a repository, verify ignore rules cover those exact paths before writing. Restrict local secret files to the current user where supported. Never display, paste, log, commit, or send credentials to unrelated services. Use Google credentials only in the intended OAuth/API exchange; the user enters passwords and verification codes directly in Google.

The scripts request only these scopes:

- `https://www.googleapis.com/auth/yt-analytics.readonly`
- `https://www.googleapis.com/auth/youtube.readonly`

## Export and analyze

With existing authorization, export the most recent 30 days:

```text
python scripts/youtube_analytics_pull.py
```

For first-time login with an existing downloaded client:

```text
python scripts/youtube_analytics_pull.py --client-secrets "<local-client-json>"
```

Useful options:

- `--start-date YYYY-MM-DD` and `--end-date today`: reporting period.
- `--channel-id <authorized-channel-id>`: report target; defaults to `MINE`.
- `--metrics <csv>`: override the Analytics metrics.
- `--skip-metadata` or `--skip-supplemental`: omit those API reports.
- `--skip-reach`: omit thumbnail reach reports.
- `--create-reach-job`: one-time setup of the selected reach report type if no active job exists; subsequent runs reuse it.
- `--reach-report-type channel_reach_combined_a1`: request reach broken down by traffic source and device instead of the default basic report.
- `--no-browser-login`: run with existing authorization only.
- `--output-dir "<export-directory>"`: write exports elsewhere.

Default outputs include `analytics_by_video.csv`, `analytics_by_day.csv`, `video_metadata.csv`, supplemental CSVs, and `manifest.json` in the resolved export directory. Reach outputs are `reach_daily.csv`, `reach_by_video.csv`, and `reach_manifest.json`. The main manifest records `analytics_available_through` and the separate reach status; the requested end date is not proof that all days have been processed. Generate a local report using those resolved paths:

```text
python scripts/youtube_growth_report.py --analytics-csv "<export-directory>/analytics_by_video.csv" --metadata-csv "<export-directory>/video_metadata.csv"
```

## Thumbnail impressions and CTR

Reporting API must be enabled in the same Google Cloud project as the existing OAuth client. The scripts use `channel_reach_basic_a1` (daily channel/video impressions and CTR) by default. `channel_reach_combined_a1` adds traffic source and device dimensions. Each report type needs its own job; do not add their totals together.

When the user requests Reporting/CTR setup, configure generation once with `--create-reach-job` in the main exporter, or run the reach-only script:

```text
python scripts/youtube_reach_pull.py --create-job --no-browser-login
```

Pass `--token` when using a non-default existing authorization. The reach-only script also accepts `--start-date`, `--end-date`, `--output-dir`, `--cache-dir`, and `--report-type`. Omit `--create-job` for later read-only retrievals. Creating a job instructs YouTube to generate that report daily; it does not publish content or set up local scheduled exports or notifications. Routine analytics reads do not create jobs automatically.

The exporter verifies the authorization's channel, reuses active jobs by report type, follows pagination, caches downloads by report ID, and selects the newest report for each period. Backfills replace prior data, including header-only replacements; rerunning does not append duplicate totals. CSV dates, not UTC request boundaries, determine inclusion in the requested interval.

Read `reach_manifest.json` before interpreting the CSVs:

- `ok`: rows are available; check `available_dates` and per-video coverage before comparing with viewing metrics.
- `job_missing`: report generation has not been configured.
- `pending`: a job exists, but no reports currently cover the requested period. Initial reports can take up to 48 hours; the preceding 30 days of history normally arrive within a couple of days.
- `api_disabled`: enable Reporting API in the existing project; do not treat this as a need for additional scopes.
- `insufficient_scope`: check for an existing token with `yt-analytics.readonly` before starting OAuth.
- `channel_mismatch`, `error`, or `no_data_in_period`: inspect the recorded message and coverage. These do not establish zero impressions.

Unavailable/error exports contain headers without fabricated zero rows. Raw downloaded reports retain Google's fields and numeric values. Exported daily dates use ISO format. Per-video CTR is weighted by impressions and stays on the API's native numeric scale, with no automatic guessing between a fraction and a percent. Missing CTR stays blank; never calculate it as total video views divided by impressions, since not all views originate from counted impressions.

For growth advice, compare CTR with impression counts over matching periods and sources. Separate public view totals from delayed processed analytics; use engaged-playback counts when assessing the sample behind average view duration. Distinguish measured findings from editorial hypotheses and avoid causal diagnoses from a handful of plays.

Official references: [Reporting authorization](https://developers.google.com/youtube/reporting/guides/authorization), [reach report types](https://developers.google.com/youtube/reporting/v1/reports/channel_reports#reach-reports), and [report generation, history, and backfills](https://developers.google.com/youtube/reporting/v1/reports).

Schedule recurring exports only when requested and after noninteractive token refresh works. Use the current host's scheduler or available automation tools, an explicit interpreter/script location resolved on that host, and the same configured storage paths. Scheduled runs must not require browser consent.
