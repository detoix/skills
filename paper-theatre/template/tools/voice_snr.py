#!/usr/bin/env python3
"""How loud is the narration against everything else in a finished mix? (per frequency band, while speaking)

    python3 tools/voice_snr.py film/audio/mix.wav

The narration (film/audio/vo.wav) is fitted into the mix by least squares; whatever is left is music + effects.
Reported: voice-to-rest ratio in dB while the narrator speaks, overall and in the bands that carry speech.
Targets here: music ≥ 20 dB and effects ≥ 18 dB under the voice while speaking (full band).
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
BANDS = [(80, 300, "80–300 Hz (podstawa głosu)"), (300, 1000, "300–1000 Hz (samogłoski)"), (1000, 4000, "1–4 kHz (spółgłoski)"), (80, 8000, "całe pasmo")]


def main(paths):
    vo, _ = sf.read(ROOT / "film/audio/vo.wav", dtype="float32")
    hop = int(0.05 * SR)
    for p in paths:
        mix, _ = sf.read(p, dtype="float32")
        mix = mix.mean(1)
        n = min(len(mix), len(vo))
        m, v = mix[:n].astype("float64"), vo[:n].astype("float64")
        a = np.dot(m, v) / np.dot(v, v)          # the narration's gain inside the mix
        rest = m - a * v
        k = n // hop
        vr = np.sqrt(np.mean(v[: k * hop].reshape(k, hop) ** 2, axis=1))
        speak = np.repeat(vr > 0.01, hop)
        stem = Path(p).with_name(Path(p).stem + "_music.wav")
        mus = None
        if stem.exists():
            mus, _ = sf.read(stem, dtype="float32")
            mus = np.pad(mus.mean(1), (0, max(0, n - len(mus))))[:n].astype("float64")
        print(f"{Path(p).name}: lektor w miksie ×{a:.2f}")
        for lo, hi, name in BANDS:
            sos = signal.butter(4, [lo, hi], btype="band", fs=SR, output="sos")
            s = speak[: k * hop]
            P = lambda x: np.mean(signal.sosfilt(sos, x[: k * hop])[s] ** 2) + 1e-12
            V = P(a * v)
            line = f"   {name:28s} głos nad resztą {10 * np.log10(V / P(rest)):5.1f} dB"
            if mus is not None:
                line += f"   (nad muzyką {10 * np.log10(V / P(mus)):5.1f} dB, nad efektami {10 * np.log10(V / P(rest - mus)):5.1f} dB)"
            print(line)


if __name__ == "__main__":
    main(sys.argv[1:])
