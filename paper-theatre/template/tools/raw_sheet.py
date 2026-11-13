#!/usr/bin/env python3
"""Contact sheets of raw/*.png on a mid-grey board: raw_sheet.py [out]

- out/raw_sheet.png: every cut-out, to check style, alpha and consistency
- out/ref_sheet.png: every cut-out listed in prompts/refs.json ({"name": ["research/ref/…jpg", …]}) beside its
  references, to compare the cut-out with the person, place, object or species it shows
"""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent.parent
out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "out" / "raw_sheet.png"
BOARD = (92, 104, 118)
files = sorted((root / "raw").glob("*.png"))
if not files:
    sys.exit("raw/ is empty: nothing to put on a sheet yet")
cell, cols = 240, 10
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cell, rows * (cell + 24)), BOARD)
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGBA")
    im.thumbnail((cell - 16, cell - 16))
    x, y = (i % cols) * cell, (i // cols) * (cell + 24)
    sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2), im)
    a = Image.open(f).getchannel("A") if Image.open(f).mode == "RGBA" else None
    clear = sum(1 for v in a.getdata() if v == 0) / (a.width * a.height) if a else 0
    d.text((x + 6, y + cell + 4), f"{f.stem}  {Image.open(f).size}  alpha0 {clear:.0%}", fill=(255, 255, 255))
out.parent.mkdir(exist_ok=True)
sheet.save(out)
print(out, sheet.size)

refs_file = root / "prompts" / "refs.json"
refs = json.loads(refs_file.read_text(encoding="utf-8")) if refs_file.exists() else {}
H = 300
strips = []
for name, paths in refs.items():
    raw = root / "raw" / f"{name}.png"
    if not raw.exists():
        continue
    ims = []
    for p in [raw] + [root / q for q in paths]:
        im = Image.open(p).convert("RGBA")
        im = im.resize((max(1, int(im.width * H / im.height)), H))
        board = Image.new("RGB", im.size, BOARD)
        board.paste(im, (0, 0), im)
        ims.append(board)
    strip = Image.new("RGB", (sum(i.width for i in ims) + 12 * len(ims), H + 22), "white")
    x = 0
    for im in ims:
        strip.paste(im, (x, 0))
        x += im.width + 12
    ImageDraw.Draw(strip).text((4, H + 4), f"{name}  vs  " + ", ".join(Path(q).name for q in paths), fill=(0, 0, 0))
    strips.append(strip)
if strips:
    ref = Image.new("RGB", (max(s.width for s in strips), sum(s.height for s in strips)), "white")
    y = 0
    for s in strips:
        ref.paste(s, (0, y))
        y += s.height
    ref_out = out.with_name("ref_sheet.png")
    ref.save(ref_out)
    print(ref_out, ref.size)
