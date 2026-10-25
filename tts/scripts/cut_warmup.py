#!/usr/bin/env python3
"""Cut a throw-away warm-up word off the start of a take: "(instruction)Cóż. Co zapisywali…" -> "Co zapisywali…"

    cut_warmup.py take_001.wav [take_002.wav ...] --out-dir cut/ [--min-pause 0.08] [--max-start 1.2]

The cut is found in the signal, not by ASR: Whisper tends to drop a short word that sits before a long pause.
The first pause of --min-pause seconds or more that starts after 0.15 s and before --max-start is the full stop
after the warm-up; the cut goes 50 ms before that pause ends, so a soft first sound of the line is kept.
A take without such a pause is reported and not written: regenerate it. Sample rate and length are preserved
apart from the cut; check the start of every result (scripts/word_confidence.py prints what Whisper hears).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def find_pause(x: np.ndarray, sr: int, min_pause: float, max_start: float, floor_db: float = -35.0):
    hop = int(0.01 * sr)
    rms = np.array([np.sqrt(np.mean(x[i : i + hop] ** 2)) for i in range(0, len(x) - hop, hop)])
    quiet = 20 * np.log10(rms + 1e-9) - 20 * np.log10(rms.max() + 1e-9) < floor_db
    k = int(0.15 / 0.01)
    while k < min(len(quiet), int(max_start / 0.01)):
        if quiet[k]:
            e = k
            while e < len(quiet) and quiet[e]:
                e += 1
            if (e - k) * 0.01 >= min_pause:
                return k * 0.01, e * 0.01
            k = e
        k += 1
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Cut a warm-up word off the start of TTS takes.")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-pause", type=float, default=0.08, help="Shortest pause after the warm-up, seconds")
    ap.add_argument("--max-start", type=float, default=1.2, help="The pause must start before this, seconds")
    args = ap.parse_args()

    import soundfile as sf

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for f in args.files:
        x, sr = sf.read(f, dtype="float32")
        mono = x.mean(1) if x.ndim > 1 else x
        pause = find_pause(mono, sr, args.min_pause, args.max_start)
        if pause is None:
            print(f"{Path(f).name}: no pause after the warm-up, not cut; regenerate")
            continue
        cut = int(max(pause[0], pause[1] - 0.05) * sr)
        y = x[cut:].copy()
        fade = np.linspace(0, 1, int(0.005 * sr))
        y[: len(fade)] *= fade[:, None] if y.ndim > 1 else fade
        sf.write(out / Path(f).name, y, sr)
        print(f"{Path(f).name}: pause {pause[0]:.2f}-{pause[1]:.2f} s, cut at {cut / sr:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
