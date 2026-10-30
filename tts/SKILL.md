---
name: tts
description: Generate local speech and voice clones with VoxCPM2, including expressive narration directed phrase by phrase.
---

# VoxCPM2 TTS

Direct narration to fit the text, audience, and timing: choose how each passage should sound, generate it, and evaluate the result.

## Runtime

The skill owns its runtime: `.venv` inside this skill directory, holding `voxcpm`, PyTorch, SoundFile, `wetext`, and WhisperX. Use `.venv/bin/python` for every script here. The runtime targets Linux and macOS; on Windows, run the skill inside WSL. When `.venv` is missing or an import fails, build it with `scripts/setup_runtime.sh` (needs `uv`); it installs CUDA PyTorch when an NVIDIA GPU is present and CPU PyTorch otherwise, and `TORCH_BACKEND=cpu|cu128|...` overrides that. The installer adds the optional OpenVINO runtime when it detects an Intel GPU on Linux; `OPENVINO=1` enables installation explicitly and `OPENVINO=0` skips it. Intel GPU execution also requires a working Intel OpenCL driver; the installer does not change system drivers.

Resolve bundled scripts relative to this skill directory. Model weights are `openbmb/VoxCPM2` in the Hugging Face cache, downloaded on first use. Leave `--device auto` as the default: prefer CUDA when available, then OpenVINO on a compatible Intel GPU, then CPU. Prefer the Intel GPU over CPU for both single lines and batches, including `--rows 1`. `--device cpu` forces CPU, `--device openvino` explicitly requests the Intel GPU path, and `--device cuda:N` selects a CUDA device. `--openvino-device GPU.0` can choose an Intel GPU when several are present.

The OpenVINO path (`scripts/voxcpm_openvino.py`) runs the diffusion estimator on the Intel GPU with an FP16 precision hint while the rest of the model uses CPU float32. It caches exports locally under the user cache directory (`--openvino-cache-dir` overrides it), keyed by model weights, configuration, runtime versions and input shapes; do not add exports, cache data, audio or local timing reports to the public skill. First use exports and compiles each required batch shape. GPU conversion, compilation or inference failure falls back to CPU with a diagnostic. Missing dependencies or a GPU in automatic mode also select CPU; an unavailable explicitly requested OpenVINO device raises an actionable error. Prefer this Intel GPU path over CPU whenever available; its actual performance depends on the device and workload. FP16 can change the generated take: verify diction and speaker identity on a representative passage and record the selected backend with the seed.

CPU orchestration uses float32 weights (about 14 GB of RAM), a compiled CPU diffusion head when needed, and up to `--rows` lines (default 4) decoded together. Each new CPU batch size compiles once per run, a fixed cost that a very short single line may not earn back (`--no-compile` skips CPU compilation, including fallback). Run one voice job at a time: parallel processes compete for cores and memory bandwidth, so put every line in one `--input` file instead, including retakes and every variant of a test, since each run pays the model load and compilation again. The diffusion head pads a batch to the next power of two (`--rows 3` costs as much as 4); a larger batch helps only up to a machine-dependent size, so measure once with `scripts/voxcpm_bench.py` for CPU row-size tuning. Changing batch size within the same backend preserves each line's seeded noise; changing backend or precision can change the take. Direct API calls on CPU support `device="cpu"`, `optimize=False`, without these speedups.

## Choose the cloning mode

| Goal | Inputs | Behavior |
|---|---|---|
| Directed narration | `--reference-audio` + delivery instruction | Controllable Cloning: clones timbre, steers expression and pace. Default for expressive voiceovers. |
| Match the sample's delivery | `--prompt-audio` + exact transcript (`--prompt-text` / `--prompt-file`) + `--reference-audio` | Ultimate Cloning: continues the sample's rhythm and emotion; style instructions are ignored. |
| Create a new voice | Text + parenthetical voice description | Voice Design. |

Controllable Cloning needs the audio reference alone. Start with a clean, representative 5–30-second clip and keep the speaker reference consistent across the piece. Clone only a voice whose owner agreed to it, and label the result as AI-generated: VoxCPM2's terms forbid impersonation, fraud and disinformation.

## Direct the performance

Infer the listener, speaker's intent, and emotional progression from the request. Split the text at meaningful shifts or montage beats. Choose concrete delivery qualities for each segment: curiosity, a smile, intimacy, emphasis, pace. Use punctuation and natural pauses to support them.

Put English instructions in parentheses immediately before the spoken text; `--control` supplies one shared instruction. Keep the spoken language unchanged. Example of a conversational opening, cheerful middle, and gentle close:

```text
(conversational, curious, slightly smiling)Masz chwilę dla siebie? Wyobraź sobie pierwszy kawałek.
(warm, cheerful, clear diction)Ależ to jest dobre! Ten smak od razu poprawia mi humor.
(warm, intimate, unhurried)A teraz zwolnij. Ta chwila jest tylko twoja.
```

The instruction is plain text joined to the spoken text, so its language carries into the first word: after an English (or Chinese) instruction, the first word of other languages can come out with English rules, as Polish "Co" read "Ko" or "Pylos" read "Pailos". Instructions written in the spoken language avoid that but steer the style only weakly, so keep them in English and check the first word of every take. When it is wrong, regenerate that line with a throw-away word in the spoken language and a full stop before the text, as in `(wry, teasing)Cóż. Co zapisywali…`, and cut it off at the pause with `scripts/cut_warmup.py`. Keep the warm-up for retakes: a line that follows it starts like a continuation rather than afresh. A reference padded with silence, a lowercase first letter and more inference steps leave the first word unchanged.

Choose the progression for the actual text. Test a representative passage for speaker identity, diction, pace, and emotional contrast. Refine the direction or seed for weak segments and retain successful takes. Preserve approved copy; when wording is editable, conversational phrasing can help.

Start with CFG `2.0`, `20` inference steps, denoiser disabled; adjust for observed issues. Every take is a random draw: `--seed S` makes it repeatable (batch line N uses `S + N − 1`; without `--seed` the script picks one and prints it with each saved file). Reproduce a take using the same backend and precision as well as its seed. For repeatable direct API calls, use the installed API's supported seed mechanism, such as a `seed` argument or `torch.manual_seed(seed)` before generation. Prepare digits, dates, abbreviations, and mixed-language tokens using `--normalize` or explicit spoken wording as appropriate; spell foreign names and words that also exist in English (Polish "wanna") the way they should sound, and keep the written form for captions.

## Generate

With `TTS_SKILL` set to this skill directory and `TTS_PYTHON` to `$TTS_SKILL/.venv/bin/python`:

```bash
"$TTS_PYTHON" "$TTS_SKILL/scripts/voxcpm_tts.py" \
  --text "Mała chwila. Wielka przyjemność." \
  --reference-audio "voice.wav" \
  --control "warm, intimate, gently smiling" \
  --cfg-value 2 --inference-timesteps 20 --output "close.wav"
```

For a shared reference, batch one utterance per nonempty UTF-8 line, each with its own parenthetical instruction. Batch mode loads the model and reference cache once; CPU/OpenVINO decoding processes `--rows` lines together and saves each as it finishes:

```bash
"$TTS_PYTHON" "$TTS_SKILL/scripts/voxcpm_tts.py" \
  --input "takes.txt" --output-dir "takes" --reference-audio "voice.wav" \
  --cfg-value 2 --inference-timesteps 20
```

Outputs `output_001.wav`, etc. follow input-line order. Regenerate individual takes in single-output mode using the original backend (`--device openvino` when the batch used it); `--seed S + N − 1` reuses batch line N's noise, another seed gives a new take. Preserve native 48 kHz sources and record reference, text, direction, parameters, actual backend/precision (including any CPU fallback), controlled seed, and duration in the project's existing audio manifest.

## Verify and assemble

Check words, duration, finite samples, and clipping. Listen when audio inspection is available to judge expression and speaker identity; otherwise report the technical/content checks and leave listening judgment to the user.

ASR detects missing/repeated words or spoken instructions, not delivery quality. Check clean takes first: music and short Polish phrases can confuse recognition. Review suspicious results in context.

`scripts/tts_pronunciation_qa.py` checks a whole project in one run (WhisperX, `--language pl` for Polish): `script.json` holds `metadata.language` and a `tts_chunks` list of `{"chunk_id", "voice_text"}`, the takes are `tts/clean/<chunk_id>.wav`, and the report goes to `manifests/tts-pronunciation-qa.json`; `--script`, `--tts-dir`, `--language` and `--output` override each. Without such a project, transcribe with WhisperX or faster-whisper directly. Both ship in the skill runtime. Use one Whisper size, `small` or larger, for every check in a project: `base` misreads clear words often enough to raise false alarms. Make FFmpeg available on `PATH` when needed.

To choose between takes of one line, `scripts/word_confidence.py` prints each script word's probability given the audio (Whisper forced alignment) beside the free transcription; a wrong first word shows in both. The numbers only rank takes of the same line: numbers spoken as words, rare names and phonetic spellings score low in every take.

Place phrases at visual beats, cut grouped takes at pauses, and add silence for intentional spacing. Apply music ducking and playback gain in the mix. Direct emotion during generation; pitch/tempo processing is a separate editorial choice. Check boundaries, overlaps, final peaks, and exported media.

[Official cloning modes](https://github.com/OpenBMB/VoxCPM#python-api) · [Maintainer explanation of style control](https://github.com/OpenBMB/VoxCPM/issues/210)
