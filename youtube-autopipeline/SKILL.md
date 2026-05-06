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
- PIP overlay positioning defaults
- available timeline segment types
- B-roll framing expectations

### Landscape Mode

- Canvas: `1920x1080`
- Composer: `moviepy-video-composer` (`scripts/compose_video.py --format landscape`)
- Segment types: `A-ROLL`, `B-ROLL`, `PIP`
- PIP default position: `("right", "bottom")`, scale `0.3`
- Presenter plates: landscape orientation

### Vertical Mode

- Canvas: `1080x1920`
- Composer: `moviepy-video-composer` (`scripts/compose_video.py --format vertical`)
- Segment types: `A-ROLL`, `B-ROLL`, `PIP`, `TEXT`, `STACK_3`
- PIP default position: `("center", "bottom")`, scale `0.34`
- Additional overlay padding: `36px` (vs `20px` landscape)
- Presenter plates: portrait orientation preferred; landscape plates will be cropped by `cover`
- Supports `STACK_3` for three horizontal videos stacked vertically
- Supports `TEXT` for keyword or caption overlays on a background clip

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
- `animated-broll-boards` for polished animated HTML/CSS/JS boards, synthetic UI, checklists, timelines, comparisons, process diagrams, maps, counters, and other abstract motion-graphic B-roll
- `moviepy-video-composer` for final assembly in landscape and vertical modes
- `reel-captions` for modern word-level caption alignment and hard-burned captioned reel exports

Only do work manually when a required sub-skill is missing or clearly cannot satisfy the current step.

Build a YouTube video as a project, not as a loose set of clips. Keep the whole job in one working directory with deterministic file names.

## Agent Intake Checks

Before generating assets, the agent verifies the runtime and required inputs directly:

- Real production runs must use user-provided identity assets: presenter plates, voice sample, exact voice-sample transcript, and optional music.
- User-provided identity assets do not limit B-roll creativity. B-roll may be sourced, recorded, generated, composited, mocked, or built as motion graphics when that is the strongest creative and factual choice for the segment.
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
4. Call `youtube-scriptwriter` and use its structured output as the planning source of truth.
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
6. Call `tts` to generate chunked cloned speech from the scriptwriter payload, then verify every chunk is target-only. Trim only if a generated file actually contains a prompt/sample prefix.
7. Run pronunciation QA on all clean TTS chunks before using them for lip-sync or final narration assembly. The QA must transcribe `<project-dir>\tts\clean\*.wav`, compare each result with `script.json` `tts_chunks[].voice_text`, and fail before `latentsync` if spoken words are materially missing or changed. Use `metadata.language`; do not hardcode Polish or any other language. This QA reads audio for ASR only and must not convert, normalize, denoise, overwrite, or otherwise modify the audio files:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\tts_pronunciation_qa.py `
     --project-dir <project-dir> `
     --script <project-dir>\script.json `
     --tts-dir <project-dir>\tts\clean `
     --language <metadata.language> `
     --output <project-dir>\manifests\tts-pronunciation-qa.json
   ```
8. Presenter Plate Variety QA must pass before `latentsync`. Read `manifests/assets-manifest.json`, create `manifests/presenter-plan.json`, and treat presenter source identity by tool-computed `sha256`, not by filename. The agent must not hand-author `sha256`; hashes must come from the asset manifest or a file-hashing tool. If the same presenter video `sha256` is assigned more than once in the film, the agent must add a `repeat_decisions` entry with the repeated `sha256`, all uses, and a concrete reason for repeating that source. Repeats are allowed when justified; there is no hard maximum repeat count. Do not claim two files add presenter variety when their `sha256` is identical.
9. Call `latentsync` to build synced presenter clips from the silent motion plates and clean chunk audio.
10. When presenter clips look soft, compressed, or artifacted after lip-sync, call `codeformer-postprocess` on the synced presenter outputs before timeline assembly.
11. Build B-roll with the source that matches the segment intent.
   - For abstract UI boards, checklists, timelines, comparisons, maps, process diagrams, counters, logistics, cost/risk boards, and other infographic-style sections, call `animated-broll-boards` as an art-direction workflow. Create a custom motion scene from a creative brief; do not route the segment to a checklist/timeline/template layout. Production reels must use animated `.webm` board clips for these sections, not ad hoc static PNG/Pillow boards.
   - Call `playwright-broll-recorder` for real webpage/app B-roll and for recording local HTML scenes when needed.
   - Call `pexels-stock-downloader` when non-web stock footage is needed.
   - When the script needs photographic, cinematic, illustrative, product-neutral, or non-UI generated visual support, create a `z-image-turbo` plan:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\z_image_plan.py `
       --project-dir <project-dir> `
       --script <project-dir>\script.json
     ```
   - Generate only the selected images with `z-image-turbo`, review them, record accepted/rejected outputs in the asset manifest, then use accepted stills as timeline `B-ROLL`, `TEXT` backgrounds, or generated visual inserts. Do not use `z-image-turbo` as the default path for UI boards, diagrams, checklists, timelines, or synthetic dashboard-style visuals.
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
   - Keep `TEXT` entries only for intentional graphic beats, labels, title cards, and comparison graphics.
   - For reels, choose B-roll section patterns from [references/broll-section-library.md](references/broll-section-library.md). Treat it as a menu, not a ranking.
   - Write `<project-dir>\manifests\selected-visuals.json` before final timeline use as an intent manifest. Each accepted non-presenter visual needs `segment_id`, `local_path` or `source_url`, `section_pattern`, `duration_seconds`, `intended_use`, `accepted`, `reason`, and `risk`. Do not hand-author `source_type`, `sha256`, `provenance`, or other identity fields as validation truth; those fields must come from an automatic resolver/indexer. Animated-board visuals also require `board_id`, `creative_concept`, `visual_metaphor`, and `motion_summary`.
13. Validate the timeline and final audio before composition:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --timeline <project-dir>\timeline.json `
     --audio <project-dir>\final_audio.wav `
     --mode timeline
   ```
   Resolve selected visuals, then validate the resolved manifest before production render. If `<project-dir>\manifests\selected-visuals.resolved.json` is missing, treat selected-visuals validation as blocked, not pass:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --selected-visuals <project-dir>\manifests\selected-visuals.resolved.json `
     --mode assets
   ```
14. Call `moviepy-video-composer` with the matching `--format` value to render the uncaptioned base video. Pass `<project-dir>\source-assets\soundtrack.<ext>` when the music manifest is enabled; pass `--music NONE` when it is disabled. The composer writes `<project-dir>\manifests\audio-mix-manifest.json`.
15. Call `reel-captions` to generate word-level ASS captions from the approved transcript and burn them into the base render. The captioned output is the delivery candidate and preserves the already mixed narration/music audio. Production runs require WhisperX forced alignment; if WhisperX is unavailable, install it before captioning or stop and report the blocker. Do not use `--words-json` for production unless it is a real precomputed timing file explicitly approved by the user.
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
16. Run final visual QA on the captioned video by extracting representative frames across the timeline and inspecting them. If any frame fails the visual acceptance criteria, revise assets, typography, PiP crop/shape, captions, layout, or timeline and rerender.
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
       --visual-review-notes "Specific notes covering hook, word-level caption sync/readability/safe zones, visual variety, generated visuals, presenter/PiP quality, and rejected frames." `
       --status pass
     ```
16. Report any blockers immediately if a required runtime tool or asset is missing.

## Interview Rules

If the user provides only a topic, infer the rest conservatively and confirm only if a missing value would change production materially.

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
- at least one 3/4-profile presenter video, around 20 seconds, suitable for lower-right PiP, landscape orientation
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
- 3/4-profile plate for PiP overlay while screen or webpage footage is visible

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
- PIP overlay position: `("center", "bottom")` with scale `0.34` instead of lower-right
- If no profile plate is provided, use front-facing A-roll alternated with full B-roll cutaways instead of PiP segments

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

## PiP Overlay Crop Decision (Vertical Mode)

When building PIP segments in vertical mode, the overlay should render as a circular talking-head bubble. Source videos may be portrait, landscape, or square; the composer square-crops the overlay before applying the circular mask.

The composer accepts `overlay_crop_x`, `overlay_crop_y`, and `overlay_crop_size` parameters to override the automatic center square crop. The orchestrator decides these values by visually inspecting the source plate when the center crop does not keep the presenter well centered.

### Workflow

1. Extract a single representative frame from the overlay source video:
   ```powershell
   ffmpeg -i "source-assets/presenter-profile.mp4" -vframes 1 -q:v 2 "source-assets/profile_frame.jpg"
   ```
2. View the extracted frame and determine the optimal crop origin where the presenter's face is centered.
3. Choose `overlay_crop_x` and `overlay_crop_y` as the top-left corner of the square crop, in pixels of the source video.
4. Optionally specify `overlay_crop_size` to control the square size. Defaults to `min(width, height)` of the source.
5. Pass the crop values in the PIP timeline entry.

### Decision Rules

- The crop origin must keep the presenter's face well-centered within the 1:1 square.
- Clamp values to valid ranges: `x + size <= source_width`, `y + size <= source_height`.
- For a 9:16 (portrait) source plate, the crop should capture the head and upper torso region.
- For a 16:9 (landscape) source plate, the crop should capture the face centered, typically from the middle horizontal band.
- If the source is already approximately square or the face is centered well enough for the automatic square crop, the crop parameters may be omitted.

### Timeline Entry Example

```json
{
  "type": "PIP",
  "background_path": "broll/B03.webm",
  "overlay_path": "synced/profile/P03.mp4",
  "overlay_crop_x": 520,
  "overlay_crop_y": 80,
  "overlay_crop_size": 900,
  "overlay_scale": 0.34,
  "overlay_position": ["center", "bottom"],
  "start_time": 10.0,
  "end_time": 18.0
}
```

### Landscape Mode

In landscape mode, overlay crop parameters are optional. Use them only when the source framing would make the lower-right PiP overlay unclear.

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
- animated board clips from `animated-broll-boards`
- project-local HTML/mock UI
- animated typography
- simple motion graphics
- screenshots
- avatar-only sections
- screen recordings
- composited layouts
- split-screen sections
- two-stack and three-stack sections
- four-grid comparison/collage sections
- bounded still-image camera motion

### B-Roll Source Mix And Uniqueness

Use a deliberate mix of resolved `source_type` values. Supported B-roll `source_type` values are exactly: `webpage`, `stock`, `screen-record`, `generated-image`, `manual`, `local-html`, `motion-graphic`, and `animated-board`. Do not treat repeated assets, renamed assets, or multiple assets from one resolved `source_type` as source diversity.

Before building `timeline.json`, create or update `manifests\selected-visuals.json` as an intent manifest that lists each non-presenter visual asset with:

- `segment_id`
- `section_pattern`
- `source_url` or `local_path`
- `duration_seconds`
- `accepted`
- `intended_use`
- `reason`
- `risk`

Agent-authored manifests are intent manifests, not validation truth. Do not use agent-authored `source_type`, `sha256`, `provenance`, or other identity fields as validation evidence. Validation must use resolver/indexer output only. If `manifests\selected-visuals.resolved.json` is missing, selected-visuals validation must be treated as blocked, not pass.

`manifests\selected-visuals.resolved.json` is the validation manifest. It must be generated by a resolver/indexer from the intent manifest and the referenced assets. For each accepted visual, it must provide the resolved `source_type`, resolved identity, and provenance. For local files it must compute `sha256` from file bytes. For remote/provider assets it must derive identity from provider id, source URL, or another resolver-owned canonical key. The agent must not fill these fields manually.

Selected visuals must satisfy a proportional source-mix rule using only `source_type` values from `manifests\selected-visuals.resolved.json`: for every started 20 seconds of accepted B-roll duration, use at least one distinct resolved `source_type`. For example, 1-20 seconds requires one source type, 21-40 seconds requires two, 41-60 seconds requires three, and so on. Do not cap this requirement. Materials from `broll/boards/**` are one resolved `source_type`/provenance regardless of board names, descriptions, or creative concepts.

Enforce reuse on resolved identity, not filename. Same `sha256` means same asset, regardless of filename, path, slot, `source_type`, or description. Renamed downloads, copied files, or identical provider URLs are the same asset and must not be treated as unique B-roll. If a resolved asset identity is reused beyond the allowed threshold, add a top-level `reuse_decisions` entry with the resolved identity, `uses`, and a concrete `reason`.

For factual nature, science, history, product, location, or how-to explainers, separate factual evidence visuals from illustrative visuals:

- Use verified or authoritative visuals for identification, comparison, measurements, UI facts, product details, locations, or claims where the image itself carries factual meaning.
- Use stock footage only when the subject match is visually clear enough after frame inspection.
- Use generated visuals as illustrative or cinematic support unless the user explicitly accepts synthetic factual stand-ins.
- Never use generic stock footage as visual proof of a specific species, product, place, person, or interface.

If a stock provider returns the same clip across multiple queries, reject duplicates before timeline assembly and refine the source strategy instead of filling the reel with repeated footage.

### Animated Boards With animated-broll-boards

Use `animated-broll-boards` when an animated explanatory board is the strongest visual choice for the segment. The agent must still choose the visual source per segment based on clarity, factual fit, pacing, and overall visual variety; resolved `source_type` is assigned by provenance rules, not by agent wording. The skill is not a template library. Each board needs a segment-specific visual metaphor and custom HTML/CSS/JS motion.

Rules:

- Save outputs under `<project-dir>\broll\boards\<board-id>\`.
- Render boards as `.webm` clips from project-local `HTML/CSS/JS`.
- Record accepted board clips in `manifests\selected-visuals.json` with a full intent entry: `segment_id`, `section_pattern`, `local_path: "broll/boards/<board-id>/<board-id>.webm"`, `duration_seconds`, `accepted: true`, `intended_use`, `reason`, `risk: "synthetic explanatory motion graphic"`, `board_id: "<board-id>"`, `creative_concept`, `visual_metaphor`, and `motion_summary`. Do not write `source_type`; the resolver must assign `source_type: "animated-board"` from the path/provenance.
- Run `qa_board.mjs` and inspect the preview before timeline use.
- Do not create production abstract/UI/infographic B-roll as ad hoc static PNG/Pillow boards. Static PNGs are allowed only as tiny auxiliary assets or when the user explicitly requests a still.
- Reject boards that look like old infographics, test harnesses, template placeholders, generic cards, clipart layouts, repeated component layouts, or low-effort mock UI.

### Generated Visuals With z-image-turbo

Use `z-image-turbo` as a first-class source when real footage, screen capture, or stock video would be generic, misleading, unavailable, or visually weak. Generated stills are acceptable for photographic, cinematic, illustrative, metaphor, product-neutral mood scenes, and non-UI graphic inserts. For synthetic UI, checklist, timeline, comparison, process, map, logistics, cost/risk, and dashboard-style boards, consider `animated-broll-boards` when an animated board is the strongest visual choice.

Do not use generated images as a cheap replacement for missing required identity or factual assets. If a production brief requires the user's actual product, location, face, brand, app, or another real-world subject whose appearance is the point of the video, ask for those assets. Otherwise, generated visuals and local motion graphics are valid B-roll choices for abstract, conceptual, educational, or product-neutral segments.

Rules:

- Generate a plan with `scripts/z_image_plan.py` from `script.json` before running image generation.
- Save outputs under `<project-dir>\broll\generated\`.
- Record prompt, output path, segment id, acceptance status, and rejection reason in the project manifest.
- Pass the z-image plan into final `visual_qa.py` so timeline references to `broll/generated/` are checked against reviewed accepted outputs.
- Keep prompts vertical-safe: central subject, clean upper/middle negative space, no fake logos, no credentials, no private data, no implied real-brand UI unless explicitly requested.
- Review generated images before using them. Reject generic, distorted, illegible, branded, unsafe, or visually cheap outputs.
- Accepted generated stills can be referenced directly by the composer as `B-ROLL` or `TEXT` background media.
- When generated stills need motion in a reel, pre-render short motion clips from the accepted stills before timeline assembly, or use the composer `STILL_MOTION` primitive. Acceptable motion treatments include slow push-in, slow pull-back, subtle pan, swipe transition, parallax-style crop, or split-panel comparison. Motion must stay inside image bounds.
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
- Consider `animated-broll-boards` when an exact concept, fake app flow, neutral diagram, checklist, timeline, comparison, counter, process, map, logistics, or privacy-safe screen demonstration is strongest as an animated board.
- Use project-local HTML/mock UI outside `animated-broll-boards` only when the board skill cannot express the required custom scene.
- Use animated typography when the idea is short, punchy, and stronger as a kinetic text beat than as literal footage.
- Use split, stack, grid, and still-motion patterns when they make comparison, proof, examples, or rhythm stronger than a single fullscreen clip.

Prefer a deliberate mix of visual assets, textures, and shot types. Do not use one resolved `source_type` to satisfy resolved source diversity.

If the most literal asset choice is boring, choose a more cinematic, graphic, kinetic, or emotionally legible option. The goal is a finished social video, not merely a valid assembled timeline.

Local HTML/mock UI guardrails:

- Do not present local HTML as a real product or real site.
- Avoid real brands, real credentials, real user data, and implied vendor endorsement unless the user explicitly requested them.
- Prefer `animated-broll-boards` for production local HTML motion graphics. Handwritten one-off HTML is a fallback for custom scenes the board skill cannot express.
- Save local HTML/mock UI files inside the project directory, then record them with `playwright-broll-recorder` using a `file:///...` URL.
- Capture and inspect a validation screenshot before accepting the clip.
- Record the local HTML/mock UI fallback in `assembly_notes` or the asset manifest so the source is transparent.
- Local HTML/mock UI is allowed for precision, but it should be designed as polished motion graphics when it is visually prominent.

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
- record landscape webpage or stock footage when the shot is intended for `STACK_3` or when the source needs wide UI context

When source footage is landscape (16:9), the `cover` crop will center-crop horizontally to fill `1080x1920`. Keep this in mind:

- ensure key visual content is vertically centered in the source footage when possible
- prefer B-roll where the subject or action is in the center third of the frame
- for `STACK_3` segments, three landscape clips are scaled to `1080px` wide and stacked vertically without cropping; use this when center-crop would lose important content

Do not substitute vague B-roll. If a query cannot be satisfied from the available sources, flag the segment for manual asset selection.

## Timeline Assembly

Translate the scriptwriter output into `timeline.json` using the schema that matches the format mode, then call `moviepy-video-composer` with the matching `--format` value.

For modern reels, use [references/broll-section-library.md](references/broll-section-library.md) as the section-pattern library. Do not make any pattern or resolved `source_type` globally preferred. Choose by segment intent and record the selected pattern in `manifests\selected-visuals.json`. Before writing `timeline.json`, choose a deliberate composition pattern for each segment from the section library; do not collapse the reel into only fullscreen and PiP layouts unless that is explicitly the strongest edit plan.

If the user supplied a soundtrack, run `scripts/music_intake.py` and pass the ingested `source-assets\soundtrack.<ext>` file to the composer. Do not normalize or mix it in the orchestrator. Audio normalization, sidechain ducking, final mix safety, and `audio-mix-manifest.json` belong to the composer step.

## Final Visual QA

Final render existence, duration, and resolution are not enough. Before delivering the video, the agent must visually inspect the actual rendered result. For captioned reels, inspect `final_output_captioned.mp4`; inspect `final_output.mp4` only when captions are explicitly disabled.

Extract representative frames from the final output:

- first 2 seconds
- every major segment boundary or at least every 8-10 seconds
- every PIP segment
- every TEXT segment
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

- overlapping text, captions, cards, PiP, or UI elements
- word-level captions out of sync with narration or active-word highlighting that distracts from readability
- text too large for its container or clipped by the frame
- dense text that cannot be read at phone size
- PiP rendered as a tall rounded rectangle when it should be circular
- subject face cropped awkwardly in PiP or A-roll
- bland placeholder UI, low-effort cards, or obviously unfinished mockups
- poor contrast, muddy colors, or unreadable typography
- visual repetition that makes the reel feel static or boring
- real-brand or credential exposure that was not explicitly intended
- black/blank/error/loading frames
- low-effort generated stills, generic stock, placeholder-looking motion graphics, or any frame that looks like a test harness rather than a finished reel
- static PNG/Pillow UI boards used as production abstract/infographic B-roll without explicit user approval

If a frame fails, do not explain it away. Fix the visual cause and rerender. Record visual QA results in `manifests/visual-qa.json` with inspected frame paths, pass/fail status, and any rerender actions.

For animated boards and generated HTML/mock UI, inspect both the source validation screenshot and the final rendered frame where it appears. Passing the isolated source screenshot is not sufficient, because final overlays, TEXT entries, PIP, scaling, and timeline composition can introduce new failures.

### Landscape Timeline

Composer: `moviepy-video-composer --format landscape`

Use these mappings by default:

- `A_ROLL` -> full-screen synced straight-to-camera clip, rotating across selected front-facing plates when multiple usable plates exist
- `B_ROLL` -> full-screen B-roll clip
- `PIP` -> full-screen B-roll or screen capture background plus synced 3/4-profile overlay in the lower right, rotating across selected profile/three-quarter plates when multiple usable plates exist

- map `PUNCH_IN` to a shorter A-roll cut, an alternate synced A-roll variant, or a flagged fallback
- map `TEXT_GRAPHIC` to `TEXT` when a simple overlay is enough; otherwise use B-roll with assembly notes

### Vertical Timeline

Composer: `moviepy-video-composer --format vertical`

Use these mappings by default:

- `A_ROLL` -> full-screen synced straight-to-camera clip (portrait or center-cropped), rotating across selected front-facing plates when multiple usable plates exist
- `B_ROLL` -> full-screen B-roll clip (center-cropped to vertical)
- `PIP` -> full-screen background plus synced overlay at `("center", "bottom")`, scale `0.34`, rotating across selected profile/three-quarter plates when multiple usable plates exist
- `SPLIT_2` -> two-panel section for presenter/demo, before/after, this/that, myth/fact, or proof/context
- `STACK_2` -> two horizontal clips stacked vertically
- `STACK_3` -> three landscape clips stacked vertically (no cropping)
- `GRID_4` -> four-tile comparison/collage
- `STILL_MOTION` -> local/generated still with bounded virtual camera motion
- `TEXT` -> keyword or caption text overlay on a background clip

### Timeline Safety Fields

Use these composer controls consistently:

- `clip_start`: shared fallback source offset for simple entries
- `background_clip_start`: PIP/TEXT background offset
- `overlay_clip_start`: PIP presenter overlay offset
- `clip_start_top`, `clip_start_mid`, `clip_start_bot`: per-layer `STACK_3` offsets
- `clip_start_a`, `clip_start_b`: per-panel `SPLIT_2` offsets
- `clip_start_1`, `clip_start_2`, `clip_start_3`, `clip_start_4`: per-panel `GRID_4` offsets
- `split_axis`: `vertical` for left/right panels or `horizontal` for top/bottom panels
- `motion_type`: `push-in`, `pull-back`, `pan-left`, `pan-right`, `pan-up`, `pan-down`, `diagonal-drift`, or `swipe-in` for `STILL_MOTION`
- `loop_policy`: `loop` or `error`
- `background_loop_policy`, `overlay_loop_policy`: per-layer PIP loop controls

Default policies:

- A-roll presenter: `loop_policy: "error"`
- PIP presenter overlay: `overlay_loop_policy: "error"`
- B-roll background: `loop_policy: "loop"` only when repeated footage is acceptable
- TEXT background: `background_loop_policy: "loop"` only when the background can repeat without being obvious

Never allow presenter media to loop silently. If a visible presenter clip is shorter than the target segment, shorten the segment, choose another clip, regenerate the presenter media, or fail validation.

Vertical mode supports `TEXT` segments for on-screen keywords and captions:

```json
{
  "type": "TEXT",
  "background_path": "broll/B01.webm",
  "text": "KEYWORD",
  "text_color": "#fad617",
  "start_time": 0.0,
  "end_time": 3.0
}
```

Do not use `caption_text` for spoken short-form captions. Use `reel-captions` after base render to create word-level captions from the approved transcript. `caption_text` may still be used sparingly for non-spoken labels or temporary test renders, but production reels should reserve timeline text for intentional graphics.

Vertical mode supports `STACK_3` segments for showing three landscape clips simultaneously:

```json
{
  "type": "STACK_3",
  "clip_path_top": "broll/B01.webm",
  "clip_path_mid": "broll/B02.webm",
  "clip_path_bot": "broll/B03.webm",
  "clip_start": 0.0,
  "start_time": 5.0,
  "end_time": 10.0
}
```

Vertical mode also supports `STACK_2`, `SPLIT_2`, `GRID_4`, and `STILL_MOTION` for modern B-roll sections. Use these when the segment benefits from comparison, multiple examples, evidence boards, presenter/demo pairing, or subtle motion on stills.

Use [references/timeline-mapping.md](references/timeline-mapping.md) for the exact conversion rules per format mode.

## Shot Variety Rules

Avoid long static presenter runs.

When a direct zoom effect is not available in the current composer, create variety using:

- shorter A-roll segments
- more frequent cutaways to B-roll
- PIP sections over screen footage
- alternate full-screen and PiP presenter visibility

### Vertical Shot Variety

In vertical mode, also use these additional variety tools:

- interleave `A-ROLL` (full screen) with `STACK_3` to avoid monotony
- use `STACK_2`, `SPLIT_2`, `GRID_4`, and `STILL_MOTION` when they make the idea faster or more varied
- use `TEXT` segments to break up visual repetition with keyword hits
- keep individual segments short (3-8 seconds) to maintain mobile attention
- ensure `(end_time - start_time)` is strictly less than or equal to the source video duration for all clip-based segments to prevent awkward short-loop artifacts
- use `clip_start` to pick different fragments of long source videos rather than always starting from zero

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

For vertical mode, the 3/4-profile plate is optional. If it is missing, route presenter visibility through A-roll and B-roll only, skipping PiP segments.

If a step is partially available, continue as far as possible but state the exact blocker and the exact artifact that could not be produced.

## Resources

- Project layout and filenames: [references/project-layout.md](references/project-layout.md)
- B-roll section pattern library: [references/broll-section-library.md](references/broll-section-library.md)
- Presenter generation strategy: [references/presenter-strategy.md](references/presenter-strategy.md)
- Script-to-timeline conversion rules: [references/timeline-mapping.md](references/timeline-mapping.md)
- Short-form production practices: [references/short-form-practices.md](references/short-form-practices.md)
- Current local change notes: [references/changelog-2026-05-05.md](references/changelog-2026-05-05.md)
