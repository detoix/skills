---
name: tts
description: Use when you need local neural speech generation or voice cloning with the VoxCPM2 engine, especially for GPU-first expressive synthesis.
---

# VoxCPM2 TTS

This skill provides access to VoxCPM2 for speech generation and voice cloning.

## Environment Note

**VoxCPM2** and **WhisperX QA** are installed in the skill-local standalone virtualenv.

Resolve these paths relative to this skill directory:

```text
.\.venv\Scripts\python.exe
scripts\voxcpm_tts.py
requirements.lock.txt
```

Prefer that interpreter explicitly for local runs:
```bash
.\.venv\Scripts\python.exe scripts\voxcpm_tts.py ...
```

The TTS script lives in:

`scripts`

If a task is being run from another workspace, do not assume a per-project `.\venv` exists in that workspace. Resolve `.\.venv` relative to this skill directory unless the user provides a different one.

### Runtime Role

This skill owns speech synthesis mechanics only. Callers own voice identity, asset discovery, project context, and approval state. Do not make this skill depend on or name upstream callers, channels, or global user-specific voice directories.

Required clone inputs from the caller:

- `voice_sample.wav`: source voice sample
- `transcript.txt`: exact transcript of that sample
- target text or batch input derived from the caller's approved narration chunks
- output path or project-local TTS output directory

Runtime paths are execution details:

- Windows/GPU production: use the skill-local VoxCPM2 wrapper and `.venv` documented below.
- Linux/CPU fallback: `/home/detoix/.local/share/voxcpm2-cpu`, used only when GPU runtime is unavailable or for short deterministic smoke tests.

On the Sandy Bridge Linux CPU fallback, VoxCPM2 low-precision CPU checkpoints must load as `float32`; otherwise the runtime can terminate with `SIGILL`. The local VoxCPM source patch in `/home/detoix/.local/share/voxcpm2-cpu/src/VoxCPM/src/voxcpm/model/utils.py` handles this and prints `adjusted dtype bfloat16 -> float32 for device cpu` during a healthy run.

## Workflow

### 1. Speech Generation

#### Using VoxCPM2
Plain TTS:
```bash
.\.venv\Scripts\python.exe scripts\voxcpm_tts.py --text "Your text" --output "out.wav"
```

Single-output cloning path when one-off regeneration is needed:
```bash
.\.venv\Scripts\python.exe scripts\voxcpm_tts.py ^
  --text "Final target text" ^
  --prompt-audio "voice_sample.wav" ^
  --prompt-text "Exact transcript of voice_sample.wav" ^
  --reference-audio "voice_sample.wav" ^
  --output "out.wav"
```

Batch cloning path for chunk generation with shared prompt/reference settings:
```bash
.\.venv\Scripts\python.exe scripts\voxcpm_tts.py ^
  --input "tts-batch-input.txt" ^
  --output-dir "tts-batch-output" ^
  --prompt-audio "voice_sample.wav" ^
  --prompt-text "Exact transcript of voice_sample.wav" ^
  --reference-audio "voice_sample.wav"
```
Map `output_001.wav`, `output_002.wav`, etc. back to chunk ids in input-line order.

Use wrapper batch mode by default for chunk generation whenever the chunks share the same prompt/reference settings. It loads the model once and builds the prompt/reference cache once for the whole input file. Use single-output mode for one-off regeneration.

Preferred PowerShell invocation for reliable local runs:
```powershell
$text = @'
Final target text
'@
$prompt = @'
Exact transcript of the sample audio
'@
& '.\.venv\Scripts\python.exe' 'scripts\voxcpm_tts.py' `
  --text $text `
  --prompt-audio 'C:\path\to\voice_sample.wav' `
  --prompt-text $prompt `
  --reference-audio 'C:\path\to\voice_sample.wav' `
  --output 'C:\path\to\out.wav'
```

### 2. VoxCPM2 Practical Guidance
- Treat `prompt-audio + prompt-text + reference-audio` as the default clone path when the user can provide a transcript of the sample; use it through `scripts\voxcpm_tts.py --input ... --output-dir ...` for chunk generation with shared settings, or single-output mode for one-off regeneration.
- `prompt-text` should be the exact spoken words from the sample audio, not a paraphrase.
- If the user wants cloning and does not provide a transcript, ask for it explicitly before continuing.
- Avoid adding style instructions if the goal is to preserve the sample's original speaking style as closely as possible.
- When reproducing a known-good clone command, do not add extra tuning flags unless the user explicitly asks for them. 
- For the default VoxCPM prompt/reference path, do not add `--normalize`, `--control`, `--no-optimize`, custom `--cfg-value`, or custom `--inference-timesteps` unless the user explicitly requests experimentation.
- If the caller supplies a parenthetical cue at the start of the text, treat it as a micro-prosody nudge only.
- Keep such cues very short and sparse so the model stays close to the cloned speaker identity.
- Prefer cues about discourse position or transition, such as `clear start`, `steady continuation`, `slight contrast`, or `gentle wrap-up`, over strong mood or performance descriptions.
- If a cue makes the output sound less like the speaker, remove it rather than strengthening it.
- Prefer handling text normalization at the TTS stage rather than pushing engine-specific rewrites upstream into the scriptwriter skill.
- If the narration contains digits, dates, abbreviations, passwords, or mixed-language tokens and the raw clone sounds garbled, test `--normalize` first so `wetext` can expand the text automatically.
- Only manually rewrite the target text when `wetext` normalization is unavailable, insufficient, or the user explicitly wants hand-normalized phrasing.
- Use the local low-VRAM defaults first when staying in the wrapper:
  `optimize=False`, `load_denoiser=False`, `cfg_value=2.0`, `inference_timesteps=8`.
- Plain English and Polish TTS were verified to fit in VRAM at roughly `5247 MiB allocated` and `~5.6-5.7 GiB reserved`.
- Start with plain TTS before cloning. Cloning is the next likely point of VRAM failure.

### 3. Pronunciation QA

Use the same standalone virtualenv for WhisperX pronunciation QA. Always prepend FFmpeg to `PATH` before running QA:

```powershell
$env:PATH='C:\Users\kdeptula\Documents\FFmpeg\ffmpeg-master-latest-win64-gpl\bin;' + $env:PATH

& '.\.venv\Scripts\python.exe' 'scripts\tts_pronunciation_qa.py' `
  --project-dir 'C:\path\to\project' `
  --script 'C:\path\to\project\script.json' `
  --tts-dir 'C:\path\to\project\tts\clean' `
  --language pl `
  --output 'C:\path\to\project\manifests\tts-pronunciation-qa.json'
```

For Polish QA use `--language pl`, not `pl-PL`.

### 4. Target-Only Clone Outputs
The required output for every cloned chunk is **target speech only**. The saved WAV must not include the prompt/sample transcript at the beginning.

Use the VoxCPM prompt/reference path with `--prompt-audio`, `--prompt-text`, and `--reference-audio`; prefer wrapper batch mode for chunk generation with shared settings, and use single-output mode for one-off regeneration. The wrapper batch path reuses one prompt/reference cache across all input lines. On the current local VoxCPM2 path this normally writes target-only audio: prompt audio/text are used as conditioning inputs, while the saved waveform contains the requested text.

Do not trim by default. After generation, verify the raw output before using it:

- Compare the raw output duration against the prompt sample duration and the expected target duration.
- If the raw output is shorter than the prompt sample, or otherwise clearly target-only, copy it directly to the clean output path.
- If the raw output audibly or durationally contains the prompt/sample prefix, trim only the prefix and save a clean target-only file.
- Never pass a WAV containing prompt/sample speech to lip-sync, concatenation, or final narration.
- Use `ffprobe` duration checks for the raw, clean, and prompt sample files, and record the check in the caller's active TTS manifest. In `youtube-autopipeline`, the current manifests are `manifests\tts-prototype-manifest.json` and `manifests\final-audio-manifest.json`; do not create `manifests\tts-manifest.json` for that pipeline.

Keep a manifest field such as `trim_mode`:

- `target_only`: raw output was already clean and was copied unchanged.
- `trimmed_prefix`: raw output contained prompt/sample speech and was trimmed.
- `manual_review`: automatic verification could not determine whether the prefix was present.

Use prefix trimming only as a corrective step for observed prefix contamination, not as the normal VoxCPM2 clone path.

### 5. Notes
- VoxCPM2 uses the installed `voxcpm` package and the local wrapper `scripts\voxcpm_tts.py`.
- For prompt/reference cloning, use `scripts\voxcpm_tts.py --input ... --output-dir ...` for chunk generation with shared settings, or `scripts\voxcpm_tts.py --text ... --output ...` for one-off regeneration.

## References
- **Model**: `openbmb/VoxCPM2`
