# Runtime setup and native request details

## Self-contained installation

The skill bundles source and model identities, download/verification logic, build commands, backend patches, a pinned score-helper installer, generation/replay tooling, and audio inspection. Weights and the compiled runtime are downloaded or built inside the ignored `.runtime/` directory; they do not ship in Git. The workflow needs a host Python 3.9+ interpreter and native build/audio tools.

Set `YUE_SKILL` to the skill's actual directory. Native prerequisites are Git, CMake 3.19+, a C/C++ compiler and its build tool, curl, FFmpeg, and ffprobe. Install missing prerequisites using the host's package manager within the user's authorized scope. Typical package sets:

- Debian/Ubuntu: `build-essential cmake git curl pkg-config ffmpeg libopenblas-dev`.
- Fedora: `gcc gcc-c++ make cmake git curl pkgconf-pkg-config ffmpeg-free openblas-devel`.
- Arch: `base-devel cmake git curl pkgconf ffmpeg openblas`.
- macOS: Xcode command line tools, then Homebrew packages `cmake git curl pkg-config ffmpeg openblas`.
- Windows: native 64-bit Python, Git, CMake, MSVC Build Tools with the C++ desktop workload and Windows SDK, curl, FFmpeg, and ffprobe. Follow the [Windows procedure](windows.md).

The agent should install missing dependencies and continue setup, rather than requiring the user to assemble a separate project or find model links. Native package installation may require the platform's normal administrator permissions. No Python packages or other skills are needed by the bundled scripts.

For a fresh installation, set `YUE_MODEL` to a backbone filename from [assets/models.json](../assets/models.json) and pass `--model FILENAME` before `setup`. Subsequent commands can omit it when exactly one backbone is installed; otherwise pass the intended filename explicitly.

For a dependency-minimal CPU build:

```bash
python3 "$YUE_SKILL/scripts/yue.py" --model "$YUE_MODEL" setup --jobs 2
python3 "$YUE_SKILL/scripts/yue.py" check --hash
```

GGML's native CPU kernels need no BLAS installation. For accelerated alternatives, use the backend procedures below. CPU remains the portable default. macOS builds may also include Metal through the native project's defaults; select a device actually available in that build.

`setup --build-only` builds and checks the native tools without downloading model weights; `check --binaries-only` verifies that installation without requiring models. Run ordinary `setup` afterward to add the verified weights.

The installer stops on download, checksum, patch, or compilation failure and preserves diagnostics. Download retries are bounded. Completed, valid model files are reused. `setup --rebuild` rebuilds the pinned source; it does not replace another revision or silently discard source changes. A different installation directory can be selected with `--runtime` before the subcommand. Installation directories must be writable.

Pinned source: [ServeurpersoCom/yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp), revision `8af01740686824ffd4a1839a457954f42e2a8ce7`. Its Git submodule identifies the required GGML revision. The available backbones, required VAE, and SHA-256 values are in [assets/models.json](../assets/models.json), pointing to the public [YuE2 GGUF model repository](https://huggingface.co/Serveurperso/YuE2-GGUF). The generator and VAE are sufficient for text-to-music. Transcription/cover models are separate capabilities and are not downloaded by this basic workflow.

The public source, base models, and optional adapters have separate licenses. Keep their licenses with the private runtime. Read current authoritative terms when publication or commercialization matters; do not infer weight or adapter terms from the code license or extend a base-model grant to a separate contributor's weights.

The bundled [unmasked-attention patch](../assets/nar-unmasked-attention.patch) omits an all-zero additive mask from NAR flash attention. Every query still sees the complete intended key range. The patch leaves model weights, precision settings, the semantic stream, solver steps, and the F32 attention fallback unchanged. Performance depends on the backend and tensor shape; validate numerical output and measure equivalent work on the selected backend.

## Select and verify a backend

### Vulkan hardware

Check the host driver and hardware with `vulkaninfo --summary`. A software renderer such as llvmpipe is not evidence of GPU acceleration. On Debian/Ubuntu, common prerequisites are `libvulkan-dev glslc spirv-headers vulkan-tools` and the appropriate vendor driver; Mesa-based Intel/AMD hosts commonly use `mesa-vulkan-drivers`. Package names differ elsewhere. Install missing dependencies before configuring:

```bash
python3 "$YUE_SKILL/scripts/yue.py" setup --backend vulkan --jobs 2
python3 "$YUE_SKILL/scripts/yue.py" check
python3 "$YUE_SKILL/scripts/yue.py" generate \
  --request "audio/prompt.json" --device Vulkan0 --clamp-fp16 --threads 2 \
  --out-dir "audio/take-vulkan"
```

`Vulkan0` is an example registry device name, not a guarantee that the first device is the intended GPU. Confirm its description and the selected backend in the log. Driver visibility in the host and device access in the execution environment must both work. A shared-memory GPU still needs sufficient memory for weights, the context cache, and working tensors.

Keep default flash attention enabled on this pinned engine. Its [numerical test notes](https://github.com/ServeurpersoCom/yue2.cpp/blob/8af01740686824ffd4a1839a457954f42e2a8ce7/docs/ARCHITECTURE.md) report an incorrect Vulkan `--no-fa` fallback. `--clamp-fp16` is available to bound hidden states to the FP16 range; retain it when comparing against a validated configuration. Do not substitute it for finite-output and numerical checks.

For drivers that time out on long compute submissions, GGML exposes `GGML_VK_SERIALIZE_SUBMISSIONS=1` and `GGML_VK_MAX_NODES_PER_SUBMIT`. A cap of `1` is a conservative diagnostic setting; measure larger caps with the same saved semantic stream before adopting them. Planning and synthesis can respond differently. These are process-local environment controls, not changes to the song's steps or duration. See the [submission-size control](https://github.com/ggml-org/llama.cpp/pull/24872) and [serialization report](https://github.com/ggml-org/llama.cpp/issues/27634). The pinned implementation enables serialization when the variable is present, so a value of `0` still enables it; unset it to disable it.

CUDA builds use `setup --backend cuda` with a matching CUDA toolkit and driver. Backend availability and relative speed are hardware-dependent; verify rather than promising acceleration from compilation alone.

### CPU with BLAS

With OpenBLAS development files installed, build with `setup --blas on` (OpenBLAS is the default vendor). On Linux with GNU C++, select an existing Intel MKL installation explicitly through `--mkl-root`; the installer chooses GNU-threaded LP64 MKL. Other compiler/platform combinations should use a supported BLAS vendor instead. Sequential MKL does not become multithreaded merely by setting `MKL_NUM_THREADS`.

The bundled scheduler patch exposes `--device CPU-BLAS`: BLAS handles supported matrix operations before CPU fallback while the model retains CPU attention behavior. A build with `GGML_BLAS=ON` running as `--device CPU` does not activate that scheduler path. Do not select the raw `BLAS` registry device as if it were a GPU.

```bash
python3 "$YUE_SKILL/scripts/yue.py" setup --blas on --jobs 2
python3 "$YUE_SKILL/scripts/yue.py" generate \
  --request "audio/prompt.json" --device CPU-BLAS --threads 4 \
  --out-dir "audio/take-blas"
```

Confirm BLAS activation and the actual thread limit in the log. BLAS benefits depend on matrix shape; large synthesis operations and token-by-token planning need not improve equally. The launcher bounds GGML, OpenMP, and BLAS thread counts together. Avoid competing OpenMP runtimes and do not increase threads without measuring throughput under the intended workload.

### Measure equivalent work

Compare backends sequentially using the same saved semantic tokens, score/prefix, model quantization, noise seed, synthesis steps, duration, guidance, context budget, and thread limit. Keep clamping and other numerical settings recorded. A low-step replay can isolate a performance question, but cannot establish finished music quality or the speed of a longer 32-step generation.

Record wall time and stage times, selected physical device, build configuration, and any competing workload. First execution can include compilation or initialization costs; distinguish these from steady computation without hiding them. Check output shape, finite latents/audio, and numerical differences against the reference. Quantify a tolerance appropriate to the comparison rather than requiring bit-identical audio across backends. Report whole-job acceleration separately from a single matrix benchmark. Keep host-specific reports and timings in the user's project, outside the public skill.

## Request and output behavior

`generate --style` creates a short request with `cot="off"`, `cfg_scale=1.0`, 12 synthesis steps, one track, `peak_clip=0`, and `output_format="wav24"`. These are preview defaults, configurable through a native JSON request. The CLI defaults to 2 CPU threads. Choose a thread count for the available hardware and other active work.

Important native fields:

| Field | Meaning |
| --- | --- |
| `style`, `lyrics` | Musical style tags and lyric/section conditioning. |
| `cot` | `off` skips score planning; `full` plans melody and chords; `melody` plans a melody. |
| `abc` | Supplied score; used with `cot=full` or `cot=melody` and bypasses score generation. `cot=off` ignores it. |
| `duration` | Maximum semantic budget in seconds; the model may finish earlier. |
| `steps` | Flow-matching steps. More steps cost more computation; evaluate their audible benefit. |
| `lm_seed`, `seed` | Separate seeds for token generation and acoustic noise. Actual values are retained in the output replay JSON. |
| `semantic_tokens` | Saved semantic stream; enables synthesis replay without composing again. |
| `cfg_scale=1.0` | Uses one semantic guidance branch. The native default for `cot=off` otherwise uses two. |
| `output_format` | Native formats include `mp3`, `wav16`, `wav24`, `wav32`; the bundled launcher preserves `wav24`. |
| `abc_sampling`, `semantic_sampling` | Native per-stage sampling budgets and temperatures. |
| `adapters` | Requested adapter names and scales; also pass `--adapters-dir` so the native loader can discover their files. |

`--max-seq` is optional. The runtime's native context is the default; a smaller context can save memory for short requests. Account for prompt, generated/supplied ABC, and audio-frame tokens, not duration alone. Short `cot=off` previews can use 4096; do not apply that limit universally to long tracks or score planning. An insufficient context can fail generation. The native semantic stream is 25 frames per second.

A requested duration range needs both a complete musical form and an appropriate semantic budget. Check the planned score's nominal length before expensive synthesis. `semantic_sampling.min_tokens` prevents an end token before its floor, while `max_tokens` and `duration` cap the stage. The stream is 25 frames per second; account for the decoder's small edge trim when computing a strict lower bound. A token floor alone can prolong an underspecified composition. Verify the actual decoded duration against the user's range before delivery.

There is no dedicated instrumental boolean in this pinned port. Use the bundled [instrumental procedure](instrumental.md) for score planning and conversion. It describes stronger conditioning, not a guarantee of voice-free output. Native replay JSON can omit `cot` when it is the default `full`; interpret the schema default rather than treating absence as `off`.

The thread override is supplied by [assets/cpu-threads.patch](../assets/cpu-threads.patch). Upstream's pinned CPU backend otherwise estimates the number of threads itself; OpenMP environment settings alone do not override that count. The launcher also bounds OpenMP/BLAS threads and applies low process priority where supported.

Each output directory is a single take and must be empty before generation. It contains `audio.wav`, `audio.json` (native replay), `request-input.json`, `run-info.json`, `generation.log`, `semantic.tokens.csv`, `acoustic.vae`, and optionally `score.abc` when a score exists. Interrupting the launcher stops its child process and retains available logs; partial data is not promised to support resume. The per-runtime lock prevents overlapping setup/generation jobs.

The audio inspector uses FFmpeg and the Python standard library, streams PCM, and can check raw float32 latent values. It reports technical results, never an automatic listening verdict. Duration budgets can cut the result mid-phrase; fades, looping, gain adjustments, and ducking are later editorial choices, with the original retained.
