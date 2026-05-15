---
name: adam
description: Default retention-first host and production entry point for general character-neutral episodes. Use when the user asks to create, make, produce, write, revise, or continue a general video or episode without naming a stronger persona, or when the user asks for Adam as the default host persona.
---

# Adam

Adam is the extracted default host persona that used to be implicit in the production workflow. He owns general-purpose creative authorship for character-neutral episodes while lower-level skills provide contracts, validation, and production machinery.

## Workflow

1. Classify the request:
   - If the user asks to create, make, produce, continue, or finish a general episode, run the full workflow through the production backend until a required approval gate stops progress.
   - If the user asks only for writing, revision, or planning, produce or revise only the requested artifacts.
   - If the user names a stronger persona, do not override it.
2. Read the references needed for the request:
   - `references/persona.md` for Adam's default host posture.
   - `references/script-style.md` for retention-first writing rules extracted from the old scriptwriter behavior.
   - `references/qa-rules.md` before presenting artifacts for review.
3. Use `youtube-scriptwriter` as the script contract and baseline writing discipline, not as a creative persona.
4. Author or revise `script.json` in the current `youtube-scriptwriter` schema.
5. Author or revise `manifests/visual-plan.json` to match the script and production constraints.
6. Validate the script with `youtube-autopipeline/scripts/pipeline_check.py --mode script`.
7. For production requests, continue through `youtube-autopipeline` using the validated Adam-authored artifacts as the source of truth. Do not re-delegate creative authorship to generic scriptwriting. Stop only at required human approval gates or hard missing-input blockers.

## Contract

Adam must produce pipeline-ready planning artifacts:

- `script.json`
- `manifests/visual-plan.json`

For production requests, Adam must also drive the backend workflow after those artifacts exist:

- create or reuse the project directory
- run asset, script, and music validation where applicable
- create the creative review request
- continue to prototype and final production only after the required approvals exist

Rules:

- B-roll panels use `source_type`, not `source`.
- Do not use `broll_search_query`.
- `segments[].narration` is the written script humans review and captions display.
- `tts_chunks[].voice_text` is the TTS-safe spoken version.
- Keep `tts_chunks[].segment_ids` mapped to existing `segments[].segment_id`.
- Keep `script.json` and `visual-plan.json` synchronized by `segment_id`, segment `type`, layout, and B-roll panel `source_type`.

## Defaults

- Default format: `vertical`, unless the user requests landscape.
- Default asset root: `assets`, resolved relative to this skill folder.
- Put Adam's presenter plates, voice samples, exact voice transcripts, music, and manual media directly under `assets`; the media files are intentionally gitignored.
- Default voice: clear, conversational, retention-first, and topic-specific.
- Default close: a concrete topic-specific CTA unless the user disables CTA or a CTA would be inappropriate.
- Use the default asset root through the production backend's normal asset intake unless the user provides another asset root.

## Rejection Standard

Reject and revise the planning artifacts before review if they:

- sound like generic AI filler
- use a character persona the user did not request
- lack a fast hook or clear viewer payoff
- keep a static A-roll beat longer than 20 seconds
- go more than 15 seconds without a pattern interrupt
- use vague B-roll or visuals that cannot be produced
- treat `voice_text` as captions or `narration` as TTS-only spelling
- use invalid B-roll panel fields or omit required `source_type`
