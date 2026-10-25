#!/usr/bin/env python3
"""Measure the CPU path on this machine: time of one decode step for several --rows, one model load.

    voxcpm_bench.py --input takes.txt --reference-audio voice.wav [--rows 1,2,4,8,16] [--patches 30]

voxcpm_fast.generate_many decodes --rows lines together; each step makes one patch (0.16 s of speech) for every
line in flight. The step time per batch size is enough to estimate any narration, so each run takes the first N
lines of --input, stops them after --patches patches (nothing is saved), skips the warm-up steps (compile) and
reports the median step time, its split between the diffusion head and the two language models, and seconds of
speech produced per minute. Pick the --rows with the best rate that fits in RAM; it does not change the audio.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
PATCHES_PER_S = 6.25  # 25 latent frames/s, 4 frames per patch


def main() -> int:
    ap = argparse.ArgumentParser(description="Step time of the VoxCPM2 CPU path for several batch sizes.")
    ap.add_argument("--input", required=True, help="Batch input file, one line per utterance (as for voxcpm_tts.py)")
    ap.add_argument("--reference-audio", required=True)
    ap.add_argument("--rows", default="1,2,4,8,16")
    ap.add_argument("--patches", type=int, default=30, help="Patches decoded per line in each run")
    ap.add_argument("--warmup", type=int, default=4, help="Steps left out of the timing (compile, caches)")
    ap.add_argument("--inference-timesteps", type=int, default=20)
    ap.add_argument("--cfg-value", type=float, default=2.0)
    args = ap.parse_args()

    import torch
    import voxcpm_fast
    from voxcpm import VoxCPM

    lines = [l for l in Path(args.input).read_text(encoding="utf-8").splitlines() if l.strip()]
    sizes = [int(x) for x in args.rows.split(",")]
    if max(sizes) > len(lines):
        raise SystemExit(f"--input has {len(lines)} lines; --rows up to {max(sizes)} needs at least that many")
    t0 = time.perf_counter()
    model = VoxCPM.from_pretrained("openbmb/VoxCPM2", optimize=False, load_denoiser=False)
    voxcpm_fast.prepare(model.tts_model, compile=True)
    cache = model.tts_model.build_prompt_cache(reference_wav_path=args.reference_audio)
    print(f"model ready in {time.perf_counter() - t0:.0f}s, torch threads {torch.get_num_threads()}", flush=True)

    m = model.tts_model
    marks: list[float] = []
    spent: dict[str, list[float]] = defaultdict(list)

    def timed(obj, name, label, mark=False):
        f = getattr(obj, name)

        def wrap(*a, **k):
            s = time.perf_counter()
            if mark:
                marks.append(s)
            try:
                return f(*a, **k)
            finally:
                spent[label].append(time.perf_counter() - s)

        setattr(obj, name, wrap)

    timed(m.feat_decoder, "solve_euler", "diffusion", mark=True)
    timed(m.base_lm, "forward_step", "base LM")
    timed(m.residual_lm, "forward_step", "residual LM")
    timed(m.base_lm, "forward", "prefill")

    for n in sizes:
        marks.clear()
        spent.clear()
        s = time.perf_counter()
        with torch.inference_mode():
            for _ in voxcpm_fast.generate_many(
                m, lines[:n], cache, 0, rows=n, inference_timesteps=args.inference_timesteps, cfg_value=args.cfg_value,
                min_len=args.patches + 1, max_len=args.patches + 1,
            ):
                pass
        w = args.warmup
        step = statistics.median(b - a for a, b in zip(marks[w:-1], marks[w + 1 :]))
        part = {k: statistics.median(v[w:]) for k, v in spent.items() if k != "prefill"}
        prefill = statistics.median(spent["prefill"]) if spent["prefill"] else 0.0
        print(
            f"rows {n:2d}: step {step:5.2f}s (diffusion {part['diffusion']:.2f}, base LM {part['base LM']:.2f}, "
            f"residual LM {part['residual LM']:.2f}) | prefill {prefill:.1f}s/line | "
            f"{n / PATCHES_PER_S / step * 60:5.1f} s of speech per minute | run {time.perf_counter() - s:.0f}s",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
