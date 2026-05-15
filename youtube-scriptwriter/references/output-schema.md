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

Do not use layout or treatment names as segment `type` values. Presenter overlays are represented by `presenter` panels in a B-roll layout. Still motion and punch-in are treatments, not segment types.

Rules:

- `A_ROLL` can never exceed 20 seconds.
- `A_ROLL` must not include `layout`, `panels`, `source`, or `source_type`.
- `B_ROLL` must include at least one panel with `kind: "broll"` and a valid `source_type`.
- A pattern interrupt must occur every 5-15 seconds.
- Visual changes should be intentional and tied to clarity, pacing, or retention.
- Keep `narration` conversational.
- By default, the final segment must be a close-CTA unless the user explicitly disables CTA.
- For the final CTA segment, set `pattern_interrupt_type` to `close-cta`.
- Keep the final CTA segment short, usually 3-7 seconds, and do not introduce a new factual claim, offer, link, or promise that was not present in the brief.

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
- `source_type`: `webpage`, `stock`, `screen-record`, `generated-image`, `synthetic-motion`, or `manual`
- `must_include`
- `avoid`
- `orientation_preference`: `landscape`, `vertical`, or `either`

Use `generated-image` when a controlled synthetic visual is likely stronger than stock or screen capture, especially for abstract concepts, privacy-safe metaphor scenes, neutral fake UI backgrounds, or clean caption-safe graphic inserts. Do not use it to hide missing user assets when the brief depends on a real product, person, location, brand, or app.



## `assembly_notes`

Each item must contain:

- `segment_id`
- `note`
- `risk`: `none`, `fallback`, or `manual-review`

Use assembly notes for:

- where to use avatar footage
- when to include a presenter panel in a B-roll layout
- when to layer text
- where a search query may need stock footage or manual asset selection
- any fallback that the pipeline must not hide
