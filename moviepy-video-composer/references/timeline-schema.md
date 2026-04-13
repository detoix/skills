# Timeline Schema

The script expects `timeline.json` to be a JSON array of ordered timeline entries.

## Supported Types

### `A-ROLL`

```json
{
  "type": "A-ROLL",
  "clip_path": "assets/avatar_front_1.mp4",
  "start_time": 0.0,
  "end_time": 15.5
}
```

### `B-ROLL`

```json
{
  "type": "B-ROLL",
  "clip_path": "assets/broll_hackers.mp4",
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
  "start_time": 22.0,
  "end_time": 45.0,
  "overlay_scale": 0.3,
  "overlay_position": ["right", "bottom"]
}
```

## Notes

- `start_time` and `end_time` define the target duration for the visual segment.
- Paths may be relative to the project directory.
- `overlay_scale` is optional for `PIP`; default is `0.3`.
- `overlay_position` is optional for `PIP`; default is `["right", "bottom"]`.
- The script validates file existence before rendering.
