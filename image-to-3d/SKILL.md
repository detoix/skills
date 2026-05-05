---
name: image-to-3d
description: Standalone TRELLIS.2 GGUF image-to-3D generation on local Windows RTX GPUs without ComfyUI. Use when an agent needs to convert one image into a textured 3D asset (GLB/OBJ), set up the local TRELLIS.2 GGUF environment in this folder, download the required TRELLIS/DINOv3 model files, or troubleshoot partial / untextured mesh output on a 6 GB RTX 4050 class machine.
---

# Image-to-3D

Use the files in this folder as the source of truth. Do not route through ComfyUI.

## Run Order

1. If `.venv` is missing or broken, run:
   `powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1`
2. If `models/Trellis2/pipeline.json` or the DINOv3 files are missing, run:
   `.\.venv\Scripts\python.exe scripts/download_models.py`
3. Generate the asset with:
   `.\.venv\Scripts\python.exe scripts/inference.py --input <image> --output <mesh.glb>`

## Safe Defaults For RTX 4050 6 GB

- Default to `--pipeline-type 1024_cascade`. The GGUF Q4_K_M quantization + `low_vram` mode keeps peak VRAM under 6 GB by loading one model at a time.
- Keep low-VRAM mode enabled unless the user explicitly says to disable it.
- Leave preprocessing enabled unless the source image already has a good alpha mask.
- Use textured export unless the user explicitly asks for mesh-only output.
- Default `--texture-size 1024` and `--target-face-num 500000` to stay within 6 GB during baking.

## Troubleshooting

- If the output is only a fragment of the object or has no textures, ensure you are using `scripts/inference.py` with default `--pipeline-type 1024_cascade`. The `remesh=False` path in the textured exporter is the known-good route; the old `remesh=True, remesh_project=0` call produced broken geometry.
- If CUDA OOM occurs, retry with `--pipeline-type 512`, lower `--texture-size 512`, and close other GPU-heavy apps. Keep tiled decoding enabled.
- If imports fail on `comfy.utils`, the standalone shim under `scripts/standalone_shims` is missing from the script path; use `scripts/inference.py` directly instead of ad hoc snippets.
- Read [references/troubleshooting.md](references/troubleshooting.md) for setup/runtime issues.
- Read [references/vram_optimization.md](references/vram_optimization.md) when tuning step counts or pipeline size.
