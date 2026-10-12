---
name: tts
description: Generate local speech and voice clones with VoxCPM2, including expressive narration directed phrase by phrase.
---

# VoxCPM2 TTS

Direct narration to fit the text, audience, and timing: choose how each passage should sound, generate it, and evaluate the result.

## Runtime

The skill owns its runtime: `.venv` inside this skill directory, holding `voxcpm`, PyTorch, SoundFile, `wetext`, and WhisperX. Use `.venv/bin/python` (`.venv\Scripts\python.exe` on Windows) for every script here. When `.venv` is missing or an import fails, build it with `scripts/setup_runtime.sh` (needs `uv`); it installs CUDA PyTorch when an NVIDIA GPU is present and CPU PyTorch otherwise, and `TORCH_BACKEND=cpu|cu128|...` overrides that.

Resolve bundled scripts relative to this skill directory. Model weights are `openbmb/VoxCPM2` in the Hugging Face cache, downloaded on first use. Inspect available hardware and choose the device, optimization, and thread count for it. GPU is faster; on CPU expect roughly a minute of compute per few seconds of speech, so test on short passages; direct CPU calls support `device="cpu"`, `optimize=False`.

## Choose the cloning mode

| Goal | Inputs | Behavior |
|---|---|---|
| Directed narration | `--reference-audio` + delivery instruction | Controllable Cloning: clones timbre, steers expression and pace. Default for expressive voiceovers. |
| Match the sample's delivery | `--prompt-audio` + exact transcript (`--prompt-text` / `--prompt-file`) + `--reference-audio` | Ultimate Cloning: continues the sample's rhythm and emotion; style instructions are ignored. |
| Create a new voice | Text + parenthetical voice description | Voice Design. |

Controllable Cloning needs the audio reference alone. Start with a clean, representative 5–30-second clip and keep the speaker reference consistent across the piece.

## Direct the performance

Infer the listener, speaker's intent, and emotional progression from the request. Split the text at meaningful shifts or montage beats. Choose concrete delivery qualities for each segment: curiosity, a smile, intimacy, emphasis, pace. Use punctuation and natural pauses to support them.

Put English instructions in parentheses immediately before the spoken text; `--control` supplies one shared instruction. Keep the spoken language unchanged. Example of a conversational opening, cheerful middle, and gentle close:

```text
(conversational, curious, slightly smiling)Masz chwilę dla siebie? Wyobraź sobie pierwszy kawałek.
(warm, cheerful, clear diction)Ależ to jest dobre! Ten smak od razu poprawia mi humor.
(warm, intimate, unhurried)A teraz zwolnij. Ta chwila jest tylko twoja.
```

Choose the progression for the actual text. Test a representative passage for speaker identity, diction, pace, and emotional contrast. Refine the direction or seed for weak segments and retain successful takes. Preserve approved copy; when wording is editable, conversational phrasing can help.

Start with CFG `2.0`, `20` inference steps, denoiser disabled; adjust for observed issues. For repeatable direct API calls, use the installed API's supported seed mechanism, such as a `seed` argument or `torch.manual_seed(seed)` before generation. Prepare digits, dates, abbreviations, and mixed-language tokens using `--normalize` or explicit spoken wording as appropriate.

## Generate

With `TTS_SKILL` set to this skill directory and `TTS_PYTHON` to `$TTS_SKILL/.venv/bin/python`:

```bash
"$TTS_PYTHON" "$TTS_SKILL/scripts/voxcpm_tts.py" \
  --text "Mała chwila. Wielka przyjemność." \
  --reference-audio "voice.wav" \
  --control "warm, intimate, gently smiling" \
  --cfg-value 2 --inference-timesteps 20 --output "close.wav"
```

For a shared reference, batch one utterance per nonempty UTF-8 line, each with its own parenthetical instruction. Batch mode loads the model and reference cache once:

```bash
"$TTS_PYTHON" "$TTS_SKILL/scripts/voxcpm_tts.py" \
  --input "takes.txt" --output-dir "takes" --reference-audio "voice.wav" \
  --cfg-value 2 --inference-timesteps 20
```

Outputs `output_001.wav`, etc. follow input-line order. Regenerate individual takes in single-output mode. Preserve native 48 kHz sources and record reference, text, direction, parameters, controlled seed, and duration in the project's existing audio manifest.

## Verify and assemble

Check words, duration, finite samples, and clipping. Listen when audio inspection is available to judge expression and speaker identity; otherwise report the technical/content checks and leave listening judgment to the user.

ASR detects missing/repeated words or spoken instructions, not delivery quality. Check clean takes first: music and short Polish phrases can confuse recognition. Review suspicious results in context.

Use `scripts/tts_pronunciation_qa.py` for `script.json` / `tts_chunks` projects (WhisperX, `--language pl` for Polish); otherwise transcribe with WhisperX or faster-whisper directly. Both ship in the skill runtime. Make FFmpeg available on `PATH` when needed.

Place phrases at visual beats, cut grouped takes at pauses, and add silence for intentional spacing. Apply music ducking and playback gain in the mix. Direct emotion during generation; pitch/tempo processing is a separate editorial choice. Check boundaries, overlaps, final peaks, and exported media.

[Official cloning modes](https://github.com/OpenBMB/VoxCPM#python-api) · [Maintainer explanation of style control](https://github.com/OpenBMB/VoxCPM/issues/210)
