---
name: tts
description: Use when you need local neural speech generation or voice cloning with the VoxCPM2 engine, especially for GPU-first expressive synthesis.
---

# VoxCPM2 TTS

This skill provides access to VoxCPM2 for speech generation and voice cloning.

## Environment Note

**VoxCPM2** is installed in the local speech generation environment at:

`%USERPROFILE%\Downloads\speech-gen\venv`

Prefer that interpreter explicitly for local runs:
```bash
%USERPROFILE%\Downloads\speech-gen\venv\Scripts\python.exe generate_voxcpm.py ...
%USERPROFILE%\Downloads\speech-gen\venv\Scripts\python.exe -m voxcpm.cli ...
```

The wrapper script `generate_voxcpm.py` lives in:

`%USERPROFILE%\Downloads\speech-gen`

If a task is being run from another workspace, do not assume a per-project `.\venv` exists. Use the known `speech-gen` environment unless the user provides a different one.

### Linux CPU VoxCPM2 Runtime

A persistent CPU-only VoxCPM2 runtime is installed at:

`/home/detoix/.local/share/voxcpm2-cpu`

Use it for deterministic short Polish clone tests or emergency CPU fallback when the Windows/RTX setup is unavailable:

```bash
/home/detoix/.local/share/voxcpm2-cpu/venv/bin/python \
  /home/detoix/.local/share/voxcpm2-cpu/scripts/generate_clone.py \
  --voice-dir /home/detoix/.local/share/voxcpm2-cpu/voices/krzysztof \
  --text "Cześć, to jest krótka próba klonowania głosu po polsku." \
  --steps 4 \
  --max-len 80 \
  --output /home/detoix/.local/share/voxcpm2-cpu/outputs/out.wav
```

The script writes a JSON manifest next to each WAV containing steps, hashes, VoxCPM commit, Torch version, device, and output SHA256.

## Workflow

### 1. Speech Generation

#### Using VoxCPM2
Plain TTS:
```bash
.\venv\Scripts\python.exe generate_voxcpm.py --text "Your text" --output "out.wav"
```

Single-output cloning path when one-off regeneration is needed:
```bash
.\venv\Scripts\python.exe -m voxcpm.cli clone ^
  --text "Final target text" ^
  --prompt-audio "voice_sample.wav" ^
  --prompt-text "Exact transcript of voice_sample.wav" ^
  --reference-audio "voice_sample.wav" ^
  --output "out.wav"
```

Batch cloning path for chunk generation with shared prompt/reference settings:
```bash
.\venv\Scripts\python.exe -m voxcpm.cli batch ^
  --input "tts-batch-input.txt" ^
  --output-dir "tts-batch-output" ^
  --prompt-audio "voice_sample.wav" ^
  --prompt-text "Exact transcript of voice_sample.wav" ^
  --reference-audio "voice_sample.wav"
```
Map `output_001.wav`, `output_002.wav`, etc. back to chunk ids in input-line order.

Use batch mode by default for chunk generation whenever the chunks share the same prompt/reference settings. Use single-output clone mode for one-off regeneration.

Preferred PowerShell invocation for reliable local runs:
```powershell
$text = @'
Final target text
'@
$prompt = @'
Exact transcript of the sample audio
'@
& 'C:\path\to\venv\Scripts\python.exe' -m voxcpm.cli clone `
  --text $text `
  --prompt-audio 'C:\path\to\voice_sample.wav' `
  --prompt-text $prompt `
  --reference-audio 'C:\path\to\voice_sample.wav' `
  --output 'C:\path\to\out.wav'
```

### 2. VoxCPM2 Practical Guidance
- For cloning, prefer the upstream CLI entrypoint:
  `.\venv\Scripts\python.exe -m voxcpm.cli ...`
- Treat `prompt-audio + prompt-text + reference-audio` as the default clone path when the user can provide a transcript of the sample; use it through `voxcpm.cli batch` for chunk generation with shared settings, or `voxcpm.cli clone` for one-off regeneration.
- `prompt-text` should be the exact spoken words from the sample audio, not a paraphrase.
- If the user wants cloning and does not provide a transcript, ask for it explicitly before continuing.
- Avoid adding style instructions if the goal is to preserve the sample's original speaking style as closely as possible.
- When reproducing a known-good clone command, do not add extra tuning flags unless the user explicitly asks for them. 
- For the default VoxCPM prompt/reference path, do not add `--normalize`, `--control`, `--no-optimize`, custom `--cfg-value`, or custom `--inference-timesteps` unless the user explicitly requests experimentation.
- If the caller supplies a parenthetical cue at the start of the text, treat it as a micro-prosody nudge only.
- Keep such cues very short and sparse so the model stays close to the cloned speaker identity.
- Prefer cues about discourse position or transition, such as `clear start`, `steady continuation`, `slight contrast`, or `gentle wrap-up`, over strong mood or persona descriptions.
- If a cue makes the output sound less like the speaker, remove it rather than strengthening it.
- Prefer handling text normalization at the TTS stage rather than pushing engine-specific rewrites upstream into the scriptwriter skill.
- If the narration contains digits, dates, abbreviations, passwords, or mixed-language tokens and the raw clone sounds garbled, test `--normalize` first so `wetext` can expand the text automatically.
- Only manually rewrite the target text when `wetext` normalization is unavailable, insufficient, or the user explicitly wants hand-normalized phrasing.
- Use the local low-VRAM defaults first when staying in the wrapper:
  `optimize=False`, `load_denoiser=False`, `cfg_value=2.0`, `inference_timesteps=8`.
- Plain English and Polish TTS were verified to fit in VRAM at roughly `5247 MiB allocated` and `~5.6-5.7 GiB reserved`.
- Start with plain TTS before cloning. Cloning is the next likely point of VRAM failure.

### 3. Target-Only Clone Outputs
The required output for every cloned chunk is **target speech only**. The saved WAV must not include the prompt/sample transcript at the beginning.

Use the VoxCPM prompt/reference path with `--prompt-audio`, `--prompt-text`, and `--reference-audio`; prefer `voxcpm.cli batch` for chunk generation with shared settings, and use `voxcpm.cli clone` for one-off regeneration. On the current local VoxCPM2 CLI this normally writes target-only audio: prompt audio/text are used as conditioning inputs, while the saved waveform contains the requested text.

Do not trim by default. After generation, verify the raw output before using it:

- Compare the raw output duration against the prompt sample duration and the expected target duration.
- If the raw output is shorter than the prompt sample, or otherwise clearly target-only, copy it directly to the clean output path.
- If the raw output audibly or durationally contains the prompt/sample prefix, trim only the prefix and save a clean target-only file.
- Never pass a WAV containing prompt/sample speech to lip-sync, concatenation, or final narration.
- Use `ffprobe` duration checks for the raw, clean, and prompt sample files, and record the check in the project `tts-manifest.json`.

Keep a manifest field such as `trim_mode`:

- `target_only`: raw output was already clean and was copied unchanged.
- `trimmed_prefix`: raw output contained prompt/sample speech and was trimmed.
- `manual_review`: automatic verification could not determine whether the prefix was present.

Use prefix trimming only as a corrective step for observed prefix contamination, not as the normal VoxCPM2 clone path.

### 4. Notes
- VoxCPM2 uses the installed `voxcpm` package and the local wrapper `generate_voxcpm.py`.
- For prompt/reference cloning, use `python -m voxcpm.cli batch` for chunk generation with shared settings, or `python -m voxcpm.cli clone` for one-off regeneration.
- `generate_voxcpm_samples.py` prepares the numbered sample set `voxcpm_1.wav`, `voxcpm_2.wav`, `voxcpm_3.wav`, and `voxcpm_clone_test.wav`.
- The clone sample expects a placeholder reference file at `temp\voxcpm_clone_reference.wav`.

## References
- **Model**: `openbmb/VoxCPM2`
