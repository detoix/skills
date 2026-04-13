# Presenter Strategy

Use two presenter modes:

- `front`: full-screen presenter, looking straight at camera
- `profile`: 3/4-profile presenter used as lower-right PiP over screen or webpage footage

## Source Intake

Require:

- one silent `front` motion plate
- one silent `profile` motion plate
- one speech sample for voice cloning

Optional:

- transcript of the speech sample

## Sync Strategy

Generate visible presenter clips only for segments that need visible presenter footage.

Default mapping:

- `A_ROLL` segments use synced `front` clips
- `PIP` segments use synced `profile` clips

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
