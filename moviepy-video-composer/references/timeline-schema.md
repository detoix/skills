# Timeline Schema

The composer accepts one segment model:

- `type: "A_ROLL"`
- `type: "B_ROLL"`

The composer does not accept layout or treatment names as top-level `type` values.

## A_ROLL

```json
{
  "type": "A_ROLL",
  "clip_path": "synced/front/A01.mp4",
  "clip_start": 0.0,
  "start_time": 0.0,
  "end_time": 5.0
}
```

## B_ROLL

```json
{
  "type": "B_ROLL",
  "layout": "fullscreen",
  "panels": [
    { "kind": "broll", "source": "stock", "path": "broll/B01.mp4" }
  ],
  "start_time": 5.0,
  "end_time": 10.0
}
```

Allowed `layout` values:

- `fullscreen`
- `stack2`
- `stack3`
- `grid4`

Allowed B-roll panel `source` values:

- `synthetic-motion`
- `stock`
- `webpage`
- `generated-image`
- `screen-record`
- `manual`

## Presenter Panels

Presenter overlay over fullscreen B-roll:

```json
{
  "type": "B_ROLL",
  "layout": "fullscreen",
  "panels": [
    { "kind": "broll", "source": "webpage", "path": "broll/site.mp4", "role": "background" },
    { "kind": "presenter", "path": "synced/profile/P01.mp4", "role": "overlay", "overlay_scale": 0.34 }
  ],
  "start_time": 10.0,
  "end_time": 16.0
}
```

Presenter as a stack panel:

```json
{
  "type": "B_ROLL",
  "layout": "stack2",
  "panels": [
    { "kind": "presenter", "path": "synced/front/A02.mp4" },
    { "kind": "broll", "source": "generated-image", "path": "broll/generated/S02.png", "treatment": "still_motion" }
  ],
  "start_time": 16.0,
  "end_time": 21.0
}
```

Presenter panels do not have `source` and do not count as B-roll source diversity.

## Treatments

Still motion is a B-roll panel treatment:

```json
{
  "kind": "broll",
  "source": "generated-image",
  "path": "broll/generated/S03.png",
  "treatment": "still_motion",
  "motion_type": "push-in"
}
```

Punch-in is an A-roll crop/edit treatment, not a segment type.
