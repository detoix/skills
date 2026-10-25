---
name: youtube-analytics
description: Fetch and analyze read-only YouTube channel analytics using local Google OAuth credentials, the YouTube Analytics API, and the YouTube Data API. Use for channel/video metrics, local CSV/JSON exports, OAuth authorization, and growth reports.
---

# YouTube Analytics

## Paths and runtime

Resolve `scripts/` relative to this skill's directory, not the conversation's working directory. Run the examples below from that directory using an available Python interpreter (`python` or `python3`). If a virtual environment is used, select its interpreter for the current operating system; do not assume a particular username, drive, checkout location, or installed environment.

The export script resolves storage independently of the skill's installation location:

- Base directory: `Path.home() / ".youtube-analytics"` by default; override with `YOUTUBE_ANALYTICS_HOME`.
- OAuth client: `<base>/secrets/youtube_oauth_client.json`.
- Saved authorization: `<base>/secrets/youtube_token.json`.
- Exports: `<base>/data/`.

`Path.home()` resolves the current user's home on Windows, macOS, and Linux. `--client-secrets`, `--token`, and `--output-dir` override their individual paths; `~` is expanded. A custom `YOUTUBE_ANALYTICS_HOME` should be an absolute path so scheduled runs do not depend on their working directory.

Keep machine-specific paths and account/channel identifiers in local runtime configuration, never in this skill's instructions or source.

## Authorization

Reuse existing credentials first. A valid saved token or one that can be refreshed is sufficient; the client JSON is only needed for interactive OAuth login. Reauthorizing an existing Google app does not require creating a new Cloud project, reenabling its APIs, or creating another client.

When login is needed:

1. Locate the user's existing OAuth **Desktop app** client JSON. Ask for its local path, not its contents.
2. Install dependencies with `python -m pip install -r scripts/requirements.txt` in the selected environment if needed.
3. Run the export script with `--client-secrets "<local-client-json>"`, or place the client JSON at its default private storage path. The OAuth flow opens the system browser; the user selects the Google account/channel and grants read-only access.
4. The script saves authorization at the resolved token path and refreshes it on subsequent runs. Report where authorization was saved without displaying its contents.

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
- `--output-dir "<export-directory>"`: write exports elsewhere.

Default outputs include `analytics_by_video.csv`, `analytics_by_day.csv`, `video_metadata.csv`, supplemental CSVs, and `manifest.json` in the resolved export directory. Generate a local report using those resolved paths:

```text
python scripts/youtube_growth_report.py --analytics-csv "<export-directory>/analytics_by_video.csv" --metadata-csv "<export-directory>/video_metadata.csv"
```

For growth advice, inspect the latest exports and distinguish measured findings from subjective strategy recommendations.

Schedule recurring exports only when requested and after noninteractive token refresh works. Use the current host's scheduler or available automation tools, an explicit interpreter/script location resolved on that host, and the same configured storage paths. Scheduled runs must not require browser consent.
