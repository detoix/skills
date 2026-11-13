#!/usr/bin/env python3
"""Figures side by side with a 10% grid, to read anchor points (fractions of width/height): grid.py name [name ...]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent.parent
ims = []
for n in sys.argv[1:]:
    im = Image.open(root / "film" / "fig" / f"{n}.png").convert("RGBA")
    im.thumbnail((520, 520))
    bg = Image.new("RGBA", im.size, (92, 104, 118, 255))
    bg.alpha_composite(im)
    d = ImageDraw.Draw(bg)
    for k in range(1, 10):
        x, y = im.width * k // 10, im.height * k // 10
        d.line((x, 0, x, im.height), fill=(255, 60, 60, 160)); d.line((0, y, im.width, y), fill=(255, 60, 60, 160))
        d.text((x + 2, 2), f".{k}", fill=(255, 255, 0)); d.text((2, y + 2), f".{k}", fill=(255, 255, 0))
    ims.append(bg)
sheet = Image.new("RGB", (sum(i.width for i in ims) + 10 * len(ims), max(i.height for i in ims)), (30, 30, 30))
x = 0
for i in ims:
    sheet.paste(i, (x, 0)); x += i.width + 10
sheet.save(root / "out" / "grid.png")
