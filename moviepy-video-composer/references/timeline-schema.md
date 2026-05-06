# Timeline Schema

The script expects `timeline.json` to be a JSON array of ordered timeline entries. Entries must be sequential: each `start_time` must match the previous entry's `end_time`.

## Output Format

Pass the format on the command line:

- `--format landscape`: `1920x1080`
- `--format vertical`: `1080x1920`

## Supported Types

### `A-ROLL`

```json
{
  "type": "A-ROLL",
  "clip_path": "assets/avatar_front_1.mp4",
  "clip_start": 0.0,
  "loop_policy": "error",
  "start_time": 0.0,
  "end_time": 15.5
}
```

### `B-ROLL`

```json
{
  "type": "B-ROLL",
  "clip_path": "assets/broll_hackers.mp4",
  "caption_text": "STOP SCROLLING PAST THIS",
  "caption_position": "top",
  "clip_start": 0.0,
  "loop_policy": "loop",
  "start_time": 15.5,
  "end_time": 22.0
}
```

### `PIP`

```json
{
  "type": "PIP",
  "background_path": "assets/screen_record_1.mp4",
  "overlay_path": "assets/avatar_profile.mp4",
  "background_clip_start": 4.0,
  "overlay_clip_start": 0.0,
  "background_loop_policy": "loop",
  "overlay_loop_policy": "error",
  "start_time": 22.0,
  "end_time": 45.0,
  "overlay_scale": 0.3,
  "overlay_position": ["right", "bottom"]
}
```

Optional square crop for the overlay:

```json
{
  "type": "PIP",
  "background_path": "assets/screen_record_1.mp4",
  "overlay_path": "assets/avatar_profile.mp4",
  "overlay_crop_x": 520,
  "overlay_crop_y": 80,
  "overlay_crop_size": 900,
  "start_time": 22.0,
  "end_time": 45.0
}
```

### `TEXT`

```json
{
  "type": "TEXT",
  "background_path": "assets/broll_hackers.mp4",
  "text": "HASLA",
  "text_color": "#fad617",
  "font": "C:\\Windows\\Fonts\\arialbd.ttf",
  "background_clip_start": 2.0,
  "background_loop_policy": "loop",
  "start_time": 45.0,
  "end_time": 48.0
}
```

### `STACK_3`

```json
{
  "type": "STACK_3",
  "clip_path_top": "assets/top.mp4",
  "clip_path_mid": "assets/middle.mp4",
  "clip_path_bot": "assets/bottom.mp4",
  "clip_start_top": 0.0,
  "clip_start_mid": 3.0,
  "clip_start_bot": 6.0,
  "loop_policy": "loop",
  "start_time": 48.0,
  "end_time": 54.0
}
```

### `STACK_2`

```json
{
  "type": "STACK_2",
  "clip_path_top": "assets/top.mp4",
  "clip_path_bot": "assets/bottom.mp4",
  "clip_start_top": 0.0,
  "clip_start_bot": 2.0,
  "loop_policy": "loop",
  "start_time": 54.0,
  "end_time": 60.0
}
```

### `SPLIT_2`

`split_axis: "vertical"` means left/right panels. `split_axis: "horizontal"` means top/bottom panels.

```json
{
  "type": "SPLIT_2",
  "clip_path_a": "assets/presenter.mp4",
  "clip_path_b": "assets/demo.mp4",
  "split_axis": "vertical",
  "clip_start_a": 0.0,
  "clip_start_b": 4.0,
  "loop_policy": "error",
  "start_time": 60.0,
  "end_time": 66.0
}
```

### `GRID_4`

```json
{
  "type": "GRID_4",
  "clip_path_1": "assets/example_1.mp4",
  "clip_path_2": "assets/example_2.mp4",
  "clip_path_3": "assets/example_3.mp4",
  "clip_path_4": "assets/example_4.mp4",
  "loop_policy": "loop",
  "start_time": 66.0,
  "end_time": 72.0
}
```

### `STILL_MOTION`

```json
{
  "type": "STILL_MOTION",
  "clip_path": "broll/generated/S03_concept.png",
  "motion_type": "push-in",
  "start_time": 72.0,
  "end_time": 76.0
}
```

## Notes

- Paths may be absolute or relative to the project directory.
- Any segment type may include `caption_text` for static labels or test-only overlays. Do not use it for production spoken captions in modern reels; use `reel-captions` after base render.
- `caption_position` accepts `top`, `center`, or `bottom`; use it only for static labels and verify it does not collide with the bottom presenter bubble or platform UI.
- `caption_y` optionally overrides `caption_position` with an exact top pixel coordinate after visual inspection.
- Keep `caption_text` short, high-contrast, and readable at phone size. Treat captions as production graphics, not transcripts dumped on screen.
- `clip_start` is optional and defaults to `0.0`. It is the shared fallback offset for entries that do not provide more specific offsets.
- `background_clip_start` and `overlay_clip_start` are optional PIP/TEXT offsets. They override `clip_start` for their layer.
- `clip_start_top`, `clip_start_mid`, and `clip_start_bot` are optional `STACK_2`/`STACK_3` offsets. They override `clip_start` for each stacked clip.
- `clip_start_a` and `clip_start_b` are optional `SPLIT_2` offsets.
- `clip_start_1`, `clip_start_2`, `clip_start_3`, and `clip_start_4` are optional `GRID_4` offsets.
- `split_axis` accepts `vertical` for left/right panels or `horizontal` for top/bottom panels.
- `motion_type` for `STILL_MOTION` accepts `push-in`, `pull-back`, `pan-left`, `pan-right`, `pan-up`, `pan-down`, `diagonal-drift`, or `swipe-in`.
- `loop_policy`, `background_loop_policy`, and `overlay_loop_policy` accept `loop` or `error`.
- Use `loop_policy: "error"` for visible presenter clips unless the loop is deliberate.
- Use `loop` for B-roll only when repeated footage is acceptable.
- `overlay_scale` is optional for `PIP`; defaults are format-specific.
- `overlay_position` is optional for `PIP`; defaults are `["right", "bottom"]` in landscape and `["center", "bottom"]` in vertical.
- `PIP` overlays render as circular overlays by default. The composer square-crops the overlay before masking; use optional crop fields when the automatic center crop does not keep the subject centered.
- `TEXT` is intended for short keyword overlays, not long paragraphs.
- `STACK_2` is designed for vertical before/after, problem/solution, claim/evidence, or this/that layouts.
- `STACK_3` is designed for vertical assembly when three landscape clips should remain uncropped.
- `SPLIT_2` is designed for presenter/demo, proof/context, before/after, this/that, myth/fact, or mistake/fix sections.
- `GRID_4` is designed for fast comparison/collage/evidence-board sections.
- `STILL_MOTION` is designed for subtle bounded motion on local or generated stills; for repeated use, pre-render the still motion with `scripts/render_still_motion.py` and reference the MP4 as normal B-roll.
- The script validates file existence before rendering.
