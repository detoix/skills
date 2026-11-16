# Narration, music, mix

## Narration (`tts` skill)

1. Point `film.json` → `voice_library` at the channel's voice library; `voice_moods` names a mood for lines whose direction does not settle it.
2. After `python3 tools/script.py`, ask the `tts` skill to plan `audio/narration.json` against the library. That only reads the library. For a mood it reports missing, it makes candidates, the user chooses by ear and the choice joins the library for later films. A channel with no library starts one the same way, with a reference the user picked by ear.
3. Have the `tts` skill narrate `audio/narration.json` into `audio/takes/`, with provenance in `audio/provenance.json`, in one run for the whole film. Wrap long jobs in `tools/clock.py run`. Pass these inputs and outputs to the skill; read its instructions for invocation.
4. Check every take with `tools/check_takes.py`: word by word against the spoken text, report in `audio/check.json`. Listen to the openings and to every flagged line. Use the number-check procedure below for numerical expressions.

## Retakes

- Have the `tts` skill narrate only the lines the user flagged into `audio/retakes_X`, in one run. `tools/check_takes.py --takes audio/retakes_X --against audio/takes` checks them next to the takes they would replace and writes `audio/retakes_X/comparison.wav` (old, then new, per line) for the user to hear.
- Copy accepted takes into `audio/takes/output_NNN.wav`, keeping the old ones as `output_NNN_vK.wav`, record the choice in a JSON next to them.

## Timeline and mix (`tools/build_audio.py`)

- Run the project's audio tools in a Python environment with `numpy`, `soundfile`, `scipy` and NVIDIA NeMo (`nemo_toolkit[asr]` with PyTorch; a GPU is used when present), with FFmpeg and Node on `PATH`. The first recognition downloads the model from Hugging Face. This environment belongs to the film tools.
- Recognition (`tools/asr.py`, Parakeet TDT 0.6B v3) is cached per take in `audio/asr_cache/`: an entry is keyed by the file's SHA-256, the model settings, the film language and the tool version, so a retake or a changed setting is recognised again and nothing else is. Word times are stored against the raw file, so trim and pause settings can change without new recognition. The take check fills the cache and the timing reads it.
- Trims and levels every take, maps its cached word times through the trim and pause edits (a take not yet recognised is recognised here), lays lines out with `film.json` → `gaps` (pause before a line; 2.5–3 s breaths after strong lines), scene gaps, the title tail and the 14 s end screen → `film/timeline.json`, `film/audio/vo.wav`.
- Asks `film/film.js` for the sound cues, synthesises the effects, lays out the music from the library (`tools/music.py`), mixes to -14 LUFS with the true peak held at -2 dBTP → `film/audio/mix.wav` (+ music stems).
- Missing takes become provisional silence of the expected length, so scenes can be built before the voice exists.
- `--reuse` keeps the timeline and voice and only rebuilds effects and music.

## Number and pronunciation checks

- Keep three distinct records: the written caption text, the intended spoken text and the literal free ASR hypothesis. Never substitute expected words for the recognised result or convert recognised number words back to digits in a pronunciation report.
- For numerical passages, use free transcription without the expected text as a prompt. The recogniser writes numbers in digits: the check matches them to their caption span and flags them, because digits do not show whether the spoken form and its inflection are right; listen to every flagged number. Preserve omissions, foreign words and Roman numerals exactly as returned. A spelling match is not proof of correct pronunciation.
- The word differences (substitutions, omissions, insertions, the first word) choose what to hear first; they are not a pronunciation verdict. Compare takes of one line only through the same tool and settings.
- Report the intended phrase, literal hypothesis, missing words and flagged probabilities with the version and timestamps of the full film. Account for source trimming and line placement; provide surrounding context in the complete mix rather than only isolated take times.
- Inspect acoustic onsets after pauses. Word alignment and interpolated timings can start a caption or action inside silence; correct and review the affected anchors before deriving captions and scene cues.
- Confirm suspected errors by listening. Keep the report tied to the selected audio hashes and rebuild its times after an edit changes the timeline.

## Selected-take provenance

- After selecting audio, write `audio/provenance.json` with a `takes` object keyed by stable line ID. Each record identifies the selected file with `sha256`, the spoken `text`, the `direction`, its `source`, and a `generation` object containing the actual known model, reference identity, parameters and seed. Record trimming or other edits connecting the source to the selected file.
- Identify reference audio and raw source recordings by hash as well as path. Preserve enough information to trace a processed take back to its source; a numbered filename alone is not identity.
- Unknown generation values remain null or absent. Do not reconstruct parameters or seeds from defaults, filenames or current line numbers.
- `tools/build_audio.py` records the current selected-file hash, raw duration and trim interval in `audio/manifest.json`. It attaches a generation record only when its hash, spoken text and direction match the current selection; otherwise it records the provenance as unverified with unknown generation settings.
- Refresh provenance after a replacement or edit. Use stable line IDs to select source audio for derived exports, checking hashes against the current manifest before reuse.

## Music library

All music comes from the channel's library of generated modules; nothing is synthesised for a film. `film.json` → `music.package` points to the library root, where each palette holds moods, the motif and chapter gestures under the names in `tools/music.py` → `Pack.path`. Variants play only for moods in `music.variants_safe`.

Preflight, right after the script is approved. It reads the music plan and library independently of the voice preflight and generated takes. Something is made only when it is missing, and it stays in the library for later films.

1. Plan one palette (`music.palette`), one mood per chapter (`music.plan`: chapter number → mood), the chapter gestures (`music.transitions`) and the breaths (`music.breaths`). The bed changes mood only at a chapter change, under the chapter card and its gesture: pick the mood that carries the whole chapter; neighbouring chapters may share one.
2. `python3 tools/music.py` lists what the library lacks and which loops may vanish under the voice.
3. Fill the gaps from the library first: modules share key and tempo, so a mood can come from another palette (`music.borrow`: mood → palette) and a brighter variant can come more often (`music.variant_every`: mood → every Nth phrase). Only what the library does not have is generated, with the `yue-music` skill, and cut into modules as the library's README describes.
4. Listen: a new module, or one with a vocal-detector warning, goes in only after the user has heard it, and a loop is judged under narration. Equal loudness does not mean audible: a loop with nearly all its energy under 400 Hz measures the same as the others and vanishes under a male voice.

## Music rules

- `tools/music.py` keeps the continuous bed and the foreground cues (signal, chapter gestures, breaths, end screen) on separate buses and exports both stems for inspection.
- The bed stays about 18 dB under the voice during speech (`music.voice_over_bed_db`) and restrained in pauses. Lower it further while a scored break has its own foreground music; lack of narration must not raise the whole bed.
- Foreground music plays at its intended level during a clear musical break and ducks whenever narration overlaps it. Actual speech wins over a nominal break window, including cue tails crossing into the next line.
- Use passage-level ducking within speech: bridge short pauses and avoid reacting to individual words. Use intentional music-break windows from the timeline to fit release and attack inside silence instead of holding the foreground down throughout a transition.
- The template accepts `music_breaks` on the timeline as absolute start/end windows. `tools/build_audio.py` derives scored breaks from the arranged line gaps. If the edit defines different breaks, write their exact windows to the timeline. Overlapping narration still overrides them.
- The end screen is not a break: the score plays it out (the motif right after the last line, then its ending) with the bed back at its own level, and fades only over the last seconds (`music.py` → `END_SCREEN`, `END_FADE`).
- Choose the additional bed attenuation and fade lengths for the approved score in `film.json` → `music_mix` (`bed_break_db`, `break_fade_seconds`). They are mix settings, not universal mastering targets. The bed remains at or below its restrained level.
- Keep melody out of short gaps inside a spoken passage. Place the motif and gestures only where the edit leaves room, and choose palette and moods for the subject and approved pilot.

## Level checks before sending anything

- `tools/voice_snr.py film/audio/mix.wav`: voice over music 18–20 dB, over effects about 18 dB or more, overall 17–20 dB while speaking.
- Loudness and true peak of the encoded file, not the WAV: `ffmpeg -i out/<file>.mp4 -af ebur128=peak=true -f null -` → about -14 LUFS, true peak under -1 dBTP. AAC can lift an inter-sample peak by about 3 dB over the mix, which is why mastering holds the mix at -2 dBTP.
- Check every scored transition and the end screen, including entry, silent centre and return to narration; the music should carry the end screen to its last seconds. Measure the bed and foreground separately, listen in context and recheck the final encoded mix; a global loudness value cannot establish the correct balance between buses.
