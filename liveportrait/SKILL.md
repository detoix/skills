---
name: liveportrait
description: Efficient portrait animation that transfers motion from a driving video to a source image with a stable local CPU workflow.
---

# LivePortrait: Efficient Portrait Animation

LivePortrait is a high-speed motion transfer framework that animates a static avatar using a "driving video" or motion template.

## Environment Details
- **Location**: `C:\Users\kdeptula\LivePortrait`
- **Virtual Env**: `C:\Users\kdeptula\LivePortrait\.venv`
- **Weights**: `C:\Users\kdeptula\LivePortrait\pretrained_weights`

## Workflow

### 1. Simple Animation (Headless)
Run from the `LivePortrait` directory using the local venv. 
**Default**: Use the stable local CPU path.
**Note**: Force UTF-8 on Windows to avoid `rich`/emoji console crashes. LivePortrait itself still generates concat preview output, so if you do not want it, remove the `_concat` file after a successful run. Outputs should go next to the source file, and auto-generated driving `.pkl` templates should be removed after successful runs unless they are explicitly wanted for reuse.

```powershell
# Set Environment
$env:PATH += ";C:\Users\kdeptula\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:ORT_TENSORRT_UNAVAILABLE = "1"
$env:ORT_CUDA_UNAVAILABLE = "1"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$source = "path/to/avatar.png"
$driving = "path/to/driving_video.mp4"
$outputDir = Split-Path -Parent $source

cd C:\Users\kdeptula\LivePortrait
.\.venv\Scripts\python.exe inference.py `
    -s $source `
    -d $driving `
    -o $outputDir `
    --flag_crop_driving_video `
    --flag_stitching

Remove-Item -LiteralPath (Join-Path $outputDir "$([System.IO.Path]::GetFileNameWithoutExtension($source))--$([System.IO.Path]::GetFileNameWithoutExtension($driving))_concat.mp4") -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $outputDir "$([System.IO.Path]::GetFileNameWithoutExtension($source))--$([System.IO.Path]::GetFileNameWithoutExtension($driving))_concat.jpg") -ErrorAction SilentlyContinue
Remove-Item -LiteralPath ([System.IO.Path]::ChangeExtension($driving, ".pkl")) -ErrorAction SilentlyContinue
```

### 1a. Preferred Wrapper
Prefer the local helper when possible. It bakes in the UTF-8 fix, writes outputs next to the source by default, removes `_concat` artifacts automatically, and deletes auto-generated driving `.pkl` templates after success.

```powershell
cd C:\Users\kdeptula\LivePortrait
.\.venv\Scripts\python.exe animate_custom.py `
    -s "path/to/avatar.png" `
    -d "path/to/driving_video.mp4"
```

### 2. Behavior Control
- **Idle Blinking**: Use a driving video where you simply look at the camera and blink.
- **Natural Talking**: Use a video of a person talking to transfer lip sync.
- **Gradio UI**: Run `python app.py` to use sliders for precise eye/mouth control.

## Troubleshooting
- **DLL Load Failed**: Use the local CPU path by setting `ORT_TENSORRT_UNAVAILABLE=1` and `ORT_CUDA_UNAVAILABLE=1`.
- **`rich` / UnicodeEncodeError on Windows**: Set `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, and `[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()` before running.
- **Stitching Issues**: Always use `--flag_stitching` to ensure the head doesn't "float" away from the shoulders.

## References
- **GitHub**: [KwaiVGI/LivePortrait](https://github.com/KwaiVGI/LivePortrait)
- **Local Animate Script**: `C:\Users\kdeptula\LivePortrait\animate_custom.py`
