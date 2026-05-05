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

## Notes

- Paths may be absolute or relative to the project directory.
- `clip_start` is optional and defaults to `0.0`. It is the shared fallback offset for entries that do not provide more specific offsets.
- `background_clip_start` and `overlay_clip_start` are optional PIP/TEXT offsets. They override `clip_start` for their layer.
- `clip_start_top`, `clip_start_mid`, and `clip_start_bot` are optional `STACK_3` offsets. They override `clip_start` for each stacked clip.
- `loop_policy`, `background_loop_policy`, and `overlay_loop_policy` accept `loop` or `error`.
- Use `loop_policy: "error"` for visible presenter clips unless the loop is deliberate.
- Use `loop` for B-roll only when repeated footage is acceptable.
- `overlay_scale` is optional for `PIP`; defaults are format-specific.
- `overlay_position` is optional for `PIP`; defaults are `["right", "bottom"]` in landscape and `["center", "bottom"]` in vertical.
- `PIP` overlays render as circular overlays by default. The composer square-crops the overlay before masking; use optional crop fields when the automatic center crop does not keep the subject centered.
- `TEXT` is intended for short keyword overlays, not long paragraphs.
- `STACK_3` is designed for vertical assembly when three landscape clips should remain uncropped.
- The script validates file existence before rendering.
