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
    music-manifest.json
    audio-mix-manifest.json
    selected-visuals.json
    z-image-plan.json
    visual-qa.json
    visual-qa.md
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
  script.md
  script.json
  validation-report.json
  manifests/
    tts-manifest.json
    assets-manifest.json
    music-manifest.json
    audio-mix-manifest.json
    selected-visuals.json
    visual-qa.json
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
    boards/
      S03_process/
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
- Save asset intake output from `asset_inventory.py` as `manifests/assets-manifest.json`.
- Save music intake output from `music_intake.py` as `manifests/music-manifest.json`; disabled music should still be recorded with `enabled: false` when the run made an explicit music decision.
- Save composer audio mix output as `manifests/audio-mix-manifest.json` after final audio muxing.
- For test-only runs, run `asset_inventory.py` with `--test-input-label` so disposable test inputs cannot be confused with user-provided production assets.
- Validate production asset manifests with `pipeline_check.py --asset-manifest`; only test runs may pass `--allow-test-input`.
- Save z-image planning output from `z_image_plan.py` as `manifests/z-image-plan.json`; generated stills belong under `broll/generated/`.
- Save animated board outputs from `animated-broll-boards` under `broll/boards/<board-id>/`; production abstract/UI/infographic boards should be `.webm` clips, not ad hoc static PNG/Pillow boards.
- Save selected B-roll and non-presenter visual choices as `manifests/selected-visuals.json`.
- Validate z-image plans with `pipeline_check.py --z-image-plan --require-z-image-review` before timeline use.
- Validate selected visuals with `pipeline_check.py --selected-visuals` before timeline use.
- Save final-render frame QA output from `visual_qa.py` as `manifests/visual-qa.json`; the helper writes extracted frames under `qa/final-frames/<video-stem>/` and a matching `qa/contact-sheet-<video-stem>.jpg`.
- Save the Markdown QA report beside the JSON report. Final pass status requires agent visual review notes, not only structural checks.
- If the user provides soundtrack music, run `music_intake.py`; it copies the local file under `source-assets/` with a deterministic name such as `soundtrack.mp3` or `soundtrack.wav`.
- For vertical mode, presenter source videos should be portrait (9:16) when available. Landscape plates are accepted but will be center-cropped.
- For vertical mode, `presenter-profile.mp4` and the `synced/profile/` directory are optional. Omit them entirely when no 3/4-profile plate is provided.
