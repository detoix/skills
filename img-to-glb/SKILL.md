---
name: img-to-glb
description: Generate a 3D GLB model from an image using local Hunyuan3D-2.1. Use when the user pastes an image and asks to generate a 3D model, convert image to 3D, or create a GLB from a photo/render.
---

# Image to GLB (Hunyuan3D-2.1)

Converts an image to a `.glb` 3D model using the local Hunyuan3D-2.1 installation.
Generation time depends on hardware and settings. Run in the foreground so progress is visible.

## Step 1 — Get a name

Ask the user for a short output name (e.g. `chair`, `table`) if they haven't provided one.
This becomes the filename: `<name>.png` (input copy) and `<name>_3d.glb` (output).

## Step 2 — Get the image on disk

**If the user provided a file path** — use it directly, skip to step 3.

**If the user pasted an image in the chat** — use its available attachment path, or save it into the current project's working directory using a supported file tool. If the attachment is not accessible, ask the user for a local file path.

## Step 3 — Run img_to_glb.py

This skill contains instructions only. It requires an external Hunyuan3D-2.1 installation providing the custom `img_to_glb.py` runner; that runner is not bundled in this repository. Resolve `<hunyuan-root>` to the existing checkout and `<hunyuan-python>` to its configured Python interpreter. Verify the script exists and inspect its `--help` before using the options below. If it is unavailable, report the missing prerequisite rather than assuming a local installation.

Run from the checkout directory so its imports resolve. Example for PowerShell:

```powershell
Set-Location "<hunyuan-root>"
& "<hunyuan-python>" ./img_to_glb.py "<absolute_image_path>"
```

### Options
- `--steps N` — number of diffusion inference steps (default: 50). More steps = more detail but slower. Measure runtime on the available hardware.
- `--cpu` — run on CPU instead of GPU (slower; requires runner support)

**Ask the user** if they want to change the step count. If not specified, omit the flag (uses default of 50).

- Bash tool `timeout`: `600000` (10 min)
- Do NOT use `run_in_background` — user watches progress live
- Expected output lines: `Loading model...` → `Quantizing DiT to INT8...` → `Moving to CUDA...` → `Removing background...` → `Generating 3D mesh...` → `Exporting...` → `Done!`
- Output GLB is written to `<image_path_without_ext>_3d.glb` automatically by the script

## Step 4 — Report

Tell the user the output path and file size.

## Notes

- Inspect available GPU memory and the external runner's quantization settings before generation.
- If CUDA OOM: suggest rerunning with `--cpu` flag if supported by the installed runner
- HuggingFace model weights (~6GB) are cached after first run
