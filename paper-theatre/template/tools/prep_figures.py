#!/usr/bin/env python3
"""Turn raw Codex imagegen PNGs into trimmed cut-outs for the film.

- snaps near-opaque alpha to fully opaque and near-zero alpha to zero
- trims to the figure's bounding box (small padding)
- caps the longest side so the canvas renderer stays fast
- writes film/fig/<name>.png and film/fig/meta.json
"""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "raw", ROOT / "film" / "fig"
DEFAULT_MAX = 1100
PAD = 6
# per film, from film.json "figures": {"max_side": {"name": px}, "big": ["name", ...]} (big sets, maps → 1536 px)
_FIG = json.loads((ROOT / "film.json").read_text(encoding="utf-8")).get("figures", {})
MAX_SIDE, BIG = _FIG.get("max_side", {}), set(_FIG.get("big", []))


def clean_alpha(im: Image.Image) -> Image.Image:
    r, g, b, a = im.split()
    a = a.point(lambda v: 255 if v >= 246 else (0 if v <= 6 else v))
    return Image.merge("RGBA", (r, g, b, a))


def head_top(im: Image.Image, x0: float, x1: float) -> int:
    """Topmost opaque row inside a horizontal band (used to ignore raised arms)."""
    a = im.getchannel("A")
    w, h = im.size
    band = a.crop((int(w * x0), 0, int(w * x1), h))
    return band.point(lambda v: 255 if v > 128 else 0).getbbox()[1]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    for src in sorted(RAW.glob("*.png")):
        name = src.stem
        im = clean_alpha(Image.open(src).convert("RGBA"))
        bbox = im.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
        x0, y0, x1, y1 = bbox
        entry = {}
        box = (max(0, x0 - PAD), max(0, y0 - PAD), min(im.width, x1 + PAD), min(im.height, y1 + PAD))
        im = im.crop(box)
        cap = MAX_SIDE.get(name, 1536 if name.startswith("map_") or name in BIG else DEFAULT_MAX)
        if max(im.size) > cap:
            k = cap / max(im.size)
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        im.save(OUT / f"{name}.png", optimize=True)
        entry.update(w=im.width, h=im.height)
        meta[name] = entry
        print(f"{name:10s} {im.size} {entry}")
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
