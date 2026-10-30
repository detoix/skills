# tts: VoxCPM2 narration skill

An agent skill (Claude Code, or any agent that reads `SKILL.md`) for local text-to-speech with
[VoxCPM2](https://github.com/OpenBMB/VoxCPM) by OpenBMB: voice cloning from a short reference clip and
narration directed phrase by phrase. It grew out of months of Polish narration work (documentaries and
reels); the model speaks 30 languages and nothing in the skill is Polish-only.

## What it adds to VoxCPM2

- **Direction per phrase.** An English delivery instruction in parentheses before each line:
  `(whispering, intimate)Szeptem, jakbym zdradzał ci sekret.`
- **The first-word fix.** After an English instruction, the first word of another language can come out with
  English rules (Polish „Co” read „Ko”). The skill checks every take for it and retakes with a throw-away
  warm-up word, cut off afterwards by `scripts/cut_warmup.py`.
- **Settings that hold up:** cfg 2.0, 20 steps, no denoiser, a seed per take so a good take can be reproduced.
- **A faster CPU path:** float32, a compiled diffusion head and several lines decoded together
  (`scripts/voxcpm_fast.py`); same takes as the upstream sampler.
- **Intel GPU acceleration:** an optional OpenVINO diffusion head with CPU orchestration.
  Automatic selection prefers a compatible Intel GPU over CPU for both single lines and batches.
  GPU runtime failures fall back to CPU.
- **Checks:** ASR transcription, and per-word Whisper confidence to choose between takes of one line
  (`scripts/word_confidence.py`).

## Requirements

- Linux (tested) or macOS (CPU path, untested); on Windows, use WSL. [uv](https://docs.astral.sh/uv/) and FFmpeg.
- An NVIDIA GPU, or a CPU with about 14 GB of free RAM. A compatible Intel GPU with a working OpenCL driver
  can run the diffusion head; the rest still runs on CPU. A C++ compiler enables the
  compiled CPU path and its fallback.
- About 5 GB for the VoxCPM2 weights and about 0.5 GB for Whisper `small` (used by the checks), both
  downloaded from Hugging Face on first use.

## Install

```bash
git clone https://github.com/detoix/skills.git
mkdir -p ~/.claude/skills && cp -r skills/tts ~/.claude/skills/tts
~/.claude/skills/tts/scripts/setup_runtime.sh
```

Then ask the agent for a voiceover; it reads `SKILL.md` and drives the scripts. To run them yourself:

```bash
~/.claude/skills/tts/.venv/bin/python ~/.claude/skills/tts/scripts/voxcpm_tts.py \
  --input lines.txt --output-dir takes --reference-audio voice.wav --seed 1000
```

`lines.txt` holds one line per take, each with its own instruction in parentheses. Every option is in
`SKILL.md` and `--help`.

The default `--device auto` chooses CUDA first, then OpenVINO on an available Intel GPU,
then CPU. Intel GPU execution is preferred over CPU for single lines as well as batches. The installer detects Intel GPU hardware on Linux; `OPENVINO=1 scripts/setup_runtime.sh` installs
the optional runtime explicitly, and `OPENVINO=0` skips it. Install Intel's GPU OpenCL driver separately.
Use `--device cpu` to force CPU or `--device openvino` to request the Intel GPU path explicitly.

OpenVINO exports are generated locally and cached outside the skill folder; first use includes export and
compilation time. FP16 execution can change a take, so keep the backend and precision with its seed and
review a representative sample. Performance depends on the device and batch size; no universal speedup
is assumed. Do not publish model caches, reference voices, generated recordings or local benchmark logs.

## Responsible use

Clone only your own voice, or a voice whose owner agreed to it. VoxCPM2's model card forbids impersonation,
fraud and disinformation and asks that AI-generated speech be labelled as such.

## License

The skill (this folder) is MIT-licensed, see [LICENSE](LICENSE). VoxCPM2 and its weights are Apache-2.0,
by OpenBMB.
