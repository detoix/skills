# Instrumental music and background textures

Use this procedure when vocals, humming, or choir would make a take unsuitable. It follows the [official instrumental workflow](https://github.com/multimodal-art-projection/YuE/blob/main/skills/yue2-music/instrumental/SKILL.md), adapted to the bundled native runtime. The bundled `scripts/instrumental_tools.py` installs hash-verified, pinned standard-library score helpers and their license into ignored `.runtime/instrumental-tools/`; no separate checkout, Python packages, or score-planning model are required. Voice-free output still needs an auditory check.

## Plan, transfer, render

For text-only requests, let YuE2 compose the score. Preserve a user's supplied score when one exists. Do not quietly replace model planning with an agent-written example melody. Write a native planning request with the intended `style`, `cot: "full"`, an explicit `lm_seed`, and empty lyrics or section tags without prose. Keep it in the project. For example, the core request fields are:

```json
{
  "style": "Instrumental, soft sustained synthesizer pads, stable harmony, restrained dynamics, slow smooth timbral movement, no vocals, no singing, no choir",
  "lyrics": "[Instrumental]",
  "cot": "full",
  "duration": 24,
  "steps": 32,
  "cfg_scale": 1.0,
  "lm_seed": 42,
  "seed": 42,
  "output_format": "wav24"
}
```

This example describes a neutral texture. Change its musical direction for the actual brief. Duration is a cap, not guaranteed score length. Set `YUE_RUNTIME` to the configured runtime directory (normally `"$YUE_SKILL/.runtime"`) and `YUE_MODEL` to the selected backbone filename, then run the native planner, using the same verified device and thread limits as synthesis:

```bash
YUE_THREADS=2 OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 \
  "$YUE_RUNTIME/bin/yue-plan" \
  --model "$YUE_RUNTIME/models/$YUE_MODEL" \
  --request "audio/plan-request.json" --device CPU \
  --out "audio/original.abc"
```

For Vulkan, use the verified registry device and add `--clamp-fp16`. A native planner invocation bypasses the launcher's lock and priority handling: run it sequentially with other operations using that runtime. A planning failure or truncated/unparseable score is not permission to synthesize a broken plan; retain diagnostics and repair or retry the planning stage within the task's scope.

The pinned `yue-plan` does not use request `duration` as a hard planning limit. A brief ambient request can still yield a full sectional song. Before conversion or synthesis, inspect note density, voice activity, chord changes, and sections against the brief. Transferring an unwanted melody into Ins does not turn it into an ambient texture. A static texture may instead need one held tone and unchanged harmony. Any agent-authored replacement or simplification must fit the user's authorization, retain the original plan, and explicitly record its authorship and musical changes.

Convert musical events, not just voice names. The helper transfers Vocal pitches, onsets, and durations to monophonic Ins while leaving rests and chords in Vocal. It preserves existing Ins material where it does not overlap; transferred Vocal notes take priority at overlaps, with changes recorded. Keep the original and review `transfer.json` before accepting any musical loss.

Save the intended style in `audio/style.txt`. Use new output directories:

```bash
python3 "$YUE_SKILL/scripts/instrumental_tools.py" convert \
  "audio/original.abc" --out-dir "audio/conversion"
python3 "$YUE_SKILL/scripts/instrumental_tools.py" validate \
  --abc "audio/conversion/score.abc"
python3 "$YUE_SKILL/scripts/instrumental_tools.py" prepare \
  --abc "audio/conversion/score.abc" --style-file "audio/style.txt" \
  --out-dir "audio/prepared" --seed 42
```

Validation checks the supported notation and event timing. Preparation writes `request.json`, the checked score, prompt, style, lyrics, and check records. Its `cot` is `full` with chord conditioning and `melody` for a chordless score; retain that checked value rather than forcing an incompatible mode. The wrapper's optional `--runtime` precedes the subcommand when using a nondefault installation.

The prepared request targets the official Python protocol. Merge its musical fields into the native request rather than passing it blindly to `yue-synth`. Preserve the chosen native duration, synthesis steps, guidance, planning seed, and output settings; omit the Python-only `id`. For example:

```bash
python3 - <<'PY'
import json
from pathlib import Path
base = json.loads(Path("audio/plan-request.json").read_text())
prepared = json.loads(Path("audio/prepared/request.json").read_text())
assert prepared["seed"] == base["seed"], "Keep the chosen acoustic seed consistent"
for field in ("abc", "style", "lyrics", "cot"):
    base[field] = prepared[field]
base.pop("id", None)
base.pop("semantic_tokens", None)
Path("audio/native-request.json").write_text(json.dumps(base, indent=2) + "\n")
PY
python3 "$YUE_SKILL/scripts/yue.py" generate \
  --request "audio/native-request.json" --device CPU --threads 2 \
  --out-dir "audio/instrumental-take"
```

Use the same seed in preparation and the intended native request; `seed` controls acoustic noise while `lm_seed` remains the native planning/token seed. Apply the selected Vulkan or CPU-BLAS flags when appropriate. The converted score must condition fresh semantic generation: discard old semantic tokens and planning prefixes. Check the output's saved score/request against the prepared input. An acoustic replay of old tokens does not apply the conversion. Retain both scores and the conversion/preparation records.

## Optional adapters

Load adapters only when their license and purpose fit the user's task. Pass a directory with `--adapters-dir`, and put the native adapter names/scales in the request's `adapters` array. Verify that the native log reports the requested adapter loaded; a JSON field alone is not evidence of application. Planner and synthesis support can differ: the pinned `yue-plan` CLI does not expose an adapter-directory option.

The community [Mothersuperior instrumental adapter](https://huggingface.co/Mothersuperior/YuE2-instrumental-cot-full-loras) targets the AR branch. Its author recommends `cot=full`, strength 1.0, and lyrics containing only `[instrumental]` or bare structure tags. Applying it only to NAR does not apply its intended planning behavior. Its own model card specifies CC BY-NC 4.0 and non-commercial use only. Do not silently include it in a workflow intended for commercial output; check for separate applicable permission or use another suitable approach. A base-model license grant does not establish permission from the adapter author.

## Evaluate the intended role

For ambient support under speech, assess continuity, dynamics, foreground melodies, rhythmic pulses, abrupt changes, and possible voice-like sound throughout the sample. Sparse instrument names alone do not imply low attention: a clear motif can dominate even a quiet mix. Do not fix a rejected melodic composition by turning it down and calling it ambient.

Keep a representative audition length and the actual generation settings in the record. Finite latents, normal signal levels, and correct score structure do not prove the absence of singing. If listening is unavailable, state that limitation and deliver the raw music for review without claiming an auditory pass. Rejected vocals or musical direction call for a new composition/conditioning decision, not merely more acoustic synthesis steps.
