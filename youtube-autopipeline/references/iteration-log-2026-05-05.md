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

## Iteration 4 - First z-image Fixture Batch

- Artifact: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\broll\generated`
- Result: z-image generated files successfully from the autopipeline plan, but the first batch was rejected.
- Failure: prompts leaked on-screen copy into text-to-image generation, producing fake presenters and garbled text.
- Source response: `scripts/z_image_plan.py` now avoids using on-screen copy as image prompt material and restricts generated-image planning to explicit generated-image queries or visual fallbacks that need it.

## Iteration 5 - 60s Fixture Reel, Low Variety Warning

- Artifact: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\final_output.mp4`
- Result: 60s vertical render passed duration, resolution, TTS-prefix, generated-image provenance, and human/aesthetic checks.
- Failure: QA reported low visual variety because the first passing cut used only fullscreen B-roll plus captions.
- Source response: the timeline was revised to include circular PiP fixture inserts so PiP crop/shape is covered and the reel uses multiple visual treatments.

## Iteration 6 - Passing 60s Fixture Reel

- Artifact: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\final_output.mp4`
- QA report: `C:\Users\kdeptula\Videos\ai-videos\autopipeline-validation-20260505\04-meeting-reuse-pass\manifests\visual-qa.md`
- Result: 60s 1080x1920 fixture reel passed strict QA with no automated findings and explicit human/aesthetic review notes.
- Evidence: the final timeline uses 10 B-roll segments, 2 PiP segments, 12 caption checks, 2 accepted generated-image refs, 2 PiP checks, 13 distinct media references, and target-only cloned TTS.
- Remaining limitation: this is a fixture validation reel, not a production user-asset reel. Production still requires user-provided assets.

## Current Status

One full 60-90s fixture reel has passed structural and human/aesthetic QA. Two previous full 72s fixture reels remain documented as failed aesthetic iterations. Production use still requires user-provided assets; `C:\Users\kdeptula\Videos\avatar` remains a fixture set only.
