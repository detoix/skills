# tts: VoxCPM2 narration skill

An agent skill (Claude Code, or any agent that reads `SKILL.md`) for local text-to-speech with
[VoxCPM2](https://github.com/OpenBMB/VoxCPM) by OpenBMB: voice cloning from a short reference clip and
narration directed phrase by phrase. It grew out of months of Polish narration work (documentaries and
reels); the model speaks 30 languages and nothing in the skill is Polish-only.

## What it adds to VoxCPM2

- **Two-stage cloning.** Direct an 8–15-second mood sample, choose it by ear, then read the final
  script from that sample and its exact transcript. Final takes use the sample's expression and pace.
- **A reusable voice library.** `scripts/narrate.py --plan` checks the script against approved samples
  without loading the model or generating audio. Make a sample only for a missing mood; keep it for
  future scripts. Whole-script narration loads the model once and groups lines by mood.
- **Settings that hold up:** CFG 2.0, 20 steps for mood samples, 30 for final takes, no denoiser;
  provenance records each take's actual seed, reference, sample, backend and precision.
- **A faster CPU path:** float32, a compiled diffusion head and several lines decoded together
  (`scripts/voxcpm_fast.py`); same takes as the upstream sampler.
- **Intel GPU acceleration:** an optional OpenVINO diffusion head with CPU orchestration.
  Automatic selection prefers a compatible Intel GPU over CPU for both single lines and batches.
  GPU runtime failures fall back to CPU.
- **Native Vulkan inference.** The GGUF runtime supports voice design and continuation cloning,
  with optional two-line diffusion batching for whole-script narration.
- **Checks:** word-by-word free ASR comparison, with conservative Polish phonetic equivalences and
  explicit review of every unresolved word edit (`scripts/tts_pronunciation_qa.py`), plus per-word
  Whisper confidence to rank takes (`scripts/word_confidence.py`).

## Python runtime requirements

- Linux (tested) or macOS (CPU path, untested); on Windows, use WSL. [uv](https://docs.astral.sh/uv/) and FFmpeg.
- An NVIDIA GPU, or a CPU with about 14 GB of free RAM. A compatible Intel GPU with a working OpenCL driver
  can run the diffusion head; the rest still runs on CPU. A C++ compiler enables the
  compiled CPU path and its fallback.
- About 5 GB for the VoxCPM2 weights and about 0.5 GB for Whisper `small` (used by the checks), both
  downloaded from Hugging Face on first use.

## Install

For native GGUF inference, see the [Vulkan runtime guide](references/native-vulkan.md).

```bash
git clone https://github.com/detoix/skills.git
mkdir -p ~/.claude/skills && cp -r skills/tts ~/.claude/skills/tts
~/.claude/skills/tts/scripts/setup_runtime.sh
```

Then ask the agent for a voiceover; it reads `SKILL.md` and drives the scripts. To run them yourself:

```bash
TTS_SKILL=~/.claude/skills/tts
"$TTS_SKILL/.venv/bin/python" "$TTS_SKILL/scripts/narrate.py" \
  --lines lines.json --library voices --plan
"$TTS_SKILL/.venv/bin/python" "$TTS_SKILL/scripts/narrate.py" \
  --lines lines.json --library voices --out takes --provenance provenance.json --seed 1000
```

`lines.json` is a list of `{"id", "say", "direction", "mood"}` objects (`mood` is optional).
The library holds `voice.wav`, approved mood samples and transcripts in `bank/bank.json`, and optional
mood-selection rules in `bank/rules.json`. `--plan` exits with 2 when the reference or any required
sample is missing or unusable. Follow `SKILL.md` to create and approve a missing mood; narration does
not generate mood samples itself. Every option is in `SKILL.md` and `--help`.

In the Python runtime, `--device auto` chooses CUDA first, then OpenVINO on an available Intel GPU,
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
