# Native VoxCPM2 with Vulkan

Use the [llama.cpp-omni VoxCPM2 runtime](https://github.com/tc-mb/llama.cpp-omni/tree/master/tools/omni/voxcpm2) at revision `e1047e121ee83cfa70865c0e4d7ebfb858c2cc69`. Keep its checkout in this skill's ignored `.runtime/engine` and weights under `.runtime/models`. Keep outputs and voice libraries in the user's project.

Build with `-DGGML_VULKAN=ON -DGGML_CUDA=OFF -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON`, targeting `voxcpm2-cli` and `llama-quantize`. Follow the upstream converter instructions to make the F32 BaseLM quantization input, the Q8_0 BaseLM used for synthesis, and the F16 acoustic baseline. Retain model and engine revisions and checksums locally.

The narration adapter prepares temporary **16 kHz PCM16 WAV** prompts for the VoxCPM2 audio encoder. For other input rates it uses band-limited polyphase resampling with a Kaiser window (beta 8.6). This avoids aliasing from the CLI’s linear decimation of 48 kHz inputs. Library masters and synthesis output can use 48 kHz. Provenance records the original and prepared hashes, sample rates and resampling parameters.

For `scripts/narrate.py`, put `executable`, `base_model` and `acoustic_model` in the ignored `.runtime/narrate.json`. Paths can be absolute or relative to that file. Optional fields are `timesteps` (30), `cfg` (2), `max_steps` (1000), `backend_marker` (an exact log substring), `batch` (false when omitted), and `batch_rows` (1 when omitted). Run it with an interpreter providing NumPy, SciPy and SoundFile. The adapter uses continuation cloning and records line IDs, approved mood transcripts, per-line seeds, and model and audio hashes. It checks the configured backend, WAV contents, and decode cap.

## Persistent narration process

Apply [voxcpm2-batch.patch](../patches/voxcpm2-batch.patch) to the pinned checkout and rebuild `voxcpm2-cli` with the Vulkan flags above. Point `executable` to the rebuilt CLI and set `"batch": true`. A script loads models once per process and reuses encoded prompts. Set `"batch_rows": 2` to run LocDiT for two lines together. Each line keeps its own seed and stopping point, and the solver runs at the configured step count. A single remaining line uses the one-line solver. `"batch_rows": 1` synthesizes lines sequentially in the same process. `"batch": false` uses standalone calls and works with the upstream CLI.

Paired and one-line computations can produce different takes at the same seed. Provenance records the effective `batch_rows`, and paired takes include `batch_partner` and `batch_lane`. To reproduce a paired take, replay the same ordered pair with the original prompts, seeds, settings and runtime.

## Selective LocDiT Q8_0

Generate a separate acoustic model with Q8_0 weights for the attention and MLP projections in the 12 LocDiT transformer blocks. The converter preserves the other acoustic tensors and metadata. Keep the F16 acoustic model for reproducing F16 takes. Stage 2 still uses 30 solver steps and CFG 2.

```bash
"$TTS_SKILL/.venv/bin/python" "$TTS_SKILL/scripts/quantize_native_locdit.py" \
  "$TTS_SKILL/.runtime/models/gguf/VoxCPM2-Acoustic-F16.gguf" \
  "$TTS_SKILL/.runtime/models/gguf/VoxCPM2-Acoustic-LocDiT-Q8_0.gguf"
```

The converter uses the `gguf` package from native model conversion. Set `acoustic_model` to the new file in the runtime JSON and keep the BaseLM at Q8_0. Confirm Vulkan offload and compare with the F16 configuration on the same lines, references, seeds, and solver settings. Quantization can change timing, pronunciation, and speaker likeness. Review the intended voice and wording on representative takes before using the variant on a new voice library. Use `--native-config` to select the F16 configuration for existing F16 projects.

## Standalone CLI examples

For direct cloning calls, use a band-limited 16 kHz PCM16 copy of the reference. FFmpeg can prepare one with `ffmpeg -i voice.wav -ar 16000 -c:a pcm_s16le voice-16k.wav`.

```bash
TTS_NATIVE="$TTS_SKILL/.runtime/engine/build-vulkan-local/bin"
TTS_MODELS="$TTS_SKILL/.runtime/models/gguf"

"$TTS_NATIVE/voxcpm2-cli" \
  -t "(A warm adult male voice, clear diction, friendly tone)Dzień dobry! To jest nowy, syntetyczny głos." \
  --timesteps 20 --cfg 2 --seed 42 -o voice.wav \
  "$TTS_MODELS/VoxCPM2-BaseLM-Q8_0.gguf" "$TTS_MODELS/VoxCPM2-Acoustic-F16.gguf"

"$TTS_NATIVE/voxcpm2-cli" \
  -t "To jest nowy tekst wypowiedziany klonem tego głosu." \
  --prompt-wav voice-16k.wav --prompt-text "Dzień dobry! To jest nowy, syntetyczny głos." \
  --timesteps 30 --cfg 2 --seed 43 -o clone.wav \
  "$TTS_MODELS/VoxCPM2-BaseLM-Q8_0.gguf" "$TTS_MODELS/VoxCPM2-Acoustic-F16.gguf"
```

Verify the Vulkan device, `custom component backend=Vulkan0`, and BaseLM GPU offload in the log when targeting Vulkan. The CLI's `--steps` caps acoustic patches and `--timesteps` sets the CFM solver steps. A 200-patch cap is about 32 seconds for VoxCPM2. Check for cap truncation before delivery.

Use `-r voice-16k.wav` for reference-only cloning. In this revision, prompt audio plus transcript selects continuation cloning and takes precedence over `-r`; passing both does not enable the Python API's additional reference-conditioning path. Do not claim exact equivalence to its Ultimate Cloning mode. Preserve an exact transcript for continuation and assess actual words and voice identity by listening.

Compare engines using equivalent text, references and timesteps before making speed claims. See the [official on-device guide](https://github.com/OpenBMB/VoxCPM#-on-device-inference-llamacpp-omni) for upstream scope.
