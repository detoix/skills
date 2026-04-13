# Project Layout

Create one project directory per video.

Recommended structure:

```text
project-root/
  brief.json
  script.md
  script.json
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

Rules:

- Keep source assets immutable after intake.
- Save generated outputs in dedicated directories by stage.
- Use stable IDs that match script segment ids or chunk ids.
- Keep one manifest for TTS and one manifest for media assets.
- If the user provides soundtrack music, store it under `source-assets/` with a deterministic name such as `soundtrack.mp3` or `soundtrack.wav`.
