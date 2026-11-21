# {{TITLE}}

Paper-theatre film (skill `paper-theatre`): hand-cut cardboard figures drawn in code (Canvas 2D), narration through the `tts` skill.

## Files

- `script.md` — narration with delivery instructions and the picture, scene by scene
- `film.json` — the film's settings for the tools (title, language, voice, spoken forms, music, figures)
- `film/` — the film: `engine.js`, `stage.js`, `kit.js` (engine), `config.js` (label colours, rail years, map paper), `film.js` (scenes in order), `scenes/sN.js`, `geo.js` + `geodata.js` (maps from Natural Earth, `tools/geodata.py`), `thumb.html` (the thumbnail)
- `prompts/` — imagegen prompts (`_style.txt` + sets; `refs.json` maps cut-outs of real subjects to their references in `research/ref/`), `raw/` — generated PNGs, `film/fig/` — trimmed cut-outs
- `research/` — sources, the claim register, references for cut-outs, `*.georef.json` lines read off published maps (`tools/georef.py`)
- `audio/` — `narration.json`, `takes/`; `provenance.json` records selected-file hashes and actual generation settings, `manifest.json` records the current arranged takes; `asr_cache/` holds the recognition of every take by file hash (`tools/asr.py`), shared by the take check (`tools/check_takes.py` → `check.json`) and the word timings (`tools/build_audio.py`)
- requested vertical shorts use separate portrait scenes and a derived timeline; retain the approved audio identities and check their hashes before reuse
- `timings.md` — timing of every activity (`tools/clock.py`)
- `out/` — video versions, subtitles, description with chapters, control stills

## Versions
