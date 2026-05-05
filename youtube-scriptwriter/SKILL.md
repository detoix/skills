---
name: youtube-scriptwriter
description: Generate retention-optimized YouTube scripts only. Use when the user explicitly asks for a script, rundown, narration, or A-roll/B-roll edit script. Do not use this skill for end-to-end video creation, new video production, or full YouTube pipeline requests; use `youtube-autopipeline` for those.
---

# YouTube Scriptwriter

Generate scripts as production-ready assets, not as plain prose. Always optimize for retention, visual motion, and downstream automation.

## Workflow

1. Collect the required inputs:
   - Topic
   - Format mode: landscape or vertical
   - Target audience
   - Tone
   - Language
   - Target duration
2. Return the strict JSON object defined in [references/output-schema.md](references/output-schema.md).
3. Enforce pacing rules before finalizing:
   - No static `A_ROLL` shot longer than 20 seconds
   - Insert a pattern interrupt every 5-15 seconds
   - Alternate frequently across the visual modes supported by the selected format
4. Write for spoken delivery, not essay reading:
   - Use short spoken sentences
   - Open with a fast hook
   - Keep transitions tight
   - Avoid long setup before payoff
5. Produce one JSON object every time:
   - `metadata`
   - `segments`
   - `tts_chunks`
   - `broll_queries`
   - `graphics`
   - `assembly_notes`

## Operating Rules

- Treat retention as a hard requirement, not a nice-to-have.
- Break long explanations into multiple visual beats.
- Mark each segment with an explicit visual mode and a pattern interrupt flag.
- Make `B_ROLL` and `PIP` instructions concrete enough for asset fetching or screen-record capture.
- Make `TEXT_GRAPHIC` copy short enough to be readable on screen.
- Make `on_screen_text` usable as `caption_text` when the timeline needs burned-in reel captions: short, punchy, and not a full transcript dump.
- Keep the spoken narration aligned with the claimed duration.
- If the requested duration is too short for the topic, compress aggressively instead of relaxing the pacing constraints.
- If the topic is abstract, convert examples into visuals, metaphors, screenshots, or text overlays rather than leaving long avatar monologues.
- Write narration for spoken delivery, not for visual text-only reading.
- Keep narration natural in the target language, but avoid overfitting the script to a specific TTS engine.
- If a line contains literals such as digits, shorthand, passwords, or mixed-language tokens, it is acceptable to keep the authored wording when that is important for the script, as long as the line is still understandable to a human reader.

## Direct Agent Use

This skill is instruction-first. Do not rely on external scripts or external API wrappers. Use the skill directly inside the agent turn and produce the script in the required structure.

Always follow this contract:

- return exactly the JSON structure described in [references/output-schema.md](references/output-schema.md)
- keep segment timing explicit
- never output a single uninterrupted block of talking-head narration
- reject your own draft mentally if it violates the A-roll or interrupt rules
- ask for or infer only these inputs:
  - Topic
  - Format mode
  - Target audience
  - Tone
  - Language
  - Target duration

## Generation Procedure

1. Restate the five inputs internally and convert target duration into approximate seconds.
2. Outline the hook, core beats, and close.
3. Break the video into short segments.
4. Ensure no `A_ROLL` segment exceeds 20 seconds.
5. Insert a pattern interrupt every 5-15 seconds.
6. Alternate visual treatment aggressively enough to avoid static talking-head runs.
7. Fill the production payload arrays so the output can drive TTS, B-roll fetch, text graphics, and assembly.
8. Before finalizing, check:
   - no timing gaps
   - no overlong `A_ROLL`
   - no long interrupt gaps
   - B-roll queries are concrete
   - on-screen text is readable and short
   - caption-style text fits phone viewing and avoids bottom UI/PiP collisions
   - narration is natural for spoken delivery in the target language

## Output Template

Return only valid JSON in the top-level shape from [references/output-schema.md](references/output-schema.md). Add Markdown only if the caller explicitly asks for an additional human-readable rendering.

## Resources

- Schema and field contract: [references/output-schema.md](references/output-schema.md)
