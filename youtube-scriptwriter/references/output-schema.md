# Output Schema

Return exactly two top-level parts. This schema is for the agent's generated output, not for an external API wrapper.

## PART A: A/V Editing Script

Use an ordered list of segments. Each segment must contain:

- `segment_id`: Stable identifier such as `S01`
- `start_seconds`
- `end_seconds`
- `duration_seconds`
- `primary_visual`: One of `A_ROLL`, `B_ROLL`, `PUNCH_IN`, `TEXT_GRAPHIC`, `PIP`
- `pattern_interrupt`: `true` or `false`
- `pattern_interrupt_type`: Short label such as `hook`, `zoom`, `stat-overlay`, `cutaway`, `screen-demo`
- `narration`: Spoken line for that segment
- `on_screen_text`: Exact overlay copy, or `""`
- `visual_direction`: Concrete editing instruction
- `broll_search_query`: Search query or shot brief, or `""`
- `avatar_direction`: Performance note for the avatar, or `""`
- `sfx_cue`: Optional cue, or `""`
- `editor_notes`: Practical assembly note

Rules:

- `A_ROLL` can never exceed 20 seconds.
- A pattern interrupt must occur every 5-15 seconds.
- Do not allow long runs of the same visual mode without a justified change.
- Keep narration conversational and easy for TTS.

## PART B: Production Payload

Return four payload blocks:

### `tts_chunks`

Each item must contain:

- `chunk_id`
- `segment_ids`
- `voice_text`
- `delivery_style`
- `estimated_seconds`

### `broll_queries`

Each item must contain:

- `segment_id`
- `query`
- `must_include`
- `avoid`

### `graphics`

Each item must contain:

- `segment_id`
- `graphic_type`
- `copy`

### `assembly_notes`

Short operational notes for the automation pipeline, such as:

- where to use avatar footage
- when to swap to PiP
- when to layer captions or kinetic text
- where a search query may need a generated motion graphic instead of stock footage

## Metadata

Include a `metadata` object with:

- `topic`
- `target_audience`
- `tone`
- `language`
- `target_duration_seconds`
- `estimated_duration_seconds`
- `estimated_word_count`
- `pattern_interrupt_interval_seconds`
- `max_static_aroll_seconds`

## Rendering Guidance

If the caller wants Markdown, render:

1. `PART A: A/V Editing Script`
2. `PART B: Production Payload`

Keep field names stable so the Markdown can be converted back to structured data later.
