# Troubleshooting

## Partial Mesh Or Missing Textures

- Cause: the `export_textured_mesh` function was using `remesh=True` with `remesh_project=0`, which produces broken geometry via Dual Contouring without vertex projection-back.
- Fix: `remesh=False` is now the default in `scripts/inference.py`. The standard simplification + cleanup path matches the ComfyUI workflow behavior.

## UnicodeDecodeError On Windows

- Cause: bare `open(path, 'r')` uses the system codepage (e.g. cp1250) instead of UTF-8.
- Fix: all `open(..., 'r')` calls in `trellis2_core` now use `encoding='utf-8'`.

## CUDA Out Of Memory

- Retry with `--pipeline-type 512`.
- Lower `--texture-size` to 512.
- Keep low-VRAM mode enabled (default).
- Leave tiled decoding enabled (default).
- Close other GPU-heavy apps before rerunning.

## Missing Models

- Run `.\.venv\Scripts\python.exe scripts/download_models.py`.
- Verify these paths exist:
  - `models/Trellis2/pipeline.json`
  - `models/Trellis2/refiner/ss_flow_img_dit_1_3B_64_bf16_Q4_K_M.gguf`
  - `models/Trellis2/shape/slat_flow_img2shape_dit_1_3B_512_bf16_Q4_K_M.gguf`
  - `models/Trellis2/shape/slat_flow_img2shape_dit_1_3B_1024_bf16_Q4_K_M.gguf`
  - `models/Trellis2/texture/slat_flow_imgshape2tex_dit_1_3B_512_bf16_Q4_K_M.gguf`
  - `models/Trellis2/texture/slat_flow_imgshape2tex_dit_1_3B_1024_bf16_Q4_K_M.gguf`
  - `models/Trellis2/shape/slat_flow_img2shape_dit_1_3B_1024_bf16.json`
  - `models/Trellis2/texture/slat_flow_imgshape2tex_dit_1_3B_1024_bf16.json`
  - `models/facebook/dinov3-vitl16-pretrain-lvd1689m/model.safetensors`

## Import Errors

- If `trellis2_gguf` cannot be imported, run the script from this skill folder so its relative paths resolve correctly.
- If `comfy.utils` cannot be imported, use `scripts/inference.py` unchanged; it prepends the standalone shim automatically.
- If CUDA wheel imports fail (`cumesh`, `o_voxel`, `nvdiffrast`, `flex_gemm`), rerun `scripts/setup_env.ps1` with Python 3.12 active.
