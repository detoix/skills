# Timeline Mapping

`timeline.json` uses the same public segment model as `script.json`.

Allowed top-level `type` values:

- `A_ROLL`
- `B_ROLL`

Do not use layout or treatment names as timeline `type` values.

## A_ROLL

Presenter-only segment:

```json
{
  "type": "A_ROLL",
  "clip_path": "synced/front/A01.mp4",
  "clip_start": 0.0,
  "loop_policy": "error",
  "start_time": 0.0,
  "end_time": 6.5
}
```

`A_ROLL` must not include `layout`, `panels`, or `source`.

## B_ROLL

B-roll segment with required layout and panels:

```json
{
  "type": "B_ROLL",
  "layout": "fullscreen",
  "panels": [
    { "kind": "broll", "source": "stock", "path": "broll/B02.mp4" }
  ],
  "start_time": 6.5,
  "end_time": 12.0
}
```

Allowed layouts:

- `fullscreen`
- `stack2`
- `stack3`
- `grid4`

Allowed B-roll panel sources:

- `synthetic-motion`
- `stock`
- `webpage`
- `generated-image`
- `screen-record`
- `manual`

## Presenter With B-Roll

Presenter over fullscreen B-roll:

```json
{
  "type": "B_ROLL",
  "layout": "fullscreen",
  "panels": [
    { "kind": "broll", "source": "webpage", "path": "broll/S03_demo.mp4", "role": "background" },
    { "kind": "presenter", "path": "synced/profile/P03.mp4", "role": "overlay", "overlay_scale": 0.34 }
  ],
  "start_time": 12.0,
  "end_time": 18.0
}
```

Presenter as one stacked panel:

```json
{
  "type": "B_ROLL",
  "layout": "stack2",
  "panels": [
    { "kind": "presenter", "path": "synced/front/A02.mp4", "loop_policy": "error" },
    { "kind": "broll", "source": "generated-image", "path": "broll/generated/S04.png", "treatment": "still_motion" }
  ],
  "start_time": 18.0,
  "end_time": 23.0
}
```

Presenter panels never count toward source diversity.

## Panel Treatments

Still motion is a panel treatment, not a segment type:

```json
{
  "kind": "broll",
  "source": "generated-image",
  "path": "broll/generated/S04.png",
  "treatment": "still_motion",
  "motion_type": "push-in"
}
```

Punch-in is an A-roll crop/edit treatment, not a segment type. Keep it as an edit note or treatment field on `A_ROLL`.

## Timing Rules

- All timeline entries must be sequential with no gaps.
- Duration is `end_time - start_time`.
- Use `clip_start` on an entry as a fallback source offset.
- Use panel-level `clip_start` when different panels need different source offsets.
- Use `loop_policy: "error"` for all visible presenter media.
