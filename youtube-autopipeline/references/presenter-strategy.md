# Presenter Strategy

Use two presenter modes:

- `front`: full-screen presenter, looking straight at camera
- `profile`: 3/4-profile presenter used as a `presenter` panel overlay over screen or webpage footage

## Source Intake

Require:

- one silent `front` motion plate
- one speech sample for voice cloning

Optional:

- one silent `profile` motion plate (required for landscape; optional for vertical)
- transcript of the speech sample

### Landscape Requirements

- `front` plate: landscape (16:9), 1920x1080 or similar
- `profile` plate: landscape (16:9), used as lower-right presenter overlay

### Vertical Requirements

- `front` plate: portrait (9:16) preferred, 1080x1920 or similar; landscape plates accepted but will be center-cropped to fill vertical canvas
- `profile` plate: portrait preferred; if omitted, skip presenter-overlay panels and use A-roll / B-roll alternation instead

## Sync Strategy

Generate visible presenter clips only for segments that need visible presenter footage.

### Landscape Default Mapping

- `A_ROLL` segments use synced `front` clips
- `B_ROLL` fullscreen layouts with presenter overlay panels use synced `profile` clips at lower-right, scale `0.3`

### Vertical Default Mapping

- `A_ROLL` segments use synced `front` clips
- `B_ROLL` fullscreen layouts with presenter overlay panels use synced `profile` clips with explicit per-panel `overlay_position`, scale `0.34`
- If no `profile` plate is available, omit presenter overlay panels

For a long continuous narration run, split visible presenter generation into smaller clips that match the timeline rather than one oversized synced render.

Audio source rule:

- reuse existing TTS chunk audio as the source for presenter sync
- if a visible segment is only a slice of a chunk, derive a cut audio file from that chunk rather than regenerating fresh TTS
- keep TTS generation and presenter sync as separate stages; presenter prep should clip or map existing narration, not re-synthesize it
- only re-run TTS for a visible segment when the original chunk itself needs correction

## Practical Rules

- Keep clip names aligned to segment ids where possible, e.g. `A01.mp4`, `P03.mp4`
- Trim or loop the silent motion plate before lip-sync if the toolchain requires it
- Trim the narration audio from the existing chunk files before lip-sync when only a portion of a chunk is visible on screen
- Generate lip-synced presenter media only for timeline segments or panels where the presenter is actually visible. If a `B_ROLL` segment has no presenter panel, do not generate unused presenter media for that covered duration.
- If a segment switches from full-screen presenter to presenter-over-B-roll while narration continues, split the visible media into two synced outputs even if the spoken text is contiguous
- In `timeline.json`, set `loop_policy: "error"` for full-screen presenter clips and presenter panels.
- Use panel-level `clip_start` when B-roll and presenter panels need different source offsets.

### Vertical Practical Rules

- Portrait presenter plates fill the vertical canvas naturally. Landscape plates will be center-cropped via `cover`; ensure the presenter face is vertically centered in the source.
- For presenter overlay in vertical mode, set `overlay_position` explicitly on the presenter panel. Choose the position for the actual frame, captions, and B-roll composition; no vertical overlay position is globally preferred.
- When no profile plate is available for vertical mode, use `A_ROLL` and `B_ROLL` segments without presenter-overlay panels.
