---
name: tts
description: "Generate local speech and voice clones with VoxCPM2: reuse a voice library, create only missing moods, then narrate scripts and compare retakes."
---

# VoxCPM2 TTS

Direct narration to fit the text, audience, and timing: choose how each passage should sound, generate it, and evaluate the result.

## Runtime

The [native Vulkan runtime](references/native-vulkan.md) supports GGUF voice design and continuation cloning. The Python synthesis commands use `voxcpm_tts.py`.

The skill owns its runtime: `.venv` inside this skill directory, holding `voxcpm`, PyTorch, SoundFile, `wetext`, and WhisperX. Use `.venv/bin/python` for the Python synthesis backend; native narration and audio QA can use the lighter film-tools environment described below. The runtime targets Linux and macOS; on Windows, run the skill inside WSL. When `.venv` is missing or an import fails, build it with `scripts/setup_runtime.sh` (needs `uv`); it installs CUDA PyTorch when an NVIDIA GPU is present and CPU PyTorch otherwise, and `TORCH_BACKEND=cpu|cu128|...` overrides that. The installer adds the optional OpenVINO runtime when it detects an Intel GPU on Linux; `OPENVINO=1` enables installation explicitly and `OPENVINO=0` skips it. Intel GPU execution also requires a working Intel OpenCL driver; the installer does not change system drivers.

Resolve bundled scripts relative to this skill directory. Model weights are `openbmb/VoxCPM2` in the Hugging Face cache, downloaded on first use. Leave `--device auto` as the default: prefer CUDA when available, then OpenVINO on a compatible Intel GPU, then CPU. Prefer the Intel GPU over CPU for both single lines and batches, including `--rows 1`. `--device cpu` forces CPU, `--device openvino` explicitly requests the Intel GPU path, and `--device cuda:N` selects a CUDA device. `--openvino-device GPU.0` can choose an Intel GPU when several are present.

The OpenVINO path (`scripts/voxcpm_openvino.py`) runs the diffusion estimator on the Intel GPU with an FP16 precision hint while the rest of the model uses CPU float32. It caches exports locally under the user cache directory (`--openvino-cache-dir` overrides it), keyed by model weights, configuration, runtime versions and input shapes; do not add exports, cache data, audio or local timing reports to the public skill. First use exports and compiles each required batch shape. GPU conversion, compilation or inference failure falls back to CPU with a diagnostic. Missing dependencies or a GPU in automatic mode also select CPU; an unavailable explicitly requested OpenVINO device raises an actionable error. Prefer this Intel GPU path over CPU whenever available; its actual performance depends on the device and workload. FP16 can change the generated take: verify diction and speaker identity on a representative passage and record the selected backend with the seed.

CPU orchestration uses float32 weights (about 14 GB of RAM), a compiled CPU diffusion head when needed, and up to `--rows` lines (default 4) decoded together. Each new CPU batch size compiles once per run, a fixed cost that a very short single line may not earn back (`--no-compile` skips CPU compilation, including fallback). Run one voice job at a time: parallel processes compete for cores and memory bandwidth, so put every line in one `--input` file instead, including retakes and every variant of a test, since each run pays the model load and compilation again. The diffusion head pads a batch to the next power of two (`--rows 3` costs as much as 4); a larger batch helps only up to a machine-dependent size, so measure once with `scripts/voxcpm_bench.py` for CPU row-size tuning. Changing batch size within the same backend preserves each line's seeded noise; changing backend or precision can change the take. Direct API calls on CPU support `device="cpu"`, `optimize=False`, without these speedups.

## Clone in two stages

Narration takes two passes. The first gives it a mood, the second gives it quality and reads the script.

| Stage | Inputs | Mode | Result |
|---|---|---|---|
| 1. Mood | `--reference-audio` + delivery instruction | Controllable Cloning: clones the timbre, steers expression and pace | Mood samples of 8–15 s, chosen by ear |
| 2. Quality | `--prompt-audio` + its exact transcript (`--prompt-text` / `--prompt-file`) + `--reference-audio` | Ultimate Cloning: continues the sample's rhythm and emotion; style instructions are ignored | The final takes |

Keep the approved samples with their transcripts in a voice library next to the reference, one per mood. Stage 1 runs only for a mood the library lacks, and an approved final take can also become a sample. At stage 2 no instruction comes before the text, so first words follow the rules of their own language. A take inherits its sample's pace: measure the sample's syllables per second and choose one near the pace you want, since a slow sample slows every line made from it.

Start with a clean, representative 5–30-second reference and keep it the same across the piece and the library. Clone only a voice whose owner agreed to it, and label the result as AI-generated: VoxCPM2's terms forbid impersonation, fraud and disinformation. To create a new voice instead, use Voice Design: text with a parenthetical voice description.

## Stage 1: direct the mood

Infer the listener, speaker's intent, and emotional progression from the request. Choose a mood for each kind of passage and concrete delivery qualities for it: curiosity, a smile, intimacy, emphasis, pace. Use punctuation and natural pauses to support them.

Put English instructions in parentheses immediately before the spoken text; `--control` supplies one shared instruction. Keep the spoken language unchanged. Example of a conversational opening, cheerful middle, and gentle close:

```text
(conversational, curious, slightly smiling)Masz chwilę dla siebie? Wyobraź sobie pierwszy kawałek.
(warm, cheerful, clear diction)Ależ to jest dobre! Ten smak od razu poprawia mi humor.
(warm, intimate, unhurried)A teraz zwolnij. Ta chwila jest tylko twoja.
```

The instruction is plain text joined to the spoken text, so its language carries into the first word: after an English (or Chinese) instruction, the first word of other languages can come out with English rules, as Polish "Co" read "Ko" or "Pylos" read "Pailos". Instructions written in the spoken language avoid that but steer the style only weakly, so keep them in English, listen to the start of every sample and take another seed when it is wrong.

Test each sample for speaker identity, diction, pace, and emotional contrast, refine the direction or seed for weak ones and retain the good ones. Preserve approved copy; when wording is editable, conversational phrasing can help.

## Settings

Use CFG `2.0`, `20` inference steps at stage 1 and `30` at stage 2, denoiser disabled; adjust for observed issues. Every take is a random draw: `--seed S` makes it repeatable (batch line N uses `S + N − 1`; without `--seed` the script picks one and prints it with each saved file). Reproduce a take using the same backend and precision as well as its seed. For repeatable direct API calls, use the installed API's supported seed mechanism, such as a `seed` argument or `torch.manual_seed(seed)` before generation. Prepare digits, dates, abbreviations, and mixed-language tokens using `--normalize` or explicit spoken wording as appropriate; spell foreign names and words that also exist in English (Polish "wanna") the way they should sound, and keep the written form for captions.

## Generate

With `TTS_SKILL` set to this skill directory and `TTS_PYTHON` to `$TTS_SKILL/.venv/bin/python`:

```bash
"$TTS_PYTHON" "$TTS_SKILL/scripts/voxcpm_tts.py" \
  --text "Mała chwila. Wielka przyjemność." \
  --reference-audio "voice.wav" \
  --control "warm, intimate, gently smiling" \
  --cfg-value 2 --inference-timesteps 20 --output "close.wav"
```

That is stage 1. At stage 2, batch one utterance per nonempty UTF-8 line, without instructions. A batch shares one sample, so group the lines by mood. Batch mode loads the model and reference cache once; CPU/OpenVINO decoding processes `--rows` lines together and saves each as it finishes:

```bash
"$TTS_PYTHON" "$TTS_SKILL/scripts/voxcpm_tts.py" \
  --input "takes.txt" --output-dir "takes" --reference-audio "voice.wav" \
  --prompt-audio "mood.wav" --prompt-file "mood.txt" \
  --cfg-value 2 --inference-timesteps 30
```

Outputs `output_001.wav`, etc. follow input-line order. Regenerate individual takes in single-output mode using the original backend (`--device openvino` when the batch used it); `--seed S + N − 1` reuses batch line N's noise, another seed gives a new take. Preserve native 48 kHz sources and record reference, text, direction, parameters, actual backend/precision (including any CPU fallback), controlled seed, and duration in the project's existing audio manifest.

## Narrate a script from the library

`scripts/narrate.py` is this skill's interface for whole scripts: it takes the lines and a voice library, and callers need nothing else from here.

An ignored `.runtime/narrate.json` selects the native CLI when present. Explicit Python device or batching options select Python when `--engine` is omitted. Use `--engine python|native` to choose the engine or `--native-config` to select a native configuration. The [native runtime guide](references/native-vulkan.md) covers filtered 16 kHz prompt preparation, two-line LocDiT batching and selective Q8_0 weights.

- Library: `voice.wav`, `bank/bank.json` (mood → sample, exact transcript, direction, measured pace), optional `bank/rules.json` mapping a line's direction to a mood.
- Lines: a JSON list of `{"id", "say", "direction", "mood"}`, `mood` optional. A take is `output_NNN.wav` by its place in the list.

```bash
"$TTS_PYTHON" "$TTS_SKILL/scripts/narrate.py" --lines lines.json --library voices --plan
"$TTS_PYTHON" "$TTS_SKILL/scripts/narrate.py" --lines lines.json --library voices --out takes --provenance provenance.json
"$TTS_PYTHON" "$TTS_SKILL/scripts/narrate.py" --library voices --add-mood NAME --sample clip.wav --text "exact transcript" --direction "..."
"$TTS_PYTHON" "$TTS_SKILL/scripts/compare_takes.py" --lines lines.json --old takes --new retakes --language pl
```

`--plan` lists each mood's lines, checks that the reference exists and validates sample files against their recorded hashes, and generates nothing. It exits with 2 for a missing reference, an uncovered mood or an unusable sample; repair a changed sample instead of treating a hash mismatch as approval to regenerate it. Make a mood only when the plan reports it missing: run stage 1, let the listener choose by ear, and `--add-mood` keeps the clip for all later work. For retakes, `--ids` picks the lines, `--mood` forces another sample and another `--seed` gives a new draw; `compare_takes.py` prints what the recogniser heard in the old and new takes, and writes `comparison.wav` for the listener. `--device`, `--openvino-device`, `--openvino-cache-dir`, `--rows` and `--no-compile` have the same meaning as in the generator above. Output numbering always follows the original list, including retakes; unknown IDs are rejected. Provenance records the seed actually used, rather than deriving it later from line order. Other workflows may run their audio tools with this runtime (`$TTS_PYTHON`).

## Verify and assemble

Check words, duration, finite samples, and clipping. Listen when audio inspection is available to judge expression and speaker identity; otherwise report the technical/content checks and leave listening judgment to the user.

Compare free ASR against the intended spoken text **word by word** on clean takes. Every unresolved substitution, omission, insertion or repetition needs review, even when the rest of a long line matches. ASR is evidence for listening, not proof of a pronunciation error or a reason to regenerate automatically; music and short phrases can confuse recognition.

`scripts/tts_pronunciation_qa.py` checks a whole project in one run (WhisperX, `--language pl` for Polish): `script.json` holds `metadata.language` and a `tts_chunks` list of `{"chunk_id", "voice_text"}`, the takes are `tts/clean/<chunk_id>.wav`, and the report goes to `manifests/tts-pronunciation-qa.json`. For narration from the library, use `--script lines.json --tts-dir takes --language pl`: it also accepts the `{"id", "say"}` list and `output_NNN.wav` files. Optional `check_text` supplies the intended spoken wording when the generator's `say` uses a pronunciation spelling. `--output` chooses the report. It records word positions, expected/heard words and accepted phonetic equivalences; exit 0 means no unresolved edits, 1 means listen to the flagged words, and 2 means the check could not complete. Use one Whisper size, `small` or larger, for every check in a project: `base` misreads clear words often enough to raise false alarms. Make FFmpeg available on `PATH` when needed.

For Polish, the comparison accepts a conservative set of spelling equivalents: ó/u, ch/h, final devoicing (e.g. Gród/Grud and Bóg/Buk), contextual nasal-vowel spellings such as kąt/kont, and final ę/e. It keeps c distinct from k/g, so proc/prog is flagged. This is not a full Polish pronunciation model; review other discrepancies in context rather than stripping all diacritics or using a sentence similarity threshold. Keep numerals enabled in free transcription: a year written as digits can be correctly spoken even when forced alignment of the spelled-out year scores poorly. Check that the free transcript contains the right number before considering a retake.

To choose between takes of one line, `scripts/word_confidence.py` prints each script word's probability given the audio (Whisper forced alignment) beside the free transcription and its word-level differences. `compare_takes.py` uses the same comparison. Forced probabilities only rank takes of the same line; they neither clear a differing word nor prove it wrong. Numbers spoken as words, rare names and phonetic spellings can score low in every take. Confirm a suspected pronunciation error in the audio before retaking it.

Place phrases at visual beats, cut grouped takes at pauses, and add silence for intentional spacing. Apply music ducking and playback gain in the mix. Direct emotion during generation; pitch/tempo processing is a separate editorial choice. Check boundaries, overlaps, final peaks, and exported media.

[Official cloning modes](https://github.com/OpenBMB/VoxCPM#python-api) · [Maintainer explanation of style control](https://github.com/OpenBMB/VoxCPM/issues/210)
