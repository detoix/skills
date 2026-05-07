---
name: pexels-stock-downloader
description: Search and download stock video clips from Pexels with the official API. Use when Codex needs non-web B-roll for video production, wants to fetch stock clips from a text query, or needs to save one or more matching Pexels videos into a local project folder.
---

# Pexels Stock Downloader

Use this skill to fetch stock video clips from Pexels with the official API. Prefer the bundled script over ad hoc HTTP requests so clip selection, filenames, and manifest output stay consistent.

For YouTube autopipeline production projects, pass `--project-dir <project-dir>` to the downloader. The script enforces the parent Creative Approval Gate before downloading clips.

## Workflow

1. Confirm `PEXELS_API_KEY` is available either in the environment or in `.env` at the skill root.
2. Collect the query and download target:
   - search query
   - output directory
   - number of clips
   - optional orientation
   - optional min and max duration
3. Run [scripts/download_pexels_videos.py](scripts/download_pexels_videos.py).
4. Verify the downloaded files and `pexels_manifest.json`.
5. Deduplicate candidate clips against all selected B-roll for the project by Pexels `id` and `video_file_url`.
6. Inspect at least one preview frame from each accepted clip before using it in a reel timeline.
7. Report the saved paths, rejected duplicates, and weak matches back to the user.

## Use The Script

```powershell
python scripts\download_pexels_videos.py `
  --query "modern office teamwork laptops" `
  --output-dir "C:\project\broll" `
  --count 3 `
  --orientation landscape
```

Useful options:

- `--min-duration 4`: reject very short clips
- `--max-duration 20`: reject very long clips
- `--orientation landscape|portrait|square|vertical|either`: filter by orientation; `vertical` maps to `portrait`, `either` omits the filter
- `--page 1`: fetch a later result page
- `--manifest path\to\manifest.json`: override manifest location
- `--dry-run`: search and score results without downloading files

## Authentication

The downloader loads `PEXELS_API_KEY` in this order:

1. real environment variable
2. `.env` file in the skill root
3. `.env` file in the current working directory

For local use, put this in [`.env`](.env):

```dotenv
PEXELS_API_KEY=your_key_here
```

## Operating Rules

- Use the script directly when possible.
- Use the official API key in `PEXELS_API_KEY`.
- Prefer landscape clips for YouTube unless the user explicitly wants vertical footage.
- When called from `youtube-autopipeline`, pass scriptwriter `orientation_preference` directly; the downloader handles `vertical` and `either`.
- Prefer a small number of strong matches over a large number of weak matches.
- Keep the manifest because downstream video skills can use it to map query to downloaded files.
- If the search results are poor, refine the query instead of downloading irrelevant clips.
- For vertical reels, reject clips whose main subject will be lost by center-crop unless they are planned for `STACK_3`.
- Record rejected weak matches in the project asset manifest so repeated searches do not reuse stale generic B-roll.
- Treat Pexels `id` and `video_file_url` as canonical identity. If the same id or URL appears in multiple search manifests, it is the same clip even when downloaded under different filenames.
- Do not use multiple renamed copies of the same Pexels clip as separate B-roll segments. Reject duplicates before timeline assembly unless the reuse is an intentional visual callback recorded in the project manifest.
- Pexels results are not authoritative species, location, product, or event evidence by default. If a segment depends on exact factual identity, use verified visuals or another source class instead of generic stock unless the preview frames clearly establish the required subject.
- When several searches return overlapping clips, stop expanding Pexels queries and switch source strategy: verified stills, generated visuals, local motion graphics, webpage/screen capture, or user-provided assets.

## References

- Script: [scripts/download_pexels_videos.py](scripts/download_pexels_videos.py)
- API notes and result fields: [references/api-notes.md](references/api-notes.md)
