#!/usr/bin/env python3
"""YouTube chapters from the final timeline: one per scene, at the transition that opens it → out/youtube.txt"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    tl = json.loads((ROOT / "film/timeline.json").read_text(encoding="utf-8"))
    titles = dict(re.findall(r"^## (\d+)\. (.+)$", (ROOT / "script.md").read_text(encoding="utf-8"), re.M))
    out = []
    for k in sorted({l["scene"] for l in tl["lines"]}):
        first = next(l for l in tl["lines"] if l["scene"] == k)
        t = 0 if k == 1 else max(0, first["start"] - 0.55 - 1.55 - 0.75)   # początek przejścia z kartą rozdziału: film/film.js chapterCut
        out.append(f"{int(t // 60)}:{int(t % 60):02d} {titles.get(str(k), f'{k}')}")
    text = "\n".join(out)
    cfg = json.loads((ROOT / "film.json").read_text(encoding="utf-8"))
    (ROOT / "out/youtube.txt").write_text(f"{cfg['title']}\n\n{cfg.get('description', '')}\n\n{cfg.get('chapters_heading', 'Chapters:')}\n{text}\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
