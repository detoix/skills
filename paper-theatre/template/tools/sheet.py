#!/usr/bin/env python3
"""Contact sheet of out/stills/*.png for quick visual review: sheet.py [cols] [thumb_width] [out]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent.parent
cols = int(sys.argv[1]) if len(sys.argv) > 1 else 4
tw = int(sys.argv[2]) if len(sys.argv) > 2 else 480
out = Path(sys.argv[3]) if len(sys.argv) > 3 else root / "out" / "sheet.png"
files = sorted((root / "out" / "stills").glob("t_*.png"))
th = tw * 9 // 16
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 24))
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB").resize((tw, th), Image.LANCZOS)
    x, y = (i % cols) * tw, (i // cols) * th
    sheet.paste(im, (x, y))
    d.rectangle((x, y, x + 74, y + 20), fill=(0, 0, 0))
    d.text((x + 4, y + 4), f.stem[2:] + " s", fill=(255, 255, 255))
sheet.save(out)
print(out, sheet.size)
