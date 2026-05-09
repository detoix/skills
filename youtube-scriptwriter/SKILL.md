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
4. Write for spoken delivery, not essay reading:
   - Use short spoken sentences
   - Open with a fast hook
   - Keep transitions tight
   - Avoid long setup before payoff
5. End short-form scripts with a concrete close-CTA by default unless the user explicitly disables CTA.
6. Produce one JSON object every time:
   - `metadata`
   - `segments`
   - `tts_chunks`
   - `broll_queries`
   - `graphics`
   - `assembly_notes`

## Operating Rules

- Treat retention as a hard requirement, not a nice-to-have.
- Break long explanations into clear beats.
- Mark each segment with `type: A_ROLL` or `type: B_ROLL` and a pattern interrupt flag.
- If `B_ROLL` is used, make its `layout` and `panels[]` concrete enough for production.
- Use `generated-image` in `broll_queries.source_type` when a controlled synthetic still is stronger than stock, webpage capture, or manual assets for an abstract or privacy-safe segment.
- Do not use generated-image plans to hide missing user assets when the topic depends on the user's real product, presenter, brand, location, or app.
- Make `on_screen_text` usable as `caption_text` when the timeline needs burned-in reel captions: short, punchy, and not a full transcript dump.
- Keep the spoken narration aligned with the claimed duration.
- If the requested duration is too short for the topic, compress tightly instead of relaxing the pacing constraints.
- If the topic is abstract, use concrete examples or metaphors when helpful.
- Write narration for spoken delivery, not for visual text-only reading.
- Keep narration natural in the target language, but avoid overfitting the script to a specific TTS engine.
- If a line contains literals such as digits, shorthand, passwords, or mixed-language tokens, it is acceptable to keep the authored wording when that is important for the script, as long as the line is still understandable to a human reader.
- Treat `tts_chunks[].voice_text` as the TTS-safe spoken version of the script. It may differ from `segments[].narration` when pronunciation improves.
- In `voice_text`, write numbers, units, symbols, abbreviations, and mixed technical shorthand the way they should be spoken.
- Avoid dense clusters of acronyms or product terms in a single `voice_text` sentence. Split them with punctuation or connective words so TTS has natural pauses.
- Preserve the target language's normal writing system, accents, punctuation, and diacritics in both `narration` and `voice_text`.
- By default, make the final segment a concrete `close-cta` segment unless the user explicitly disables CTA or the format makes CTA inappropriate.
- Put the CTA in the final segment's `narration`, a short version in `on_screen_text`, and a matching `graphics[]` entry with `graphic_type: "cta"`.
- Select CTAs by purpose: tutorials/checklists should ask viewers to save or use the checklist; comparisons should ask viewers to compare before deciding; diagnostics should ask viewers to check their own case; lead comments should ask for a specific keyword; education series may ask viewers to follow only when no more specific CTA fits.
- Avoid generic "subscribe" or "follow for more" CTAs when a topic-specific action is possible.
- Keep CTA segments short, usually 3-7 seconds, and do not introduce a new factual claim, offer, link, or promise that was not present in the brief.

## Anti-AI Voice Rules

Scripts must sound like a real person talking, not like AI-generated text. Consult [references/humanize-guidelines.md](references/humanize-guidelines.md) for full vocabulary tables and rewrite examples in English and Polish.

The lists below are **soft avoids**, not hard bans. A flagged word is acceptable when it is genuinely the best fit, but defaulting to these words signals the script sounds artificial.

### Vocabulary

Strongly avoid these categories in `narration` and `voice_text`:

- **Inflated verbs:** delve, leverage, utilize, harness, streamline, underscore, embark, facilitate, optimize, foster, elevate, navigate (metaphorical). Prefer: use, help, improve, simplify, highlight, start.
- **Buzzword adjectives:** pivotal, robust, innovative, seamless, cutting-edge, intricate, comprehensive, vibrant, unparalleled, groundbreaking, game-changing. Prefer: key, solid, new, smooth, latest, detailed, big.
- **Abstract nouns:** landscape (metaphorical), realm, tapestry, synergy, testament, underpinnings, paradigm, ecosystem, framework, treasure trove, journey (metaphorical). Prefer: space, area, mix, proof, basics, system, setup.
- **Academic transitions:** Furthermore, Moreover, Consequently, Notably, Importantly, Thus, Accordingly, Nonetheless, Subsequently, In conclusion. Prefer: Plus, Also, So, On top of that, That said, Still, Then, Bottom line.
- **Cliché openers:** "In today's [adj] world/landscape," "Let's dive in," "Without further ado," "In this video we will." Prefer: just start the content.

The same principles apply in Polish — see the reference doc for Polish-specific avoid lists and rewrite examples.

### Sentence Rhythm and Burstiness

- Vary sentence length deliberately. Mix short punchy lines (≤8 words) with medium (12–18) and occasional long (25+).
- Never stack 3 or more sentences of similar length in a row.
- The script should look "jagged" on the page — if every line ends in roughly the same column, the rhythm is too uniform.

### Conversational Voice

- Write as if explaining to one friend, not presenting to an auditorium.
- Use contractions: "don't" not "do not," "it's" not "it is," "you'll" not "you will."
- Use casual connectors: "But here's the thing," "So," "Plus," "Anyway," "The catch is," "Look," "Thing is."
- Allow sentence fragments when they improve spoken rhythm.
- Prefer active voice. Passive voice is permitted only when the object genuinely matters more than the actor.

### Human Color

- Include at least one rhetorical question per script.
- Use concrete, specific examples over abstract generalizations.
- Prefer opinionated phrasing ("This is overrated," "Most people get this wrong") over neutral summaries.
- Avoid triple-balanced lists — it is a pattern AI defaults to and viewers recognize as robotic.

## TTS-Safe Voice Text

Use `segments[].narration` for the editorial spoken script and `tts_chunks[].voice_text` for the exact TTS input. When a literal may be misread, keep the natural meaning but rewrite the literal in a pronunciation-safe form.

Examples for Polish TTS:

- `4K120` -> `cztery K sto dwadzieścia`
- `120Hz` -> `sto dwadzieścia herców`
- `10 ms` -> `dziesięć milisekund`
- `55"` -> `pięćdziesiąt pięć cali`
- `20%` -> `dwadzieścia procent`
- `kWh` -> `kilowatogodzin`
- `m²` -> `metrów kwadratowych`
- `OLED/QLED/Mini LED` -> `OLED, QLED albo Mini LED`

Do not phoneticize every brand or acronym blindly. Keep common acronyms as written when they are normally pronounced as letters and the TTS voice is likely to handle them; rewrite only when the literal is likely to produce awkward or incorrect speech.

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
2. Outline the hook, core beats, and close-CTA.
3. Break the video into short segments.
4. Ensure no `A_ROLL` segment exceeds 20 seconds.
5. Insert a pattern interrupt every 5-15 seconds.
6. Use visual changes only when they improve clarity, pacing, or retention.
7. Fill the production payload arrays so the output can drive TTS, B-roll fetch, text graphics, and assembly.
8. Before finalizing, check:
   - no timing gaps
   - no overlong `A_ROLL`
   - no long interrupt gaps
   - B-roll queries are concrete when present
   - on-screen text is readable and short
   - caption-style text fits phone viewing and avoids bottom UI/presenter overlay collisions
   - generated-image B-roll panels are explicitly justified in `broll_queries` or `assembly_notes`
   - narration is natural for spoken delivery in the target language
   - `tts_chunks[].voice_text` is TTS-safe: no avoidable raw symbols, digit-heavy shorthand, or hard-to-say acronym clusters
   - all numbers, measurements, percentages, screen sizes, refresh rates, and technical shorthand in `voice_text` are written as they should be spoken
   - the final segment contains a concrete CTA unless CTA was explicitly disabled
   - the final CTA appears in `narration`, `on_screen_text`, and `graphics[]`
   - the CTA is topic-specific when a topic-specific action is possible
   - the CTA does not promise anything unsupported by the brief
   - no soft-avoid AI vocabulary or academic transitions remain in `narration` or `voice_text` without clear justification
   - sentence lengths vary across the script — no 3+ consecutive sentences of similar word count
   - at least one rhetorical question exists somewhere in the script
   - contractions are used consistently; stiff "do not" / "it is" / "you will" phrasing appears only when emphasis is intentional

## Output Template

Return only valid JSON in the top-level shape from [references/output-schema.md](references/output-schema.md). Add Markdown only if the caller explicitly asks for an additional human-readable rendering.

## Resources

- Schema and field contract: [references/output-schema.md](references/output-schema.md)
- Anti-AI voice rules and rewrite examples: [references/humanize-guidelines.md](references/humanize-guidelines.md)
