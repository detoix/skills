---
name: img-to-glb
description: Generate a 3D GLB model from an image using local Hunyuan3D-2.1. Use when the user pastes an image and asks to generate a 3D model, convert image to 3D, or create a GLB from a photo/render.
---

# Image to GLB (Hunyuan3D-2.1)

Converts an image to a `.glb` 3D model using the local Hunyuan3D-2.1 installation.
Generation takes ~5 minutes — always run in **foreground** so progress is visible.

## Step 1 — Get a name

Ask the user for a short output name (e.g. `chair`, `table`) if they haven't provided one.
This becomes the filename: `<name>.png` (input copy) and `<name>_3d.glb` (output).

## Step 2 — Get the image on disk

**If the user provided a file path** — use it directly, skip to step 3.

**If the user pasted an image in the chat** — try saving from clipboard via PowerShell:

```bash
powershell -Command "
  Add-Type -AssemblyName System.Windows.Forms;
  Add-Type -AssemblyName System.Drawing;
  \$img = [System.Windows.Forms.Clipboard]::GetImage();
  if (\$img -eq \$null) { Write-Error 'No image in clipboard'; exit 1 };
  \$img.Save('%USERPROFILE%\\Downloads\\modele-blender\\NAME.png', [System.Drawing.Imaging.ImageFormat]::Png);
  Write-Host 'Saved'
"
```

Replace `NAME` with the name from step 1.

If clipboard is empty (returns error), ask the user to save the image to disk and provide the path.

## Step 3 — Run img_to_glb.py

Script: `%USERPROFILE%/Downloads/modele-blender/Hunyuan3D-2.1/img_to_glb.py`
Python: `%USERPROFILE%/Downloads/modele-blender/venv/Scripts/python`
Must run with CWD = `%USERPROFILE%/Downloads/modele-blender/Hunyuan3D-2.1` (required for imports).

```bash
cd "%USERPROFILE%/Downloads/modele-blender/Hunyuan3D-2.1" && \
  "%USERPROFILE%/Downloads/modele-blender/venv/Scripts/python" img_to_glb.py "<absolute_image_path>" [--steps N] [--cpu]
```

### Options
- `--steps N` — number of diffusion inference steps (default: 50). More steps = more detail but slower. 100 steps ≈ 4.5 min on RTX 4050.
- `--cpu` — run on CPU instead of GPU (~30 min)

**Ask the user** if they want to change the step count. If not specified, omit the flag (uses default of 50).

- Bash tool `timeout`: `600000` (10 min)
- Do NOT use `run_in_background` — user watches progress live
- Expected output lines: `Loading model...` → `Quantizing DiT to INT8...` → `Moving to CUDA...` → `Removing background...` → `Generating 3D mesh...` → `Exporting...` → `Done!`
- Output GLB is written to `<image_path_without_ext>_3d.glb` automatically by the script

## Step 4 — Report

Tell the user the output path and file size.

## Notes

- GPU: RTX 4050 Laptop 6GB VRAM — INT8 quantization is already in the script, do not change it
- If CUDA OOM: suggest rerunning with `--cpu` flag (works but takes ~30 min)
- HuggingFace model weights (~6GB) are cached after first run
