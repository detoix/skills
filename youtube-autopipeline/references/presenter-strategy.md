# Presenter Strategy

Use two presenter modes:

- `front`: full-screen presenter, looking straight at camera
- `profile`: 3/4-profile presenter used as PiP overlay over screen or webpage footage

## Source Intake

Require:

- one silent `front` motion plate
- one speech sample for voice cloning

Optional:

- one silent `profile` motion plate (required for landscape; optional for vertical)
- transcript of the speech sample

### Landscape Requirements

- `front` plate: landscape (16:9), 1920x1080 or similar
- `profile` plate: landscape (16:9), used as lower-right PiP

### Vertical Requirements

- `front` plate: portrait (9:16) preferred, 1080x1920 or similar; landscape plates accepted but will be center-cropped to fill vertical canvas
- `profile` plate: portrait preferred; if omitted, skip PiP segments and use A-roll / B-roll alternation instead

## Sync Strategy

Generate visible presenter clips only for segments that need visible presenter footage.

### Landscape Default Mapping

- `A_ROLL` segments use synced `front` clips
- `PIP` segments use synced `profile` clips at lower-right, scale `0.3`

### Vertical Default Mapping

- `A_ROLL` segments use synced `front` clips
- `PIP` segments use synced `profile` clips at bottom-center, scale `0.34`
- If no `profile` plate is available, convert `PIP` segments to either `A_ROLL` or `B_ROLL` depending on visual context

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
- Do not generate a presenter clip for narration that will be fully covered by B-roll
- If a segment switches from full-screen presenter to PiP while narration continues, split the visible media into two synced outputs even if the spoken text is contiguous
- In `timeline.json`, set `loop_policy: "error"` for full-screen presenter clips and `overlay_loop_policy: "error"` for PIP presenter overlays.
- Use `background_clip_start` and `overlay_clip_start` in PIP entries when the background footage and presenter overlay need different source offsets.

### Vertical Practical Rules

- Portrait presenter plates fill the vertical canvas naturally. Landscape plates will be center-cropped via `cover`; ensure the presenter face is vertically centered in the source.
- For `PIP` overlay in vertical mode, the overlay sits at `("center", "bottom")` with scale `0.34` and `36px` padding. This places the small presenter circle above the bottom safe area on mobile.
- When no profile plate is available for vertical mode, prefer alternating between short `A_ROLL` (presenter face) and `B_ROLL` or `STACK_3` cutaways rather than long presenter holds.
