---
name: youtube-autopipeline
description: >-
  End-to-end YouTube video orchestration for local automation pipelines. Use
  when the user asks to create a new YouTube video, make a video, produce a
  full video, or build a video pipeline from scratch. This skill should be
  preferred over `youtube-scriptwriter` whenever the request implies the whole
  workflow: planning, script, TTS, lip-sync, B-roll, timeline, and final
  assembly. Supports both landscape (16:9) and vertical (9:16) output formats.
---

# YouTube Autopipeline

This is an orchestration skill. It coordinates production stages, approval
gates, artifact dependencies, and final readiness. Capability skills own their
own implementation details and output contracts.

## Ownership

- The upstream authoring workflow owns `script.json`, including B-roll layouts,
  panels, source types, and visual direction.
- `youtube-scriptwriter` owns the `script.json` schema and baseline spoken-writing
  contract.
- `tts`, `latentsync`, `animated-broll-boards`,
  `playwright-broll-recorder`, `pexels-stock-downloader`,
  `moviepy-video-composer`, and `reel-captions` own their implementation choices.
- `youtube-autopipeline` owns gate order, artifact flow, validation calls, and
  final delivery readiness.

When upstream-authored planning artifacts exist, run validation and production
against those artifacts.

## Format Modes

- **landscape**: `1920x1080`, composer flag `--format landscape`, default
  presenter overlay scale `0.3`, landscape presenter plates.
- **vertical**: `1080x1920`, composer flag `--format vertical`, default presenter
  overlay scale `0.34`, portrait presenter plates preferred.

Composer invocation:

```powershell
python C:\Users\kdeptula\skills\moviepy-video-composer\scripts\compose_video.py `
  --project-dir <project-dir> `
  --timeline <project-dir>\timeline.json `
  --audio <project-dir>\final_audio.wav `
  --music <project-dir>\source-assets\soundtrack.mp3 `
  --output <project-dir>\final_output.mp4 `
  --format <landscape-or-vertical>
```

Use `--music NONE` when the project has no background music. Ingest user-supplied
music with:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\music_intake.py `
  --project-dir <project-dir> `
  --music <local-audio-path>
```

## Required Stages

The pipeline has three mandatory stages. Each later stage starts from the valid
approval artifact produced by the previous gate.

### Stage 1: Creative Gate

1. Gather or infer the topic, format mode, audience, language, tone,
   target duration, CTA goal, asset root, presenter assets, voice sample,
   exact voice-sample transcript, and optional music.
2. Create one project directory and keep generated artifacts inside it. Use
   [references/project-layout.md](references/project-layout.md).
3. Normalize available assets:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\asset_inventory.py `
     --asset-root <asset-root> `
     --output <project-dir>\manifests\assets-manifest.json
   ```
4. Create or reuse `script.json`. Upstream author QA runs before creative
   review when an upstream author is active.
5. Validate the script and assets:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --script <project-dir>\script.json `
     --format <landscape-or-vertical> `
     --mode script
   ```
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --asset-manifest <project-dir>\manifests\assets-manifest.json `
     --format <landscape-or-vertical> `
     --mode assets
   ```
6. Create the blocking creative review request:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\request_creative_review.py `
     --project-dir <project-dir>
   ```
7. After the user replies exactly `approved`, create the approval artifact:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\approve_creative_plan.py `
     --project-dir <project-dir> `
     --resume-signal approved
   ```
8. Validate the gate before prototype work:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --mode creative-gate
   ```

### Stage 2: Prototype Review Ready Gate

1. Generate final-quality narration through `tts` from the approved
   `script.json`.
2. Produce clean TTS chunks, `<project-dir>\final_audio.wav`,
   `manifests\tts-prototype-manifest.json`, and
   `manifests\final-audio-manifest.json`. Record TTS settings used for the
   approved prototype and final narration path.
3. Run pronunciation QA:
   ```powershell
   C:\Users\kdeptula\skills\tts\.venv\Scripts\python.exe C:\Users\kdeptula\skills\tts\scripts\tts_pronunciation_qa.py `
     --project-dir <project-dir> `
     --script <project-dir>\script.json `
     --tts-dir <project-dir>\tts\clean `
     --language <metadata.language> `
     --output <project-dir>\manifests\tts-pronunciation-qa.json
   ```
4. For the Prototype Review stage, build B-roll from each approved
   `script.json` panel `source_type` using its owning capability skill.
5. Create `timeline.prototype.source.json`, then materialize generated-image
   placeholders and `timeline.prototype.json`:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\build_prototype_timeline.py `
     --project-dir <project-dir> `
     --timeline <project-dir>\timeline.prototype.source.json `
     --script <project-dir>\script.json `
     --output <project-dir>\timeline.prototype.json `
     --format <landscape-or-vertical>
   ```
6. Use raw muted presenter video for prototype presenter panels. Record
   `presenter.latentsync: "skipped"` and
   `presenter.presenter_mode: "raw_muted_video"` in
   `manifests\prototype-manifest.json`.
7. Render the uncaptioned prototype review video as `outputs\prototype.mp4`.
8. Write `manifests\prototype-manifest.json` with project-relative paths and
   SHA-256 bindings for the script, prototype timeline, prototype MP4, final
   audio, final audio manifest, TTS manifest, pronunciation QA, presenter
   assets, TTS chunks, and generated-image placeholders.
9. Create the review request and portable handoff bundle:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\request_prototype_review.py `
     --project-dir <project-dir>
   ```
10. Validate prototype review readiness:
    ```powershell
    python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
      --project-dir <project-dir> `
      --mode prototype-review-ready
    ```
11. After the user replies exactly `approved`, create the prototype approval:
    ```powershell
    python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\approve_prototype.py `
      --project-dir <project-dir> `
      --resume-signal approved
    ```

### Stage 3: Final Production

1. Validate the approved prototype gate:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --mode prototype-approved
   ```
2. Reuse the approved `final_audio.wav` and
   `manifests\final-audio-manifest.json` from Stage 2 as final narration.
3. Create or update `manifests\presenter-plan.json`, then run `latentsync` for
   visible presenter segments and panels. Do not run LatentSync for B-roll
   presenter panels using `treatment: "blur"` because the presenter plate is
   heavily blurred behind evidence and is not a visible talking presenter.
4. Make and record the presenter-quality decision before final timeline
   assembly.
5. Produce final generated images for approved generated-image placeholder
   panels and review them before timeline use.
6. Reuse prototype B-roll assets that still match the approved script and
   final quality checks.
7. Write `manifests\selected-visuals.json` for final non-presenter visual
   assets, then resolve and validate it:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --selected-visuals <project-dir>\manifests\selected-visuals.json `
     --mode assets `
     --resolve-selected-visuals
   ```
8. Build `timeline.json` from accepted assets in
   `manifests\selected-visuals.resolved.json`, then validate timeline and audio:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --timeline <project-dir>\timeline.json `
     --audio <project-dir>\final_audio.wav `
     --format <landscape-or-vertical> `
     --mode timeline
   ```
9. Render `final_output.mp4` with `moviepy-video-composer`.
10. Burn captions with `reel-captions`:
    ```powershell
    python C:\Users\kdeptula\skills\reel-captions\scripts\generate_reel_captions.py `
      --project-dir <project-dir> `
      --audio <project-dir>\final_audio.wav `
      --video <project-dir>\final_output.mp4 `
      --script <project-dir>\script.json `
      --output <project-dir>\final_output_captioned.mp4 `
      --language <metadata.language>
    ```
11. Run final render QA on the captioned output unless captions are disabled:
    ```powershell
    python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\final_render_qa.py `
      --project-dir <project-dir> `
      --video <project-dir>\final_output_captioned.mp4 `
      --timeline <project-dir>\timeline.json `
      --status needs_review
    ```
12. Report final outputs or blockers. When final production succeeds, include:
    final video path, QA status, notable warnings, exactly 3 title options, one
    concise description, and 5-10 relevant tags.

## Cross-Skill Artifact Contracts

- `script.json`: shape and baseline contract are owned by `youtube-scriptwriter`;
  authored content, B-roll layouts, panels, source types, and visual direction
  are owned by the upstream authoring workflow when present.
- `manifests\creative-approval.json`: generated by
  `approve_creative_plan.py`; binds `script.json`.
- `manifests\prototype-manifest.json`: portable prototype manifest with
  project-relative paths and SHA-256 bindings.
- `manifests\prototype-approval.json`: generated by `approve_prototype.py`;
  unlocks final production.
- `manifests\selected-visuals.json`: agent-authored final visual intent.
- `manifests\selected-visuals.resolved.json`: resolver-authored validation
  manifest for final non-presenter B-roll timeline use.
- `manifests\final-render-qa.json`: final delivery QA record with inspected
  frames and agent visual review status.

## B-Roll and Timeline Boundaries

Supported B-roll panel `source_type` values are `webpage`, `stock`,
`screen-record`, `generated-image`, `manual`, `synthetic-motion`, and
`web-evidence`.

`web-evidence` selected visuals are user/project-supplied local cropped proof
images with `source_url` or `capture_source_url`.

Presenter panels, A-roll, captions, overlays, and layout names are outside
selected-visuals source diversity.

Final non-presenter B-roll timeline paths come from accepted items in
`manifests\selected-visuals.resolved.json`. The resolver owns identity,
provenance, source-type verification, and reuse checks.

## Final Render QA

Final delivery requires visual inspection of the rendered result. For captioned
reels, inspect `final_output_captioned.mp4`; for caption-disabled runs, inspect
`final_output.mp4`.

Use enough extracted frames to cover the opening, major segment boundaries,
presenter-overlay segments, text-overlay segments, synthetic-motion segments,
generated visuals, and the ending. Use
[references/professional-qa-rubric.md](references/professional-qa-rubric.md)
before setting final pass status.

Record inspected frame paths, pass/fail status, review notes, and rerender
actions in `manifests\final-render-qa.json`.

## Failure Rules

Report the exact blocker and artifact when any required input, runtime,
approval artifact, validation output, or production output is unavailable.

Production requires:

- topic after intake
- presenter source videos
- speech sample
- exact speech-sample transcript
- working TTS path
- working lip-sync path
- working final composition path

Landscape mode also requires 3/4-profile presenter source videos. Vertical
mode can route presenter visibility through A-roll and B-roll without profile
overlay panels.

## Resources

- Project layout and filenames: [references/project-layout.md](references/project-layout.md)
