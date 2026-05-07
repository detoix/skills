# Changelog - 2026-05-05

## Changed

- Clarified that production runs must use user-provided project assets and must not rely on any local example folder unless the user explicitly provides it for that run.
- Added `scripts/asset_inventory.py` to classify local presenter, audio, still, transcript, B-roll, and previous-output assets into a project manifest.
- Extended `scripts/asset_inventory.py` with explicit disposable test-input labeling and grouped asset categories.
- Extended `scripts/pipeline_check.py` with asset manifest validation that blocks test input in production unless `--allow-test-input` is explicitly passed.
- Added `scripts/visual_qa.py` to extract representative final-render frames, generate a contact sheet, run basic blank/contrast checks, and write `manifests/visual-qa.json`.
- Extended `scripts/visual_qa.py` with duration/resolution checks, timeline category checks, caption/PiP/TTS-prefix reporting, Markdown reports, and mandatory agent visual review gating.
- Extended `scripts/visual_qa.py` to audit generated-image timeline references against reviewed z-image plan entries.
- Added `scripts/z_image_plan.py` to create z-image prompt/command manifests from script segments.
- Extended `scripts/pipeline_check.py` with z-image plan validation and optional required review status.
- Tightened `scripts/z_image_plan.py` so generated-image prompts do not ingest on-screen copy as render text and so routine B-roll/TEXT segments are not planned for z-image unless the script explicitly requests generated imagery or needs a visual fallback.
- Extended `moviepy-video-composer` to accept reviewed still images as visual media, enabling z-image outputs in timelines.
- Extended `moviepy-video-composer` so any timeline segment can carry `caption_text`; captions support `caption_position` and inspected `caption_y` placement.
- Made composer `TEXT` beats more reliable by reducing dynamic font size and adding a subdued backing band for readability over busy footage.
- Extended timeline validation to catch invalid caption fields and overlong caption text.
- Documented short-form reel practices, including hook timing, vertical-safe composition, caption use, visual variation, safe zones, and frame-level QA.
- Added `references/professional-qa-rubric.md` to make agent visual review explicit before final pass status.
- Tightened dependent skill instructions for TTS, LatentSync, CodeFormer, Pexels, and generated-image B-roll manifests.
- Documented failed validation iterations and added a hard distinction between structural QA and professional/aesthetic QA.

## Test Evidence

- Asset manifest: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\manifests\assets-manifest.json`
- Synthetic-motion B-roll preview: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\broll\B01_motion_preview.png`
- Failed QA render retained for comparison: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\final_output_v2.mp4`
- Short structural proof render, not production-accepted: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\final_output.mp4`
- Regression QA manifest showing the proof is too short and lacks aesthetic review: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\manifests\visual-qa-regression.json`
- Regression QA contact sheet: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\qa\contact-sheet-final_output.jpg`

## Additional Proof

- TTS clone chunk: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\tts\clean\T01.wav`
- LatentSync output: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\synced\front\A_TTS01_retry.mp4`
- TTS/lip-sync proof render, not production-accepted: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\final_output_tts_lipsync.mp4`
- TTS/lip-sync QA manifest from earlier structural proof: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\manifests\visual-qa-tts-lipsync.json`
- TTS/lip-sync QA contact sheet: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\qa\contact-sheet-final_output_tts_lipsync.jpg`
- Still-image composer smoke test: `C:\Users\kdeptula\Videos\ai-videos\still-smoke-20260505\final_output.mp4`
- Failed 72s strict QA reports retained for comparison:
  - `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\01-password-hygiene\manifests\visual-qa-strict.md`
  - `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\02-ai-workflow\manifests\visual-qa-strict.md`
- Passing 60s test-input reel:
  - Video: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\final_output.mp4`
  - QA report: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\manifests\visual-qa.md`
  - z-image plan: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\manifests\z-image-plan.json`
  - TTS manifest: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\manifests\tts-manifest.json`
