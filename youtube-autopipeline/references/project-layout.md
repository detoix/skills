# Project Layout

Create one project directory per video.

## Landscape (16:9) Layout

```text
project-root/
  brief.json
  script.json
  validation-report.json
  manifests/
    tts-prototype-manifest.json
    final-audio-manifest.json
    assets-manifest.json
    music-manifest.json
    audio-mix-manifest.json
    selected-visuals.json
    selected-visuals.resolved.json
    z-image-plan.json
    final-render-qa.json
    final-render-qa.md
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
    boards/
      S03_process/
        board-creative-brief.json
        index.html
        board-manifest.json
        board-qa.json
        preview.png
        S03_process.webm
    generated/
      S03_concept-still.png
  timeline.json
  final_audio.wav
  final_output.mp4
  qa/
    final-frames/
      final_output/
    contact-sheet-final_output.jpg
```

## Vertical (9:16) Layout

```text
project-root/
  brief.json
  script.json
  validation-report.json
  manifests/
    tts-prototype-manifest.json
    final-audio-manifest.json
    assets-manifest.json
    music-manifest.json
    audio-mix-manifest.json
    selected-visuals.json
    selected-visuals.resolved.json
    final-render-qa.json
  source-assets/
    presenter-front.mp4
    presenter-profile.mp4        (optional - omit if no presenter overlay needed)
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
    boards/
      S03_process/
        board-creative-brief.json
        index.html
        board-manifest.json
        board-qa.json
        preview.png
        S03_process.webm
  timeline.json
  final_audio.wav
  final_output.mp4
  qa/
    final-frames/
      final_output/
    contact-sheet-final_output.jpg
```

## Rules

- Keep source assets immutable after intake.
- Save generated outputs in dedicated directories by stage.
- Use stable IDs that match script segment ids or chunk ids.
- Keep one manifest for TTS and one manifest for media assets.
- Save checker output as `validation-report.json` when running `pipeline_check.py --json`.
