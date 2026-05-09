---
name: moviepy-video-composer
description: Assemble final landscape or vertical videos from a structured JSON timeline, local media assets, and a master audio track using MoviePy. Use when asked to stitch avatar clips, B-roll, screen recordings, text overlays, stacked clips, or presenter-overlay layouts into a final video, render an MP4 from timeline.json, or automate local video composition from assets plus voiceover.
---

# MoviePy Video Composer

Use this skill to build a final edited video from local assets and a structured edit list. Prefer the bundled Python script instead of rewriting composition logic from scratch.

For YouTube autopipeline production projects, `scripts\compose_video.py` enforces the parent Creative Approval Gate before final composition. `scripts\render_still_motion.py` also enforces the gate when rendering stills into motion clips.

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
4. Verify that `final_output.mp4` and `manifests/audio-mix-manifest.json` exist.
5. Extract representative frames from the rendered video and inspect them for actual visual quality before reporting success.
6. Rerender when frames show obvious visual defects such as overlap, clipped text, unreadable typography, bad presenter overlay shape/crop, blank frames, or unfinished-looking UI.
7. Report the output path and any warnings back to the user.

## Expected Inputs

- `timeline.json`: ordered edit list
- `final_audio.mp3` or `final_audio.wav`: continuous master voiceover
- optional soundtrack file: user-provided local music bed for the final mix, normally ingested as `source-assets/soundtrack.<ext>`
- local clips referenced by JSON:
  - `A_ROLL`
  - `B_ROLL`
- `B_ROLL` entries must define `layout` and `panels[]`; do not use layout or treatment names as top-level `type`
- accepted generated stills or project images (`.png`, `.jpg`, `.jpeg`, `.webp`) may be used anywhere a visual media path is accepted; stills are held for the segment duration
- optional `caption_text` fields on any segment for burned-in short-form captions

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
- Treat still images as duration-flexible visual media. Do not set `clip_start` on still images.
- Use `clip_start` when a segment should begin from a non-zero point in the source clip.
- Use panel-level `clip_start` when panels need different source offsets.
- Use `layout: "stack2"`, `layout: "stack3"`, or `layout: "grid4"` for multi-panel B-roll.
- In `layout: "stack2"` only, portrait front-facing presenter panels whose path contains a `front` directory segment are automatically cropped higher than center before `cover` scaling. For a 9:16 front plate in a half-height panel, the crop keeps the upper half starting at 1/8 of source height. This does not apply to PiP/presenter overlays, A-roll fullscreen, B-roll panels, profile plates, `stack3`, or `grid4`.
- Use panel `treatment: "still_motion"` for subtle bounded camera movement on a local/generated still. The composer applies the motion inside fullscreen, stack, and grid panel bounds. Use [scripts/render_still_motion.py](scripts/render_still_motion.py) only when a manually pre-rendered motion clip is explicitly needed.
- For `A_ROLL`, optionally use `treatment: "camera_motion"` with `motion_type` for subtle virtual camera movement on presenter video:
  ```json
  {
    "type": "A_ROLL",
    "clip_path": "synced/front/A01.mp4",
    "treatment": "camera_motion",
    "motion_type": "push-in"
  }
  ```
  Use this selectively, not on every A-roll. Prefer `push-in`, `pull-back`, `pan-left`, `pan-right`, or `diagonal-drift`; avoid `pan-up`, `pan-down`, and `swipe-in` unless manually justified after visual inspection.
- Use `loop_policy: "error"` for visible presenter clips to prevent repeated mouth/body motion.
- Use panel-level `loop_policy` to control looping separately for each panel.
- Normalize fullscreen assets into the selected output canvas before assembly.
- Use `cover` as the default fullscreen framing rule for timeline-driven video layers.
- Keep presenter overlays on explicit overlay sizing and placement; do not treat overlays as fullscreen assets.
- Apply circular masking to presenter overlays by default. The composer square-crops the overlay before masking so portrait, landscape, and square source plates render as circles.
- Use optional presenter overlay crop fields when the automatic center square crop does not keep the presenter's face centered.
- Do not letterbox or pillarbox fullscreen clips unless the user explicitly asks for that treatment.
- Do not use `caption_text` for production spoken captions in modern reels. Use the separate `reel-captions` skill after base render for word-level aligned captions.
- Keep `caption_text` only for non-spoken labels, test renders, or intentionally static graphic annotations. Use `caption_position` and `caption_y` only after visual inspection proves the label does not collide with presenter overlays or platform safe zones.
- Treat the narration track as the primary audio source.
- Validate narration and soundtrack with `ffprobe`; both must contain an audio stream with positive duration.
- If soundtrack music is present, use `ffmpeg` sidechain ducking so the music drops under narration and recovers in pauses.
- For short-form videos, keep the music clearly audible as part of the pacing and energy, while still keeping narration intelligible. The default mix should sound like an active Shorts/Reels music bed, not a barely audible safety track.
- Use conservative music only when the user asks for a quiet/corporate/explainer mix or when the narration is hard to understand.
- Normalize narration and apply final peak safety during the audio mix stage.
- Write `manifests/audio-mix-manifest.json` with narration probe data, music probe data, ducking settings, fallback status, and output path.
- Attach the final mixed audio after the visual timeline is assembled.
- Render standard output with `fps=30`, `codec=libx264`, `audio_codec=aac`.

## Visual QA

The composer workflow requires visual inspection of the rendered MP4, not just schema validation. Extract frames from the final output at regular intervals and around presenter-overlay/static-label segments. Prefer `youtube-autopipeline\scripts\visual_qa.py` for extraction and manifest output. Reject the render if the final composed image has overlapping text, clipped elements, incorrect presenter overlay shape, awkward subject crops, blank frames, or obviously unfinished mock visuals. For spoken reel captions, run visual QA again after the `reel-captions` burn-in stage.

## Resources

- Composer script: [scripts/compose_video.py](scripts/compose_video.py)
- Still motion renderer: [scripts/render_still_motion.py](scripts/render_still_motion.py)
- Timeline contract: [references/timeline-schema.md](references/timeline-schema.md)
