#!/usr/bin/env python3
"""Narrate a script using approved library moods; --plan reads only and never loads the model.

A line is {"id", "say", "direction", "mood"}, mood optional. Output numbering follows
its original position, including with --ids. See SKILL.md for the public interface.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

CFG_VALUE, STEPS, ROWS = 2.0, 30, 4
VOWELS = "aeiouyąęóáéíúàèìòùäöü"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bank(root):
    path = root / "bank/bank.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def mood_of(line, rules):
    if line.get("mood"):
        return line["mood"]
    for pattern, mood in rules.get("rules", []):
        if re.search(pattern, line.get("direction", "")):
            return mood
    return rules.get("default")


def sample_problem(root, data):
    if not isinstance(data, dict) or not data.get("file") or not data.get("text", "").strip():
        return "sample file or exact transcript missing"
    sample = root / data["file"]
    if not sample.is_file():
        return f"sample file missing: {sample}"
    if data.get("sha256") and sha(sample) != data["sha256"]:
        return f"sample hash differs from the approved library entry: {sample}"
    return None


def add_mood(a, root):
    import numpy as np
    import soundfile as sf

    if not re.fullmatch(r"[\w-]+", a.add_mood):
        raise ValueError("Mood names use letters, numbers, underscores or hyphens.")
    if not a.sample or not a.text or not a.text.strip():
        raise ValueError("--add-mood requires --sample and its exact --text.")
    bank = read_bank(root)
    if a.add_mood in bank:
        raise ValueError(f"Mood {a.add_mood!r} already exists; choose a new name to preserve the approved sample.")
    x, sr = sf.read(a.sample, dtype="float32")
    x = x.mean(1) if x.ndim > 1 else x
    if not len(x) or not np.isfinite(x).all() or np.max(np.abs(x)) == 0:
        raise ValueError("Mood sample must contain finite, audible audio.")
    env = np.sqrt(np.convolve(x * x, np.ones(min(480, len(x))) / min(480, len(x)), mode="same"))
    hot = np.flatnonzero(env > env.max() * 0.03)
    duration = (hot[-1] - hot[0] + 1) / sr
    rate = sum(c in VOWELS for c in a.text.lower()) / duration
    dest = root / "bank" / f"{a.add_mood}.wav"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(a.sample).resolve() != dest.resolve():
        shutil.copyfile(a.sample, dest)
    (root / "bank" / f"{a.add_mood}.txt").write_text(a.text, encoding="utf-8")
    bank[a.add_mood] = {"file": f"bank/{a.add_mood}.wav", "text": a.text, "sha256": sha(dest), "direction": a.direction,
                        "seconds": round(len(x) / sr, 2), "syl_per_s": round(float(rate), 2),
                        "source": str(Path(a.sample).resolve()), "source_sha256": sha(a.sample)}
    (root / "bank/bank.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.add_mood}: {len(x) / sr:.1f} s, {rate:.2f} syllables/s")


def generate(a, root, bank, groups, index):
    import soundfile as sf
    import torch
    from voxcpm import VoxCPM
    from voxcpm_tts import select_backend

    backend = select_backend(torch, a)
    t0 = time.perf_counter()
    device = ("cuda:0" if a.device in ("auto", "cuda") else a.device) if backend == "cuda" else "cpu"
    tts = VoxCPM.from_pretrained("openbmb/VoxCPM2", optimize=False, load_denoiser=False, device=device).tts_model
    fast = None
    if backend != "cuda":
        import voxcpm_fast as fast
        fast.prepare(tts, compile=backend == "cpu" and not a.no_compile)
        if backend == "openvino":
            try:
                import voxcpm_openvino
                voxcpm_openvino.configure(tts, device=a.openvino_device, cache_dir=a.openvino_cache_dir, compile_cpu=not a.no_compile)
            except Exception as exc:
                print(f"OpenVINO setup failed ({type(exc).__name__}: {exc}); continuing on CPU.", file=sys.stderr)
                backend = "cpu"
                if not a.no_compile:
                    tts.feat_decoder.estimator = fast.CompiledOrEager(tts.feat_decoder.estimator)
    print(f"model {time.perf_counter() - t0:.1f}s, backend {backend}", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    prov_path = Path(a.provenance) if a.provenance else out / "provenance.json"
    prov_path.parent.mkdir(parents=True, exist_ok=True)
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.exists() else {"takes": {}}
    voice = root / "voice.wav"
    voice_sha = sha(voice)
    done, total, offset = 0, sum(len(v) for v in groups.values()), 0
    for mood, lines in groups.items():
        data = bank[mood]
        sample = root / data["file"]
        prompt_sha = sha(sample)
        cache = tts.build_prompt_cache(prompt_text=data["text"], prompt_wav_path=str(sample), reference_wav_path=str(voice))
        seed = a.seed + offset
        offset += len(lines)
        estimator = tts.feat_decoder.estimator
        started_backend = getattr(estimator, "active_backend", backend)

        def cuda_takes():
            for j, line in enumerate(lines):
                torch.manual_seed(seed + j)
                chunks = tts._generate_with_prompt_cache(
                    target_text=line["say"], prompt_cache=cache, min_len=2, max_len=4096,
                    inference_timesteps=STEPS, cfg_value=CFG_VALUE, retry_badcase=True,
                    retry_badcase_max_times=3, retry_badcase_ratio_threshold=6.0, streaming=False)
                for wav, _, _ in chunks:
                    yield j, wav.squeeze(0).cpu(), {"attempts": None}

        with torch.inference_mode():
            takes = (cuda_takes() if backend == "cuda" else
                     fast.generate_many(tts, [l["say"] for l in lines], cache, seed, rows=a.rows,
                                        inference_timesteps=STEPS, cfg_value=CFG_VALUE))
            for j, audio, info in takes:
                line = lines[j]
                path = out / f"output_{index[line['id']]:03d}.wav"
                sf.write(path, audio.numpy(), tts.sample_rate)
                actual_backend = getattr(estimator, "active_backend", backend)
                mixed = started_backend != actual_backend
                done += 1
                print(f"{line['id']} {mood} {len(audio) / tts.sample_rate:.2f}s [{done}/{total}] {time.perf_counter() - t0:.0f}s", flush=True)
                prov["takes"][line["id"]] = {
                    "file": os.path.relpath(path), "sha256": sha(path), "text": line["say"], "direction": line.get("direction"),
                    "source": "narrate.py",
                    "generation": {"model": "openbmb/VoxCPM2", "mode": "ultimate cloning: sample + reference",
                                   "reference_file": str(voice.resolve()), "reference_sha256": voice_sha,
                                   "prompt_mood": mood, "prompt_file": str(sample.resolve()), "prompt_sha256": prompt_sha,
                                   "prompt_text": data["text"], "cfg_value": CFG_VALUE, "inference_timesteps": STEPS,
                                   "requested_device": a.device, "device": device if actual_backend == "cuda" else actual_backend,
                                   "precision": None if mixed else "FP16 diffusion hint; float32 orchestration" if actual_backend == "openvino" else getattr(getattr(tts, "config", None), "dtype", None) if actual_backend == "cuda" else "float32",
                                   "mixed_backend_possible": mixed, "fallback_reason": getattr(estimator, "fallback_reason", None),
                                   "rows": min(a.rows, len(lines)) if backend != "cuda" else 1, "seed": seed + j, "attempts": info.get("attempts")},
                }
                prov_path.write_text(json.dumps(prov, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Narrate a script from a voice library.")
    ap.add_argument("--library", required=True)
    ap.add_argument("--lines")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--provenance")
    ap.add_argument("--ids", default="")
    ap.add_argument("--mood", default="", help="use this mood for every chosen line")
    ap.add_argument("--seed", type=int, default=5000)
    ap.add_argument("--device", default="auto", help="auto, cpu, openvino, cuda[:N]")
    ap.add_argument("--openvino-device", default="GPU")
    ap.add_argument("--openvino-cache-dir")
    ap.add_argument("--rows", type=int, default=ROWS)
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--add-mood")
    ap.add_argument("--sample")
    ap.add_argument("--text")
    ap.add_argument("--direction", default="")
    a = ap.parse_args(argv)
    root = Path(a.library)
    if a.add_mood:
        if a.plan:
            ap.error("--plan is read-only and cannot be combined with --add-mood")
        return add_mood(a, root)
    if not a.lines:
        ap.error("--lines is required for planning or narration")
    if a.rows < 1:
        ap.error("--rows must be at least 1")
    lines = json.loads(Path(a.lines).read_text(encoding="utf-8"))
    if not isinstance(lines, list) or not lines:
        ap.error("--lines must contain a nonempty JSON list")
    if any(not isinstance(l, dict) or not isinstance(l.get("id"), str) or not l["id"].strip()
           or not isinstance(l.get("say"), str) or not l["say"].strip() for l in lines):
        ap.error("each line needs a nonempty string id and say")
    all_ids = {l["id"] for l in lines}
    if len(all_ids) != len(lines):
        ap.error("line ids must be unique")
    wanted = {s.strip() for s in a.ids.split(",") if s.strip()} if a.ids else all_ids
    if not wanted or wanted - all_ids:
        ap.error("--ids contains no valid selection or unknown ids: " + ", ".join(sorted(wanted - all_ids)))
    bank = read_bank(root)
    rules_path = root / "bank/rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path.exists() else {}
    groups = {}
    for line in lines:
        if line["id"] in wanted:
            groups.setdefault(a.mood or mood_of(line, rules), []).append(line)
    problems = {m: "mood not in the library" if m not in bank else sample_problem(root, bank[m]) for m in groups}
    if not (root / "voice.wav").is_file():
        print(f"MISSING reference: {root / 'voice.wav'}")
    if a.plan:
        for mood, ls in groups.items():
            rate = bank.get(mood, {}).get("syl_per_s", "?")
            print(f"{mood}: {len(ls)} lines, {sum(len(l['say'].split()) for l in ls)} words, sample {rate} syl/s")
    missing = {str(m): {"lines": [l["id"] for l in groups[m]], "reason": reason} for m, reason in problems.items() if reason}
    if missing:
        print("MISSING or unusable moods (add only missing samples; repair changed files):", json.dumps(missing, ensure_ascii=False))
    if missing or not (root / "voice.wav").is_file():
        return 2
    if a.plan:
        print("the library covers every line; nothing to make")
        return 0
    if not a.out:
        ap.error("--out is required")
    generate(a, root, bank, groups, {l["id"]: i + 1 for i, l in enumerate(lines)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
