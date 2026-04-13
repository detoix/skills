---
name: playwright-broll-recorder
description: Record webpage B-roll clips as video files using Playwright. Use when asked to capture a website, scroll through a landing page, record a product page, make a screen recording for B-roll, save a webpage clip, or generate browser footage from a URL for video editing.
---

# Playwright B-Roll Recorder

Use this skill to turn a webpage into a saved video clip for editing. Prefer the bundled script over ad hoc browser automation so output paths, timing, and scrolling behavior stay consistent.

## Workflow

1. Collect the recording inputs:
   - URL
   - output file path
   - clip duration
   - whether to use `constant` scroll or `static` hold
   - optional selector to wait for before recording
   - optional selectors to click or hide first
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
- Default viewport: `1440x900`
- Default video frame: `1280x720`

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
- `--click ".cookie-accept"`: click a cookie banner or modal close button before recording
- `--hide ".sticky-header"`: hide obstructive UI before recording
- `--screenshot "C:\clips\preview.png"`: save a preview still for validation
- `--scroll constant`: record with steady readable downward motion
- `--scroll static`: hold a fixed frame and let the page's own motion play
- `--viewport 1600x1000`: change browser viewport
- `--video-size 1280x720`: change output video frame size

## Operating Rules

- Use the script directly; do not improvise a separate Playwright flow unless you need behavior the script cannot provide.
- Save clips as `.webm`. Do not promise `.mp4` unless the environment has a separate transcoding step.
- Prefer 8-20 second clips for B-roll.
- Always capture a preview screenshot and inspect it before declaring success.
- Treat obvious failures as invalid even if the recorder exits cleanly: `404`, access denied pages, blank shells, login walls, broken hero sections, cookie walls covering the frame, or obviously off-topic content.
- Treat final URL, page title, and HTTP status as validation signals. A saved file alone is not enough.
- Choose `static` for docs pages, strong hero sections, dashboards, product UIs, or pages with their own animation.
- Choose `constant` for long marketing pages or when the shot needs visible downward motion.
- If a site has a cookie banner, newsletter modal, or chat bubble, remove it before recording using `--click` or `--hide`.
- If the page is very short, use `--scroll static` instead of pretending to scroll.
- If the user wants multiple clips, run the script multiple times with distinct output paths.

## Resources

- Recorder script: [scripts/record_broll.mjs](scripts/record_broll.mjs)
- Flags and behavior: [references/usage.md](references/usage.md)
