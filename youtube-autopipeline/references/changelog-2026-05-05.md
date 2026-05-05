# Changelog - 2026-05-05

## Changed

- Added `scripts/asset_inventory.py` to classify local presenter, audio, still, transcript, B-roll, and previous-output assets into a project manifest.
- Added `scripts/visual_qa.py` to extract representative final-render frames, generate a contact sheet, run basic blank/contrast checks, and write `manifests/visual-qa.json`.
- Extended `moviepy-video-composer` so any timeline segment can carry `caption_text`; captions support `caption_position` and inspected `caption_y` placement.
- Made composer `TEXT` beats more reliable by reducing dynamic font size and adding a subdued backing band for readability over busy footage.
- Extended timeline validation to catch invalid caption fields and overlong caption text.
- Documented short-form reel practices, including hook timing, vertical-safe composition, caption use, visual variation, safe zones, and frame-level QA.
- Tightened dependent skill instructions for TTS, LatentSync, CodeFormer, Pexels, and generated-image B-roll manifests.

## Test Evidence

- Asset manifest: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\manifests\assets-manifest.json`
- Local HTML B-roll preview: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\broll\B01_motion_preview.png`
- Failed QA render retained for comparison: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\final_output_v2.mp4`
- Accepted render: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\final_output.mp4`
- Accepted QA manifest: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\manifests\visual-qa.json`
- Accepted QA contact sheet: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\qa\contact-sheet-final_output.jpg`

## Additional Proof

- TTS clone chunk: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\tts\clean\T01.wav`
- LatentSync output: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\synced\front\A_TTS01_retry.mp4`
- TTS/lip-sync proof render: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\final_output_tts_lipsync.mp4`
- TTS/lip-sync QA manifest: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\manifests\visual-qa-tts-lipsync.json`
- TTS/lip-sync QA contact sheet: `C:\Users\kdeptula\Videos\ai-videos\reel-proof-20260505\qa\contact-sheet-final_output_tts_lipsync.jpg`
