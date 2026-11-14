---
name: compress-image
description: Compress, resize, or convert static PNG, JPEG, WebP, and AVIF images locally. Use for smaller image assets, thumbnails, or WebP/AVIF delivery variants from files or HTTP(S) image URLs.
---

# Compress images locally

Run `scripts/compress.mjs` relative to this skill directory, using an absolute script path from the user's project. Output keeps the input format and dimensions by default. The first run installs the locked Sharp dependency into the ignored `.runtime/` directory. It requires Node.js 20.9+ and npm. Image encoding runs locally. A URL input is downloaded from its source.

```bash
node "$SKILL_DIR/scripts/compress.mjs" photo.png
node "$SKILL_DIR/scripts/compress.mjs" photo.png --format webp --output photo.webp
node "$SKILL_DIR/scripts/compress.mjs" photo.jpg --resize fit --width 1200 --height 800
node "$SKILL_DIR/scripts/compress.mjs" normals.png --format webp --lossless
```

The default filename is `<name>.optimized.<extension>` beside a local input or in the working directory for a URL. Use `--force` to replace a file and `--json` to report format, dimensions, and byte savings. `--validate` checks the local installation.

- Match the requested output format. Use `--format smallest` only when changing format is acceptable. For transparent input, choose PNG, WebP, or AVIF.
- Use `--lossless` with PNG or WebP for normal maps, masks, and other data textures. Keep their dimensions unless resizing was requested.
- For photos or illustrations, verify fine detail and gradients before replacing a source. PNG palette reduction and default WebP, JPEG, and AVIF encoding can be lossy.
- Use `--keep-metadata` when supported metadata needs to be retained. Otherwise re-encoding strips nonessential metadata, and an already smaller original is copied as-is.
