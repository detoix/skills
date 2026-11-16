#!/usr/bin/env python3
"""Checks narration takes word by word: what the recogniser heard (tools/asr.py, through its cache) against the
text to be spoken (audio/narration.json → say).

- For Polish the comparison accepts cautious spelling equivalents (ó/u, ch/h, final devoicing, ą as om/on before a
  consonant, final ę/e).
- Words recognised in their caption form (a number in digits, a foreign name in its own spelling) count for their
  span of the text. A number recognised in digits is still flagged for listening: digits do not prove the inflected
  spoken form. The recognised words stay literal in the report.
- This is evidence for listening, not a verdict: a difference does not prove a pronunciation error (audio reference).
- The recognition is cached per file hash, and tools/build_audio.py reads the same cache for the word timings.

Report: audio/check.json (or check.json in the checked folder) and a summary on screen. Usage:
  python3 tools/check_takes.py                                          all current takes
  python3 tools/check_takes.py --takes audio/retakes_2 --against audio/takes
      retakes, each next to the take it would replace; writes audio/retakes_2/comparison.wav (old, then new, per line)
"""
import argparse
import difflib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asr  # noqa: E402

ROOT = asr.ROOT
POLISH = asr.language() == "pl"


def canon(w):
    w = re.sub(r"[^\w]", "", w.lower())
    if not POLISH:
        return w
    w = w.replace("ó", "u").replace("ch", "h")
    for a, b in (("rz", "sz"), ("ż", "sz"), ("dź", "ć"), ("dz", "c"), ("ź", "ś"),
                 ("b", "p"), ("d", "t"), ("g", "k"), ("w", "f"), ("z", "s")):
        if len(w) > 1 and w.endswith(a):
            w = w[: -len(a)] + b
            break
    if w.endswith("ę"):
        w = w[:-1] + "e"
    w = re.sub(r"ą(?=[bp])", "om", w)
    w = re.sub(r"ą(?=[^bpą\W])", "on", w)
    return w


def units_of(line):
    """Spans of a line: the caption form and the spoken words it stands for (spans from tools/script.py)."""
    say = line["say"].split()
    units, pos = [], 0
    for display, n in line["spans"]:
        units.append({"display": display, "spoken": say[pos:pos + n]})
        pos += n
    return units


def compare(line, heard_words):
    units = units_of(line)
    expected = [w for u in units for w in u["spoken"]]
    exp_c = [canon(w) for w in expected]
    heard = [h["w"] for h in heard_words if canon(h["w"])]
    heard_c = [canon(w) for w in heard]
    # words recognised in their caption form → the spoken words they stand for
    notes = []
    for u in units:
        disp = [canon(t) for t in re.split(r"\s+", u["display"]) if canon(t)]
        spoken = [canon(w) for w in u["spoken"]]
        if not disp or disp == spoken:
            continue
        k = len(disp)
        for j in range(len(heard_c) - k + 1):
            if heard_c[j:j + k] == disp:
                is_number = any(c.isdigit() for c in u["display"])
                notes.append({"display": u["display"], "heard": " ".join(heard[j:j + k]),
                              "kind": "number in digits: inflection not checked" if is_number else "caption spelling"})
                heard_c[j:j + k] = [None] * k
                heard_c[j] = spoken
                break
    flat = []
    for h in heard_c:
        if h is None:
            continue
        flat.extend(h if isinstance(h, list) else [h])
    ops, S, D, I = [], 0, 0, 0
    sm = difflib.SequenceMatcher(None, exp_c, flat, autojunk=False)
    first_ok = True
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if i1 == 0:
            first_ok = False
        a, b = i2 - i1, j2 - j1
        S += min(a, b)
        D += max(0, a - b)
        I += max(0, b - a)
        ops.append({"op": tag, "expected": " ".join(expected[i1:i2]), "heard": " ".join(flat[j1:j2])})
    n = len(expected)
    return {"words": n, "S": S, "D": D, "I": I, "wer": round((S + D + I) / max(n, 1), 3), "first_word_ok": first_ok,
            "edits": ops, "display_matches": notes}


def check(takes_dir="audio/takes", verbose=True, report_path=None):
    t0 = time.perf_counter()
    narr = json.loads((ROOT / "audio/narration.json").read_text(encoding="utf-8"))
    paths = [ROOT / takes_dir / f"output_{k + 1:03d}.wav" for k in range(len(narr))]
    have = [(l, p) for l, p in zip(narr, paths) if p.exists()]
    results, stats = asr.transcribe([p for _, p in have], verbose=verbose)
    lines, tot = [], {"words": 0, "S": 0, "D": 0, "I": 0}
    for (l, p), r in zip(have, results):
        c = compare(l, r["words"])
        for k in tot:
            tot[k] += c[k]
        lines.append({"id": l["id"], "take": str(p.relative_to(ROOT)), "sha256": r["sha256"], "cached": r["cached"],
                      "transcribe_seconds": r["transcribe_seconds"], "say": l["say"], "heard": r["text"], **c})
    report = {"model": stats["model"], "asr": stats, "missing_takes": len(narr) - len(have),
              "words": tot["words"], "S": tot["S"], "D": tot["D"], "I": tot["I"],
              "wer": round((tot["S"] + tot["D"] + tot["I"]) / max(tot["words"], 1), 4),
              "lines_with_edits": sum(1 for x in lines if x["edits"]),
              "first_word_flags": sum(1 for x in lines if not x["first_word_ok"]),
              "numbers_as_digits": sum(1 for x in lines for n in x["display_matches"] if n["kind"].startswith("number")),
              "check_wall_seconds": round(time.perf_counter() - t0, 2), "lines": lines}
    out = report_path or ROOT / "audio/check.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if verbose:
        show(report)
        print(f"\n{report['words']} words, WER {report['wer']:.3f} (S {tot['S']}, D {tot['D']}, I {tot['I']}), "
              f"lines with differences {report['lines_with_edits']}/{len(lines)}, first word {report['first_word_flags']}, "
              f"numbers in digits {report['numbers_as_digits']}; report {out.relative_to(ROOT)}")
    return report


def show(report, only=None):
    for x in report["lines"]:
        if only is not None and x["id"] not in only:
            continue
        if x["edits"] or x["display_matches"] or only is not None:
            print(f"{x['id']:7s} {x['take']}  WER {x['wer']:.2f}{'  FIRST WORD' if not x['first_word_ok'] else ''}")
            print(f"   text : {x['say']}\n   heard: {x['heard']}")
            for e in x["edits"]:
                print(f"   - {e['op']}: “{e['expected']}” → “{e['heard']}”")
            for n in x["display_matches"]:
                print(f"   · {n['kind']}: “{n['display']}” heard as “{n['heard']}”")


def comparison(new, old, folder):
    """folder/comparison.wav: for every line with a new take, the old take, a pause, then the new one."""
    parts, pause = [], None
    for x in new["lines"]:
        prev = next((o for o in old["lines"] if o["id"] == x["id"]), None)
        if prev is None:
            continue
        for take in (prev["take"], x["take"]):
            y, sr = sf.read(ROOT / take, dtype="float32")
            if y.ndim > 1:
                y = y.mean(1)
            pause = np.zeros(int(0.8 * sr), dtype="float32")
            parts += [y, pause]
        parts.append(pause)
    if parts:
        sf.write(folder / "comparison.wav", np.concatenate(parts), sr)
        print(f"\nlistening file: {(folder / 'comparison.wav').relative_to(ROOT)} (old, then new, per line)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--takes", default="audio/takes")
    ap.add_argument("--against", default=None, help="folder of the current takes the checked ones would replace")
    a = ap.parse_args()
    if not a.against:
        check(a.takes)
        return
    folder = ROOT / a.takes
    new = check(a.takes, verbose=False, report_path=folder / "check.json")
    ids = {x["id"] for x in new["lines"]}
    old = check(a.against, verbose=False, report_path=folder / "check_against.json")
    for x in new["lines"]:
        print(f"\n== {x['id']}")
        show(old, {x["id"]})
        show(new, {x["id"]})
    comparison(new, old, folder)
    print(f"\nnew takes: {len(ids)}, first word flags {sum(1 for x in new['lines'] if not x['first_word_ok'])}, "
          f"lines with differences {new['lines_with_edits']}")


if __name__ == "__main__":
    main()
