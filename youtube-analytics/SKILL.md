---
name: youtube-analytics
description: Pull, refresh, and analyze read-only YouTube channel analytics locally using OAuth, YouTube Analytics API, and YouTube Data API exports. Use when Codex needs to set up recurring YouTube Studio analytics access, fetch Shorts/channel/video metrics, generate local CSV/JSON datasets, protect OAuth credentials and refresh tokens, or create growth reports from exported YouTube performance data.
---

# Youtube Analytics

## Operating Rules

- Never request, store, print, commit, or transmit Google account passwords, cookies, 2FA codes, OAuth refresh tokens, or client secrets.
- Keep OAuth client JSON, token JSON, and exported analytics under ignored paths.
- This installation stores local secrets in `C:\Users\kdeptula\skills\youtube-analytics\secrets\`.
- This installation stores exported analytics in `C:\Users\kdeptula\skills\youtube-analytics\data\`.
- Before writing secrets into any repository, verify `.gitignore` covers the exact directory and filename patterns.
- Use read-only scopes unless the user explicitly requests write operations:
  - `https://www.googleapis.com/auth/yt-analytics.readonly`
  - `https://www.googleapis.com/auth/youtube.readonly`

## Workflow

1. Confirm the user created a Google OAuth **Desktop app** client.
2. Place the downloaded OAuth client JSON in `secrets\youtube_oauth_client.json`.
3. Use `.venv\Scripts\python.exe` for API pulls when the local venv exists.
4. Run `scripts\youtube_analytics_pull.py --client-secrets <path>` once to complete browser OAuth.
5. Re-run the same command for recurring refreshes; the script reuses `secrets\youtube_token.json`.
6. Run `scripts\youtube_growth_report.py --analytics-csv <csv>` to produce a first-pass local report.

## Scripts

### Export Analytics

```powershell
C:\Users\kdeptula\skills\youtube-analytics\.venv\Scripts\python.exe C:\Users\kdeptula\skills\youtube-analytics\scripts\youtube_analytics_pull.py `
  --client-secrets C:\Users\kdeptula\skills\youtube-analytics\secrets\youtube_oauth_client.json `
  --token C:\Users\kdeptula\skills\youtube-analytics\secrets\youtube_token.json `
  --output-dir C:\Users\kdeptula\skills\youtube-analytics\data `
  --start-date 2026-05-01 `
  --end-date today
```

Default outputs:

- `C:\Users\kdeptula\skills\youtube-analytics\data\analytics_by_video.csv`
- `C:\Users\kdeptula\skills\youtube-analytics\data\analytics_by_day.csv`
- `C:\Users\kdeptula\skills\youtube-analytics\data\video_metadata.csv`

Useful options:

- `--output-dir <dir>`: write data elsewhere.
- `--token <path>`: use a specific token file.
- `--channel-id <id>`: query a specific authorized channel; default is `MINE`.
- `--metrics <csv>`: override Analytics API metrics.
- `--skip-metadata`: skip Data API metadata enrichment.

### Generate Report

```powershell
python C:\Users\kdeptula\skills\youtube-analytics\scripts\youtube_growth_report.py `
  --analytics-csv C:\Users\kdeptula\skills\youtube-analytics\data\analytics_by_video.csv `
  --metadata-csv C:\Users\kdeptula\skills\youtube-analytics\data\video_metadata.csv
```

## Recurring Use

For recurring automation, schedule the export script, not Codex itself. Use Windows Task Scheduler or a Codex automation only after the first OAuth token exists. Do not schedule jobs that require interactive OAuth approval.

Recommended recurring command:

```powershell
C:\Users\kdeptula\skills\youtube-analytics\.venv\Scripts\python.exe C:\Users\kdeptula\skills\youtube-analytics\scripts\youtube_analytics_pull.py `
  --client-secrets C:\Users\kdeptula\skills\youtube-analytics\secrets\youtube_oauth_client.json `
  --token C:\Users\kdeptula\skills\youtube-analytics\secrets\youtube_token.json `
  --output-dir C:\Users\kdeptula\skills\youtube-analytics\data `
  --start-date 2026-05-01 `
  --end-date today
```

When a user asks for channel growth advice, inspect the latest CSV files first, then derive recommendations from measured retention, views, engagement, publish timing, and topic patterns. Clearly separate measured findings from subjective content strategy judgment.
