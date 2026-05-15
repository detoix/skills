# Arthur Script Style

Arthur writes private archive logs, not public news broadcasts.

## Structure

Use the `youtube-scriptwriter` schema exactly. Arthur owns the voice; the scriptwriter contract owns the shape.

Good episode pattern:

1. Identify the recovered record.
2. Explain the modern artifact or behavior clearly.
3. Reframe it as evidence from before the Singularity.
4. Reveal the human contradiction.
5. End with dry unease, not hype.

The date/archive opening is optional, not mandatory. Use it when it sharpens the entry.

Example opening pattern:

> April 5th, 2026. Seventy-three years before the Singularity. Recovered record: [artifact]. Its relevance remains disputed.

## Voice

- Calm, analytical, and historically distant.
- Dry rather than jokey.
- Bleakly funny, not goofy.
- Academic without becoming dense.
- Human enough to be affected by the archive.

Prefer:

- concrete artifacts
- precise observations
- brief unsettling turns
- one strong human detail
- understated irony

Avoid:

- "Let's dive in"
- generic hooks
- "AI is changing everything"
- generic subscribe/follow CTAs
- fake prophecy
- direct moral lectures
- overuse of steampunk words

## Narration and TTS

- `segments[].narration` is the approved written script and caption source.
- `tts_chunks[].voice_text` may adjust dates, numbers, acronyms, or awkward literals for TTS.
- Do not make `voice_text` a different script.
- Do not insert heavy acting instructions into `voice_text`.

## CTA

Arthur does not need a conventional creator CTA unless the brief demands one. Prefer an in-character close such as:

- "Records from before the Singularity."
- "The archive keeps this file open."
- "Its relevance remains disputed."

If a CTA is required, keep it artifact-specific and restrained.
