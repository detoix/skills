# Dependency Audit - 2026-05-05

Scope: `youtube-autopipeline`, `youtube-scriptwriter`, `tts`, `latentsync`, `codeformer-postprocess`, `moviepy-video-composer`, `playwright-broll-recorder`, `pexels-stock-downloader`, `z-image-turbo`, and discovered local helpers.

## Findings

- `youtube-autopipeline`: already contains vertical mode rules, asset intake, TTS prefix handling, PiP crop guidance, visual strategy, timeline mapping, and final visual QA requirements. Gap found: executable QA did not measure enough reel-specific gates and the research note was under-sourced.
- `youtube-scriptwriter`: current instructions require strict JSON, segment timing, pattern interrupts, short spoken lines, visual-mode alternation, and phone-readable caption text. No contradictory instruction found.
- `tts`: current instructions prefer VoxCPM clone with `prompt-audio`, `prompt-text`, and `reference-audio`, require target-only outputs, and record trim mode in `tts-manifest.json`. No contradictory instruction found.
- `latentsync`: current instructions require output existence, non-empty file, duration checks, and stage logging before use. No contradictory instruction found.
- `codeformer-postprocess`: current instructions require duration/resolution comparison and visual inspection before replacing synced clips. No contradictory instruction found.
- `moviepy-video-composer`: current script supports `A-ROLL`, `B-ROLL`, `PIP`, `TEXT`, `STACK_3`, vertical `1080x1920`, circular PiP masks, caption overlays, loop policies, audio normalization, and sidechain ducking. Gap found: no separate machine-readable final QA report existed before the `visual_qa.py` update.
- `playwright-broll-recorder`: current instructions require preview screenshots, page-status validation, aspect-ratio-aware capture, and rejection of broken/blank/cookie-blocked captures. No contradictory instruction found.
- `pexels-stock-downloader`: current instructions require API-key confirmation, result manifest, preview-frame inspection, and weak-match rejection. No contradictory instruction found.
- `z-image-turbo`: current instructions include reel B-roll placement, vertical-safe prompts, clean caption negative space, and avoidance of fake credentials/logos. Gap found: autopipeline did not have a planning helper or first-class manifest contract for generated images.

## Source Changes From Audit

- `asset_inventory.py` now emits grouped categories for usable presenter plates, voice samples, transcripts, music, stills, overlays, previous outputs, and rejected assets.
- `asset_inventory.py` can mark an asset root as disposable test input so test data is not confused with production user assets.
- `pipeline_check.py` can validate asset manifests and blocks test input in production unless `--allow-test-input` is explicitly passed.
- `visual_qa.py` now measures duration, expected resolution, timeline visual categories, distinct media references, caption lengths/positions, PiP entries, frame blankness/contrast, and TTS prompt-prefix status, then writes both JSON and Markdown QA reports.
- `visual_qa.py` now refuses final pass status unless agent visual review is explicitly recorded.
- `z_image_plan.py` now creates a `z-image-turbo` prompt/command manifest from script segments and defines generated visual acceptance criteria.
- `moviepy-video-composer` now accepts still image media paths, allowing reviewed z-image outputs to be used directly in visual timelines.

## Remaining Production Caveat

Two early validation renders used local Windows SAPI narration and synthetic motion plates. Those renders are failed quality iterations, not production proof. They validated some render and QA mechanics, but they do not satisfy the professional-reel goal.
