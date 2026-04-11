---
name: latentsync
description: High-fidelity lip-syncing for videos using LatentSync. Use when you need to synchronize a video of a person talking with a new audio track, ensuring realistic lip movements and proper audio-video alignment.
---

# LatentSync Lip-Syncing

High-quality synchronization of facial movements using the LatentSync pipeline.

## Prerequisites
- **FFmpeg**: Must be in PATH. Local path: `C:\Users\kdeptula\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin`
- **Environment**: Use the local venv in `official-latentsync`.

## Workflow

### 1. Running Inference
Execute from the `official-latentsync` directory using its local virtual environment.

```powershell
cd official-latentsync
.\.venv\Scripts\python.exe -m scripts.inference `
    --unet_config_path "configs/unet/stage2.yaml" `
    --inference_ckpt_path "checkpoints/latentsync_unet.pt" `
    --video_path "../input.mov" `
    --audio_path "../input.wav" `
    --video_out_path "../output_synced.mp4" `
    --inference_steps 25 `
    --guidance_scale 1.5
```

## Key Features
- **Patched Pipeline**: Handles partial chunks/padding. Output duration matches input audio exactly.
- **Audio Fidelity**: Uses original source audio for final mux instead of 16kHz internal degraded audio.
- **Guidance Scale**: Default 1.5. Increase for tighter sync, decrease for more fluid movement.

## References
- **Models**: `checkpoints/latentsync_unet.pt` and Whisper checkpoints.
- **Configs**: `configs/unet/stage2.yaml`.

