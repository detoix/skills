---
name: fetch-texture
description: Downloads a texture from a CC0 texture provider URL, resizes to 512px, converts to WebP, compresses via TinyPNG, and saves diff/nor/metadata files to the current working directory
---

# Fetch Texture

Given a URL to a CC0 texture asset, your goal is to end up with three files in the **current working directory**:
- `<name>_diff.webp` — diffuse/color map, 512px, compressed
- `<name>_nor.webp` — normal map (OpenGL convention preferred), 512px, compressed
- `<name>_metadata.json` — asset info including physical width and source

## What you need to figure out per provider

Every texture site is different. Your job is to:

1. **Find the diffuse and normal map download URLs** — use the site's API if one exists, otherwise use claude-in-chrome to navigate the page and find download links. Always prefer 1K resolution.

2. **Find the physical real-world width** — some providers expose this in their API (e.g. Polyhaven has a `dimensions` field in millimeters), others mention it on the page. If unavailable, make a best-guess estimate based on material type (see Known providers below).
   If that estimate is still unclear, you may view the texture preview image and use visible scale cues (e.g. weave size, thread thickness, pattern repeat) as a weak heuristic. Treat image-based scale guesses as low confidence and note that they are inferred from appearance rather than source metadata.

3. **Download the files** — direct download if URLs are available, or via browser. Some sites package maps in ZIP files — extract them and identify which file is which by name/suffix (`_Color`, `_NormalGL`, `_diff`, `_nor`, etc.).

4. **Identify diffuse vs normal** — use your judgment based on filenames, map type labels, and context. For normal maps prefer OpenGL (`nor_gl`) over DirectX (`nor_dx`) since the target is three.js.

## Known providers

- **Polyhaven** (`polyhaven.com`) — has a public API:
  - `GET https://api.polyhaven.com/info/<asset_id>` — metadata including `dimensions` in mm
  - `GET https://api.polyhaven.com/files/<asset_id>` — download URLs by map type and resolution
  - **API key naming gotcha**: top-level map keys use mixed case — diffuse is `Diffuse` (not `diff`), normal maps are `nor_gl` / `nor_dx`. Always inspect the actual top-level keys before assuming names.

- **AmbientCG** (`ambientcg.com`) — has a public API:
  - `GET https://ambientcg.com/api/v2/full_json?id=<asset_id>&include=downloadData,dimensionData` — asset info and download links
  - Asset ID is the last path segment of the URL (e.g. `ambientcg.com/a/Fabric001` → `Fabric001`)
  - Downloads are ZIPs — always use `1K-JPG` attribute. Extract and identify maps by suffix: `_Color.jpg` = diffuse, `_NormalGL.jpg` = normal (prefer over `_NormalDX.jpg`)
  - `dimensionX`/`dimensionY` fields exist but are always 0 — estimate `width_m` from material type like CC0 Textures

- **CC0 Textures** (`cc0-textures.com`) — no public API, use claude-in-chrome to navigate and download ZIPs. **Does not provide real-world dimensions** — make a best-guess estimate based on material type and typical real-world tile sizes (e.g. fabric ~0.5m, ceramic tile ~0.3m, wood plank ~1.2m).

For any other provider, inspect the page with claude-in-chrome and use your judgment.

## Processing pipeline (same for all providers)

Once you have the raw image buffers:

1. **Resize to 512px and convert to WebP** using the `sharp` npm package (installed in `~/.agents/skills/fetch-texture/`):
```js
sharp(buffer).resize(512, 512, { fit: 'fill' }).webp({ quality: 90 }).toBuffer()
```

2. **Compress via TinyPNG** using the `tinify` npm package (installed). API key is in `TINYPNG_API_KEY` env var.

3. **Save files** to the current working directory. Do not overwrite existing files without asking.

4. **Write metadata JSON**:
```json
{
  "asset_id": "granite_tile",
  "source_url": "https://polyhaven.com/a/granite_tile",
  "name": "Granite Tile",
  "output_resolution": 512,
  "width_m": 0.23,
  "files": {
    "diff": "granite_tile_diff.webp",
    "nor": "granite_tile_nor.webp"
  }
}
```

5. **Report** final file sizes and width to the user.

6. **Clean up** — delete any temporary scripts written to the skill directory.

## Notes
- Run Node.js scripts from `~/.agents/skills/fetch-texture/` so package imports resolve correctly
- Use `process.cwd()` as the output directory so files land in the user's current working directory
- The skill directory uses `"type": "module"` in `package.json`, so `.js` files are treated as ES modules — **use `.cjs` extension** for CommonJS scripts (with `require()`), or use ESM `import` syntax in `.js` files
- TinyPNG API key is in `~/.agents/skills/fetch-texture/.env` — load it with `dotenv` or read the file manually before running
