---
name: youtube-autopipeline
description: >-
  End-to-end YouTube video orchestration for local automation pipelines. Use
  when the user asks to create a new YouTube video, make a video, produce a
  full video, or build a video pipeline from scratch. This skill should be
  preferred over `youtube-scriptwriter` whenever the request implies the whole
  workflow: planning, script, TTS, lip-sync, B-roll, timeline, and final
  assembly.
---

# YouTube Autopipeline

This is an orchestration skill. When it triggers, use the existing video-production skills in sequence instead of manually recreating their responsibilities.

Use these skills as the default sub-workflow:

- `youtube-scriptwriter` for the structured script
- `tts` for chunked voice generation and cloning
- `codeformer-postprocess` for optional presenter face restoration after lip-sync
- `playwright-broll-recorder` for webpage and screen-record B-roll
- `pexels-stock-downloader` for non-web stock B-roll
- `moviepy-video-composer` for final assembly

Only do work manually when a required sub-skill is missing or clearly cannot satisfy the current step.

Build a YouTube video as a project, not as a loose set of clips. Keep the whole job in one working directory with deterministic file names.

## Workflow

1. Gather or infer the required inputs.
2. Create a project directory and normalize the asset set.
3. Call `youtube-scriptwriter` and use its structured output as the planning source of truth.
4. Call `tts` to generate chunked cloned speech from the scriptwriter payload.
5. Use the lip-sync path to build synced presenter clips from the straight-to-camera and 3/4-profile silent motion plates.
6. When presenter clips look soft, compressed, or artifacted after lip-sync, call `codeformer-postprocess` on the synced presenter outputs before timeline assembly.
7. Call `playwright-broll-recorder` for webpage B-roll and call `pexels-stock-downloader` when non-web stock footage is needed.
8. Build `timeline.json` and call `moviepy-video-composer` for final assembly, including optional background soundtrack mixing.
9. Report any blockers immediately if a required runtime tool or asset is missing.

## Interview Rules

If the user provides only a topic, infer the rest conservatively and confirm only if a missing value would change production materially.

If the user does not provide a topic, interview for these fields:

- topic
- target audience
- tone
- language
- target duration
- CTA or end goal

Interview for production assets whenever they are missing:

- straight-to-camera presenter video, around 20 seconds, looking at camera
- 3/4-profile presenter video, around 20 seconds, suitable for lower-right PiP
- speech sample for voice cloning
- exact transcription of the speech sample for voice cloning
- optional soundtrack or music bed for the final mix
- optional brand assets such as logo, fonts, colors, lower-thirds

Treat the presenter generically. Do not assume gender in prompts, labels, filenames, or on-screen copy.

## Project Contract

Create one project directory per video. Use the layout in [references/project-layout.md](references/project-layout.md).

Keep all generated artifacts inside the project directory:

- script output
- TTS chunks
- synced presenter clips
- B-roll clips
- soundtrack asset if the user provided one
- timeline
- final render

If the user gives absolute paths to source assets, copy or reference them into the project contract consistently before continuing.

## Script Generation

Call `youtube-scriptwriter` first. Its output is the planning source of truth.

Require the scriptwriter output to contain:

- segment timing
- visual mode per segment
- pattern interrupts
- narration
- B-roll queries
- production payload blocks

Do not write a fresh freeform script if the scriptwriter skill is available. Use its segment timing and payloads as the basis for downstream steps.

## TTS Rules

Call `tts` and use its local VoxCPM path. Generate audio in chunks from the scriptwriter `tts_chunks` payload, not as a single monolithic file.

Operating rules:

- clone from the provided speech sample
- use the `VoxCPM` clone path with `prompt-audio + prompt-text + reference-audio`
- treat the exact speech-sample transcription as required input for the default cloning path
- preserve the scriptwriter chunk boundaries
- save each chunk deterministically, e.g. `tts/T01.wav`, `tts/T02.wav`
- concatenate chunk audio into a continuous master track only after chunk generation succeeds
- keep a manifest that maps `chunk_id` to segment ids and output files

Do not ask the user to pick a generic voice style such as male or female when a cloned presenter voice is expected.

If the speech sample or its exact transcription is missing, stop and ask for both explicitly before proceeding with TTS.

Do not silently fall back to plain TTS or simpler reference-only cloning. Only use a fallback path if the user explicitly approves that downgrade.

### Per-Chunk Normalization Decision

The orchestrator, not the scriptwriter, decides whether a TTS chunk should be synthesized raw or with `--normalize`.

For each `tts_chunk`, inspect the text before synthesis and choose the first pass:

- use raw clone first when the chunk is ordinary spoken language
- use `--normalize` on the first pass when the chunk contains likely TTS-hostile literals such as:
  - raw digits or number-heavy examples
  - dates, times, currencies, percentages, or measurements
  - abbreviations or shorthand
  - password-style tokens such as `123456`, `ImieRok`, `Haslo123!`
  - mixed-language phrasing that may benefit from text normalization

Decision rule:

- if the chunk reads like normal prose, run the bare `voxcpm.cli clone` command first
- if the chunk contains literal tokens that are likely to be spoken badly, run the same command with `--normalize`

Escalation rule:

- if the raw pass sounds wrong, retry with `--normalize`
- if the normalized pass still sounds wrong, only then consider manual text rewriting or ask the user

When reproducing a known-good clone command, keep all other flags at default unless the user explicitly asks for experimentation.

### Soft Context Cues

The orchestrator may add a very small parenthetical control prefix to the chunk text before synthesis, but only as a delicate prosody nudge, not as voice design.

Use this only when chunk boundaries or discourse transitions justify it. The orchestrator should decide this from:

- the current `tts_chunk`
- the previous chunk
- the next chunk
- the scriptwriter `delivery_style`

Allowed use cases:

- start of a new thought
- continuation of an explanation
- slight contrast turn
- slight warning emphasis
- gentle wrap-up
- slightly firmer CTA close

Do not use it for strong character acting, explicit persona changes, or heavy emotional steering.

Default rule:

- no control prefix for most chunks
- add a cue only when it helps the chunk start, end, or transition more naturally

Strength rule:

- cues must be very short
- prefer discourse and boundary cues over mood cues
- one short cue is better than a list of adjectives
- if the result drifts from the cloned speaker identity, remove the cue

Examples of acceptable soft cues:

- `(clear start)`
- `(steady continuation)`
- `(slight contrast)`
- `(slight warning emphasis)`
- `(gentle wrap-up)`
- `(slightly firmer close)`

## Presenter Clip Rules

There are two presenter source videos:

- straight-to-camera plate for full-screen A-roll
- 3/4-profile plate for lower-right PiP while screen or webpage footage is visible

Treat both source videos as silent motion plates to be lip-synced against generated narration. Do not assume their original mouth motion matches the final script.

Generate presenter outputs as reusable synced chunks or grouped scene clips. Use the conventions in [references/presenter-strategy.md](references/presenter-strategy.md).

Important timing rule:

- presenter speech may continue while the presenter is off-screen

That means lip-synced presenter media is only needed for segments where the presenter is visibly on screen. Do not waste time generating visible talking-head footage for fully covered B-roll segments.

Important audio reuse rule:

- do not regenerate TTS just to make presenter-only sync clips
- treat the generated TTS chunk files as the audio source of truth
- when a visible presenter segment uses only part of a TTS chunk, cut a subclip from the existing chunk audio and use that for lip-sync
- only regenerate TTS for a segment if the original chunk audio is unusable and the user explicitly wants a rerender

### Presenter Restoration Rule

After lip-sync and before final assembly, evaluate the synced presenter clips for visible softness, compression artifacts, or face-detail loss.

Default rule:

- if `codeformer-postprocess` is available, restore all synced presenter clips that will appear on screen
- use restored clips as the default timeline inputs for `A_ROLL` and `PIP` overlays

Default settings:

- use `fidelity 0.6` as the balanced local starting point
- raise to `0.7` when identity drift or over-restoration becomes noticeable
- drop to `0.5` only when the source is visibly soft enough to justify a slightly stronger pass
- lower to `0.3` only when restoration strength is clearly too weak and the source is visibly degraded

Scope rule:

- restore the synced presenter outputs, not the original silent motion plates
- only restore presenter clips that actually appear in the edit
- do not waste time restoring fully covered non-visible segments

Escalation rule:

- if restoration introduces visible identity drift, waxiness, or instability, keep the original synced clip for that segment
- report the segment-level exception rather than silently swapping aesthetics mid-video without noting it

Parallelism rule:

- this restoration step may be run in parallel batches when the local GPU can sustain it
- known-good local setting: up to `3` concurrent `codeformer-postprocess` runs at `fidelity 0.6`
- prefer parallel batches for the visible presenter clips before timeline assembly

## B-Roll Rules

Call `playwright-broll-recorder` for webpage and screen-record footage.

If the script calls for non-webpage footage, call `pexels-stock-downloader` for stock acquisition. If it is not available in the current session, report the gap and continue with webpage B-roll where possible.

Prefer concrete B-roll tasks:

- webpage URL
- target section or selector
- duration
- scrolling vs static
- obstructive UI to click or hide

Do not substitute vague B-roll. If a query cannot be satisfied from the available sources, flag the segment for manual asset selection.

## Timeline Assembly

Translate the scriptwriter output into `timeline.json` for `moviepy-video-composer`, then call `moviepy-video-composer`.

If the user supplied a soundtrack, keep it as a project asset and pass it to the composer as optional background music. Do not try to normalize or mix it in the orchestrator. Audio normalization, sidechain ducking, and final mix safety belong to the composer step.

Use these mappings by default:

- `A_ROLL` -> full-screen synced straight-to-camera clip
- `B_ROLL` -> full-screen B-roll clip
- `PIP` -> full-screen B-roll or screen capture background plus synced 3/4-profile overlay in the lower right
- `TEXT_GRAPHIC` and `PUNCH_IN` -> convert into the nearest supported representation or flag for fallback handling

Current composer support is limited to `A-ROLL`, `B-ROLL`, and `PIP`. Because of that:

- map `PUNCH_IN` to a shorter A-roll cut, an alternate synced A-roll variant, or a flagged fallback
- map `TEXT_GRAPHIC` to B-roll with assembly notes unless a separate graphics step exists

Use [references/timeline-mapping.md](references/timeline-mapping.md) for the exact conversion rules.

## Shot Variety Rules

Avoid long static presenter runs.

When a direct zoom effect is not available in the current composer, create variety using:

- shorter A-roll segments
- more frequent cutaways to B-roll
- PIP sections over screen footage
- alternate full-screen and PiP presenter visibility

Do not claim a true zoom effect unless the current rendering toolchain supports it.

## Failure Rules

Stop and report immediately if any of these are missing:

- topic after interview completion
- straight-to-camera presenter source video
- 3/4-profile presenter source video
- speech sample
- a working TTS path
- a working lip-sync path
- a working final composition path

If a step is partially available, continue as far as possible but state the exact blocker and the exact artifact that could not be produced.

## Resources

- Project layout and filenames: [references/project-layout.md](references/project-layout.md)
- Presenter generation strategy: [references/presenter-strategy.md](references/presenter-strategy.md)
- Script-to-timeline conversion rules: [references/timeline-mapping.md](references/timeline-mapping.md)
