#!/usr/bin/env python3
"""script.md → audio/narration.json (display text, spoken text, word spans).

Numbers are shown as digits in the captions but spoken as words: each one is written in
SPOKEN as {display|spoken}. A display token then covers all the spoken words it stands for.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

import film_config

# on screen → spoken, from film.json "spoken": numbers shown as digits but read as words, and words the voice gets
# wrong spelled for the ear, e.g. (Polish) "W 1952 roku": "W {1952|tysiąc dziewięćset pięćdziesiątym drugim} roku",
# "gliniana wanna.": "gliniana {wanna.|wana.}" ("wanna" is English to the model)
SPOKEN = film_config.load().get("spoken", {})
MARK = re.compile(r"\{([^|}]+)\|([^}]+)\}")


def parse():
    scene, n, lines = 0, 0, []
    for raw in (ROOT / "script.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d+)\. (.+)", raw)
        if m:
            scene, n = int(m.group(1)), 0
            continue
        m = re.match(r"^\(([^)]*)\)(.+)$", raw.strip())
        if not m or not scene:
            continue
        n += 1
        direction, text = m.group(1).strip(), m.group(2).strip()
        marked = text
        for k, v in SPOKEN.items():
            marked = marked.replace(k, v)
        if re.search(r"\d", MARK.sub("", marked)):
            raise SystemExit(f"unhandled number in: {text}")
        say = MARK.sub(lambda q: q.group(2), marked)
        # spans: every display token with the number of spoken words it covers
        spans = []
        for part in re.split(r"(\{[^}]+\})", marked):
            q = MARK.fullmatch(part)
            if q:
                spans.append([q.group(1), len(q.group(2).split())])
            else:
                spans += [[w, 1] for w in part.split()]
        assert sum(k for _, k in spans) == len(say.split()), text
        lines.append({"id": f"s{scene}_{n:02d}", "scene": scene, "direction": direction, "text": text, "say": say, "spans": spans})
    return lines


def main():
    lines = parse()
    out = ROOT / "audio"
    out.mkdir(exist_ok=True)
    moods = film_config.load().get("voice_moods", {})
    for l in lines:
        if l["id"] in moods:
            l["mood"] = moods[l["id"]]
    (out / "narration.json").write_text(json.dumps(lines, ensure_ascii=False, indent=1), encoding="utf-8")
    words = sum(len(l["say"].split()) for l in lines)
    print(f"{len(lines)} lines, {words} spoken words, scenes {sorted({l['scene'] for l in lines})}")


if __name__ == "__main__":
    main()
