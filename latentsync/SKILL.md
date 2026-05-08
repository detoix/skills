---
name: latentsync
description: High-fidelity lip-syncing for videos using LatentSync. Use when you need to synchronize a video of a person talking with a new audio track, ensuring realistic lip movements and proper audio-video alignment.
---

# LatentSync Lip-Syncing

High-quality synchronization of facial movements using the LatentSync pipeline.

## Prerequisites
- **FFmpeg**: Must be in PATH. Local path: `%USERPROFILE%\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin`
- **Environment**: Use the local venv in `official-latentsync`.

## Workflow

### 1. Running Inference
For YouTube autopipeline projects, run LatentSync only through the guarded production wrapper so the Creative Approval Gate
is checked immediately before inference. Replace `<command...>` with the normal LatentSync command:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\guarded_production_command.py `
  --project-dir <project-dir> `
  -- <command...>
```

Use `scripts.inference` for all LatentSync inference. It loads LatentSync once, processes one or more jobs sequentially,
and can reuse affine face transforms when jobs use the same silent presenter plate. This is a performance optimization
only; keep the same checkpoint, `inference_steps`, `guidance_scale`, seed policy, source plates, and clean audio files.

For user-provided reusable avatar assets, use persistent affine cache in the asset folder, not in the project folder. If
the asset manifest has `asset_root`, create/use:

```text
<asset_root>\.latentsync-cache
```

Cache identity must be hash-based, not filename-based. The batch runner keys cache files by source video SHA-256,
resolution, mask, mask image SHA-256, and cache schema version. If cache metadata does not match, the runner ignores it
and recomputes normally.

To precompute persistent affine cache for all reusable avatar videos in an asset folder, run:

```powershell
cd C:\Users\kdeptula\Downloads\speech-gen\official-latentsync
.\.venv\Scripts\python.exe -m scripts.precompute_affine_cache `
    --asset-root "<asset-root>" `
    --report-json "<asset-root>\.latentsync-cache\precompute-report.json"
```

This precomputes face alignment data only. It must not synthesize dummy audio or run full lip-sync.

Batch job file shape:

```json
[
  {
    "job_id": "S04",
    "video_path": "C:/path/project/source-assets/presenter-front.mp4",
    "source_video_path": "C:/Users/kdeptula/Videos/avatar/front-9x16_2.mp4",
    "video_sha256": "7ff8f11da8e99bd719598acb86aa1e7e20286c7537da2be3f8e9bf17f1006409",
    "affine_cache_dir": "C:/Users/kdeptula/Videos/avatar/.latentsync-cache",
    "audio_path": "C:/path/project/tts/clean/T04.wav",
    "video_out_path": "C:/path/project/synced/front/S04.mp4",
    "inference_steps": 30,
    "guidance_scale": 1.5,
    "seed": 1247
  }
]
```

For best cache reuse, group jobs by identical `video_path` and run longer audio chunks before shorter chunks within each
group. Use `--reuse_affine_cache` only for sequential batch jobs, never for parallel LatentSync runs.

```powershell
cd C:\Users\kdeptula\Downloads\speech-gen\official-latentsync
.\.venv\Scripts\python.exe -m scripts.inference `
    --unet_config_path "configs/unet/stage2.yaml" `
    --inference_ckpt_path "checkpoints/latentsync_unet.pt" `
    --jobs_json "<project-dir>\manifests\latentsync-jobs.json" `
    --report_json "<project-dir>\manifests\latentsync-batch-report.json" `
    --inference_steps 30 `
    --guidance_scale 1.5 `
    --reuse_affine_cache `
    --affine_cache_dir "C:\Users\kdeptula\Videos\avatar\.latentsync-cache"
```

For standalone non-autopipeline single-clip work, execute the same runner from the `official-latentsync` directory using
its local virtual environment.

```powershell
cd official-latentsync
.\.venv\Scripts\python.exe -m scripts.inference `
    --unet_config_path "configs/unet/stage2.yaml" `
    --inference_ckpt_path "checkpoints/latentsync_unet.pt" `
    --video_path "../input.mov" `
    --audio_path "../input.wav" `
    --video_out_path "../output_synced.mp4" `
    --inference_steps 30 `
    --guidance_scale 1.5
```

### 2. Verify Output

Do not assume LatentSync succeeded because inference printed progress. After every run:

1. Verify `--video_out_path` exists and is non-empty.
2. Use `ffprobe` to compare output duration with the input audio duration.
3. Save the command, exit status, output path, and duration check in the project manifest or stage log.
4. If the output file is missing, zero-byte, or duration-mismatched, treat the sync as failed and do not pass that segment to the composer.

## Key Features
- **Patched Pipeline**: Handles partial chunks/padding. Output duration matches input audio exactly.
- **Audio Fidelity**: Uses original source audio for final mux instead of 16kHz internal degraded audio.
- **Guidance Scale**: Default 1.5. Increase for tighter sync, decrease for more fluid movement.

## References
- **Models**: `checkpoints/latentsync_unet.pt` and Whisper checkpoints.
- **Configs**: `configs/unet/stage2.yaml`.
