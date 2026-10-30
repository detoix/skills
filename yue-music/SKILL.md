---
name: yue-music
description: Generate local music, instrumental underscores, jingles, and songs with YuE2. Set up the model and native runtime, render prompts, refine saved takes, and check audio files. Use for YuE2 music generation; speech narration belongs to a TTS workflow.
---

# YuE Music

Use YuE2 through its portable C++ runtime to make music from a style description and optional lyrics. This skill contains its installer, pinned model manifest, backend patches, score-helper installer, generation launcher, and audio inspector. Resolve every bundled resource relative to this skill directory.

## Prepare the runtime

Set `YUE_SKILL` to this skill's resolved directory. Keep downloads, source checkouts, compiled programs, and installation metadata in its ignored `.runtime/` directory. Keep prompts, generated audio, logs, and listening decisions in the user's project.

Check an existing installation without loading a model:

```bash
python3 "$YUE_SKILL/scripts/yue.py" check
```

For a fresh installation or backend change, read [references/runtime.md](references/runtime.md). Inspect the platform, memory, disk space, hardware devices, and native tools, install missing dependencies, then run `setup`. Select a backbone filename from `assets/models.json` with `--model FILENAME` before the subcommand; this flag applies to setup, check, generation, and replay. It may be omitted when exactly one backbone is installed. The installer downloads the pinned engine, selected backbone, and VAE, verifies SHA-256, applies the backend patches, and builds the runtime. CPU needs no NVIDIA GPU; Vulkan can use supported Intel or AMD hardware. For native Windows, follow [references/windows.md](references/windows.md). Verify the selected device in the actual generation log.

`setup` installs without generating audio. `check` and `--dry-run` also perform no inference. Honor requests to prepare only, defer generation, or limit CPU use. Reuse a valid installation instead of downloading another copy.

## Direct and generate a take

Infer instrumentation, mood, pace, duration, and space for narration from the brief. Write concise comma-separated style tags. Distinguish an attention-grabbing theme from a background texture: for neutral ambient underscore, sustained sound, stable harmony, restrained dynamics, and smooth timbral change suit a different role from prominent melodies, ostinatos, beats, or dramatic sections.

For lyrics stored in a file, pass `generate --lyrics-file path/to/lyrics.txt` to read UTF-8 directly in Python instead of passing text through shell decoding. JSON artifacts escape non-ASCII characters without changing the decoded lyrics. Before inference, compare the dry-run lyrics with the source text, including diacritics; a valid JSON file alone does not prove the words are intact.

For instrumental output, read [references/instrumental.md](references/instrumental.md) before generating. Prefer a model-planned score with Vocal notes transferred into Ins, then render fresh semantics with the converted score. The bundled score-helper wrapper installs and verifies its pinned standard-library tools automatically. `[Instrumental]` and negative vocal tags alone do not ensure silence from voices. Check any adapter's own license before using it.

Match the requested duration and musical form; use a short audition when that is what the user requested. For a bounded duration, read the request notes in [references/runtime.md](references/runtime.md) and verify the decoded length before delivery. Choose an audition long enough to judge the intended music. Keep the normal 32 synthesis steps when assessing a finished sound. The launcher's 10-second, 12-step, `cot=off` defaults are inexpensive sketches, not a strict instrumental workflow. Use a native request for score-conditioned output, lyrics, or other settings:

```bash
python3 "$YUE_SKILL/scripts/yue.py" generate \
  --request "audio/prompt.json" --threads 2 \
  --out-dir "audio/take-01"
```

`--dry-run` validates and prints the request without creating output, downloading anything, or loading weights. Set `--device` explicitly for a verified backend; see the runtime reference for `Vulkan0`, `CPU-BLAS`, `--clamp-fp16`, and adapters. The launcher uses low priority and bounds CPU threads; run one generation per runtime at a time.

Read the [runtime reference](references/runtime.md) for context budgets, formats, seeds, and equivalent-work performance comparisons. Duration is an upper budget; hitting it can produce an abrupt ending. Longer material and more synthesis steps need a measured estimate. Choose sample length for musical judgment; shortening the requested work is not a backend speedup.

## Refine without recomposing

Every take retains its request, log, 24-bit stereo WAV, actual seeds and semantic tokens in `audio.json`, plus separate token and latent files. To render a promising take with more synthesis steps while keeping its composition:

```bash
python3 "$YUE_SKILL/scripts/yue.py" replay \
  --request "audio/take-01/audio.json" --steps 32 --threads 2 \
  --out-dir "audio/take-01-refined"
```

Keep approved takes intact. A replay reuses semantic tokens; changing style, lyrics, or the score calls for a new generation. More acoustic steps do not remove a melody or vocal part already represented in the saved tokens.

## Verify and deliver

The launcher records actual elapsed time and performs technical audio inspection. Inspection can also run independently:

```bash
python3 "$YUE_SKILL/scripts/inspect_audio.py" "audio/take-01/audio.wav" \
  --latents "audio/take-01/acoustic.vae" --output "audio/take-01/quality-check.json"
```

Check duration, successful decoding, finite samples and latents, signal level, and sustained near-full-scale runs. A single full-scale sample can be normal peak normalization. Technical checks cannot establish musical quality, prompt adherence, natural endings, or the absence of singing. Listen when audio inspection is available; otherwise state which technical checks passed and give the user playable audio without inventing a listening judgment.

Deliver the audio, its prompt, actual duration and generation time, and any material limitation. Keep native source audio and replay data for later refinement. Do not copy runtime files, personal paths, hardware reports, project material, or generated recordings into the public skill package.
