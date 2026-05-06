# Timeline Mapping

Convert the scriptwriter output into the composer schema conservatively. The schema depends on the format mode.

## Landscape Mode (16:9)

Composer: `moviepy-video-composer` (`scripts/compose_video.py --format landscape`)
Canvas: `1920x1080`

### Supported Types

- `A-ROLL`
- `B-ROLL`
- `PIP`
- `TEXT`

### A_ROLL

Map to:

```json
{
  "type": "A-ROLL",
  "clip_path": "synced/front/A01.mp4",
  "clip_start": 0.0,
  "loop_policy": "error",
  "start_time": 0.0,
  "end_time": 6.5
}
```

Add `caption_text` when the segment needs burned-in captions. Keep caption copy shorter than the narration and place it at `top` in vertical PiP layouts unless QA frames prove another placement is clean.

### B_ROLL

Map to:

```json
{
  "type": "B-ROLL",
  "clip_path": "broll/B02.webm",
  "clip_start": 0.0,
  "loop_policy": "loop",
  "start_time": 6.5,
  "end_time": 12.0
}
```

Reviewed generated stills from `z-image-turbo` can also be used as `clip_path` values:

```json
{
  "type": "B-ROLL",
  "clip_path": "broll/generated/S03_concept-still.png",
  "start_time": 5.0,
  "end_time": 10.0
}
```

Do not set `clip_start` on still images.

Animated board clips from `animated-broll-boards` should be custom art-directed `.webm` motion scenes with a passing `board-qa.json`. Use them as normal video `clip_path` values:

```json
{
  "type": "B-ROLL",
  "clip_path": "broll/boards/S03_process/S03_process.webm",
  "clip_start": 0.0,
  "loop_policy": "loop",
  "start_time": 5.0,
  "end_time": 11.0
}
```

### PIP

Map to:

```json
{
  "type": "PIP",
  "background_path": "broll/B03.webm",
  "overlay_path": "synced/profile/P03.mp4",
  "background_clip_start": 0.0,
  "overlay_clip_start": 0.0,
  "background_loop_policy": "loop",
  "overlay_loop_policy": "error",
  "start_time": 12.0,
  "end_time": 18.0,
  "overlay_scale": 0.3,
  "overlay_position": ["right", "bottom"]
}
```

### Unsupported Scriptwriter Modes (Landscape)

#### PUNCH_IN

The current composer does not support a real zoom instruction.

Fallback order:

1. convert to a shorter `A-ROLL` beat with a different synced presenter clip
2. convert to `B-ROLL` or `PIP` if the segment still works visually
3. flag the segment in assembly notes as requiring a future zoom-capable renderer

#### TEXT_GRAPHIC

The composer supports simple `TEXT` overlays. Prefer `TEXT` when the graphic is a short keyword or phrase.

Fallback order:

1. convert to `TEXT` when the overlay can be represented as short text on a background clip
2. convert to `B-ROLL` with assembly notes when text is secondary
3. flag the segment for manual graphics if the layout is complex or essential

---

## Vertical Mode (9:16)

Composer: `moviepy-video-composer` (`scripts/compose_video.py --format vertical`)
Canvas: `1080x1920`

### Supported Types

- `A-ROLL`
- `B-ROLL`
- `PIP`
- `TEXT`
- `STACK_3`

### A_ROLL

Map to:

```json
{
  "type": "A-ROLL",
  "clip_path": "synced/front/A01.mp4",
  "clip_start": 0.0,
  "loop_policy": "error",
  "start_time": 0.0,
  "end_time": 5.0
}
```

Use `clip_start` to pick different fragments of long source videos. Ensure `(end_time - start_time)` is less than or equal to the source video duration to prevent awkward looping.

### B_ROLL

Map to:

```json
{
  "type": "B-ROLL",
  "clip_path": "broll/B02.webm",
  "clip_start": 0.0,
  "loop_policy": "loop",
  "start_time": 5.0,
  "end_time": 10.0
}
```

### PIP

Map to (without crop):

```json
{
  "type": "PIP",
  "background_path": "broll/B03.webm",
  "overlay_path": "synced/profile/P03.mp4",
  "background_clip_start": 0.0,
  "overlay_clip_start": 0.0,
  "background_loop_policy": "loop",
  "overlay_loop_policy": "error",
  "start_time": 10.0,
  "end_time": 18.0,
  "overlay_scale": 0.34,
  "overlay_position": ["center", "bottom"]
}
```

Map to (with 1:1 crop when overlay source is not square):

```json
{
  "type": "PIP",
  "background_path": "broll/B03.webm",
  "overlay_path": "synced/profile/P03.mp4",
  "background_clip_start": 0.0,
  "overlay_clip_start": 0.0,
  "background_loop_policy": "loop",
  "overlay_loop_policy": "error",
  "overlay_crop_x": 520,
  "overlay_crop_y": 80,
  "overlay_crop_size": 900,
  "start_time": 10.0,
  "end_time": 18.0,
  "overlay_scale": 0.34,
  "overlay_position": ["center", "bottom"]
}
```

Defaults for vertical PIP:
- `overlay_scale`: `0.34` (height as fraction of 1920)
- `overlay_position`: `["center", "bottom"]`
- overlay padding: `36px`
- corner radius: `36px`
- `overlay_crop_x`, `overlay_crop_y`: optional; when both provided, the overlay is cropped to a 1:1 square at that origin before resizing
- `overlay_crop_size`: optional; defaults to `min(source_width, source_height)`

The orchestrator should extract a frame from the overlay source, inspect it, and decide the crop origin to center the presenter's face in the square. See the "PiP Overlay Crop Decision" section in the main SKILL.md for the full workflow.

If no profile plate is available, convert PIP segments to `A-ROLL` or `B-ROLL` instead.

### TEXT

Map to:

```json
{
  "type": "TEXT",
  "background_path": "broll/B01.webm",
  "text": "KEYWORD",
  "text_color": "#fad617",
  "background_clip_start": 0.0,
  "background_loop_policy": "loop",
  "start_time": 18.0,
  "end_time": 21.0
}
```

Fields:
- `text`: string to display (use short keywords or phrases, not long sentences)
- `text_color`: optional HEX color, default `"#fad617"` (yellow)
- `font`: optional path to a `.ttf` file, default `arialbd.ttf`
- `clip_start`: optional offset into the background video; omit for still images

Use `TEXT` segments for:
- keyword hits that reinforce the narration
- section titles or topic markers
- call-to-action phrases at the end

Use `caption_text` on ordinary `A-ROLL`, `B-ROLL`, `PIP`, and `STACK_3` entries for subtitles or hook captions. Use `TEXT` entries for full-screen kinetic keyword beats.

Generate candidate stills with:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\z_image_plan.py `
  --project-dir <project-dir> `
  --script <project-dir>\script.json
```

Only accepted images from the generated plan should enter `timeline.json`.

### STACK_3

Map to:

```json
{
  "type": "STACK_3",
  "clip_path_top": "broll/B01.webm",
  "clip_path_mid": "broll/B02.webm",
  "clip_path_bot": "broll/B03.webm",
  "clip_start_top": 0.0,
  "clip_start_mid": 2.0,
  "clip_start_bot": 4.0,
  "loop_policy": "loop",
  "start_time": 21.0,
  "end_time": 26.0
}
```

Three landscape (16:9) clips scaled to `1080px` wide and stacked vertically without cropping. Use when center-crop would lose important visual content from the edges.

Fields:
- `clip_path_top`: top video
- `clip_path_mid`: middle video
- `clip_path_bot`: bottom video
- `clip_start`: fallback offset applied to all three clips when per-clip offsets are omitted
- `clip_start_top`, `clip_start_mid`, `clip_start_bot`: optional per-clip offsets

### Unsupported Scriptwriter Modes (Vertical)

#### PUNCH_IN

Fallback order:

1. convert to a shorter `A-ROLL` beat with a different `clip_start` offset
2. convert to `STACK_3` or `TEXT` if the segment benefits from visual variety
3. flag the segment in assembly notes

#### TEXT_GRAPHIC

The vertical composer supports `TEXT` natively. Prefer mapping directly:

1. map to `TEXT` with the graphic text content
2. if the text is too complex for a single `TEXT` overlay, convert to `B-ROLL` with assembly notes
3. flag the segment for manual graphics if a rich layout is essential

---

## Assembly Notes

Keep a sidecar note list for every fallback. Never silently pretend a missing visual treatment was rendered when it was not.

## General Timing Rules

- All segments must be sequential with no gaps: `start_time` of entry N must equal `end_time` of entry N-1.
- Duration is `end_time - start_time`.
- For vertical mode, prefer shorter segments (3-8 seconds) to maintain mobile viewer attention.
- For vertical mode, use `clip_start` to diversify visuals from long source clips instead of always starting from zero.
