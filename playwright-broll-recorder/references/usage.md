# Usage

## Core Command

```powershell
node scripts/record_broll.mjs `
  --url "https://example.com" `
  --output "C:\clips\example.webm"
```

## Important Flags

- `--duration <seconds>`: total clip length, default `12`
- `--scroll constant|static`: steady scroll or static capture
- `--viewport <width>x<height>`: browser viewport, default `1600x900`
- `--video-size <width>x<height>`: saved video frame, default `1600x900`
- `--wait-for-selector <selector>`: wait until a target element is visible
- `--click <selector>`: click a selector before recording; repeatable
- `--hide <selector>`: hide elements before recording; repeatable
- `--settle-ms <milliseconds>`: time to let the page settle before recording starts
- `--screenshot <path>`: save a preview still before recording for validation

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
  --click ".cookie-accept" `
  --hide ".chat-widget"
```

## Output Behavior

- The script saves a `.webm` file at the requested path.
- If requested, the script also saves a screenshot at the requested path.
- Parent directories are created automatically.
- The script prints the resolved output path on success.
- The script prints the final URL, page title, and initial navigation HTTP status for validation.
- If the site is too short to scroll meaningfully, the script automatically holds or performs minimal movement rather than forcing a fake long scroll.
