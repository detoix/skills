---
name: youtube-scriptwriter
description: Script contract and baseline spoken-writing discipline for YouTube automation. Use when a persona skill, production pipeline, or agent needs the required script.json schema, pacing rules, B-roll query fields, TTS-safe voice_text guidance, or baseline anti-AI narration checks. Do not use this skill to invent persona, worldview, recurring format, humor, or character voice when a persona skill is active.
---

# YouTube Scriptwriter

This skill defines the script contract and baseline writing rules for automated YouTube production. It is not the creative authority when a persona skill is active.

## Role

Use this skill for:

- `script.json` structure
- segment timing rules
- A-roll and B-roll contract
- B-roll query payloads
- `tts_chunks[]` mapping
- TTS-safe `voice_text`
- baseline anti-AI narration checks

Do not use this skill for:

- persona invention
- character worldview
- recurring story frame
- humor style
- visual taste
- episode identity

If a persona skill is active, preserve that persona's voice and constraints. Apply only the contract and baseline quality checks here.

## Required Inputs

The authoring agent or persona must know:

- topic or artifact
- format mode: `landscape` or `vertical`
- target audience
- tone or persona style
- language
- target duration

## Output

Return exactly the strict JSON object defined in `references/output-schema.md`.

Top-level keys:

- `metadata`
- `segments`
- `tts_chunks`
- `broll_queries`

Do not use Markdown as the automation interface unless the caller explicitly asks for a human-readable companion after the JSON exists.

## Baseline Rules

- Keep segment timing explicit and sequential.
- Keep `A_ROLL` segments at or below 15 seconds.
- Insert a pattern interrupt every 5-15 seconds.
- By default, end with a short close-CTA segment unless the user disables CTA; set its `pattern_interrupt_type` to `close-cta` and do not introduce a new factual claim, offer, link, or promise.
- Use only `A_ROLL` and `B_ROLL` as segment types.
- B-roll panels must define `source_type`.
- B-roll treatments are panel-level.
- Fullscreen PiP is one B-roll panel plus one presenter panel with `treatment: "overlay"`.
- Select `web-evidence` only when the user or project already supplies a local cropped proof image with `source_url` or `capture_source_url`.
- Fullscreen evidence overlay is one presenter panel with `treatment: "blur"` plus one `web-evidence` B-roll panel with `treatment: "overlay"`.
- Do not use `broll_search_query`.
- Keep `segments[].narration` natural and correctly written; captions use this text.
- Use `tts_chunks[].voice_text` only for TTS-safe spoken wording.
- Keep `tts_chunks[].segment_ids` mapped to existing segment ids.
- Keep `broll_queries[]` concrete when B-roll is present.

## Baseline Humanization

Scripts must sound like a real person talking, not AI filler. Use the full reference only when needed: `references/humanize-guidelines.md`.

Avoid defaulting to:

- inflated verbs such as delve, leverage, utilize, harness, facilitate
- buzzword adjectives such as pivotal, robust, seamless, cutting-edge
- abstract filler such as landscape, realm, tapestry, journey
- academic transitions such as Furthermore, Moreover, Consequently
- cliché openers such as "In today's world", "Let's dive in", or "In this video we will"

These are soft avoids. A persona can intentionally violate them when the character voice requires it.

## TTS-Safe Voice Text

Use `segments[].narration` for reviewed/captioned script text. Use `tts_chunks[].voice_text` for pronunciation-safe TTS input when needed.

Examples:

- `4K120` -> `four K, one twenty`
- `120Hz` -> `one hundred twenty hertz`
- `20%` -> `twenty percent`
- `10 ms` -> `ten milliseconds`

For Polish examples and language-specific guidance, read `references/humanize-guidelines.md` and `references/output-schema.md`.

## Validation

When the output feeds `youtube-autopipeline`, validate the saved script:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
  --project-dir <project-dir> `
  --script <project-dir>\script.json `
  --format <vertical-or-landscape> `
  --mode script
```

## Resources

- Schema and field contract: `references/output-schema.md`
- Anti-AI voice rules and rewrite examples: `references/humanize-guidelines.md`
