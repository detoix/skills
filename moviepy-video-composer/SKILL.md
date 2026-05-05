---
name: moviepy-video-composer
description: Assemble final landscape or vertical videos from a structured JSON timeline, local media assets, and a master audio track using MoviePy. Use when asked to stitch avatar clips, B-roll, screen recordings, text overlays, stacked clips, or PiP layouts into a final video, render an MP4 from timeline.json, or automate local video composition from assets plus voiceover.
---

# MoviePy Video Composer

Use this skill to build a final edited video from local assets and a structured edit list. Prefer the bundled Python script instead of rewriting composition logic from scratch.

## Output Formats

- `--format landscape`: `1920x1080` / `16:9`
- `--format vertical`: `1080x1920` / `9:16`

Both formats use [scripts/compose_video.py](scripts/compose_video.py).

## Workflow

1. Confirm the project contains:
   - `timeline.json`
   - a master voice track such as `final_audio.mp3` or `final_audio.wav`
   - optional soundtrack music such as `source-assets/soundtrack.mp3`
   - referenced local media assets
2. Validate the timeline contract before rendering when the project comes from `youtube-autopipeline`:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir C:\project `
     --timeline C:\project\timeline.json `
     --audio C:\project\final_audio.wav `
     --mode timeline
   ```
3. Run [scripts/compose_video.py](scripts/compose_video.py) with the correct `--format`.
4. Verify that `final_output.mp4` exists and has the expected resolution.
5. Extract representative frames from the rendered video and inspect them for actual visual quality before reporting success.
6. Rerender when frames show obvious visual defects such as overlap, clipped text, unreadable typography, bad PiP shape/crop, blank frames, or unfinished-looking UI.
7. Report the output path and any warnings back to the user.

## Expected Inputs

- `timeline.json`: ordered edit list
- `final_audio.mp3` or `final_audio.wav`: continuous master voiceover
- optional soundtrack file: user-provided music bed for the final mix
- local clips referenced by JSON:
  - `A-ROLL`
  - `B-ROLL`
  - `PIP`
  - `TEXT`
  - `STACK_3`

## Use The Script

```powershell
python C:\Users\kdeptula\skills\moviepy-video-composer\scripts\compose_video.py `
  --project-dir C:\project `
  --timeline C:\project\timeline.json `
  --audio C:\project\final_audio.mp3 `
  --music C:\project\source-assets\soundtrack.mp3 `
  --output C:\project\final_output.mp4 `
  --format vertical
```

Use `--music NONE` to skip soundtrack mixing.

If paths are omitted, the script defaults to the project directory and common soundtrack locations:

- `timeline.json`
- `final_audio.mp3` or `final_audio.wav`
- `source-assets/soundtrack.*` when present
- `final_output.mp4`

## Operating Rules

- Use the script directly unless the user explicitly wants code changes instead of execution.
- Keep timeline order intact; do not reorder entries.
- Match each segment to the exact target duration defined by `end_time - start_time`.
- Loop clips when they are too short; trim them when they are too long.
- Use `clip_start` when a segment should begin from a non-zero point in the source clip.
- Use `background_clip_start` and `overlay_clip_start` for `PIP` when the background and presenter overlay need different source offsets.
- Use `clip_start_top`, `clip_start_mid`, and `clip_start_bot` for `STACK_3` when stacked clips need different source offsets.
- Use `loop_policy: "error"` for visible presenter clips to prevent repeated mouth/body motion.
- Use `background_loop_policy` and `overlay_loop_policy` to control looping separately in PIP entries.
- Normalize fullscreen assets into the selected output canvas before assembly.
- Use `cover` as the default fullscreen framing rule for timeline-driven video layers.
- Keep `PIP` overlays on explicit overlay sizing and placement; do not treat overlays as fullscreen assets.
- Apply circular masking to `PIP` overlays by default. The composer square-crops the overlay before masking so portrait, landscape, and square source plates render as circles.
- Use optional PiP crop fields when the automatic center square crop does not keep the presenter's face centered.
- Do not letterbox or pillarbox fullscreen clips unless the user explicitly asks for that treatment.
- Treat the narration track as the primary audio source.
- If soundtrack music is present, use `ffmpeg` sidechain ducking so the music drops under narration and recovers in pauses.
- Keep the music bed conservative by default so narration stays clearly dominant.
- Normalize narration and apply final peak safety during the audio mix stage.
- Attach the final mixed audio after the visual timeline is assembled.
- Render standard output with `fps=30`, `codec=libx264`, `audio_codec=aac`.

## Visual QA

The composer workflow requires visual inspection of the rendered MP4, not just schema validation. Extract frames from the final output at regular intervals and around PIP/TEXT segments. Reject the render if the final composed image has overlapping text, clipped elements, unreadable captions, incorrect PiP shape, awkward subject crops, blank frames, or obviously unfinished mock visuals.

## Resources

- Composer script: [scripts/compose_video.py](scripts/compose_video.py)
- Timeline contract: [references/timeline-schema.md](references/timeline-schema.md)
