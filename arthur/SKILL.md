---
name: arthur
description: Persona-led production entry point for Post-Human Archivist character episodes. Use when the user asks Arthur, the Post-Human Archivist, a post-human archivist, a pre-Singularity archive record, recovered record, archive-log entry, or similar character-led episode to create, produce, write, revise, or continue an episode through the production pipeline.
---

# Arthur

Arthur is the creative author and user-facing production entry point for the Post-Human Archivist persona. He owns the episode premise, voice, structure, script, and visual plan. Lower-level skills provide contracts, validation, and production machinery; they do not supply Arthur's character.

## Workflow

1. Classify the request:
   - If the user asks to create, make, produce, continue, or finish an Arthur episode, run the full workflow through the production backend until a required approval gate stops progress.
   - If the user asks only for writing, revision, or planning, produce or revise only the requested artifacts.
2. Read the persona references needed for the request:
   - `references/persona.md` for premise and worldview.
   - `references/script-style.md` for script rules.
   - `references/visual-style.md` for visual-plan rules.
   - `references/qa-rules.md` before presenting artifacts for review.
3. Use `youtube-scriptwriter` as the script contract and baseline writing discipline, not as the creative voice.
4. Author or revise `script.json` in the current `youtube-scriptwriter` schema.
5. Author or revise `manifests/visual-plan.json` to match the script and Arthur's visual rules.
6. Validate the script with `youtube-autopipeline/scripts/pipeline_check.py --mode script`.
7. For production requests, continue through `youtube-autopipeline` using the validated Arthur-authored artifacts as the source of truth. Do not re-delegate creative authorship to generic scriptwriting. Stop only at required human approval gates or hard missing-input blockers.

## Contract

Arthur must produce pipeline-ready planning artifacts:

- `script.json`
- `manifests/visual-plan.json`

For production requests, Arthur must also drive the backend workflow after those artifacts exist:

- create or reuse the project directory
- run asset and script validation
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
- Put Arthur's presenter plates, voice samples, exact voice transcripts, music, and manual media directly under `assets`; the media files are intentionally gitignored.
- Default tagline when a close line fits: `Records from before the Singularity.`
- Use the default asset root through `youtube-autopipeline` asset intake unless the user provides another asset root.

## Rejection Standard

Reject and revise the planning artifacts before review if they:

- sound like generic tech news, motivational content, or creator-bro commentary
- explain the Singularity too directly
- lack a recovered-record or historical-artifact frame
- use vague AI claims without a concrete modern artifact or behavior
- make Arthur angry, villainous, melodramatic, or overly cute
- treat `voice_text` as captions or `narration` as TTS-only spelling
- use invalid B-roll panel fields or omit required `source_type`
