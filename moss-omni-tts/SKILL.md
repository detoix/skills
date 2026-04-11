---
name: moss-omni-tts
description: High-quality neural speech generation and voice cloning using MOSS-TTS (GGUF) and OmniVoice. Use when you need to generate realistic audio from text, clone voices from reference samples, or design custom voices with descriptive tags.
---

# MOSS & OmniVoice TTS

This skill provides access to two powerful TTS engines for generating high-fidelity speech and performing zero-shot voice cloning.

## Environment Note
**OmniVoice** is installed in the project virtual environment. Always use the local venv:
```bash
.\venv\Scripts\python.exe generate_omnivoice.py ...
```

## Workflow

### 1. Engine Selection
- **MOSS-TTS (GGUF)**: Best for stable, high-quality generation. Ideal for long-form content.
- **OmniVoice**: Best for rapid voice design using specific tags or zero-shot cloning.

### 2. Speech Generation

#### Using MOSS-TTS
```bash
python generate_moss.py --text "Your text" --output "out.wav" [--reference "ref.wav"]
```

#### Using OmniVoice
```bash
.\venv\Scripts\python.exe generate_omnivoice.py --text "Your text" --instruct "tags" --output "out.wav"
```

**Valid English Tags (Strict):**
`american accent`, `australian accent`, `british accent`, `canadian accent`, `chinese accent`, `indian accent`, `japanese accent`, `korean accent`, `portuguese accent`, `russian accent`, `female`, `male`, `child`, `teenager`, `young adult`, `middle-aged`, `elderly`, `very high pitch`, `high pitch`, `moderate pitch`, `low pitch`, `very low pitch`, `whisper`.

## References
- **Config**: MOSS-TTS uses `moss_local_config.yaml`.
- **Models**:
  - MOSS: `models/MOSS-TTS-GGUF/MOSS_TTS_Q4_K_M.gguf`
  - OmniVoice: `drbaph/OmniVoice-bf16`

