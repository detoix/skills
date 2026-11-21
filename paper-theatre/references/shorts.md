# Vertical shorts

## Selection and layout

- Treat a short as its own edit and 9:16 stage, 1080×1920 at the film's frame rate. Choose a self-contained question, explanation and payoff; preserve the source's qualifications when shortening it.
- Recompose figures, maps, labels, title and stage decoration for portrait viewing: the picture fills the frame. A horizontal frame or a square card placed inside a vertical border is not an adaptation.
- Establish the subject or hook from the opening frame. Use readable burned-in captions and keep text and key details clear of the destination's interface; check its current layout rather than treating one safe-area percentage as universal.
- Carry the film's approved material treatment, typography, palette and musical character into the new composition. End with the agreed next action or related-film reference only where it fits the publication plan.

## Building

1. Name each short in `film.json` → `shorts`: `{"<name>": {"title": "…", "parts": [[line id, first word or null, last word or null], …], "mood": "<music mood>"}}`. Parts reuse the selected recordings of the approved film; a part may start later in its line or end at a word at a sentence boundary. New narration, if a short needs it, goes through the normal voice workflow with its own provenance.
2. `python tools/build_shorts.py [--only <name>]` checks every source take against `audio/manifest.json` and `audio/provenance.json`, cuts the parts from the levelled voice master, moves words aligned over silence to their onsets, and writes `film/short_<name>/` (timeline, voice, music in phrases stopping on a full bar, then the motif's ending under the closing card, effects, mix at -14 LUFS, provenance, recogniser check) and `out/short_<name>.<language>.srt`.
3. Compose each short in `film/shorts/shorts.js` (`createShort`, `FIGURES`, `soundCues` on the short's own timeline: every caption, anchor and cue comes from `film/short_<name>/timeline.json`), then rebuild the sound so the effects follow the picture.
4. Render with `node tools/render.mjs --page "short.html?name=<name>" --audio film/short_<name>/mix.wav --out out/short_<name>_v1.mp4`.

## Verification

- Check portrait dimensions, frame rate, stream duration, full decoding and loudness/true peak in the final encoded file.
- Inspect frames extracted from the finished short at the opening, crowded moments, caption changes, maps and ending. Check legibility and interface clearance at phone size, including the lowest and rightmost text.
- Read the recogniser check of the short (`film/short_<name>/asr.json`) and its provenance: which full-film version, timeline and selected audio it derives from. When a source correction changes an included fact, recording or title, review the affected short and its publication text together.
