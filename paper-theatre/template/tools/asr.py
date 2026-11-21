#!/usr/bin/env python3
"""Speech recognition of the narration takes with NVIDIA Parakeet TDT 0.6B v3, cached per file.

The recogniser is the GGUF file that Superwhisper's Offline Lite mode uses for dictation
(parakeet-tdt-0.6b-v3-Q4_K_M.gguf, converted from nvidia/parakeet-tdt-0.6b-v3), run by transcribe.cpp (the
`transcribe-cpp` Python package; ggml on Vulkan when a GPU is present, otherwise CPU). One model file serves
dictation and the film tools.

Model file, first found: film.json "asr" → "model", $PARAKEET_GGUF, Superwhisper's models directory
(`superwhisper models download transcription` puts it in ~/.local/share/superwhisper/models).

One recognition serves two stages: the take check (tools/check_takes.py) writes the cache and the word timing
(tools/build_audio.py) reads it, so every take is recognised once.

A cache entry, audio/asr_cache/<sha256 of the file>.json, is valid while:
  - the file's SHA-256 is unchanged: a replaced line (retake, fix) has another hash, so only that line is recomputed;
  - the model file's SHA-256, its settings, the film's language and CODE_VERSION are unchanged: changing any of them
    invalidates it.
Word times are relative to the raw file; tools/build_audio.py maps them through its trim and pause edits, so
changing those settings needs no new recognition. Each word also carries "p", the lowest probability of its tokens
(a confidence hint for listening, not a verdict).

Usage: python3 tools/asr.py audio/takes/output_*.wav
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "audio/asr_cache"
CODE_VERSION = 2
SR_ASR = 16000
MODEL_FILE = "parakeet-tdt-0.6b-v3-Q4_K_M.gguf"
SUPERWHISPER_MODELS = Path.home() / ".local/share/superwhisper/models"
MODEL = {"model": "nvidia/parakeet-tdt-0.6b-v3", "file": MODEL_FILE, "runtime": "transcribe.cpp", "timestamps": "token"}


def config():
    return json.loads((ROOT / "film.json").read_text(encoding="utf-8"))


def language():
    return config().get("language", "pl")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_path():
    for candidate in (config().get("asr", {}).get("model"), os.environ.get("PARAKEET_GGUF"),
                      SUPERWHISPER_MODELS / MODEL_FILE):
        if candidate and Path(candidate).expanduser().is_file():
            return Path(candidate).expanduser().resolve()
    raise SystemExit(f"{MODEL_FILE} not found: run `superwhisper models download transcription`, "
                     "or set film.json asr.model / $PARAKEET_GGUF")


_MODEL_SHA = {}


def model_sha():
    p = model_path()
    if p not in _MODEL_SHA:
        _MODEL_SHA[p] = sha256(p)
    return _MODEL_SHA[p]


def key():
    return {"params": MODEL, "model_sha256": model_sha(), "language": language(), "code_version": CODE_VERSION}


def load_16k(path):
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if sr != SR_ASR:
        g = np.gcd(sr, SR_ASR)
        x = signal.resample_poly(x, SR_ASR // g, sr // g).astype("float32")
    return np.ascontiguousarray(x, dtype=np.float32)


class Recogniser:
    """Loads the model only for the first take that is not in the cache."""

    def __init__(self):
        self.model, self.load_seconds = None, 0.0

    def load(self):
        if self.model is not None:
            return
        t = time.perf_counter()
        import transcribe_cpp
        self.model = transcribe_cpp.Model(str(model_path()))
        self.load_seconds = time.perf_counter() - t

    def versions(self):
        import importlib.metadata as md
        return {"transcribe-cpp": md.version("transcribe-cpp"), "model_file": str(model_path())}

    def run(self, paths):
        """→ list of (words, text, seconds) in the order of the paths."""
        self.load()
        out = []
        with self.model.session() as session:
            for p in paths:
                x = load_16k(p)
                t = time.perf_counter()
                r = session.run(x, timestamps=MODEL["timestamps"])
                secs = time.perf_counter() - t
                lowest = {}
                for tok in r.tokens:
                    if tok.word_index >= 0 and np.isfinite(tok.p):
                        lowest[tok.word_index] = min(tok.p, lowest.get(tok.word_index, 1.0))
                words = [{"w": w.text.strip(), "s": round(w.t0_ms / 1000, 3), "e": round(w.t1_ms / 1000, 3),
                          "p": round(float(lowest.get(i, float("nan"))), 3)}
                         for i, w in enumerate(r.words) if w.text.strip()]
                out.append((words, r.text.strip(), secs))
        return out


def cache_path(digest):
    return CACHE / f"{digest}.json"


def read_cache(digest):
    f = cache_path(digest)
    if not f.exists():
        return None
    try:
        e = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return e if e.get("key") == key() and e.get("sha256") == digest else None


def transcribe(paths, verbose=True):
    """Results for the paths (dicts as in the cache file + 'path', 'cached') and the call's statistics.
    Recognises only what is missing from the cache or has changed."""
    t0 = time.perf_counter()
    paths = [Path(p) for p in paths]
    digests = [sha256(p) for p in paths]
    results, todo = [None] * len(paths), []
    for i, d in enumerate(digests):
        e = read_cache(d)
        if e is None:
            todo.append(i)
        else:
            results[i] = {**e, "path": str(paths[i]), "cached": True}
    rec = Recogniser()
    if todo:
        ran = rec.run([paths[i] for i in todo])
        versions = rec.versions()
        for i, (words, text, secs) in zip(todo, ran):
            info = sf.info(str(paths[i]))
            e = {"key": key(), "sha256": digests[i], "versions": versions, "audio_seconds": round(info.duration, 3),
                 "transcribe_seconds": round(secs, 3), "created": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "source_name": paths[i].name, "text": text, "words": words}
            f = cache_path(digests[i])
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(f)
            results[i] = {**e, "path": str(paths[i]), "cached": False}
    stats = {"model": MODEL["file"], "files": len(paths), "cache_hits": len(paths) - len(todo), "computed": len(todo),
             "model_load_seconds": round(rec.load_seconds, 2),
             "transcribe_seconds": round(sum(r["transcribe_seconds"] for r in results if not r["cached"]), 2),
             "wall_seconds": round(time.perf_counter() - t0, 2),
             "audio_seconds": round(sum(r["audio_seconds"] for r in results), 1)}
    if verbose:
        print(f"[asr] {stats['files']} files, {stats['cache_hits']} from the cache, {stats['computed']} recognised "
              f"(model {stats['model_load_seconds']} s, recognition {stats['transcribe_seconds']} s, total {stats['wall_seconds']} s)",
              file=sys.stderr)
    return results, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    res, stats = transcribe(a.files)
    for r in res:
        print(f"{Path(r['path']).name}  {'cache' if r['cached'] else 'new  '}  {r['audio_seconds']:5.1f}s  {r['text']}")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
