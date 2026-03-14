---
name: optimize-glb
description: Optimize, simplify, retexture, and recompress `.glb` assets with Blender and `gltf-transform`. Use when Codex is asked to reduce GLB file size, decimate mesh geometry, clean up imported 3D assets, apply a diffuse or normal texture during export, or turn an ad hoc Blender optimization shell script into a repeatable workflow.
---

# Optimize Glb

Use this skill to process a `.glb` through a deterministic pipeline instead of rewriting Blender automation each time.

The bundled script handles:
- optional pre-simplification with `@gltf-transform/cli`
- Blender import, limited dissolve, decimation, and cube-projection UVs
- optional diffuse and normal-map assignment
- final `gltf-transform optimize` with Draco compression

## Quick Start

Run the bundled script. The script lives at `scripts/optimize_glb.sh` within this skill's directory — resolve the full path from your skill installation before running:

```bash
bash <skill-dir>/scripts/optimize_glb.sh -i model.glb
```

Common variants:

```bash
# Stronger cleanup for dense meshes
bash <skill-dir>/scripts/optimize_glb.sh -i asset.glb -d 3 -r 0.35

# Pre-simplify before Blender if the model is too heavy
bash <skill-dir>/scripts/optimize_glb.sh -i asset.glb -s 0.25

# Add textures while exporting
bash <skill-dir>/scripts/optimize_glb.sh -i asset.glb -T color.webp -N normal.webp

# Use Flatpak Blender
bash <skill-dir>/scripts/optimize_glb.sh -i asset.glb -f
```

## Workflow

1. Confirm the input is a `.glb`.
2. Check whether `blender` is on PATH (`which blender`). If not, check for Flatpak (`flatpak list | grep -i blender`). If found via Flatpak, always pass `-f`.
3. Always pass `-s 0.25 -t 180` by default. Pre-simplification reduces Blender processing time and avoids timeouts regardless of file size.
4. Start with the default settings unless the user explicitly wants aggressive reduction.
5. If the user provides texture maps, pass `-T` for base color and `-N` for the normal map.
6. Check the output size and report the before/after reduction.

## Parameter Guidance

- `-d <degrees>` controls Limited Dissolve. Lower values preserve more hard edges.
- `-r <ratio>` controls Blender Decimate. `0.5` is a reasonable default. Values near `0.2` are aggressive.
- `-s <ratio>` runs pre-simplification before Blender. Use it when imports are slow or the model is extremely dense.
- `-t <seconds>` increases the Blender timeout for large assets.
- `-T <path>` assigns a diffuse texture to Base Color.
- `-N <path>` assigns a normal map through a Normal Map node.
- `-f` uses `flatpak run org.blender.Blender` instead of a system `blender` binary.

## Dependencies

The script expects:
- `bash`
- `timeout`
- `npx`
- Blender, either on `PATH` or via Flatpak
- `@gltf-transform/cli`, fetched automatically through `npx --yes`

## Notes

- The script writes temporary Blender Python and intermediate GLBs to a temp directory and cleans them up automatically.
- The final output defaults to `<input>_processed.glb`.
- If the user asks for no Draco compression, patch the script or duplicate it rather than improvising a separate one-off command.
- If the source asset is not `.glb`, convert it first or use Blender directly.
