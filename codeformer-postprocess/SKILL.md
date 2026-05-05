---
name: codeformer-postprocess
description: High-fidelity face restoration for videos using CodeFormer. Use when you need to sharpen facial features, enhance clarity in generated videos, or restore low-resolution human faces in video files.
---

# CodeFormer Face Restoration

Enhance facial clarity in generated videos (LatentSync/SVD) using the CodeFormer architecture.

## Prerequisites
- **FFmpeg**: Must be in PATH. Local: `%USERPROFILE%\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin`
- **Environment**: Use ComfyUI venv and set `PYTHONPATH` to ComfyUI core.
- **Implementation Root**: `%USERPROFILE%\Downloads\speech-gen`
- **Script**: `%USERPROFILE%\Downloads\speech-gen\postprocess_face_restore.py`

## Workflow

### 1. Set Environment
```powershell
# Set PYTHONPATH to your local ComfyUI path
$env:PYTHONPATH = "%USERPROFILE%\AppData\Local\Programs\ComfyUI\resources\ComfyUI"

# Run with ComfyUI venv
& "%USERPROFILE%\Documents\ComfyUI\.venv\Scripts\python.exe" `
  "%USERPROFILE%\Downloads\speech-gen\postprocess_face_restore.py" `
  --input "input.mp4" `
  --output "restored.mp4" `
  --fidelity 0.6 `
  --device cuda
```

Run from the implementation root when possible:

```powershell
Set-Location "%USERPROFILE%\Downloads\speech-gen"
```

### 2. Verify Output

After every restoration pass:

- verify the restored MP4 exists and is non-empty
- compare duration and resolution with the input presenter clip using `ffprobe`
- extract at least one face frame for visual inspection before replacing the original synced clip
- keep the original synced clip when restoration introduces identity drift, waxy detail, or temporal instability
- record accepted and rejected restored clips in the project manifest

## Options
- **Fidelity (`--fidelity`)**:
  - `0.6`: Balanced local default for this machine and workflow.
  - `0.5`: Slightly stronger restoration.
  - `0.7`: Preserves more identity.
  - `0.3`: Stronger restoration.
- **Detector (`--detector`)**: Default `retinaface_resnet50`, use `YOLOv5n` for speed.

## Parallelism

- This step can run in parallel on the local GPU.
- Known-good local setting: up to `3` concurrent runs at `--fidelity 0.6`.
- Prefer batching visible presenter clips in groups of `2-3` instead of strictly serial execution when throughput matters.
- If GPU instability appears, reduce the batch size before changing fidelity.

## References
- **Model**: `%USERPROFILE%\Documents\ComfyUI\models\facerestore_models\codeformer.pth`
- **Custom Node**: Uses `facerestore_cf` for architecture definitions.

