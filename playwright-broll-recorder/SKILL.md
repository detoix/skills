---
name: playwright-broll-recorder
description: Record webpage B-roll clips as video files using Playwright. Use when asked to capture a website, scroll through a landing page, record a product page, make a screen recording for B-roll, save a webpage clip, or generate browser footage from a URL for video editing.
---

# Playwright B-Roll Recorder

Use this skill to turn a webpage into a saved video clip for editing. Prefer the bundled script over ad hoc browser automation so output paths, timing, and scrolling behavior stay consistent.

For YouTube autopipeline production projects, pass `--project-dir <project-dir>` to `scripts\record_broll.mjs`. The script enforces the parent Creative Approval Gate before recording.

## Workflow

1. Collect the recording inputs:
   - URL, including `file:///...` URLs for project-local synthetic-motion HTML/mock UI created as B-roll
   - output file path
   - clip duration
   - whether to use `constant` scroll or `static` hold
   - target video language or locale when relevant
   - optional selector to wait for before recording
   - cleanup selectors to click or hide before recording when any overlay, popup, banner, modal, cookie wall, newsletter prompt, sticky UI, or chat widget is visible
2. Run [scripts/record_broll.mjs](scripts/record_broll.mjs).
3. Save a validation screenshot with `--screenshot` and inspect it before accepting the clip.
4. Check the script output for final URL, page title, and HTTP status.
5. Verify that the output `.webm` file exists.
6. Reject the capture and re-record if the preview or metadata indicates a broken page, error state, empty shell, or obviously wrong target.
7. Report the saved path back to the user only after validation.

## Defaults

- Default output format: `.webm`
- Default duration: `12` seconds
- Default mode: `constant`
- Default viewport: `1600x900`
- Default video frame: `1600x900`

## Use The Script

```powershell
node scripts/record_broll.mjs `
  --url "https://www.spacex.com" `
  --output "C:\clips\spacex-homepage.webm" `
  --duration 14 `
  --scroll constant
```

Useful options:

- `--wait-for-selector ".hero"`: wait for a specific element before recording
- `--cookie-consent auto`: try to dismiss common cookie consent banners before recording
- `--click ".cookie-accept"`: click a cookie banner or modal close button before recording
- `--hide ".sticky-header"`: hide obstructive UI before recording
- `--screenshot "C:\clips\preview.png"`: save a preview still for validation
- `--scroll constant`: record with steady readable downward motion
- `--scroll static`: hold a fixed frame and let the page's own motion play
- `--viewport 1600x900`: change browser viewport
- `--video-size 1600x900`: change output video frame size

## Operating Rules

- Use the script directly; do not improvise a separate Playwright flow unless you need behavior the script cannot provide.
- `file:///...` inputs are valid for recording project-local synthetic-motion HTML/mock UI created for B-roll.
- Save clips as `.webm`. Do not promise `.mp4` unless the environment has a separate transcoding step.
- Prefer 8-20 second clips for B-roll.
- Keep the browser viewport and recorded video frame on the same aspect ratio. Default both to `16:9`.
- For vertical full-screen B-roll, use a portrait viewport and video frame such as `--viewport 1080x1920 --video-size 1080x1920` when the page has a useful responsive layout.
- For vertical `STACK_3` or wide UI context, keep landscape capture such as `1600x900` and let the composer place it in the stack.
- Let the page fully load, apply required clicks/hides, and honor `--settle-ms` before the useful recording window begins.
- Prefer pages whose visible language matches the video language or locale when a localized version exists.
- When multiple candidate pages are available, prefer the one that feels culturally and regionally appropriate for the target audience instead of defaulting to generic English.
- For localized videos, prefer localized docs, regional landing pages, country-specific pricing or onboarding flows, and UI text that matches the narration language when possible.
- If the best visual source is only available in another language, treat that as a conscious fallback and note it instead of silently mixing languages.
- Always capture a preview screenshot and inspect it before declaring success.
- For project-local synthetic-motion HTML/mock UI, the validation screenshot must show the intended scene, no overlapping scene states, text fitting in frame, no accidental real data, and an output aspect ratio that matches the planned timeline use.
- Treat obvious failures as invalid even if the recorder exits cleanly: `404`, access denied pages, blank shells, login walls, broken hero sections, cookie walls covering the frame, missing CSS/unloaded styling, non-functional page state, or obviously off-topic content.
- Treat final URL, page title, and HTTP status as validation signals. A saved file alone is not enough.
- Choose `static` for docs pages, strong hero sections, dashboards, product UIs, or pages with their own animation.
- Choose `constant` for long marketing pages or when the shot needs visible downward motion.
- Every webpage capture must include a cleanup pass before the validation screenshot: use `--cookie-consent auto`, and add explicit `--click` or `--hide` selectors for any visible overlay, popup, modal, banner, newsletter prompt, sticky UI, or chat widget.
- Any validation screenshot or recorded clip with a visible popup, modal, cookie banner, newsletter prompt, chat widget, login wall, or other obstructive overlay is invalid. Re-record with stronger `--click` or `--hide` selectors before accepting the asset.
- If the page is very short, use `--scroll static` instead of pretending to scroll.
- If the user wants multiple clips, run the script multiple times with distinct output paths.

## Resources

- Recorder script: [scripts/record_broll.mjs](scripts/record_broll.mjs)
- Flags and behavior: [references/usage.md](references/usage.md)
