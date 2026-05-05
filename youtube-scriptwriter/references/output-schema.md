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
  "broll_queries": [],
  "graphics": [],
  "assembly_notes": []
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
- `primary_visual`
- `pattern_interrupt`: `true` or `false`
- `pattern_interrupt_type`: short label such as `hook`, `zoom`, `stat-overlay`, `cutaway`, `screen-demo`
- `narration`: spoken line for that segment
- `on_screen_text`: exact overlay copy, or `""`
- `visual_direction`: concrete editing instruction
- `broll_search_query`: search query or shot brief, or `""`
- `avatar_direction`: performance note for the avatar, or `""`
- `sfx_cue`: optional cue, or `""`
- `editor_notes`: practical assembly note

Allowed `primary_visual` values:

- landscape: `A_ROLL`, `B_ROLL`, `PUNCH_IN`, `TEXT_GRAPHIC`, `PIP`
- vertical: `A_ROLL`, `B_ROLL`, `PUNCH_IN`, `TEXT`, `TEXT_GRAPHIC`, `PIP`, `STACK_3`

Use `TEXT` directly for simple vertical keyword overlays. Use `TEXT_GRAPHIC` only when the intended graphic is richer than the composer-native `TEXT` segment.

Rules:

- `A_ROLL` can never exceed 20 seconds.
- A pattern interrupt must occur every 5-15 seconds.
- Do not allow long runs of the same visual mode without a justified change.
- Keep narration conversational and easy for TTS.
- Keep `on_screen_text` short enough to map directly to `caption_text` or a `TEXT` segment in vertical reels.

## `tts_chunks`

Each item must contain:

- `chunk_id`
- `segment_ids`
- `voice_text`
- `delivery_style`
- `estimated_seconds`

## `broll_queries`

Each item must contain:

- `segment_id`
- `query`
- `source_type`: `webpage`, `stock`, `screen-record`, or `manual`
- `must_include`
- `avoid`
- `orientation_preference`: `landscape`, `vertical`, or `either`

## `graphics`

Each item must contain:

- `segment_id`
- `graphic_type`
- `copy`
- `composer_target`: `TEXT`, `B_ROLL`, `PIP`, or `manual`

## `assembly_notes`

Each item must contain:

- `segment_id`
- `note`
- `risk`: `none`, `fallback`, or `manual-review`

Use assembly notes for:

- where to use avatar footage
- when to swap to PiP
- when to layer text
- where a search query may need stock footage or manual asset selection
- any fallback that the pipeline must not hide
