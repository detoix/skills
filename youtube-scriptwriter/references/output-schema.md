# Output Schema

Return one strict JSON object. Do not use Markdown as the automation interface unless the caller explicitly asks for a human-readable rendering after the JSON.

When this output feeds `youtube-autopipeline`, validate the saved `script.json` before generating TTS or media:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
  --project-dir <project-dir> `
  --script <project-dir>\script.json `
  --format <landscape-or-vertical> `
  --mode script
```

## Top-Level Shape

```json
{
  "metadata": {},
  "segments": [],
  "tts_chunks": [],
  "broll_queries": []
}
```

## `metadata`

Required fields:

- `topic`
- `target_audience`
- `tone`
- `language`
- `format_mode`: `landscape` or `vertical`
- `target_duration_seconds`
- `estimated_duration_seconds`
- `estimated_word_count`
- `pattern_interrupt_interval_seconds`
- `max_static_aroll_seconds`

## `segments`

Each item must contain:

- `segment_id`: stable identifier such as `S01`
- `start_seconds`
- `end_seconds`
- `duration_seconds`
- `type`: `A_ROLL` or `B_ROLL`
- `layout`: required only for `B_ROLL`; one of `fullscreen`, `stack2`, `stack3`, `grid4`
- `panels`: required only for `B_ROLL`; each panel is `{ "kind": "broll", "source_type": "<source_type>" }` or `{ "kind": "presenter" }`
- `pattern_interrupt`: `true` or `false`
- `pattern_interrupt_type`: short label such as `hook`, `zoom`, `stat-overlay`, `cutaway`, `screen-demo`
- `narration`: natural, correctly written line for that segment

- `visual_direction`: concrete editing instruction
- `avatar_direction`: performance note for the avatar, or `""`
- `sfx_cue`: optional cue, or `""`
- `editor_notes`: practical assembly note

Allowed segment `type` values:

- `A_ROLL`: presenter.
- `B_ROLL`: non-presenter visual segment.

Allowed `B_ROLL` panel source_type values:

- `synthetic-motion`
- `stock`
- `webpage`
- `generated-image`
- `screen-record`
- `manual`
- `web-evidence`: user/project-supplied local cropped proof image

## `tts_chunks`

Each item must contain:

- `chunk_id`
- `segment_ids`
- `voice_text`
- `delivery_style`
- `estimated_seconds`

`segment_ids` maps each TTS chunk to its referenced `segments[].narration`.

## `broll_queries`

Each item must contain:

- `segment_id`
- `query`
- `source_type`: `webpage`, `stock`, `screen-record`, `generated-image`, `synthetic-motion`, `manual`, or `web-evidence`
- `must_include`
- `avoid`
- `orientation_preference`: `landscape`, `vertical`, or `either`

`web-evidence` entries describe a user/project-supplied local proof image and its source page.
