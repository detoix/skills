---
name: tts
description: Use when you need local neural speech generation or voice cloning with the MOSS-TTS, OmniVoice, or VoxCPM2 engines, especially when choosing between stable long-form TTS, tag-driven voice design, and GPU-first expressive synthesis.
---

# MOSS, OmniVoice & VoxCPM2 TTS

This skill provides access to three local TTS engines for speech generation and voice cloning.

## Environment Note
**OmniVoice** and **VoxCPM2** are installed in the local speech generation environment at:

`%USERPROFILE%\Downloads\speech-gen\venv`

Prefer that interpreter explicitly for local runs:
```bash
%USERPROFILE%\Downloads\speech-gen\venv\Scripts\python.exe generate_omnivoice.py ...
%USERPROFILE%\Downloads\speech-gen\venv\Scripts\python.exe generate_voxcpm.py ...
%USERPROFILE%\Downloads\speech-gen\venv\Scripts\python.exe -m voxcpm.cli ...
```

For YouTube autopipeline projects, run TTS production commands only through the guarded production wrapper so the Creative
Approval Gate is checked immediately before audio generation:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\guarded_production_command.py `
  --project-dir <project-dir> `
  -- <tts command...>
```

The wrapper scripts such as `generate_voxcpm.py` and `generate_omnivoice.py` live in:

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
  --seed 424242 \
  --steps 4 \
  --max-len 80 \
  --output /home/detoix/.local/share/voxcpm2-cpu/outputs/out.wav
```

Verified runtime facts:
- VoxCPM source commit: `19b6bf7590025418821a86dcb817504e0ad7e5df`.
- Uses CPU-only PyTorch: `torch==2.11.0+cpu`, `torchaudio==2.11.0+cpu`; `torch.cuda.is_available() == False`.
- Model/cache/venv are sandboxed under `/home/detoix/.local/share/voxcpm2-cpu`; current verified size was about `7.3G` after model download.
- Cleanup if this runtime must be removed: `/home/detoix/.local/share/voxcpm2-cpu/cleanup_runtime.sh`.
- Determinism verified for fixed settings: seed `424242`, steps `4`, `cfg_value=2.0`, `max_len=80` produced identical WAV SHA256 across two runs: `8a0b6436a9e61da5c785935da7cc392fa8792d39ee1279f2dd7d121719b1fc1a`.
- Changing `--steps` changes the sampling trajectory and may change duration/prosody; do not treat a 4-step draft as the same sample simply refined at 6/8 steps.
- Performance on the i5-2520M CPU is slow: short full prompt+reference clones take roughly 6-8 minutes for ~3-4 seconds of audio. Not suitable for 1-minute narration unless batching/prompt-cache reuse is implemented.
- Peak RAM during clone is about `10.7-11G`; do not run clone jobs in parallel.

The script writes a JSON manifest next to each WAV containing seed, steps, hashes, VoxCPM commit, Torch version, device, and output SHA256.

## Workflow

### 1. Engine Selection
- **MOSS-TTS (GGUF)**: Best for stable, high-quality generation. Ideal for long-form content.
- **OmniVoice**: Best for rapid voice design using specific tags or zero-shot cloning.
- **VoxCPM2**: Best for GPU-first expressive synthesis and basic cloning when you want to test whether it can outperform MOSS on the local RTX 4050 6 GB setup.

### 2. Quick Selection Guide
- Use **MOSS-TTS** when stability matters most or the text is longer.
- Use **OmniVoice** when the user wants a voice described with explicit tags such as accent, gender, age, or pitch.    
- Use **VoxCPM2** when the user wants cloning from a real speech sample.
- When the user provides both a speech sample and its exact transcription, use the `clone` CLI path as the default, not as an optional upgrade.
- Do not ask for generic voice labels such as `male calm` or `female assertive` if a cloned voice is the goal.

### 3. Speech Generation

#### Using MOSS-TTS
```bash
python generate_moss.py --text "Your text" --output "out.wav" [--reference "ref.wav"]
```

#### Using OmniVoice
```bash
.\venv\Scripts\python.exe generate_omnivoice.py --text "Your text" --instruct "tags" --output "out.wav"
```

#### Using VoxCPM2
Plain TTS:
```bash
.\venv\Scripts\python.exe generate_voxcpm.py --text "Your text" --output "out.wav"
```

Basic cloning:
```bash
.\venv\Scripts\python.exe generate_voxcpm.py --text "Your text" --reference "ref.wav" --output "out.wav"
```

Default cloning path when the user has a speech sample and exact transcription:
```bash
.\venv\Scripts\python.exe -m voxcpm.cli clone ^
  --text "Final target text" ^
  --prompt-audio "voice_sample.wav" ^
  --prompt-text "Exact transcript of voice_sample.wav" ^
  --reference-audio "voice_sample.wav" ^
  --output "out.wav"
```

Use this mode by default for cloning whenever the user can provide the exact transcript of the sample audio. This was the best-performing local workflow for Polish cloning in practice.

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

### 4. VoxCPM2 Practical Guidance
- The local wrapper `generate_voxcpm.py` only exposes plain TTS and basic `--reference` cloning.
- For cloning, prefer the upstream CLI entrypoint:
  `.\venv\Scripts\python.exe -m voxcpm.cli ...`
- Treat `prompt-audio + prompt-text + reference-audio` as the default clone path when the user can provide a transcript of the sample.
- `prompt-text` should be the exact spoken words from the sample audio, not a paraphrase.
- If the user wants cloning and does not provide a transcript, ask for it explicitly before continuing.
- Only fall back to basic `--reference` cloning if the user explicitly approves that downgrade.
- Avoid adding style instructions if the goal is to preserve the sample's original speaking style as closely as possible.
- When reproducing a known-good clone command, do not add extra tuning flags unless the user explicitly asks for them. 
- For the default `voxcpm.cli clone` path, do not add `--normalize`, `--control`, `--no-optimize`, custom `--cfg-value`, or custom `--inference-timesteps` unless the user explicitly requests experimentation.
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

### 5. Target-Only Clone Outputs
The required output for every cloned chunk is **target speech only**. The saved WAV must not include the prompt/sample transcript at the beginning.

Use the default `voxcpm.cli clone` command with `--prompt-audio`, `--prompt-text`, and `--reference-audio`. On the current local VoxCPM2 CLI this normally writes target-only audio: prompt audio/text are used as conditioning inputs, while the saved waveform contains the requested `--text`.

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

### 6. Notes
- VoxCPM2 uses the installed `voxcpm` package and the local wrapper `generate_voxcpm.py`.
- The wrapper is convenient, but it does not expose the stronger `clone` workflow that uses prompt audio and a transcript.
- When the user wants a cloned voice, use `python -m voxcpm.cli clone` instead of the wrapper unless they explicitly ask for a fallback.
- VoxCPM2 basic clone mode uses `--reference` and maps to the upstream `reference_wav_path` API.
- `generate_voxcpm_samples.py` prepares the numbered sample set `voxcpm_1.wav`, `voxcpm_2.wav`, `voxcpm_3.wav`, and `voxcpm_clone_test.wav`.
- The clone sample expects a placeholder reference file at `temp\voxcpm_clone_reference.wav`.

## References
- **Config**: MOSS-TTS uses `moss_local_config.yaml`.
- **Models**:
  - MOSS: `models/MOSS-TTS-GGUF/MOSS_TTS_Q4_K_M.gguf`
  - OmniVoice: `drbaph/OmniVoice-bf16`
  - VoxCPM2: `openbmb/VoxCPM2`
