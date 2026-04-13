# Timeline Mapping

Convert the scriptwriter output into the composer schema conservatively.

## Supported Composer Types

- `A-ROLL`
- `B-ROLL`
- `PIP`

## Default Mapping

### A_ROLL

Map to:

```json
{
  "type": "A-ROLL",
  "clip_path": "synced/front/A01.mp4",
  "start_time": 0.0,
  "end_time": 6.5
}
```

### B_ROLL

Map to:

```json
{
  "type": "B-ROLL",
  "clip_path": "broll/B02.webm",
  "start_time": 6.5,
  "end_time": 12.0
}
```

### PIP

Map to:

```json
{
  "type": "PIP",
  "background_path": "broll/B03.webm",
  "overlay_path": "synced/profile/P03.mp4",
  "start_time": 12.0,
  "end_time": 18.0,
  "overlay_scale": 0.3,
  "overlay_position": ["right", "bottom"]
}
```

## Unsupported Scriptwriter Modes

### PUNCH_IN

The current composer does not support a real zoom instruction.

Fallback order:

1. convert to a shorter `A-ROLL` beat with a different synced presenter clip
2. convert to `B-ROLL` or `PIP` if the segment still works visually
3. flag the segment in assembly notes as requiring a future zoom-capable renderer

### TEXT_GRAPHIC

The current composer does not place text overlays by itself.

Fallback order:

1. convert to `B-ROLL` with a note for external text overlay
2. convert to `PIP` if the graphic accompanies an on-screen demo
3. flag the segment for manual graphics if the text is essential

## Assembly Notes

Keep a sidecar note list for every fallback. Never silently pretend a missing visual treatment was rendered when it was not.
