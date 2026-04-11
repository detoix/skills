---
name: fetch-texture
description: Downloads a texture from a CC0 provider URL, resizes to 512px, converts to WebP, compresses via TinyPNG, and saves diff/nor/metadata files to the current working directory.
---

# Fetch Texture

Download and process CC0 textures into optimized 512px WebP assets.

## Workflow

1. **Find URLs**: Locate diffuse and normal map URLs (prefer 1K resolution).
2. **Determine Physical Width**: Use provider API or estimate based on material type.
3. **Process**: Write a Node.js script in the skill directory to use its pre-installed `sharp` and `tinify`.

### Processing script template
```javascript
// run from skill directory
import sharp from "sharp";
import tinify from "tinify";
import fs from "fs";

tinify.key = "YOUR_API_KEY"; // Load from .env in skill dir

const processImage = async (buffer, outPath) => {
  const resized = await sharp(buffer)
    .resize(512, 512, { fit: "fill" })
    .webp({ quality: 90 })
    .toBuffer();
  await tinify.fromBuffer(resized).toFile(outPath);
};
```

## Environment Note
This skill directory contains a specialized `node_modules` with `sharp` and `tinify`. Always run your temporary processing scripts from within this directory to ensure dependencies are found.

## Known Providers
- **Polyhaven**: Use `api.polyhaven.com`.
- **AmbientCG**: Use `ambientcg.com/api/v2`.
- **CC0 Textures**: Manual navigation/download.

## References
- **Metadata**: Always save a `<name>_metadata.json` with `width_m` and `source_url`.

