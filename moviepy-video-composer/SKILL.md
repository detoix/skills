---
name: moviepy-video-composer
description: Assemble final videos from a structured JSON timeline, local media assets, and a master audio track using MoviePy. Use when asked to stitch avatar clips, B-roll, screen recordings, or PiP layouts into a final YouTube video, render an MP4 from timeline.json, or automate local video composition from assets plus voiceover.
---

# MoviePy Video Composer

Use this skill to build a final edited video from local assets and a structured edit list. Prefer the bundled Python script instead of rewriting composition logic from scratch.

## Workflow

1. Confirm the project contains:
   - `timeline.json`
   - a master voice track such as `final_audio.mp3` or `final_audio.wav`
   - optional soundtrack music such as `source-assets/soundtrack.mp3`
   - referenced local media assets
2. Run [scripts/compose_video.py](scripts/compose_video.py).
3. Verify that `final_output.mp4` exists.
4. Report the output path and any warnings back to the user.

## Expected Inputs

- `timeline.json`: ordered edit list
- `final_audio.mp3` or `final_audio.wav`: continuous master voiceover
- optional soundtrack file: user-provided music bed for the final mix
- local clips referenced by JSON:
  - `A-ROLL`
  - `B-ROLL`
  - `PIP`

## Use The Script

```powershell
python scripts\compose_video.py `
  --project-dir C:\project `
  --timeline C:\project\timeline.json `
  --audio C:\project\final_audio.mp3 `
  --music C:\project\source-assets\soundtrack.mp3 `
  --output C:\project\final_output.mp4
```

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
- For `PIP`, keep the background full-frame and place the overlay with padding near the requested corner.
- Treat the narration track as the primary audio source.
- If soundtrack music is present, use `ffmpeg` sidechain ducking so the music drops under narration and recovers in pauses.
- Normalize narration and apply final peak safety during the audio mix stage.
- Prevent clipping in the final mix with a safety gain pass.
- Attach the final mixed audio after the visual timeline is assembled.
- Render standard YouTube-friendly output: `fps=30`, `codec=libx264`, `audio_codec=aac`.

## Resources

- Composer script: [scripts/compose_video.py](scripts/compose_video.py)
- Timeline contract: [references/timeline-schema.md](references/timeline-schema.md)
