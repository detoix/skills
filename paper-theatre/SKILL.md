---
name: paper-theatre
description: Make an explainer film in the paper-theatre style — hand-cut cardboard cut-outs animated in Canvas 2D code, narration through the tts skill, music from a generated library — from topic to a publish-ready video, on any subject, in any narration language and length. Use when the user asks for a film, episode or explainer "w stylu teatrzyku z kartonu" / "paper theatre", or to continue, fix or re-render such a project.
---

# Paper theatre

A film is one pure function of time: cardboard figures, paper strips and hanging cards on a painted stage, every move hung off the narrator's words. This skill owns the convention, the engine and the production tools; the `tts` skill owns the voice and its library, and the `yue-music` skill makes what the music library lacks.

## Settle first

Ask, or take from the request, before anything is written:

- topic and the viewer it is for
- narration language (supported by the `tts` skill; captions use the same)
- target length; scenes follow from it (about one scene per minute for long-form, fewer and shorter for short pieces)
- tone and anything the film must or must not say
- the channel's ask to the viewer (like and subscribe): its usual wording and place; by default one line at the close of the chapter about two thirds in (script reference)
- a subject-specific visual and musical direction: palette, typography, ornament, transitions, instrumentation and the role of music; adapt the template to this direction before the pilot

The full film is 16:9 (1920×1080, 30 fps). Vertical shorts, when the request or the project's notes call for them, are built from the approved film's narration (`tools/build_shorts.py`) on their own 9:16 stage: [references/shorts.md](references/shorts.md).

## Workflow

At stages marked as a gate, show the result and wait for the user's word. New library samples also need listening approval. Log every activity with `tools/clock.py` (it writes `timings.md`).

1. **Research.** Find the viewer loop — the open question that keeps the viewer to the end, "Viewer keeps watching to find out ___". Collect facts with sources; prefer concrete objects, people and finds over generalities. Keep a claim register with exact source locations, uncertainty and the corresponding narration and picture; resolve material issues before producing voice and scenes.
2. **Project.** `scripts/new_film.sh <dir> "<Title>" <slug> <language> "<palette>"` copies `template/` and fills in the names. The palette describes the subject's own visual world. Adapt the supplied visual defaults to the agreed direction; the template's decoration is not a requirement.
3. **Script → gate.** Write `script.md` following [references/script.md](references/script.md), fact-check it, then `python3 tools/script.py` → `audio/narration.json`.
4. **Music preflight.** Plan the film's music moods from the script and check them against the channel's music library ([references/audio.md](references/audio.md)). Only what is missing gets made, with the `yue-music` skill; the user approves it by ear and it stays in the library for later films. When nothing is missing, nothing is generated. This check runs independently of the voice plan and takes.
5. **Voice → gate.** Delegate the voice preflight and narration to the `tts` skill, passing the script, voice library and output locations. It reuses approved moods and makes a mood only when it is missing; the user approves a new one by ear. Check the takes with `tools/check_takes.py` as in [references/audio.md](references/audio.md). This check runs independently of music; `tts` owns its library format, model, settings and execution.
6. **Cut-outs.** References for everything real (`research/ref/`, `prompts/refs.json`) → imagegen prompts (`prompts/_style.txt` + one file per set, referenced assets with their reference) → `raw/` → contact sheets against the references (`tools/raw_sheet.py`) → `tools/prep_figures.py` → `film/fig/`. See [references/visuals.md](references/visuals.md).
7. **Pilot → gate.** Scene 1 with sound (`tools/build_audio.py --scenes 1`), rendered (`tools/render.mjs --to <end>`). Typography, palette, transitions in picture and sound, instrumentation, pace and the balance of voice, bed and foreground music get approved here, before the other scenes.
8. **All scenes.** `film/scenes/sN.js`, control stills at the busy moments, full sound, the layout check, full render. See [references/render.md](references/render.md).
9. **Review → fixes → final.** The user watches and lists problems by time. Fix picture in the scenes and voice with retakes, rebuild, re-check, deliver; a picture fix renders again only the seconds it touches (`tools/render.mjs --patch`).

## Contract

A finished film delivers, in `out/`:

- `<slug>_vN.mp4` — 1920×1080, 30 fps, H.264 + AAC, about -14 LUFS, true peak under -1 dBTP (measured on the MP4)
- `<slug>.<language>.srt` — subtitles from the narration's word timings (`tools/srt.py`)
- `youtube.txt` — title, description and one chapter per scene (`tools/chapters.py`)
- `thumb.jpg` — one 1280×720 thumbnail (`film/thumb.html`); no A/B variants
- the project `README.md` lists every version and what changed

Rules:

- The script's written text is what captions show. The spoken form differs only where pronunciation needs it, through `film.json` → `spoken` (numbers as words, phonetic spellings); never rewrite a sentence for the voice.
- Every on-screen time comes from the timeline (`anchorsOf(tl)`: line starts and word times), never a hand-typed second.
- Picture and sound share the same anchors: each scene exports `soundCues(tl)` for the actions it shows.
- One TTS job at a time with all ready lines in one batch; regenerate only lines the user flagged or the checks failed, and say beforehand what will run, for how long, and whether it is read-only.
- Record the actual selected audio file, SHA-256, spoken text, direction, source and known generation parameters per line in the audio manifest. Match provenance to the current file hash; unknown values stay unknown. Never infer a seed from line order.
- Keep the recogniser's literal text separate from the expected text and weigh every word it heard differently in the context of its line: a correct reading can come back garbled, a one-letter substitution can be a real error. Recognition guides listening; reports point to the exact version and time in the full film.
- Measure and look before showing: levels for audio, stills for picture. Do not send what has not been checked.

## Style

- Cut-outs: thick kraft cardboard, hand-cut uneven edge with the brown rim showing, matte gouache in the film's palette, glued paper details, black marker lines, chunky and friendly, people about five heads tall, flat and straight-on, transparent background (`prompts/_style.txt`).
- Stage: painted backdrops and paper bands, the apron at the bottom, figures moving on twos and boiling 7.5 times a second, cards on strings, varied transitions, paper strips and gestures from the film's own world ([references/visuals.md](references/visuals.md)), sparkle and stamp accents, a timeline rail when the story jumps in time (`film/config.js` → `RAIL_YEARS`).
- Labels name what the narration names, the moment it is said; colours by kind (highlight, name, legend, number) from `film/config.js` → `WORDS`.
- Real people, places, objects and species keep the identifying features of their references through stylisation, and settings show the period of the scene; check both against the references before animation.
- Maps and diagrams are facts: sourced geography in one projection for features and pins (`film/geo.js` on Natural Earth, lines from published maps via `tools/georef.py`), plausible routes and visible uncertainty (visuals reference).

## Before showing anything

Revise and check again when:

- the opening does not set up the viewer loop within the first ~30 seconds
- a long film lacks its one ask to like and subscribe, asks more than once, or asks in the opening
- a fact, date or number has no source, a popular claim is repeated without its correction, or a reconstruction or uncertain interpretation is presented as an established fact
- the script reads like generic AI prose, triple-balanced lists or lecture transitions
- a scene runs more than ~15 seconds without a new picture beat (figure, card, transition, label), or consecutive cuts share a transition or its sound
- a documented person, place or object, a label, pin or route disagrees with its source, the narration or the map, or a setting shows another time than the scene
- a take's first word, a name, or a word the recogniser heard differently sounds wrong in its line; words that also exist in English and foreign names go through `film.json` → `spoken` with a phonetic spelling
- the voice sits less than ~17 dB over the music or ~15 dB over effects, or a chapter change or the end screen sounds wrong in context

The music tools keep the bed under the voice, with one mood per chapter and modules joined on bar lines. Foreground music marks the title, chapter changes and the end screen. See the audio reference and look up professional practice before changing the mix.
