# Usage

## Core Command

```powershell
node scripts/record_broll.mjs `
  --url "https://example.com" `
  --output "C:\clips\example.webm"
```

## Important Flags

- `--duration <seconds>`: total clip length, default `12`
- `--scroll constant|static`: steady fixed-speed downward scroll or static capture
- `--viewport <width>x<height>`: browser viewport, default `1600x900`
- `--video-size <width>x<height>`: saved video frame, default `1600x900`
- `--wait-for-selector <selector>`: wait until a target element is visible
- `--cookie-consent off|auto`: try to dismiss common cookie consent banners before recording; default `off`
- `--click <selector>`: click a selector before recording; repeatable
- `--hide <selector>`: hide elements before recording; repeatable
- `--settle-ms <milliseconds>`: time to let the page settle before recording starts
- `--screenshot <path>`: save a preview still before recording for validation

Every webpage capture must run a cleanup pass before the validation screenshot. Use `--cookie-consent auto` and add repeatable `--click` / `--hide` selectors for any visible overlay, popup, modal, banner, newsletter prompt, sticky UI, or chat widget. Do not accept a clip if the screenshot or recording still shows an obstructive overlay; re-record with stronger cleanup selectors.

The recorder runs in two phases. It first opens the page without video recording, waits for load, runs clicks/cookie handling/hides, lets the page settle, saves the validation screenshot, and stores cookies/Web Storage. It then opens a new video-recording context with that prepared state, reloads the URL, re-runs cleanup, waits briefly for visible content, records the requested scroll/static window, and trims the final `.webm` to the last requested `--duration` seconds.

## Examples

Record a scrolling homepage clip:

```powershell
node scripts/record_broll.mjs `
  --url "https://www.spacex.com" `
  --output "C:\clips\spacex-home.webm" `
  --screenshot "C:\clips\spacex-home.png" `
  --duration 15 `
  --scroll constant
```

Record a static hero section after dismissing a cookie banner:

```powershell
node scripts/record_broll.mjs `
  --url "https://example.com" `
  --output "C:\clips\hero.webm" `
  --screenshot "C:\clips\hero.png" `
  --duration 10 `
  --scroll static `
  --cookie-consent auto `
  --click ".cookie-accept" `
  --hide ".chat-widget"
```

## Output Behavior

- The script saves a `.webm` file at the requested path.
- If requested, the script also saves a screenshot at the requested path.
- Parent directories are created automatically.
- The script prints the resolved output path on success.
- The script prints the final URL, page title, and initial navigation HTTP status for validation.
- The saved `.webm` is trimmed to the requested duration, so startup/loading frames from the recording context are discarded.
- In `constant` mode, the recorder scrolls at a fixed readable speed instead of trying to reach the bottom of the page.
- If the site is too short to scroll meaningfully, the script automatically holds or performs minimal movement rather than forcing a fake long scroll.
