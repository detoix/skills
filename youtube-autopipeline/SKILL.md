---
name: youtube-autopipeline
description: >-
  End-to-end YouTube video orchestration for local automation pipelines. Use
  when the user asks to create a new YouTube video, make a video, produce a
  full video, or build a video pipeline from scratch. This skill should be
  preferred over `youtube-scriptwriter` whenever the request implies the whole
  workflow: planning, script, TTS, lip-sync, B-roll, timeline, and final
  assembly. Supports both landscape (16:9) and vertical (9:16) output formats.
---

# YouTube Autopipeline

This is an orchestration skill. When it triggers, use the existing video-production skills in sequence instead of manually recreating their responsibilities.

## Format Modes

The pipeline supports two output formats:

- **landscape** (default): 1920x1080 (16:9), uses `moviepy-video-composer --format landscape`
- **vertical**: 1080x1920 (9:16), uses `moviepy-video-composer --format vertical`

The format mode determines:
- which output format flag is passed to the composer
- canvas dimensions for all visual assets
- presenter plate orientation requirements
- presenter overlay positioning requirements
- available B-roll layout geometry
- B-roll framing expectations

### Landscape Mode

- Canvas: `1920x1080`
- Composer: `moviepy-video-composer` (`scripts/compose_video.py --format landscape`)
- Segment types: `A_ROLL`, `B_ROLL`
- B-roll layouts: `fullscreen`, `stack2`, `stack3`, `grid4`
- Presenter overlay default position: `("right", "bottom")`, scale `0.3`
- Presenter plates: landscape orientation

### Vertical Mode

- Canvas: `1080x1920`
- Composer: `moviepy-video-composer` (`scripts/compose_video.py --format vertical`)
- Segment types: `A_ROLL`, `B_ROLL`
- B-roll layouts: `fullscreen`, `stack2`, `stack3`, `grid4`
- Presenter overlay position must be explicit per presenter overlay panel; no vertical position is globally preferred
- Presenter overlay default scale: `0.34`
- Additional overlay padding: `36px` (vs `20px` landscape)
- Presenter plates: portrait orientation preferred; landscape plates will be cropped by `cover`
- Supports three horizontal videos stacked vertically through `layout: "stack3"`
- Text, still motion, and punch-in are treatments/overlays inside the segment, not segment types

### Vertical Mode Composer Invocation

```powershell
python C:\Users\kdeptula\skills\moviepy-video-composer\scripts\compose_video.py `
  --project-dir <project-dir> `
  --timeline <project-dir>\timeline.json `
  --audio <project-dir>\final_audio.wav `
  --music <project-dir>\source-assets\soundtrack.mp3 `
  --output <project-dir>\final_output.mp4 `
  --format vertical
```

Use `--music NONE` to skip background music entirely.

When the user supplies local background music, ingest it first:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\music_intake.py `
  --project-dir <project-dir> `
  --music <local-audio-path>
```

The helper copies the file to `<project-dir>\source-assets\soundtrack.<ext>` and writes `<project-dir>\manifests\music-manifest.json`. Licensing, rights, and attribution are the user's responsibility; the pipeline records optional title/artist/notes but does not license-gate production.

## Sub-Workflow Skills

Use these skills as the default sub-workflow:

- `youtube-scriptwriter` for the structured script
- `tts` for chunked voice generation and cloning
- `latentsync` for presenter lip-sync
- `codeformer-postprocess` for optional presenter face restoration after lip-sync
- `playwright-broll-recorder` for webpage and screen-record B-roll
- `pexels-stock-downloader` for non-web stock B-roll
- `animated-broll-boards` for polished synthetic-motion clips: animated HTML/CSS/JS boards, synthetic UI, checklists, timelines, comparisons, process diagrams, maps, counters, and other local motion-design B-roll
- `moviepy-video-composer` for final assembly in landscape and vertical modes
- `reel-captions` for modern word-level caption alignment and hard-burned captioned reel exports

Only do work manually when a required sub-skill is missing or clearly cannot satisfy the current step.

Build a YouTube video as a project, not as a loose set of clips. Keep the whole job in one working directory with deterministic file names.

## Agent Intake Checks

Before generating assets, the agent verifies the runtime and required inputs directly:

- Complete the Creative Approval Gate before production work. Do not generate TTS, lip-sync clips, stock clips, B-roll clips, generated images, synthetic-motion boards, timelines, captions, or final renders until the user has approved `script.json` and `manifests\visual-plan.json`, and `manifests\creative-approval.json` validates with `pipeline_check.py --mode creative-gate`.
- Real production runs must use user-provided identity assets: presenter plates, voice sample, exact voice-sample transcript, and optional music.
- If the user has not provided the required identity assets, stop and ask for the asset root, presenter plates, voice sample, and exact voice-sample transcript before promising a production reel.
- `youtube-scriptwriter`, `tts`, `latentsync`, `animated-broll-boards`, `playwright-broll-recorder`, `moviepy-video-composer`, and `reel-captions` are available.
- `codeformer-postprocess` is available if presenter restoration is expected.
- `pexels-stock-downloader` is available and Pexels authentication is available via `PEXELS_API_KEY` in the process environment or any `.env` location supported by `pexels-stock-downloader` before promising non-web stock footage.
- The known FFmpeg directory is on `PATH` before `latentsync` or `codeformer-postprocess`:
  ```powershell
  $env:PATH = "$env:USERPROFILE\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin;$env:PATH"
  ```
- The local TTS environment exists at `%USERPROFILE%\Downloads\speech-gen\venv`.
- The composer Python environment can import `moviepy`.
- The caption runtime can import `whisperx`. Production reels must use WhisperX forced alignment unless the user explicitly approves a real precomputed word-timing file. Do not use uniformly distributed or heuristic word timings for production captions.
- The required presenter plates, speech sample, and exact speech-sample transcript are present.

Do not run a scripted preflight. If a required item is missing, stop before expensive generation unless the user explicitly approves a degraded path.

## Workflow

1. Gather or infer the required inputs, including the format mode (landscape or vertical).
2. Create a project directory and normalize the asset set.
   - Inspect source media with:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\asset_inventory.py `
       --asset-root <asset-root> `
       --output <project-dir>\manifests\assets-manifest.json
     ```
   - For test-only runs, mark disposable test inputs explicitly:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\asset_inventory.py `
       --asset-root <test-asset-root> `
       --test-input-label <test-run-label> `
       --output <project-dir>\manifests\assets-manifest.json
     ```
   - Review the manifest before selecting presenter plates, voice samples, stills, overlays, music, B-roll candidates, or previous outputs for comparison.
3. Ingest user-provided local background music, or explicitly disable it when no music should be mixed:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\music_intake.py `
     --project-dir <project-dir> `
     --music <local-audio-path-or-NONE>
   ```
   Validate the resulting manifest when music was part of the project contract:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --music-manifest <project-dir>\manifests\music-manifest.json `
     --mode assets
   ```
4. Call `youtube-scriptwriter` and use its structured output as the planning source of truth. Create `<project-dir>\manifests\visual-plan.json` before generating any assets. The script and visual plan use one segment model: `type: "A_ROLL"` for presenter segments and `type: "B_ROLL"` for non-presenter visual segments. B-roll scenes must include `layout` and `panels[]`; only panels with `kind: "broll"` define a source. Source diversity is validated only from B-roll panel `source` values. `A_ROLL`, presenter panels, overlays, avatars, layouts, still motion, and punch-in treatments do not count toward source diversity. Present the generated `script.json`, `script.md` when available, and `visual-plan.json` to the user for approval. Summarize the hook, narration, on-screen text, visual idea, B-roll panel sources per scene, target duration, tone, music decision, and any factual claims needing citations. Stop and wait for approval or edits.
   The creative gate also requires at least 50% of planned `B_ROLL` duration to include a `presenter` panel. This is measured by B-roll duration, not segment count. It does not impose any A-roll/B-roll ratio.
   Before asking for approval, create the blocking review request:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\request_creative_review.py `
     --project-dir <project-dir>
   ```
   Stop after this request and wait for the user to review the script and visual plan. After the user answers exactly
   `approved`, create the approval artifact:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\approve_creative_plan.py `
     --project-dir <project-dir> `
     --resume-signal approved
   ```
   These helpers are the only official way to create `<project-dir>\manifests\creative-review-request.json` and
   `<project-dir>\manifests\creative-approval.json`. Chat phrases such as "continue", "implement", or "go ahead" are
   not approval artifacts.
5. Validate the script JSON:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --script <project-dir>\script.json `
     --format <landscape-or-vertical> `
     --mode script
   ```
   Before TTS, perform language QA on `script.json`: verify that `metadata.language` matches the actual language of `segments[].narration`, `tts_chunks[].voice_text`, `segments[].on_screen_text`, and `graphics[].copy`; verify that the text preserves the normal writing system, accents, diacritics, punctuation, and encoding conventions for that language. For non-English scripts, ASCII-only narration is a QA failure unless the target language normally uses ASCII-only writing or the text is intentionally a quoted literal such as code, IDs, URLs, brand names, ingredient names, or other fixed strings. If the script appears transliterated, ASCII-stripped, mojibake-corrupted, accidentally mixed-language, or otherwise unnatural for the declared language, stop and fix `script.json` before generating audio.
   Validate asset intake before production work. This must fail for manifests marked as test input unless this is explicitly a test run:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --asset-manifest <project-dir>\manifests\assets-manifest.json `
     --format <landscape-or-vertical> `
     --mode assets
   ```
   For test-only regression runs, add `--allow-test-input` and label the report as a test artifact.
6. Run the hard Creative Approval Gate before every production command, including TTS, stock download, generated-image work, webpage/screen recording, synthetic-motion board creation/render, LatentSync, timeline assembly, captions, and final render:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --mode creative-gate
   ```
   If this command fails, stop. Do not call producers directly to bypass the gate.
7. Call `tts` to generate chunked cloned speech from the scriptwriter payload, then verify every chunk is target-only. Trim only if a generated file actually contains a prompt/sample prefix.
7. Run pronunciation QA on all clean TTS chunks before using them for lip-sync or final narration assembly. The QA must transcribe `<project-dir>\tts\clean\*.wav`, compare each result with `script.json` `tts_chunks[].voice_text`, and fail before `latentsync` if spoken words are materially missing or changed. Use `metadata.language`; do not hardcode Polish or any other language. This QA reads audio for ASR only and must not convert, normalize, denoise, overwrite, or otherwise modify the audio files:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\tts_pronunciation_qa.py `
     --project-dir <project-dir> `
     --script <project-dir>\script.json `
     --tts-dir <project-dir>\tts\clean `
     --language <metadata.language> `
     --output <project-dir>\manifests\tts-pronunciation-qa.json
   ```
8. Presenter Plate Variety QA must pass before `latentsync`. Read `manifests/assets-manifest.json`, create `manifests/presenter-plan.json`, and treat presenter source identity by tool-computed `sha256`, not by filename. The agent must not hand-author `sha256`; hashes must come from the asset manifest or a file-hashing tool. If the same presenter video `sha256` is assigned more than once in the film, the agent must add a measurable `repeat_decisions` entry with the repeated `sha256`, all uses, `reason_code`, `available_unique_sources_for_role`, `used_unique_sources_for_role`, and a concrete reason for repeating that source. Allowed `reason_code` values are `limited_available_sources`, `continuity_choice`, `source_quality_rejection`, `duration_or_framing_constraint`, and `production_time_constraint`. Use `limited_available_sources` only when the asset manifest has exactly one unique usable source for that role. Repeats are allowed when justified; there is no hard maximum repeat count. Do not claim two files add presenter variety when their `sha256` is identical.
9. Call `latentsync` to build synced presenter clips from the silent motion plates and clean chunk audio.
10. When presenter clips look soft, compressed, or artifacted after lip-sync, call `codeformer-postprocess` on the synced presenter outputs before timeline assembly.
11. Build B-roll with the panel `source` values approved for that segment in `manifests\visual-plan.json`.
   - For abstract UI boards, checklists, timelines, comparisons, maps, process diagrams, counters, logistics, cost/risk boards, local synthetic HTML/mock UI, kinetic typography, and other synthetic-motion sections, call `animated-broll-boards` as an art-direction workflow when a polished custom board is the strongest production path. Create a custom motion scene from a creative brief; do not route the segment to a checklist/timeline/template layout. Production reels must use animated `.webm` clips for these sections, not ad hoc static PNG/Pillow boards.
   - Call `playwright-broll-recorder` for real webpage/app B-roll and for recording local synthetic-motion scenes when needed.
   - For webpage and screen-record B-roll, every capture must have a validation screenshot taken after cleanup. Use `--cookie-consent auto` and explicit `--click` / `--hide` selectors for visible overlays. Do not accept or add a webpage/screen-record asset to `selected-visuals.json` if the screenshot or recorded clip shows any popup, modal, cookie banner, newsletter prompt, chat widget, login wall, other obstructive overlay, missing CSS/unloaded styling, or non-functional page state; re-record with stronger cleanup selectors first.
   - Call `pexels-stock-downloader` when non-web stock footage is needed.
   - When the script needs photographic, cinematic, illustrative, product-neutral, or non-UI generated visual support, create a `z-image-turbo` plan:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\z_image_plan.py `
       --project-dir <project-dir> `
       --script <project-dir>\script.json
     ```
   - Generate only the selected images with `z-image-turbo`, review them, record accepted/rejected outputs in the asset manifest, then use accepted stills as `B_ROLL` panel media. Do not use `z-image-turbo` as the default path for UI boards, diagrams, checklists, timelines, or synthetic dashboard-style visuals.
   - Validate the generated-image plan before using outputs in the timeline:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
       --project-dir <project-dir> `
       --z-image-plan <project-dir>\manifests\z-image-plan.json `
       --mode assets `
       --require-z-image-review
     ```
12. Build `timeline.json` using the schema matching the format mode.
   - Do not use `caption_text` for spoken narration captions when creating reels, Shorts, TikToks, or other modern short-form outputs. Spoken captions belong to the `reel-captions` stage after base render.
   - Keep text as an overlay/treatment inside `A_ROLL` or `B_ROLL`; do not create `TEXT` timeline entries.
   - For reels, use [references/broll-section-library.md](references/broll-section-library.md) as a menu when a non-presenter visual needs a section pattern.
   - Write `<project-dir>\manifests\selected-visuals.json` only after `pipeline_check.py --mode creative-gate` passes and before final timeline use. Each accepted non-presenter visual needs `segment_id`, `local_path` or `source_url`, `section_pattern`, `duration_seconds`, `intended_use`, `accepted`, `reason`, and `risk`, and must match one scene in `manifests\visual-plan.json`. Do not hand-author `source_type`, `sha256`, `provenance`, or other identity fields as validation truth; those fields must come from an automatic resolver/indexer. Board-created synthetic-motion visuals also require `board_id`, `creative_concept`, `visual_metaphor`, and `motion_summary`.
13. Validate the timeline and final audio before composition:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --timeline <project-dir>\timeline.json `
     --audio <project-dir>\final_audio.wav `
     --format <landscape-or-vertical> `
     --mode timeline
   ```
   Resolve and validate selected visuals as one atomic gate before production render. This command must generate a fresh `<project-dir>\manifests\selected-visuals.resolved.json`, overwrite any stale or hand-authored resolved manifest, and validate only the fresh resolver output. Do not run the resolver and validation as separate manual steps:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --selected-visuals <project-dir>\manifests\selected-visuals.json `
     --mode assets `
     --resolve-selected-visuals
   ```
14. Call `moviepy-video-composer` with the matching `--format` value to render the uncaptioned base video. Pass `<project-dir>\source-assets\soundtrack.<ext>` when the music manifest is enabled; pass `--music NONE` when it is disabled. The composer writes `<project-dir>\manifests\audio-mix-manifest.json`.
15. Call `reel-captions` to generate word-level ASS captions from the approved transcript and burn them into the base render. The captioned output is the delivery candidate and preserves the already mixed narration/music audio. Production runs require WhisperX forced alignment; if WhisperX is unavailable, install it before captioning or stop and report the blocker. Do not use `--words-json` for production unless it is a real precomputed timing file explicitly approved by the user. Before captioning, `<project-dir>\manifests\final-audio-manifest.json` must exist and contain the real `tts_chunks[].timeline_start_seconds` for `final_audio.wav`; captioning without this manifest is a production error.
   ```powershell
   & "<caption-python>" C:\Users\kdeptula\skills\reel-captions\scripts\generate_reel_captions.py `
     --project-dir <project-dir> `
     --audio <project-dir>\final_audio.wav `
     --video <project-dir>\final_output.mp4 `
     --script <project-dir>\script.json `
     --output <project-dir>\final_output_captioned.mp4 `
     --language pl
   ```
   Use the target language code from the script metadata. Use `--transcript` instead of `--script` only when no script JSON exists. If captions are explicitly disabled by the user, record that exception in the final QA notes.
16. Run final visual QA on the captioned video by extracting representative frames across the timeline and inspecting them. If any frame fails the visual acceptance criteria, revise assets, typography, presenter overlay crop/shape, captions, layout, or timeline and rerender. Final visual QA fails unless `manifests\captions-manifest.json` records `alignment_source: "final-audio-manifest"`.
   ```powershell
    python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\visual_qa.py `
     --project-dir <project-dir> `
     --video <project-dir>\final_output_captioned.mp4 `
     --timeline <project-dir>\timeline.json `
     --status needs_review
   ```
   - The helper cannot mark final success by itself. A final pass requires agent visual review with concrete notes:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\visual_qa.py `
       --project-dir <project-dir> `
       --video <project-dir>\final_output_captioned.mp4 `
       --timeline <project-dir>\timeline.json `
       --format vertical `
       --min-duration 60 `
       --max-duration 90 `
       --z-image-plan <project-dir>\manifests\z-image-plan.json `
       --agent-visual-review-pass `
       --visual-review-notes "Specific notes covering hook, word-level caption sync/readability/safe zones, visual variety, generated visuals, presenter overlay quality, and rejected frames." `
       --status pass
     ```
17. Production timing logs are written to `<project-dir>\manifests\production-timings.jsonl` by guarded commands and major local production stages. After a full run, summarize them before performance analysis:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\summarize_production_timings.py `
     --project-dir <project-dir>
   ```
18. Report any blockers immediately if a required runtime tool or asset is missing.

## Creative Approval Gate

Before production work, interview the user and produce a visual plan plus an approval artifact. Production work means TTS, lip-sync, stock download, B-roll generation, image generation, synthetic-motion board creation/rendering, timeline assembly, captioning, or final render.

No production before approved creative plan:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
  --project-dir <project-dir> `
  --mode creative-gate
```

This must pass before every production command. If it fails, stop. Do not bypass it with direct producer commands.

Required approval fields:

- topic and target audience
- format and target duration
- language and tone
- CTA or end goal
- presenter/voice/music asset choices
- factual-source strategy when the script contains factual claims
- segment-by-segment outline with narration intent, on-screen text intent, visual idea, source strategy, fallback strategy, acceptance criteria, and approximate timing

`manifests\visual-plan.json` is required and must include `schema_version`, `metadata`, and `scenes`. Each scene must include `scene_id`, `segment_id`, `type`, `purpose`, `visual_idea`, `fallback_strategy`, and `acceptance_criteria`. `type` must be `A_ROLL` or `B_ROLL`. `B_ROLL` scenes must also include `layout` (`fullscreen`, `stack2`, `stack3`, `grid4`) and `panels[]`. B-roll panel `source` values are `stock`, `manual`, `generated-image`, `webpage`, `screen-record`, and `synthetic-motion`.

`manifests\creative-approval.json` is required and must be generated by `scripts\approve_creative_plan.py`. It binds approval to the current `script.json` and `manifests\visual-plan.json` by SHA-256. If either file changes, the approval is stale and production must stop until approval is regenerated after human review.

Approval flow:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\request_creative_review.py `
  --project-dir <project-dir>
```

Stop and wait for the user to review `script.json`, `script.md` when present, and `manifests\visual-plan.json`. Only
after the user replies exactly `approved`, run:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\approve_creative_plan.py `
  --project-dir <project-dir> `
  --resume-signal approved
```

When the user gave enough detail to draft the plan, create or update `script.json`, optionally `script.md`, and `manifests\visual-plan.json` as planning artifacts only, then stop and ask for approval. Do not treat this as permission to continue production.

There is no production override. If the user requests a one-shot production run, still stop at this gate.

## Interview Rules

If the user provides only a topic, do not jump directly to production. Ask a concise interview or draft a conservative approval artifact and wait for feedback.

If the user does not provide a topic, interview for these fields:

- topic
- format: landscape (16:9) or vertical (9:16)
- target audience
- tone
- language
- target duration
- CTA or end goal

Infer the format from context clues when the user does not state it explicitly:

- keywords like "reels", "shorts", "tiktok", "stories", "vertical", "9:16", "portrait" -> vertical mode
- keywords like "youtube video", "landscape", "16:9", "widescreen" -> landscape mode
- no clear signal -> default to landscape, but confirm if the user mentions mobile-first or social platforms

Interview for required identity assets whenever they are missing. These are the presenter, voice, and optional music/brand assets needed to keep the production tied to the user. The required identity assets depend on the format mode:

### Landscape Mode Assets

- at least one straight-to-camera presenter video, around 20 seconds, looking at camera, landscape orientation
- at least one 3/4-profile presenter video, around 20 seconds, suitable for presenter overlay, landscape orientation
- any additional presenter plates, alternate takes, stills, expressions, angles, or framing variants available in the asset folder
- speech sample for voice cloning
- exact transcription of the speech sample for voice cloning
- optional soundtrack or music bed for the final mix
- optional brand assets such as logo, fonts, colors, lower-thirds

### Vertical Mode Assets

- at least one straight-to-camera presenter video, around 20 seconds, looking at camera, portrait (9:16) orientation preferred
- at least one 3/4-profile presenter video when available, around 20 seconds, portrait orientation preferred; if omitted, vertical mode uses front-facing only with B-roll cutaways
- any additional presenter plates, alternate takes, stills, expressions, angles, or framing variants available in the asset folder
- speech sample for voice cloning
- exact transcription of the speech sample for voice cloning
- optional soundtrack or music bed for the final mix
- optional brand assets such as logo, fonts, colors

Treat the presenter generically. Do not assume gender in prompts, labels, filenames, or on-screen copy.

## Project Contract

Create one project directory per video. Use the layout in [references/project-layout.md](references/project-layout.md).

Keep all generated artifacts inside the project directory:

- script output
- TTS chunks
- synced presenter clips
- B-roll clips
- soundtrack asset if the user provided one
- music and audio mix manifests
- timeline
- final render
- asset inventory and final visual QA manifests

If the user gives absolute paths to source assets, copy or reference them into the project contract consistently before continuing.

## Script Generation

Call `youtube-scriptwriter` first. Its strict JSON output is the planning source of truth.

Require the scriptwriter output to contain:

- segment timing
- visual mode per segment
- pattern interrupts
- narration
- B-roll queries
- production payload blocks

Do not write a fresh freeform script if the scriptwriter skill is available. Do not use Markdown parsing as the automation interface. Use its JSON segment timing and payload arrays as the basis for downstream steps.

## TTS Rules

Call `tts` and use its local VoxCPM path. Generate audio in chunks from the scriptwriter `tts_chunks` payload, not as a single monolithic file.

Operating rules:

- do not start TTS until language QA has passed for `script.json`; regenerate or manually fix script text first if narration is transliterated, ASCII-stripped, mojibake-corrupted, accidentally mixed-language, or unnatural for `metadata.language`
- clone from the provided speech sample
- use the `VoxCPM` clone path with `prompt-audio + prompt-text + reference-audio`
- treat the exact speech-sample transcription as required input for the default cloning path
- preserve the scriptwriter chunk boundaries
- save raw clone outputs deterministically, e.g. `tts/raw/T01.wav` or `tts/raw_with_prompt/T01.wav`
- write a clean chunk for every generated file, e.g. `tts/clean/T01.wav`
- do not trim by default; current local `voxcpm.cli clone` normally writes target-only speech even when `--prompt-audio`, `--prompt-text`, and `--reference-audio` are provided
- trim only when verification shows the raw file contains the prompt/sample prefix
- never pass prompt-prefixed clone output to lip-sync or final narration assembly
- concatenate clean chunk audio into a continuous master track only after all clean chunks are verified
- keep a manifest that maps `chunk_id` to segment ids, raw output, clean output, `trim_mode`, trim point when applicable, and output duration
- reject a clean chunk if its duration, spoken content, or leading prompt/sample fragment does not match the `tts_chunk` intent; regenerate or ask for review before lip-sync
- run `scripts\tts_pronunciation_qa.py` against the clean chunks before `latentsync`; if WhisperX/ASR is unavailable or the report status is not `pass`, stop instead of silently continuing

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

There are minimum presenter source roles, not a two-video limit:

- straight-to-camera plate for full-screen A-roll
- 3/4-profile plate for presenter overlay while screen or webpage footage is visible

When multiple presenter assets are available, inspect and classify all of them before selecting. Use filenames, ffprobe metadata, and representative frames to classify assets by:

- front-facing, profile, three-quarter, still image, or unusable
- orientation and resolution
- duration
- framing quality
- likely timeline use

Prefer a varied usable set over the minimum front/profile pair. For reels and shorts, rotate across available front/profile takes to avoid repeated motion and framing unless continuity is more important than variety. Rotation must use distinct original source files when available; copying the same source file under multiple names does not count as varied presenter use.

Treat presenter videos as silent motion plates to be lip-synced against generated narration. Do not assume their original mouth motion matches the final script.

Record selected and rejected presenter assets in the asset manifest with concise reasons.

Generate presenter outputs as reusable synced chunks or grouped scene clips. Use the conventions in [references/presenter-strategy.md](references/presenter-strategy.md).

### Format-Specific Presenter Rules

#### Landscape

- Front plate: landscape orientation, 16:9
- Profile plate: landscape orientation, positioned at lower-right

#### Vertical

- Front plate: portrait orientation (9:16) preferred; landscape plates will be center-cropped to fill the vertical canvas via `cover`
- Profile plate: portrait orientation preferred; if only a landscape profile plate is available, it will still work but may crop heavily
- Presenter overlay position must be explicit per presenter overlay panel, with scale `0.34` as the default size
- If no profile plate is provided, use front-facing A-roll alternated with B-roll segments without presenter overlays
- When a portrait front plate is used as a presenter panel in `stack2`, the composer automatically crops it higher than a center crop so the head and upper torso stay in frame. This stack-panel rule is separate from profile overlay/PiP crop settings.

Important timing rule:

- presenter speech may continue while the presenter is off-screen

Generate lip-synced presenter media only for timeline segments or panels where the presenter is actually visible. If a `B_ROLL` segment has no presenter panel, do not generate unused presenter media for that covered duration.

Important audio reuse rule:

- do not regenerate TTS just to make presenter-only sync clips
- treat the generated TTS chunk files as the audio source of truth
- when a visible presenter segment uses only part of a TTS chunk, cut a subclip from the existing chunk audio and use that for lip-sync
- only regenerate TTS for a segment if the original chunk audio is unusable and the user explicitly wants a rerender

### Presenter Restoration Rule

After lip-sync and before final assembly, evaluate the synced presenter clips for visible softness, compression artifacts, or face-detail loss.

Default rule:

- if `codeformer-postprocess` is available, restore all synced presenter clips that will appear on screen
- use restored clips as the default timeline inputs for `A_ROLL` and presenter panels

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

## Presenter Overlay Crop Decision (Vertical Mode)

When building B-roll segments with presenter overlay panels in vertical mode, the overlay should render as a circular talking-head bubble. Source videos may be portrait, landscape, or square; the composer square-crops the overlay before applying the circular mask.

The composer accepts `overlay_crop_x`, `overlay_crop_y`, and `overlay_crop_size` parameters to override the automatic center square crop. The orchestrator decides these values by visually inspecting the source plate when the center crop does not keep the presenter well centered.

### Workflow

1. Extract a single representative frame from the overlay source video:
   ```powershell
   ffmpeg -i "source-assets/presenter-profile.mp4" -vframes 1 -q:v 2 "source-assets/profile_frame.jpg"
   ```
2. View the extracted frame and determine the optimal crop origin where the presenter's face is centered.
3. Choose `overlay_crop_x` and `overlay_crop_y` as the top-left corner of the square crop, in pixels of the source video.
4. Optionally specify `overlay_crop_size` to control the square size. Defaults to `min(width, height)` of the source.
5. Pass the crop values in the presenter panel.

### Decision Rules

- The crop origin must keep the presenter's face well-centered within the 1:1 square.
- Clamp values to valid ranges: `x + size <= source_width`, `y + size <= source_height`.
- For a 9:16 (portrait) source plate, the crop should capture the head and upper torso region.
- For a 16:9 (landscape) source plate, the crop should capture the face centered, typically from the middle horizontal band.
- If the source is already approximately square or the face is centered well enough for the automatic square crop, the crop parameters may be omitted.

### Timeline Entry Example

```json
{
  "type": "B_ROLL",
  "layout": "fullscreen",
  "panels": [
    { "kind": "broll", "source": "webpage", "path": "broll/B03.webm", "role": "background" },
    {
      "kind": "presenter",
      "path": "synced/profile/P03.mp4",
      "role": "overlay",
      "overlay_crop_x": 520,
      "overlay_crop_y": 80,
      "overlay_crop_size": 900,
      "overlay_scale": 0.34,
      "overlay_position": ["right", "top"]
    }
  ],
  "start_time": 10.0,
  "end_time": 18.0
}
```

### Landscape Mode

In landscape mode, overlay crop parameters are optional. Use them only when the source framing would make the lower-right presenter overlay unclear.

## B-Roll Rules

### Creative Visual Strategy

Before fetching, generating, or recording B-roll, create a compact visual strategy for the whole video. Do not start from a fixed source priority. Start from the creative problem: what will make this video clear, credible, visually alive, and worth watching on the target platform?

The visual strategy must define:

- overall visual style and mood
- planned resolved `source_type` mix
- segment-level visual asset choice
- why each visual asset was chosen
- known tradeoffs or fallback risks
- candidate source locator for every non-presenter visual asset, such as provider id, source URL, local absolute path, or generated asset id; final identity must come from resolver/indexer output

The agent may freely combine:

- real webpage, app, documentation, or article captures
- stock footage
- generated bitmap visuals or generated video-like assets
- synthetic-motion clips from `animated-broll-boards`, project-local synthetic HTML/mock UI, animated typography, or simple local motion design
- screenshots
- avatar-only sections
- screen recordings
- composited layouts
- split-screen sections
- two-stack and three-stack sections
- four-grid comparison/collage sections
- bounded still-image camera motion

### B-Roll Source Mix And Uniqueness

Supported B-roll `source_type` values are exactly: `webpage`, `stock`, `screen-record`, `generated-image`, `manual`, and `synthetic-motion`. Do not treat repeated assets, renamed assets, or multiple assets from one resolved `source_type` as source diversity.

Before building `timeline.json`, create or update `manifests\selected-visuals.json` as an intent manifest that lists each non-presenter visual asset with:

- `segment_id`
- `section_pattern`
- `source_url` or `local_path`
- `duration_seconds`
- `accepted`
- `intended_use`
- `reason`
- `risk`

Agent-authored manifests are intent manifests, not validation truth. Do not use agent-authored `source_type`, `sha256`, `provenance`, or other identity fields as validation evidence. Validation must use resolver/indexer output only. Run `scripts\pipeline_check.py --resolve-selected-visuals` against `manifests\selected-visuals.json` to generate and validate `manifests\selected-visuals.resolved.json` in one gate; never create that file manually. If the resolver is missing, fails, or cannot resolve a referenced asset, stop the pipeline.

`manifests\selected-visuals.resolved.json` is the validation manifest. It must be generated by a resolver/indexer from the intent manifest and the referenced assets. For each accepted visual, it must provide the resolved `source_type`, resolved identity, and provenance. For local files it must compute `sha256` from file bytes. For remote/provider assets it must derive identity from provider id, source URL, or another resolver-owned canonical key. The agent must not fill these fields manually.

Selected visuals must satisfy a proportional source-mix rule using only `source_type` values from `manifests\selected-visuals.resolved.json` for accepted B-roll assets referenced by `B_ROLL` panels. Presenter panels, `A_ROLL`, captions, overlays, and layout names never count toward source diversity. For every started 20 seconds of accepted B-roll asset duration, use at least one distinct resolved `source_type`. For example, 1-20 seconds requires one source type, 21-40 seconds requires two, 41-60 seconds requires three, and so on. Do not cap this requirement. Materials from `broll/boards/**`, `broll/html/**`, and `broll/motion/**` resolve to `synthetic-motion`; do not treat their production method as source diversity.

Enforce reuse on resolved identity, not filename. Same `sha256` means same asset, regardless of filename, path, slot, `source_type`, or description. Renamed downloads, copied files, or identical provider URLs are the same asset and must not be treated as unique B-roll. If a resolved asset identity is reused beyond the allowed threshold, add a top-level `reuse_decisions` entry with the resolved identity, `uses`, and a concrete `reason`.

For factual nature, science, history, product, location, or how-to explainers, separate factual evidence visuals from illustrative visuals:

- Use verified or authoritative visuals for identification, comparison, measurements, UI facts, product details, locations, or claims where the image itself carries factual meaning.
- Use stock footage only when the subject match is visually clear enough after frame inspection.
- Use generated visuals as illustrative or cinematic support unless the user explicitly accepts synthetic factual stand-ins.
- Never use generic stock footage as visual proof of a specific species, product, place, person, or interface.

If a stock provider returns the same clip across multiple queries, reject duplicates before timeline assembly and refine the source strategy instead of filling the reel with repeated footage.

### Synthetic Motion With animated-broll-boards

Use `animated-broll-boards` only when `manifests\visual-plan.json` includes a B-roll panel with `source: "synthetic-motion"` for that scene and the creative gate passes. The agent must still choose the visual source per segment based on clarity, factual fit, and pacing; resolved `source_type` is assigned by provenance rules, not by agent wording. The skill is not a generic B-roll fallback or a template library. Each board needs a segment-specific visual metaphor and custom HTML/CSS/JS motion.

Rules:

- Save outputs under `<project-dir>\broll\boards\<board-id>\`.
- Render boards as `.webm` clips from project-local `HTML/CSS/JS`.
- Record accepted board clips in `manifests\selected-visuals.json` with a full intent entry: `segment_id`, `section_pattern`, `local_path: "broll/boards/<board-id>/<board-id>.webm"`, `duration_seconds`, `accepted: true`, `intended_use`, `reason`, `risk: "synthetic explanatory motion graphic"`, `board_id: "<board-id>"`, `creative_concept`, `visual_metaphor`, and `motion_summary`. Do not write `source_type`; the resolver must assign `source_type: "synthetic-motion"` from the path/provenance.
- Run `qa_board.mjs` and inspect the preview before timeline use.
- Do not create production abstract/UI/infographic B-roll as ad hoc static PNG/Pillow boards. Static PNGs are allowed only as tiny auxiliary assets or when the user explicitly requests a still.
- Reject boards that look like old infographics, test harnesses, template placeholders, generic cards, clipart layouts, repeated component layouts, or low-effort mock UI.

### Generated Visuals With z-image-turbo

Use `z-image-turbo` when real footage, screen capture, or stock video would be generic, misleading, unavailable, or visually weak. Generated stills are acceptable for photographic, cinematic, illustrative, metaphor, product-neutral mood scenes, and non-UI graphic inserts. For synthetic UI, checklist, timeline, comparison, process, map, logistics, cost/risk, and dashboard-style boards, use `animated-broll-boards` when synthetic motion is selected.

Do not use generated images as a cheap replacement for missing required identity or factual assets. If a production brief requires the user's actual product, location, face, brand, app, or another real-world subject whose appearance is the point of the video, ask for those assets. Otherwise, generated visuals and synthetic-motion clips are valid B-roll choices for abstract, conceptual, educational, or product-neutral segments.

Rules:

- Generate a plan with `scripts/z_image_plan.py` from `script.json` before running image generation.
- Save outputs under `<project-dir>\broll\generated\`.
- Record prompt, output path, segment id, acceptance status, and rejection reason in the project manifest.
- Pass the z-image plan into final `visual_qa.py` so timeline references to `broll/generated/` are checked against reviewed accepted outputs.
- Keep prompts vertical-safe: central subject, clean upper/middle negative space, no fake logos, no credentials, no private data, no implied real-brand UI unless explicitly requested.
- Review generated images before using them. Reject generic, distorted, illegible, branded, unsafe, or visually cheap outputs.
- Accepted generated stills can be referenced directly by the composer as `B_ROLL` panel media.
- When generated stills need motion in a reel, pre-render short motion clips from the accepted stills before timeline assembly, or set a `still_motion` treatment on the B-roll panel. Acceptable motion treatments include slow push-in, slow pull-back, subtle pan, swipe transition, parallax-style crop, or split-panel comparison. Motion must stay inside image bounds.
- Record generated-still motion clips with both the original still path and the rendered motion clip path in the selected-visuals manifest.

Choose the visual source per segment using these criteria:

- Does it make the point clear in under two seconds?
- Does it look strong in the requested aspect ratio?
- Does it avoid misleading brand endorsement?
- Does it add visual variety?
- Does it support the narration instead of merely repeating it?
- Can it be verified before final assembly?

### Source Selection Guidance

Use the strongest visual source for the segment. A fixed source order is not required.

- Use real webpages, docs, or product-neutral captures when authority, credibility, or recognizable context matters.
- Use stock footage when human behavior, physical context, pacing texture, or cinematic energy matters.
- Use generated visuals when the topic needs photographic, cinematic, illustrative, or mood support and real footage would be dull, generic, or unavailable.
- Use `synthetic-motion` for locally created boards, local synthetic HTML/mock UI, kinetic typography, simple local motion design, controlled diagrams, synthetic UI states, or abstract relationships that non-synthetic sources cannot show clearly.
- Use `animated-broll-boards` as the preferred production workflow for polished synthetic-motion clips that need custom HTML/CSS/JS motion and board QA.
- Use lightweight local synthetic HTML or other render paths only when `animated-broll-boards` cannot express the required custom scene; the resolved `source_type` is still `synthetic-motion`.
If the most literal asset choice is boring, choose a more cinematic, graphic, kinetic, or emotionally legible option. The goal is a finished social video, not merely a valid assembled timeline.

Synthetic-motion guardrails:

- Do not present synthetic-motion HTML/mock UI as a real product or real site.
- Avoid real brands, real credentials, real user data, and implied vendor endorsement unless the user explicitly requested them.
- Prefer `animated-broll-boards` for production synthetic-motion. Handwritten one-off HTML is a fallback for custom scenes the board skill cannot express.
- Save local synthetic HTML/mock UI files inside the project directory, then record them with `playwright-broll-recorder` using a `file:///...` URL; the resolver must classify the accepted output as `synthetic-motion`.
- Capture and inspect a validation screenshot before accepting the clip.
- Record any non-board synthetic-motion fallback in `assembly_notes` or the asset manifest so the source is transparent.
- Synthetic-motion HTML/mock UI is allowed for precision, but it should be designed as polished local motion design when it is visually prominent.

Prefer concrete B-roll tasks:

- webpage URL
- target section or selector
- duration
- scrolling vs static
- obstructive UI to click or hide

Locale rule:

- derive the target language and audience locale from the brief and keep that context during B-roll selection
- for webpage capture, prefer pages whose visible UI language matches the video language when localized versions exist
- prefer regionally appropriate tools, flows, labels, and examples when they materially improve audience fit
- do not default to English-language pages for a non-English video just because they are easier to find
- if a cross-language asset is the best available option, treat it as an explicit fallback and note it

### Vertical B-Roll Framing

Choose the B-roll capture shape deliberately:

- record mobile or portrait webpage footage when the page has a useful responsive layout and the full-screen segment should be vertical-native
- record landscape webpage or stock footage when the shot is intended for `layout: "stack3"` or when the source needs wide UI context

When source footage is landscape (16:9), the `cover` crop will center-crop horizontally to fill `1080x1920`. Keep this in mind:

- ensure key visual content is vertically centered in the source footage when possible
- prefer B-roll where the subject or action is in the center third of the frame
- for `layout: "stack3"` segments, three landscape clips are scaled to `1080px` wide and stacked vertically without cropping; use this when center-crop would lose important content

Do not substitute vague B-roll. If a query cannot be satisfied from the available sources, flag the segment for manual asset selection.

## Timeline Assembly

Translate the scriptwriter output into `timeline.json` using the schema that matches the format mode, then call `moviepy-video-composer` with the matching `--format` value.

For modern reels, [references/broll-section-library.md](references/broll-section-library.md) is available as a section-pattern library for non-presenter visuals. Do not make any pattern or resolved `source_type` globally preferred. Record selected patterns in `manifests\selected-visuals.json`.

If the user supplied a soundtrack, run `scripts/music_intake.py` and pass the ingested `source-assets\soundtrack.<ext>` file to the composer. Do not normalize or mix it in the orchestrator. Audio normalization, sidechain ducking, final mix safety, and `audio-mix-manifest.json` belong to the composer step.

## Final Visual QA

Final render existence, duration, and resolution are not enough. Before delivering the video, the agent must visually inspect the actual rendered result. For captioned reels, inspect `final_output_captioned.mp4`; inspect `final_output.mp4` only when captions are explicitly disabled.

Extract representative frames from the final output:

- first 2 seconds
- every major segment boundary or at least every 8-10 seconds
- every segment with a presenter overlay panel
- every segment with text-overlay treatment
- final 2 seconds

Save these frames under `qa/final-frames/` and inspect them before final delivery. Prefer the reusable helper:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\visual_qa.py `
  --project-dir <project-dir> `
  --video <project-dir>\final_output_captioned.mp4 `
  --timeline <project-dir>\timeline.json `
  --status needs_review
```

Example extraction pattern:

```powershell
$ffmpeg = "$env:USERPROFILE\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
New-Item -ItemType Directory -Force "$projectDir\qa\final-frames" | Out-Null
& $ffmpeg -y -ss 00:00:02 -i "$projectDir\final_output_captioned.mp4" -frames:v 1 "$projectDir\qa\final-frames\frame_002s.png"
& $ffmpeg -y -ss 00:00:10 -i "$projectDir\final_output_captioned.mp4" -frames:v 1 "$projectDir\qa\final-frames\frame_010s.png"
```

Use enough timestamps to cover the whole timeline. Do not inspect only one preview frame.

Automated structural checks cannot mark a reel as production-ready. A final pass requires explicit agent visual review notes. If a render looks generic, cheap, template-like, visually empty, or off-brand, mark it failed even when duration, resolution, and blank-frame checks pass.

Use [references/professional-qa-rubric.md](references/professional-qa-rubric.md) before setting `--agent-visual-review-pass`.

Reject and rerender when any frame shows:

- overlapping text, captions, cards, presenter overlays, or UI elements
- word-level captions out of sync with narration or active-word highlighting that distracts from readability
- text too large for its container or clipped by the frame
- dense text that cannot be read at phone size
- presenter overlay rendered as a tall rounded rectangle when it should be circular
- subject face cropped awkwardly in presenter overlay or A-roll
- bland placeholder UI, low-effort cards, or obviously unfinished mockups
- poor contrast, muddy colors, or unreadable typography
- visual repetition that makes the reel feel static or boring
- real-brand or credential exposure that was not explicitly intended
- black/blank/error/loading frames
- low-effort generated stills, generic stock, placeholder-looking synthetic-motion, or any frame that looks like a test harness rather than a finished reel
- static PNG/Pillow UI boards used as production abstract/infographic B-roll without explicit user approval

If a frame fails, do not explain it away. Fix the visual cause and rerender. Record visual QA results in `manifests/visual-qa.json` with inspected frame paths, pass/fail status, and any rerender actions.

For synthetic-motion boards and generated synthetic HTML/mock UI, inspect both the source validation screenshot and the final rendered frame where it appears. Passing the isolated source screenshot is not sufficient, because final overlays, text treatments, presenter overlays, scaling, and timeline composition can introduce new failures.

### Landscape Timeline

Composer: `moviepy-video-composer --format landscape`

Timeline entries use the same segment contract as the script:

- `type: "A_ROLL"` -> full-screen synced straight-to-camera clip.
- `type: "B_ROLL"` -> non-presenter segment rendered from `layout` and `panels[]`.
- Layout and treatment names must not appear as top-level `type`.

### Vertical Timeline

Composer: `moviepy-video-composer --format vertical`

The same contract applies in vertical mode. Use `layout: "fullscreen"`, `layout: "stack2"`, `layout: "stack3"`, or `layout: "grid4"` on `B_ROLL` entries. A presenter can be an overlay or one panel by adding a `{"kind": "presenter"}` panel.
For vertical fullscreen B-roll with a presenter overlay panel, set `overlay_position` explicitly on the presenter panel. Choose the position for the actual frame, captions, and B-roll composition; no vertical overlay position is globally preferred.
Timeline validation requires at least 50% of total `B_ROLL` duration to include a `presenter` panel. Count duration, not segment count; `A_ROLL` is outside this calculation.

### Timeline Safety Fields

Use these composer controls consistently:

- `clip_start`: shared fallback source offset for simple entries
- panel `clip_start`: per-panel source offset
- panel `treatment`: optional render treatment such as `still_motion`
- panel `motion_type`: optional still-motion direction
- `loop_policy`: `loop` or `error`
- panel `loop_policy`: per-panel loop control

Default policies:

- A-roll presenter: `loop_policy: "error"`
- presenter panels: `loop_policy: "error"`
- B-roll panels: `loop_policy: "loop"` only when repeated footage is acceptable

Never allow presenter media to loop silently. If a visible presenter clip is shorter than the target segment, shorten the segment, choose another clip, regenerate the presenter media, or fail validation.

Fullscreen B-roll with presenter overlay:

```json
{
  "type": "B_ROLL",
  "layout": "fullscreen",
  "panels": [
    { "kind": "broll", "source": "webpage", "path": "broll/B01.webm", "role": "background" },
    { "kind": "presenter", "path": "synced/profile/P01.mp4", "role": "overlay", "overlay_position": ["right", "top"] }
  ],
  "start_time": 0.0,
  "end_time": 5.0
}
```

Do not use `caption_text` for spoken short-form captions. Use `reel-captions` after base render to create word-level captions from the approved transcript. `caption_text` may still be used sparingly for non-spoken labels or temporary test renders, but production reels should reserve timeline text for intentional graphics.

Stacked B-roll with presenter as one panel:

```json
{
  "type": "B_ROLL",
  "layout": "stack2",
  "panels": [
    { "kind": "presenter", "path": "synced/front/A02.mp4" },
    { "kind": "broll", "source": "generated-image", "path": "broll/generated/S03.png", "treatment": "still_motion" }
  ],
  "start_time": 5.0,
  "end_time": 10.0
}
```

Use [references/timeline-mapping.md](references/timeline-mapping.md) for the exact conversion rules per format mode.

Do not claim a true zoom effect unless the current rendering toolchain supports it.

## Failure Rules

Stop and report immediately if any of these are missing:

- topic after interview completion
- straight-to-camera presenter source video
- speech sample
- a working TTS path
- a working lip-sync path
- a working final composition path

For landscape mode, also require:

- 3/4-profile presenter source video

For vertical mode, the 3/4-profile plate is optional. If it is missing, route presenter visibility through A-roll and B-roll only, without presenter-overlay panels.

If a step is partially available, continue as far as possible but state the exact blocker and the exact artifact that could not be produced.

## Resources

- Project layout and filenames: [references/project-layout.md](references/project-layout.md)
- B-roll section pattern library: [references/broll-section-library.md](references/broll-section-library.md)
- Presenter generation strategy: [references/presenter-strategy.md](references/presenter-strategy.md)
- Script-to-timeline conversion rules: [references/timeline-mapping.md](references/timeline-mapping.md)
- Short-form production practices: [references/short-form-practices.md](references/short-form-practices.md)
- Current local change notes: [references/changelog-2026-05-05.md](references/changelog-2026-05-05.md)
