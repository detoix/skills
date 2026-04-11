---
name: codeformer-postprocess
description: High-fidelity face restoration for videos using CodeFormer. Use when you need to sharpen facial features, enhance clarity in generated videos, or restore low-resolution human faces in video files.
---

# CodeFormer Face Restoration

Enhance facial clarity in generated videos (LatentSync/SVD) using the CodeFormer architecture.

## Prerequisites
- **FFmpeg**: Must be in PATH. Local: `C:\Users\kdeptula\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin`
- **Environment**: Use ComfyUI venv and set `PYTHONPATH` to ComfyUI core.

## Workflow

### 1. Running Restoration
```powershell
# Set environment
$env:PYTHONPATH = "C:\Users\kdeptula\AppData\Local\Programs\ComfyUI\resources\ComfyUI"

# Run with ComfyUI venv
& "C:\Users\kdeptula\Documents\ComfyUI\.venv\Scripts\python.exe" `
  "postprocess_face_restore.py" `
  --input "input.mp4" `
  --output "restored.mp4" `
  --fidelity 0.5 `
  --device cuda
```

## Options
- **Fidelity (`--fidelity`)**:
  - `0.5`: Balanced (default).
  - `0.7`: Preserves more identity.
  - `0.3`: Stronger restoration.
- **Detector (`--detector`)**: Default `retinaface_resnet50`, use `YOLOv5n` for speed.

## References
- **Model**: `C:\Users\kdeptula\Documents\ComfyUI\models\facerestore_models\codeformer.pth`
- **Custom Node**: Uses `facerestore_cf` for architecture definitions.

