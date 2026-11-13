#!/usr/bin/env python3
"""YouTube subtitles from the narration's word timings → out/<slug>.<language>.srt (film.json)

Cues break at sentence ends and commas, hold at most two lines of ~42 characters and ~6 s,
and use the on-screen spelling (numbers as digits).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LINE, MAX_CHARS, MAX_DUR = 42, 84, 6.0


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def wrap(words):
    """Split a cue's words into at most two balanced lines."""
    text = " ".join(words)
    if len(text) <= MAX_LINE:
        return text
    best, cut = None, 1
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if best is None or score < best:
            best, cut = score, i
    return " ".join(words[:cut]) + "\n" + " ".join(words[cut:])


def main():
    tl = json.loads((ROOT / "film/timeline.json").read_text(encoding="utf-8"))
    cues = []
    for line in tl["lines"]:
        cur = []
        for k, w in enumerate(line["words"]):
            cur.append(w)
            text = " ".join(x["w"] for x in cur)
            nxt = line["words"][k + 1] if k + 1 < len(line["words"]) else None
            end_sentence = w["w"][-1] in ".?!…”"
            soft = w["w"][-1] in ",:;—"
            too_long = nxt is not None and len(text) + 1 + len(nxt["w"]) > MAX_CHARS
            too_slow = cur[-1]["e"] - cur[0]["s"] > MAX_DUR
            if nxt is None or end_sentence or too_long or too_slow or (soft and len(text) > 30):
                cues.append((cur[0]["s"], cur[-1]["e"], [x["w"] for x in cur]))
                cur = []
    out, prev_end = [], 0.0
    for i, (s, e, words) in enumerate(cues):
        s = max(s, prev_end)
        nxt_s = cues[i + 1][0] if i + 1 < len(cues) else e + 2
        e = min(max(e + 0.25, s + 1.0), nxt_s - 0.04)
        out.append(f"{i + 1}\n{ts(s)} --> {ts(e)}\n{wrap(words)}\n")
        prev_end = e
    cfg = json.loads((ROOT / "film.json").read_text(encoding="utf-8"))
    path = ROOT / "out" / f"{cfg['slug']}.{cfg['language']}.srt"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"{path} — {len(out)} cues")


if __name__ == "__main__":
    main()
