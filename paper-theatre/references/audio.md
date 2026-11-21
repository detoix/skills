# Narration, music, mix

## Narration (`tts` skill)

1. Point `film.json` → `voice_library` at the channel's voice library; `voice_moods` names a mood for lines whose direction does not settle it.
2. After `python3 tools/script.py`, ask the `tts` skill to plan `audio/narration.json` against the library. That only reads the library. For a mood it reports missing, it makes candidates, the user chooses by ear and the choice joins the library for later films. A channel with no library starts one the same way, with a reference the user picked by ear.
3. Have the `tts` skill narrate `audio/narration.json` into `audio/takes/`, with provenance in `audio/provenance.json`, in one run for the whole film. Lines whose accent the model easily gets wrong — a negation with a short verb ending a sentence, a contrast, a foreign name, the channel's name — get 3–4 variants in the same run. Wrap long jobs in `tools/clock.py run`. Pass these inputs and outputs to the skill; read its instructions for invocation.
4. Check every take with `tools/check_takes.py`: word by word against the spoken text, report in `audio/check.json`, read as below. Listen to the openings and to every flagged line. The user picks each risky line's variant by ear from one file (the variants in order, numbered by short beeps) before the scenes are built; no measurement here settles an accent.

## Retakes

- Have the `tts` skill narrate only the lines the user flagged into `audio/retakes_X`, in one run. `tools/check_takes.py --takes audio/retakes_X --against audio/takes` checks them next to the takes they would replace and writes `audio/retakes_X/comparison.wav` (old, then new, per line) for the user to hear.
- Copy accepted takes into `audio/takes/output_NNN.wav`, keeping the old ones as `output_NNN_vK.wav`, record the choice in a JSON next to them.

## Timeline and mix (`tools/build_audio.py`)

- Run the project's audio tools in a Python environment with `numpy`, `soundfile`, `scipy` and `transcribe-cpp` (transcribe.cpp with its native library; Vulkan is used when a GPU is present), with FFmpeg and Node on `PATH`. The recogniser is the same model file Superwhisper uses for offline dictation, `parakeet-tdt-0.6b-v3-Q4_K_M.gguf`: `superwhisper models download transcription` puts it in `~/.local/share/superwhisper/models`; `film.json` → `asr.model` or `$PARAKEET_GGUF` points elsewhere. This environment belongs to the film tools.
- Recognition (`tools/asr.py`, Parakeet TDT 0.6B v3) is cached per take in `audio/asr_cache/`: an entry is keyed by the file's SHA-256, the model file's SHA-256 and settings, the film language and the tool version, so a retake or a changed setting is recognised again and nothing else is. Word times are stored against the raw file, so trim and pause settings can change without new recognition. The take check fills the cache and the timing reads it.
- Trims and levels every take, maps its cached word times through the trim and pause edits (a take not yet recognised is recognised here), lays lines out with `film.json` → `gaps` (pause before a line), scene gaps, the title tail and the 14 s end screen → `film/timeline.json`, `film/audio/vo.wav`.
- Asks `film/film.js` for the sound cues, synthesises the effects, lays out the music from the library (`tools/music.py`), mixes to -14 LUFS with the true peak held at -2 dBTP → `film/audio/mix.wav` (+ music stems).
- Missing takes become provisional silence of the expected length, so scenes can be built before the voice exists.
- `--reuse` keeps the timeline and voice and only rebuilds effects and music.

## Reading the check

- `audio/check.json` keeps three records per line: the caption text, the spoken text and the literal hypothesis of free transcription (no expected text as a prompt). Never replace the hypothesis with expected words.
- Weigh every word difference (substitution, omission, insertion, the first word) in the context of its line: a rare name or a split word can come back garbled from a correct reading, and a one-letter substitution can be a real mispronunciation. Neither the overall error rate nor a spelling match is a verdict; listening is. Numbers come back as digits, so every number is heard.
- Report what to hear with the version and time in the full film, tied to the selected audio hashes; rebuild the times after an edit changes the timeline.
- Alignment can start a word inside silence after a pause: check those onsets before deriving captions and scene cues.

## Selected-take provenance

- After selecting audio, write `audio/provenance.json` with a `takes` object keyed by stable line ID. Each record identifies the selected file with `sha256`, the spoken `text`, the `direction`, its `source`, and a `generation` object containing the actual known model, reference identity, parameters and seed. Record trimming or other edits connecting the source to the selected file.
- Identify reference audio and raw source recordings by hash as well as path. Preserve enough information to trace a processed take back to its source; a numbered filename alone is not identity.
- Unknown generation values remain null or absent. Do not reconstruct parameters or seeds from defaults, filenames or current line numbers.
- `tools/build_audio.py` records the current selected-file hash, raw duration and trim interval in `audio/manifest.json`. It attaches a generation record only when its hash, spoken text and direction match the current selection; otherwise it records the provenance as unverified with unknown generation settings.
- Refresh provenance after a replacement or edit. Use stable line IDs to select source audio for derived exports, checking hashes against the current manifest before reuse.

## Music library

All music comes from the channel's library of generated modules; nothing is synthesised for a film. `film.json` → `music.package` points to the library root, where each palette holds moods, the motif and chapter gestures under the names in `tools/music.py` → `Pack.path`. Variants play only for moods in `music.variants_safe`.

Preflight, right after the script is approved. It reads the music plan and library independently of the voice preflight and generated takes. Something is made only when it is missing, and it stays in the library for later films.

1. Plan one palette (`music.palette`), one mood per chapter (`music.plan`: chapter number → mood), and the chapter gestures (`music.transitions`). The bed changes mood only at a chapter change, under the chapter card and its gesture: pick the mood that carries the whole chapter; neighbouring chapters may share one.
2. `python3 tools/music.py` lists what the library lacks and which loops may vanish under the voice.
3. Fill the gaps from the library first: modules share key and tempo, so a mood can come from another palette (`music.borrow`: mood → palette) and a brighter variant can come more often (`music.variant_every`: mood → every Nth phrase). Only what the library does not have is generated, with the `yue-music` skill, and cut into modules as the library's README describes.
4. Listen: a new module, or one with a vocal-detector warning, goes in only after the user has heard it, and a loop is judged under narration. Equal loudness does not mean audible: a loop with nearly all its energy under 400 Hz measures the same as the others and vanishes under a male voice.

## How the score is laid

`tools/music.py` lays two buses from the library and exports both stems:

- **Bed.** One mood per chapter, in the library's four-bar loop and variant phrases joined at bar lines. At the end of a chapter the bed plays as many full bars as fit and stops on a bar line: it never starts a bar it cannot finish, and it has no ending of its own, because the transition closes the chapter. Within each chapter the bed continues through pauses at a restrained level. Its level follows the voice (`music.voice_over_bed_db`, passage by passage, short pauses bridged) and is lower at chapter transitions.
- **Foreground.** The signal after the title, a gesture at every chapter change, and the end screen played out to the film's last seconds. It plays at its own level in silence and yields to actual speech.
- **The agent decides** the palette, the mood of each chapter, the gestures (`music.transitions`, no two alike in a row), and the mix settings (`music_mix`: `bed_break_db`, `break_fade_seconds`). The timeline determines the windows for transitions and the end screen.

## Level checks before sending anything

- `tools/voice_snr.py film/audio/mix.wav`: voice over music 18–20 dB, over effects about 18 dB or more, overall 17–20 dB while speaking.
- Loudness and true peak of the encoded file, not the WAV: `ffmpeg -i out/<file>.mp4 -af ebur128=peak=true -f null -` → about -14 LUFS, true peak under -1 dBTP. AAC can lift an inter-sample peak by about 3 dB over the mix, which is why mastering holds the mix at -2 dBTP.
- Check every scored transition and the end screen, including entry, silent centre and return to narration; the music should carry the end screen to its last seconds. Measure the bed and foreground separately, listen in context and recheck the final encoded mix; a global loudness value cannot establish the correct balance between buses.
