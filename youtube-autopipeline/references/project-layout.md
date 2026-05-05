# Project Layout

Create one project directory per video.

## Landscape (16:9) Layout

```text
project-root/
  brief.json
  script.md
  script.json
  validation-report.json
  manifests/
    tts-manifest.json
    assets-manifest.json
  source-assets/
    presenter-front.mp4
    presenter-profile.mp4
    speech-sample.wav
    sample-transcript.txt
    soundtrack.mp3
  tts/
    T01.wav
    T02.wav
  synced/
    front/
      A01.mp4
      A02.mp4
    profile/
      P01.mp4
      P02.mp4
  broll/
    B01.webm
    B02.mp4
  timeline.json
  final_audio.wav
  final_output.mp4
```

## Vertical (9:16) Layout

```text
project-root/
  brief.json
  script.md
  script.json
  validation-report.json
  manifests/
    tts-manifest.json
    assets-manifest.json
  source-assets/
    presenter-front.mp4
    presenter-profile.mp4        (optional - omit if no PiP needed)
    speech-sample.wav
    sample-transcript.txt
    soundtrack.mp3
  tts/
    T01.wav
    T02.wav
  synced/
    front/
      A01.mp4
      A02.mp4
    profile/                     (omit if no profile plate provided)
      P01.mp4
      P02.mp4
  broll/
    B01.webm
    B02.mp4
  timeline.json
  final_audio.wav
  final_output.mp4
```

## Rules

- Keep source assets immutable after intake.
- Save generated outputs in dedicated directories by stage.
- Use stable IDs that match script segment ids or chunk ids.
- Keep one manifest for TTS and one manifest for media assets.
- Save checker output as `validation-report.json` when running `pipeline_check.py --json`.
- If the user provides soundtrack music, store it under `source-assets/` with a deterministic name such as `soundtrack.mp3` or `soundtrack.wav`.
- For vertical mode, presenter source videos should be portrait (9:16) when available. Landscape plates are accepted but will be center-cropped.
- For vertical mode, `presenter-profile.mp4` and the `synced/profile/` directory are optional. Omit them entirely when no 3/4-profile plate is provided.
