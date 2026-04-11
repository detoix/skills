---
name: optimize-glb
description: Optimize, simplify, retexture, and recompress `.glb` assets with Blender and `gltf-transform`. Use when Codex is asked to reduce GLB file size, decimate mesh geometry, clean up imported 3D assets, apply a diffuse or normal texture during export, or turn an ad hoc Blender optimization shell script into a repeatable workflow.
---

# Optimize Glb

Use this skill to process a `.glb` through a deterministic pipeline instead of rewriting Blender automation each time. Handles both Linux/macOS and Windows (Git Bash).

The bundled script handles:
- optional pre-simplification with `@gltf-transform/cli`
- Blender import, limited dissolve, decimation, and cube-projection UVs
- optional diffuse and normal-map assignment
- final `gltf-transform optimize` with Draco compression

## Quick Start

Run the bundled script from your skill installation directory:

```bash
# General usage
bash scripts/optimize_glb.sh -i model.glb

# Windows (if Blender is not in PATH, specify path)
bash scripts/optimize_glb.sh -i model.glb -b "/c/Program Files/Blender Foundation/Blender 4.2/blender.exe"
```

Common variants:

```bash
# Stronger cleanup for dense meshes
bash scripts/optimize_glb.sh -i asset.glb -d 3 -r 0.35

# Pre-simplify before Blender if the model is too heavy
bash scripts/optimize_glb.sh -i asset.glb -s 0.25

# Add textures while exporting
bash scripts/optimize_glb.sh -i asset.glb -T color.webp -N normal.webp
```

## Workflow

1. Confirm the input is a `.glb`.
2. **Windows**: If running on Windows, use Git Bash and ensure `cygpath` is available.
3. Check whether `blender` is on PATH. If not, check for Flatpak (Linux) or specify the path with `-b`.
4. Always pass `-s 0.25 -t 180` by default. Pre-simplification reduces Blender processing time.
5. Report the before/after reduction in file size.

## Parameter Guidance

- `-d <degrees>` controls Limited Dissolve. Lower values preserve more hard edges.
- `-r <ratio>` controls Blender Decimate. `0.5` is a reasonable default.
- `-s <ratio>` runs pre-simplification before Blender.
- `-t <seconds>` increases the Blender timeout for large assets.
- `-T <path>` assigns a diffuse texture to Base Color.
- `-N <path>` assigns a normal map.
- `-b <path>` explicitly set the Blender binary path (useful on Windows).
- `-f` uses `flatpak run org.blender.Blender` (Linux).

## Dependencies

The script expects:
- `bash`, `timeout`, `npx`, `realpath`, `mktemp`
- **Windows only**: `cygpath`
- Blender, either on `PATH`, Flatpak, or specified via `-b`
- `@gltf-transform/cli`, fetched automatically through `npx --yes`

