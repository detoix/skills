---
name: reel-captions
description: Generate and hard-burn modern word-by-word captions for reels, shorts, and vertical videos using an approved transcript, WhisperX forced alignment, ASS subtitle styling, and FFmpeg burn-in. Use when Codex needs karaoke-style captions, active-word highlights, word-level timing, captions from script.json or transcript text, or captioned final reel exports.
---

# Reel Captions

Use this skill to add modern short-form captions to a rendered reel. The default workflow preserves the approved transcript and uses alignment only for timing.

For YouTube autopipeline production projects, `scripts\generate_reel_captions.py` enforces the parent Creative Approval Gate before generating or burning captions.

## Workflow

1. Confirm inputs:
   - rendered video, usually `<project-dir>\final_output.mp4`
   - final narration audio, usually `<project-dir>\final_audio.wav`
   - approved transcript source: `script.json` `tts_chunks` or a plain transcript file
2. Generate word timings and ASS captions:
   ```powershell
   & "<caption-python>" C:\Users\kdeptula\skills\reel-captions\scripts\generate_reel_captions.py `
     --project-dir <project-dir> `
     --audio <project-dir>\final_audio.wav `
     --video <project-dir>\final_output.mp4 `
     --script <project-dir>\script.json `
     --output <project-dir>\final_output_captioned.mp4 `
     --language pl
   ```
3. Verify generated files:
   - `captions/words.json`
   - `captions/captions.ass`
   - `final_output_captioned.mp4`
   - `manifests/captions-manifest.json`
4. Run visual QA on the captioned video, not only the uncaptioned base render.

## Runtime

Production reels require a Python environment with `whisperx`, `torch`, and FFmpeg access. If WhisperX is missing, install it into the selected caption runtime before production use. Do not ship production captions with synthetic or evenly distributed word timings. The script has `--words-json` only for deterministic tests, smoke checks, or a separately produced human/forced-aligned timing file that the user explicitly approved for production.

Check the selected runtime before production alignment:

```powershell
& "<caption-python>" C:\Users\kdeptula\skills\reel-captions\scripts\check_caption_runtime.py
```

If WhisperX is missing, install it explicitly into the selected runtime. If installation fails, stop and report the captioning blocker instead of falling back to synthetic timings:

```powershell
& C:\Users\kdeptula\skills\reel-captions\scripts\install_caption_runtime.ps1 `
  -Python "$env:USERPROFILE\Downloads\speech-gen\venv\Scripts\python.exe"
```

WhisperX default behavior:

- Use supplied transcript text from `script.json` or `--transcript`.
- Use `manifests/tts-manifest.json` chunk durations only when their total duration closely matches the final audio; otherwise fall back to script segment timings.
- Use `whisperx.align(...)` for word timing.
- Use language `pl` by default for Polish reels.
- Let WhisperX choose its default Polish alignment model unless `--align-model` is provided.

## Caption Style

Default style is phrase plus active-word highlight:

- show 2-4 words at a time
- keep inactive words white
- highlight the currently spoken word in yellow
- use bold text with black outline and shadow
- position captions in the vertical safe zone above bottom platform UI and PiP bubbles
- bridge short gaps between adjacent word timings so the caption block stays visible between words; active-word changes should follow WhisperX timing, but captions must not blink during normal speech

Do not use `caption_text` timeline fields for spoken captions when this skill is available. Keep `TEXT` timeline entries only for intentional graphic beats, title cards, labels, and comparison graphics.

## Failure Rules

Fail instead of silently producing weak captions when:

- the transcript source is missing
- WhisperX is unavailable for a production reel and the user has not explicitly approved a precomputed word-timing file
- `--words-json` was produced by a uniform timing heuristic rather than real alignment, except for deterministic tests or explicit user-approved degraded output
- more than the configured fraction of words lacks timestamps
- FFmpeg cannot burn ASS subtitles
- captioned output duration or resolution differs materially from the base video
- QA frames show clipped, unreadable, colliding, or visibly flickering captions

## Resources

- Script: [scripts/generate_reel_captions.py](scripts/generate_reel_captions.py)
- Runtime check: [scripts/check_caption_runtime.py](scripts/check_caption_runtime.py)
- Runtime install helper: [scripts/install_caption_runtime.ps1](scripts/install_caption_runtime.ps1)
- Format notes: [references/caption-format.md](references/caption-format.md)
