# Iteration Log - 2026-05-05

This log records real failures and resulting source changes. Failed renders are kept in `C:\Users\kdeptula\Videos\ai-videos` only; generated media is not source material and must not be committed.

## Iteration 1 - 12s Proof Render

- Artifact: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\final_output.mp4`
- Result: mechanically valid short proof, but below required 60-90s duration.
- Failure: duration gate not satisfied; proof render could not validate long-form reel pacing.
- Source response: added/kept timeline validation and final frame extraction requirements.

## Iteration 2 - Synthetic 72s Validation Reel

- Artifact: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\01-password-hygiene\final_output.mp4`
- Result: structurally rendered 9:16 reel with QA frames, but visually unacceptable.
- Failure: synthetic colored plates and copied sample avatar clips looked like test scaffolding, not a professional reel.
- Source response: `visual_qa.py` now requires explicit human/aesthetic review before pass status; the autopipeline now states structural QA cannot mark success by itself.

## Iteration 3 - Second Synthetic 72s Validation Reel

- Artifact: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\02-ai-workflow\final_output.mp4`
- Result: structurally rendered 9:16 reel with QA frames, but repeated the same quality failure.
- Failure: asset-variety and duration checks passed while the video still looked generic and low-value.
- Source response: `z-image-turbo` planning was added as a first-class generated visual path, still images were enabled in the composer, and generated-visual rejection rules were added.

## Current Status

No full 60-90s test reel has passed professional QA. The next valid iteration must start from research-backed creative planning, user-provided or explicitly fixture-marked assets, reviewed z-image/stock/screen B-roll, cloned or approved narration, and human/aesthetic QA.
