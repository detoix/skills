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

## Sub-Workflow Skills

Use these skills as the default sub-workflow:

- `youtube-scriptwriter` for the structured script
- `tts` for chunked voice generation and cloning
- `latentsync` for presenter lip-sync
- `codeformer-postprocess` for optional presenter face restoration after lip-sync
- `playwright-broll-recorder` for webpage and screen-record B-roll
- `pexels-stock-downloader` for non-web stock B-roll
- `moviepy-video-composer` for final assembly in landscape and vertical modes

Only do work manually when a required sub-skill is missing or clearly cannot satisfy the current step.

Build a YouTube video as a project, not as a loose set of clips. Keep the whole job in one working directory with deterministic file names.

## Agent Intake Checks

Before generating assets, the agent verifies the runtime and required inputs directly:

- Real production runs must use user-provided project assets. Do not treat `C:\Users\kdeptula\Videos\avatar` as a production library; it is only a local fixture set for testing and regression checks.
- If the user has not provided production assets, stop and ask for the asset root, presenter plates, voice sample, and exact voice-sample transcript before promising a production reel.
- `youtube-scriptwriter`, `tts`, `latentsync`, `playwright-broll-recorder`, and `moviepy-video-composer` are available.
- `codeformer-postprocess` is available if presenter restoration is expected.
- `pexels-stock-downloader` is available and `PEXELS_API_KEY` is configured before promising non-web stock footage.
- The known FFmpeg directory is on `PATH` before `latentsync` or `codeformer-postprocess`:
  ```powershell
  $env:PATH = "$env:USERPROFILE\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin;$env:PATH"
  ```
- The local TTS environment exists at `%USERPROFILE%\Downloads\speech-gen\venv`.
- The composer Python environment can import `moviepy`.
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
   - For fixture tests only, mark sample assets explicitly:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\asset_inventory.py `
       --asset-root C:\Users\kdeptula\Videos\avatar `
       --fixture-label avatar-sample-fixture `
       --output C:\Users\kdeptula\Videos\ai-videos\avatar-intake\manifests\assets-manifest.json
     ```
   - Review the manifest before selecting presenter plates, voice samples, stills, overlays, music, B-roll candidates, or previous outputs for comparison.
3. Call `youtube-scriptwriter` and use its structured output as the planning source of truth.
4. Validate the script JSON:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --script <project-dir>\script.json `
     --format <landscape-or-vertical> `
     --mode script
   ```
   Validate asset intake before production work. This must fail for sample fixtures unless this is explicitly a test run:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --asset-manifest <project-dir>\manifests\assets-manifest.json `
     --format <landscape-or-vertical> `
     --mode assets
   ```
   For fixture-only regression tests, add `--allow-sample-fixture` and label the report as a test artifact.
5. Call `tts` to generate chunked cloned speech from the scriptwriter payload, then verify every chunk is target-only. Trim only if a generated file actually contains a prompt/sample prefix.
6. Validate or manually review all clean TTS chunks before using them for lip-sync or final narration assembly.
7. Call `latentsync` to build synced presenter clips from the silent motion plates and clean chunk audio.
8. When presenter clips look soft, compressed, or artifacted after lip-sync, call `codeformer-postprocess` on the synced presenter outputs before timeline assembly.
9. Call `playwright-broll-recorder` for webpage B-roll and call `pexels-stock-downloader` when non-web stock footage is needed.
   - When the script needs abstract, synthetic, product-neutral, conceptual, or visually controlled B-roll, create a `z-image-turbo` plan:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\z_image_plan.py `
       --project-dir <project-dir> `
       --script <project-dir>\script.json
     ```
   - Generate only the selected images with `z-image-turbo`, review them, record accepted/rejected outputs in the asset manifest, then use accepted stills as timeline `B-ROLL`, `TEXT` backgrounds, or generated visual inserts.
   - Validate the generated-image plan before using outputs in the timeline:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
       --project-dir <project-dir> `
       --z-image-plan <project-dir>\manifests\z-image-plan.json `
       --mode assets `
       --require-z-image-review
     ```
10. Build `timeline.json` using the schema matching the format mode.
11. Validate the timeline and final audio before composition:
   ```powershell
   python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
     --project-dir <project-dir> `
     --timeline <project-dir>\timeline.json `
     --audio <project-dir>\final_audio.wav `
     --mode timeline
   ```
12. Call `moviepy-video-composer` with the matching `--format` value.
13. Run final visual QA on the rendered video by extracting representative frames across the timeline and inspecting them. If any frame fails the visual acceptance criteria, revise assets, typography, PiP crop/shape, layout, or timeline and rerender.
   ```powershell
    python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\visual_qa.py `
     --project-dir <project-dir> `
     --video <project-dir>\final_output.mp4 `
     --timeline <project-dir>\timeline.json `
     --status needs_review
   ```
   - The helper cannot mark final success by itself. A final pass requires human/aesthetic review with concrete notes:
     ```powershell
     python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\visual_qa.py `
       --project-dir <project-dir> `
       --video <project-dir>\final_output.mp4 `
       --timeline <project-dir>\timeline.json `
       --format vertical `
       --min-duration 60 `
       --max-duration 90 `
       --z-image-plan <project-dir>\manifests\z-image-plan.json `
       --human-aesthetic-pass `
       --aesthetic-notes "Specific notes covering hook, safe zones, caption readability, visual variety, generated visuals, presenter/PiP quality, and rejected frames." `
       --status pass
     ```
14. Report any blockers immediately if a required runtime tool or asset is missing.

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

Interview for production assets whenever they are missing. The required assets depend on the format mode:

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

Prefer a varied usable set over the minimum front/profile pair. For reels and shorts, rotate across available front/profile takes to avoid repeated motion and framing unless continuity is more important than variety.

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
- source mix
- segment-level visual source choice
- why each source type was chosen
- known tradeoffs or fallback risks

The agent may freely combine:

- real webpage, app, documentation, or article captures
- stock footage
- generated bitmap visuals or generated video-like assets
- project-local HTML/mock UI
- animated typography
- simple motion graphics
- screenshots
- avatar-only sections
- screen recordings
- composited layouts

### Generated Visuals With z-image-turbo

Use `z-image-turbo` as a first-class source when real footage, screen capture, or stock video would be generic, misleading, unavailable, or visually weak. Generated stills are acceptable for abstract explainers, metaphor shots, privacy-safe synthetic UI backgrounds, product-neutral mood scenes, and graphic inserts.

Do not use generated images as a cheap replacement for missing user assets. If a production brief requires the user's product, location, face, brand, or app, ask for those assets.

Rules:

- Generate a plan with `scripts/z_image_plan.py` from `script.json` before running image generation.
- Save outputs under `<project-dir>\broll\generated\`.
- Record prompt, output path, segment id, acceptance status, and rejection reason in the project manifest.
- Pass the z-image plan into final `visual_qa.py` so timeline references to `broll/generated/` are checked against reviewed accepted outputs.
- Keep prompts vertical-safe: central subject, clean upper/middle negative space, no fake logos, no credentials, no private data, no implied real-brand UI unless explicitly requested.
- Review generated images before using them. Reject generic, distorted, illegible, branded, unsafe, or visually cheap outputs.
- Accepted generated stills can be referenced directly by the composer as `B-ROLL` or `TEXT` background media.

Choose the source type per segment using these criteria:

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
- Use generated visuals when the topic is abstract and real footage would be dull, generic, or unavailable.
- Use project-local HTML/mock UI when an exact concept, fake app flow, neutral diagram, or privacy-safe screen demonstration is needed.
- Use animated typography when the idea is short, punchy, and stronger as a kinetic text beat than as literal footage.

For videos longer than 45 seconds, avoid relying on one visual source type unless it is clearly the strongest creative choice. Prefer a deliberate mix of sources, textures, and shot types.

If the most literal asset choice is boring, choose a more cinematic, graphic, kinetic, or emotionally legible option. The goal is a finished social video, not merely a valid assembled timeline.

Local HTML/mock UI guardrails:

- Do not present local HTML as a real product or real site.
- Avoid real brands, real credentials, real user data, and implied vendor endorsement unless the user explicitly requested them.
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

If the user supplied a soundtrack, keep it as a project asset and pass it to the composer as optional background music. Do not try to normalize or mix it in the orchestrator. Audio normalization, sidechain ducking, and final mix safety belong to the composer step.

## Final Visual QA

Final render existence, duration, and resolution are not enough. Before delivering `final_output.mp4`, the agent must visually inspect the actual rendered result.

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
  --video <project-dir>\final_output.mp4 `
  --timeline <project-dir>\timeline.json `
  --status needs_review
```

Example extraction pattern:

```powershell
$ffmpeg = "$env:USERPROFILE\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
New-Item -ItemType Directory -Force "$projectDir\qa\final-frames" | Out-Null
& $ffmpeg -y -ss 00:00:02 -i "$projectDir\final_output.mp4" -frames:v 1 "$projectDir\qa\final-frames\frame_002s.png"
& $ffmpeg -y -ss 00:00:10 -i "$projectDir\final_output.mp4" -frames:v 1 "$projectDir\qa\final-frames\frame_010s.png"
```

Use enough timestamps to cover the whole timeline. Do not inspect only one preview frame.

Automated structural checks cannot mark a reel as production-ready. A final pass requires explicit human/aesthetic review notes. If a render looks generic, cheap, template-like, visually empty, or off-brand, mark it failed even when duration, resolution, and blank-frame checks pass.

Use [references/professional-qa-rubric.md](references/professional-qa-rubric.md) before setting `--human-aesthetic-pass`.

Reject and rerender when any frame shows:

- overlapping text, captions, cards, PiP, or UI elements
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

If a frame fails, do not explain it away. Fix the visual cause and rerender. Record visual QA results in `manifests/visual-qa.json` with inspected frame paths, pass/fail status, and any rerender actions.

For generated HTML/mock UI, inspect both the source validation screenshot and the final rendered frame where it appears. Passing the isolated source screenshot is not sufficient, because final overlays, TEXT entries, PIP, scaling, and timeline composition can introduce new failures.

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
- `STACK_3` -> three landscape clips stacked vertically (no cropping)
- `TEXT` -> keyword or caption text overlay on a background clip

### Timeline Safety Fields

Use these composer controls consistently:

- `clip_start`: shared fallback source offset for simple entries
- `background_clip_start`: PIP/TEXT background offset
- `overlay_clip_start`: PIP presenter overlay offset
- `clip_start_top`, `clip_start_mid`, `clip_start_bot`: per-layer `STACK_3` offsets
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

Any timeline entry may also include `caption_text` for burned-in short-form captions. Keep the copy short, high-contrast, and phone-readable. In vertical PiP sections, default captions to `caption_position: "top"` so they do not collide with the circular presenter bubble or platform UI. If the checked B-roll frame already has important top text, either omit the redundant caption or set `caption_y` to a visually inspected non-overlapping band.

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
- Presenter generation strategy: [references/presenter-strategy.md](references/presenter-strategy.md)
- Script-to-timeline conversion rules: [references/timeline-mapping.md](references/timeline-mapping.md)
- Short-form production practices: [references/short-form-practices.md](references/short-form-practices.md)
- Current local change notes: [references/changelog-2026-05-05.md](references/changelog-2026-05-05.md)
