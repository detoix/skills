---
name: tinypng
description: Compress, optimize, resize, or convert PNG, JPEG, WebP, and AVIF images with the TinyPNG/Tinify API. Use for local files or image URLs when Codex needs smaller image assets, WebP/AVIF delivery variants, optional resizing, or selected metadata preservation without hard-coded dimensions, formats, or output locations.
---

# TinyPNG

Use the bundled CLI for TinyPNG operations. Preserve the source dimensions and format unless the user requests a conversion or resize.

## Workflow

1. Inspect the source format, dimensions, alpha channel, and byte size.
2. Set `TINIFY_API_KEY` or `TINYPNG_API_KEY` in the process environment. Never print, hard-code, or commit the key.
3. Run `scripts/tinypng.mjs` from this skill directory.
4. Verify that the result decodes, retains the intended dimensions and alpha, and is smaller.
5. For appearance-sensitive assets, compare the rendered result with the source before replacing anything. TinyPNG optimization can be lossy.

## Commands

```bash
node scripts/tinypng.mjs image.png
node scripts/tinypng.mjs image.png --output image.webp --format webp
node scripts/tinypng.mjs https://example.com/image.jpg --output optimized/
node scripts/tinypng.mjs image.png --resize fit --width 1200 --height 1200
node scripts/tinypng.mjs image.jpg --preserve copyright,creation
node scripts/tinypng.mjs --validate
```

The default output is `<name>.tinypng.<extension>` beside a local input, or in the current directory for a URL. Existing files are never overwritten unless `--force` is provided.

Supported conversion targets are `keep`, `webp`, `png`, `jpeg`, `avif`, and `smallest`. `smallest` asks TinyPNG to choose the smallest supported result. Supported resize methods are `scale`, `fit`, `cover`, and `thumb`.

Use `--json` for machine-readable results and `--help` for the complete CLI contract.

## Quality rules

- Do not resize unless explicitly requested.
- Do not assume TinyPNG is lossless.
- Preserve originals until visual verification is complete.
- Treat normal maps, masks, and data textures as sensitive; compare decoded channel values or rendered output before accepting compression.
- Avoid repeated recompression of an already optimized asset.
