#!/usr/bin/env python3
"""Compare retakes by free transcription, tempo and expected-word alignment.

    compare_takes.py --lines lines.json --old takes/ --new retakes/ --language pl

comparison.wav contains old then new for each line with a new take. Its audio is
mono, 48 kHz even when source takes differ in sample rate or channel count.
"""
import argparse
import json
from pathlib import Path


def main(argv=None):
    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel
    from faster_whisper.tokenizer import Tokenizer
    from scipy import signal
    from word_confidence import score
    from tts_pronunciation_qa import compare_text

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--language", default="pl")
    a = ap.parse_args(argv)
    lines = json.loads(Path(a.lines).read_text(encoding="utf-8"))
    candidates = [(n, line) for n, line in enumerate(lines, 1)
                  if (Path(a.new) / f"output_{n:03d}.wav").is_file()]
    if not candidates:
        ap.error("no new takes match the original line positions")
    model = WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True, cpu_threads=4)
    tok = Tokenizer(model.hf_tokenizer, True, task="transcribe", language=a.language)
    both, output_rate = [], 48000
    for n, line in candidates:
        for name, folder in (("old", a.old), ("new", a.new)):
            path = Path(folder) / f"output_{n:03d}.wav"
            if not path.exists():
                continue
            x, rate = sf.read(path, dtype="float32")
            x = x.mean(1) if x.ndim > 1 else x
            if not len(x) or not np.isfinite(x).all() or not np.max(np.abs(x)):
                raise ValueError(f"Take is empty, silent or nonfinite: {path}")
            x16 = signal.resample_poly(x, 16000, rate).astype("float32")
            segs, _ = model.transcribe(x16, language=a.language, beam_size=5, condition_on_previous_text=False)
            conf = score(model, tok, x16, line["say"])
            size = min(480, len(x))
            env = np.sqrt(np.convolve(x * x, np.ones(size) / size, mode="same"))
            hot = np.flatnonzero(env > env.max() * 0.03)
            syl = sum(c in "aeiouyąęóáéíúàèìòùäöü" for c in line["say"].lower()) / ((hot[-1] - hot[0] + 1) / rate)
            weakest = min(conf, key=lambda c: c["p"]) if conf else None
            aligned = f"{weakest['word']} {weakest['p']:.2f}" if weakest else "unavailable"
            heard = " ".join(s.text.strip() for s in segs)
            checked = compare_text(line.get("check_text", line["say"]), heard, a.language)
            print(f"{line['id']:7s} {name} {len(x) / rate:5.2f} s, {syl:.2f} syl/s, weakest aligned word: {aligned}\n    free ASR: {heard}", flush=True)
            for difference in checked["word_differences"]:
                print(f"    REVIEW word {difference['expected_index']}: {difference['expected']!r} -> {difference['actual']!r} ({difference['kind']})", flush=True)
            both += [signal.resample_poly(x, output_rate, rate).astype("float32"), np.zeros(output_rate // 2, dtype="float32")]
    sf.write(Path(a.new) / "comparison.wav", np.concatenate(both), output_rate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
