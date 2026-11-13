#!/usr/bin/env python3
"""Narration → timeline → sound design → final mix.

Run with the project's audio interpreter (numpy, soundfile, scipy, faster-whisper):
    python3 tools/build_audio.py --scenes 1

1. trims and level-matches every narration take (no pitch, tempo or EQ changes)
2. reads word timings back with Whisper, checks them against the script and maps them onto the
   caption tokens (a number shown as digits covers all the words it is spoken as)
3. lays the narration out on a timeline  → film/timeline.json, film/audio/vo.wav
4. asks film/film.js for its sound cues (same anchors as the picture)
5. synthesises effects and separate bed/foreground music buses → film/audio/mix.wav
"""
import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "film" / "audio"
sys.path.insert(0, str(ROOT / "tools"))
import film_config  # noqa: E402

CFG = film_config.load()
VOICE_RMS = 0.085
LEAD = 1.15          # silence before the first line: the stage opens
GAP = 0.55           # default pause between lines
# pause before a line, from film.json "gaps": room for picture (wipes, cards, jumps) in the opening, and music
# breaths of 2.5-3 s after a strong line or a reveal, so the music answers before the story goes on
GAPS = CFG.get("gaps", {})
TAIL_FIRST, TAIL_LAST = CFG.get("tail_first", 4.0), 14.0  # after the first scene: the title card; after the last: the end card and room for
                                    # YouTube's end-screen elements (5–20 s), scored by tools/music.py
TAIL_DEFAULT = 3.55       # the old scene holds while the music breathes (the motif)
SCENE_GAP = 1.25          # then the transition, just before the first line
WIPE_LEAD = 0.55          # transition → first line of the scene (film/film.js WIPE_LEAD)
PACE = 2.75               # words per second, only for provisional lines whose take is not ready yet


def db(x):
    return float(20 * np.log10(max(float(x), 1e-9)))


def envelope(x, win):
    """Moving RMS (FFT convolution can dip a hair below zero, hence the clamp)."""
    return np.sqrt(np.maximum(signal.convolve(x * x, np.ones(win) / win, mode="same"), 0))


# ---------- narration ----------
def load_take(path):
    x, sr = sf.read(ROOT / path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if sr != SR:
        x = signal.resample_poly(x, SR, sr).astype("float32")
    return x


def trim_bounds(x):
    env = envelope(x, 480)
    hot = np.flatnonzero(env > env.max() * 10 ** (-36 / 20))
    if not len(hot):
        raise ValueError("Selected narration take contains no speech")
    a = max(0, hot[0] - int(0.02 * SR))
    b = min(len(x), hot[-1] + int(0.07 * SR))
    return a, b


def trim(x):
    a, b = trim_bounds(x)
    y = x[a:b].copy()
    fi, fo = int(0.004 * SR), int(0.03 * SR)
    y[:fi] *= np.linspace(0, 1, fi)
    y[-fo:] *= np.linspace(1, 0, fo)
    return y


def tidy_pauses(x, cap=0.62, keep=0.5):
    """Skraca zbyt długie pauzy wewnątrz nagrania do `keep` s, przenikając w ciszy. Słów nie rusza."""
    env = envelope(x, 480)
    quiet = env < env.max() * 10 ** (-34 / 20)
    edges = np.flatnonzero(np.diff(np.r_[0, quiet.astype(int), 0]))
    parts, pos = [], 0
    fade = int(0.012 * SR)
    for a, b in zip(edges[::2], edges[1::2]):
        if a == 0 or b >= len(x) or (b - a) / SR <= cap:
            continue
        cut_a, cut_b = a + int(keep * SR / 2), b - int(keep * SR / 2)
        parts.append(x[pos:cut_a].copy())
        pos = cut_b
    if not parts:
        return x
    parts.append(x[pos:].copy())
    out = parts[0]
    ramp = np.linspace(0, 1, fade, dtype="float32")
    for p in parts[1:]:
        out = np.concatenate([out[:-fade], out[-fade:] * (1 - ramp) + p[:fade] * ramp, p[fade:]])
    return out


def level(x, target):
    env = envelope(x, 2400)
    voiced = x[env > env.max() * 0.1]
    gain = target / max(np.sqrt(np.mean(voiced ** 2)), 1e-6)
    gain = min(gain, 0.9 / np.abs(x).max())
    return x * gain, gain


def norm_word(w):
    w = unicodedata.normalize("NFKD", w.lower().replace("ł", "l"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in w if not unicodedata.combining(c)))


def word_times(model, x, text):
    """Whisper word timings mapped onto the script's own words."""
    words = text.split()
    dur = len(x) / SR
    x16 = signal.resample_poly(x, 1, 3).astype("float32")
    segs, _ = model.transcribe(x16, language=CFG["language"], word_timestamps=True, beam_size=5, condition_on_previous_text=False)
    heard = [w for s in segs for w in (s.words or [])]
    heard_text = " ".join(w.word.strip() for w in heard)
    a, b = [norm_word(w) for w in words], [norm_word(w.word) for w in heard]
    ratio = difflib.SequenceMatcher(None, " ".join(a), " ".join(b), autojunk=False).ratio()
    start = [None] * len(words)
    end = [None] * len(words)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            start[blk.a + k] = float(heard[blk.b + k].start)
            end[blk.a + k] = float(heard[blk.b + k].end)
    if len(a) == len(b):  # same word count: trust positions even where spelling differs
        start = [float(w.start) for w in heard]
        end = [float(w.end) for w in heard]
    # fill gaps by sharing the time between known neighbours in proportion to word length
    i = 0
    while i < len(words):
        if start[i] is not None:
            i += 1
            continue
        j = i
        while j < len(words) and start[j] is None:
            j += 1
        t0 = end[i - 1] if i > 0 else 0.0
        t1 = start[j] if j < len(words) else dur
        total = sum(len(w) + 1.5 for w in words[i:j])
        t = t0
        for k in range(i, j):
            d = (t1 - t0) * (len(words[k]) + 1.5) / total
            start[k], end[k] = t, t + d
            t += d
        i = j
    out, prev = [], 0.0
    for w, s, e in zip(words, start, end):
        s = min(max(s, prev), dur)
        e = min(max(e, s + 0.04), dur)
        out.append((w, s, e))
        prev = s
    return out, heard_text, ratio

def tone(freq, dur, decay=None, harm=((1, 1.0),), attack=0.004):
    """freq may be a number or an array (Hz per sample)."""
    n = int(dur * SR)
    f = np.full(n, freq, dtype="float64") if np.isscalar(freq) else np.asarray(freq, dtype="float64")[:n]
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = sum(a * np.sin(ph * k) for k, a in harm)
    t = np.arange(n) / SR
    env = np.minimum(1, t / attack)
    if decay:
        env = env * np.exp(-t / decay)
    fo = min(n, int(0.01 * SR))
    env[-fo:] *= np.linspace(1, 0, fo)
    return (y * env).astype("float32")


def sweep(f0, f1, dur):
    return f0 * (f1 / f0) ** (np.arange(int(dur * SR)) / (dur * SR))


def marimba(freq, dur=0.5, decay=0.16):
    return tone(freq, dur, decay, harm=((1, 1.0), (4, 0.22), (10, 0.05)), attack=0.002)


def bell(freq, dur=1.4, decay=0.45):
    return tone(freq, dur, decay, harm=((1, 1.0), (2.76, 0.35), (5.4, 0.18), (8.9, 0.07)), attack=0.002)


def air(dur, f0, f1, f2, seed, q=1.6):
    """Noise through a band that sweeps f0 → f1 → f2: paper swishes and whooshes."""
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n).astype("float32")
    out = np.zeros(n, dtype="float32")
    hop, win = 256, 1024
    w = np.hanning(win).astype("float32")
    for i in range(0, n, hop):
        p = i / max(1, n - 1)
        fc = f0 * (f1 / f0) ** (p * 2) if p < 0.5 else f1 * (f2 / f1) ** ((p - 0.5) * 2)
        lo, hi = fc / q, min(fc * q, SR * 0.45)
        sos = signal.butter(2, [lo, hi], btype="band", fs=SR, output="sos")
        a, b = max(0, i - win // 2), min(n, i + win // 2)
        seg = signal.sosfilt(sos, x[max(0, a - win):b])[-(b - a):]
        out[a:b] += seg * w[: b - a] * (hop * 2 / win)
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
    return out * env


def pad(x, n):
    return np.pad(x, (0, max(0, n - len(x))))


def seq(notes, step):
    n = int((step * len(notes) + 1.6) * SR)
    y = np.zeros(n, dtype="float32")
    for i, part in enumerate(notes):
        a = int(i * step * SR)
        y[a:a + len(part)] += part[: n - a]
    return y


HZ = lambda m: 440.0 * 2 ** ((m - 69) / 12)  # midi → Hz
PENTA = [76, 79, 81, 84, 86]  # E5 G5 A5 C6 D6



def spans_to_tokens(spans, times):
    """Spoken-word times → caption tokens (one token may cover several spoken words)."""
    out, i = [], 0
    for tok, n in spans:
        s = times[i][1]
        e = times[i + n - 1][2]
        out.append((tok, s, e))
        i += n
    return out


def true_peak_limit(x, ceiling_db=-2.0, os_factor=4, release=0.05):
    """Limiter on 4x-oversampled peaks (an estimate of true peak): the needed reduction is held ±2 ms around each peak
    and released smoothly over `release` seconds; everything below the ceiling is untouched."""
    from scipy.ndimage import maximum_filter1d
    ceiling = 10 ** (ceiling_db / 20)
    up = signal.resample_poly(x, os_factor, 1, axis=0)
    env = np.abs(up).max(axis=1)[: len(x) * os_factor].reshape(-1, os_factor).max(axis=1)[: len(x)]
    if env.max() <= ceiling:
        return x
    r = 1 - np.minimum(1.0, ceiling / np.maximum(env, 1e-9))          # reduction needed per sample
    r = maximum_filter1d(r, size=int(0.004 * SR) | 1)                 # held 2 ms either side of the peak
    a = np.exp(-1 / (release * SR))
    r = np.maximum(r, signal.lfilter([1 - a], [1, -a], r))            # released smoothly after it
    return x * (1 - np.clip(r, 0, 1))[:, None]


def selected_provenance(path, line, records):
    """Attach only generation records matching the selected bytes and spoken content."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record = records.get(line["id"])
    matches = record and record.get("sha256") == digest and record.get("text") == line["say"] and record.get("direction") == line["direction"]
    provenance = ({"status": "recorded", **{key: record.get(key) for key in
                   ("source", "generation", "processing")}} if matches else {
        "status": "unverified", "source": None, "generation": None,
        "reason": "No provenance record matches the selected file hash, spoken text and direction",
    })
    return {"sha256": digest, "provenance": provenance}


def build_voice(model, scenes, takes_dir):
    narr = [l for l in json.loads((ROOT / "audio/narration.json").read_text(encoding="utf-8"))]
    index = {l["id"]: k + 1 for k, l in enumerate(narr)}
    use = [l for l in narr if l["scene"] in scenes]
    provenance_path = ROOT / "audio/provenance.json"
    provenance = json.loads(provenance_path.read_text()).get("takes", {}) if provenance_path.exists() else {}
    t, lines, clips, manifest = LEAD, [], [], []
    for n, l in enumerate(use):
        path = takes_dir / f"output_{index[l['id']]:03d}.wav"
        provisional = not path.exists()
        source_info = {"sha256": None, "provenance": {"status": "provisional", "generation": None}}
        trim_interval, raw_duration = None, None
        if provisional:
            # take not generated yet: silence of the expected length, words spread by their length
            words = l["say"].split()
            dur0 = len(words) / PACE + 0.2
            x, gain = np.zeros(int(dur0 * SR), dtype="float32"), 1.0
            total_w = sum(len(w) + 1.5 for w in words)
            times, tt = [], 0.1
            for w in words:
                d = (dur0 - 0.2) * (len(w) + 1.5) / total_w
                times.append((w, tt, tt + d)); tt += d
            heard, ratio = "(provisional)", 1.0
        else:
            raw = load_take(path)
            bounds = trim_bounds(raw)
            trim_interval, raw_duration = [v / SR for v in bounds], len(raw) / SR
            source_info = selected_provenance(path, l, provenance)
            x = trim(raw)
            x = tidy_pauses(x, CFG.get("pause_cap", 0.62), CFG.get("pause_keep", 0.5))
            x, gain = level(x, VOICE_RMS)
            times, heard, ratio = word_times(model, x, l["say"])
        tokens = spans_to_tokens(l["spans"], times)
        if n:
            first_of_scene = use[n - 1]["scene"] != l["scene"]
            t += SCENE_GAP if first_of_scene else GAPS.get(l["id"], GAP)
        dur = len(x) / SR
        lines.append({
            "id": l["id"], "scene": l["scene"], "text": l["text"], "start": round(t, 3), "end": round(t + dur, 3), "provisional": provisional,
            "words": [{"w": w, "s": round(t + s, 3), "e": round(t + e, 3)} for w, s, e in tokens],
        })
        clips.append((t, x))
        flag = "   (provisional)" if provisional else ("" if ratio > 0.86 else "   <-- CHECK")
        print(f"{l['id']:6s} {dur:5.2f}s gain {db(gain):+5.1f} dB  match {ratio:.2f}{flag}\n    script: {l['say']}\n    heard : {heard}")
        manifest.append({
            "id": l["id"], "take": None if provisional else str(path.relative_to(ROOT)), "text": l["say"], "direction": l["direction"],
            **source_info, "duration_raw": raw_duration, "trim_seconds": trim_interval,
            "duration_trimmed": round(dur, 3), "gain_db": round(db(gain), 2), "asr": heard, "asr_match": round(ratio, 3),
        })
        t += dur
        last_of_scene = n + 1 == len(use) or use[n + 1]["scene"] != l["scene"]
        if last_of_scene:
            t += TAIL_FIRST if l["scene"] == use[0]["scene"] else TAIL_LAST if l["scene"] == use[-1]["scene"] else TAIL_DEFAULT
    total = round(t, 3)
    vo = np.zeros(int(total * SR) + SR, dtype="float32")
    for t0, x in clips:
        i = int(t0 * SR)
        vo[i:i + len(x)] += x
    from music import music_breaks
    tl = {"fps": 30, "duration": total, "lines": lines}
    tl["music_breaks"] = [{"start": a, "end": b} for a, b in music_breaks(tl)]
    (ROOT / "film/timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "audio/manifest.json").write_text(json.dumps({
        "generation": "See matching per-take provenance; unverified settings remain unknown",
        "processing": "trim silence, long inner pauses shortened",
        "takes": manifest,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return tl, vo[: int(total * SR)]


def lowpass(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc, btype="low", fs=SR, output="sos"), x).astype("float32")


def highpass(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc, btype="high", fs=SR, output="sos"), x).astype("float32")


def noise(dur, seed):
    return np.random.default_rng(seed).standard_normal(int(dur * SR)).astype("float32")


def crackle(dur, seed, density=900, decay=0.0016):
    """Paper crinkle: sparse little clicks through a bright band."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    y = np.zeros(n, dtype="float32")
    k = int(0.004 * SR)
    click = (rng.standard_normal(k) * np.exp(-np.arange(k) / (decay * SR))).astype("float32")
    for a in rng.integers(0, max(1, n - k), int(density * dur)):
        y[a:a + k] += click * rng.uniform(0.2, 1.0)
    return highpass(y, 1800) * np.sin(np.pi * np.linspace(0, 1, n)) ** 0.7


def make_sfx():
    rng = np.random.default_rng(7)
    s = {}
    s["pop"] = tone(sweep(330, 820, 0.09), 0.09, 0.04) * 0.9
    s["hop"] = tone(sweep(250, 560, 0.14), 0.14, 0.07) * 0.8
    t = np.arange(int(0.5 * SR)) / SR
    s["boing"] = tone(175 + 70 * np.exp(-t * 6) * np.sin(2 * np.pi * 17 * t), 0.5, 0.16, harm=((1, 1.0), (2, 0.3))) * 0.8
    t = np.arange(int(0.42 * SR)) / SR
    s["slide_down"] = tone(sweep(900, 320, 0.42) * (1 + 0.012 * np.sin(2 * np.pi * 9 * t)), 0.42, 0.5, harm=((1, 1.0), (2, 0.12)), attack=0.03) * 0.42
    s["swish"] = air(0.24, 1400, 5200, 2200, 1) * 0.5
    s["whoosh"] = air(0.6, 280, 2600, 520, 2) * 0.7
    # painted paper strips sliding over the stage: a long airy slide with crinkle
    st = air(0.95, 220, 2400, 400, 3) * 0.8
    s["strips"] = st + crackle(0.95, 4, 700) * 0.35
    thud = tone(sweep(150, 58, 0.18), 0.18, 0.07)
    s["thud"] = thud * 0.9 + pad(lowpass(noise(0.03, 5), 900) * np.linspace(1, 0, int(0.03 * SR)) ** 2 * 0.5, len(thud))
    s["thud_soft"] = s["thud"] * 0.5
    st = lowpass(noise(0.07, 6), 1600) * np.exp(-np.arange(int(0.07 * SR)) / (0.012 * SR))
    s["step"] = (st * 0.7 + pad(tone(sweep(120, 70, 0.07), 0.07, 0.03) * 0.5, len(st))).astype("float32")
    s["glint"] = seq([bell(HZ(m), 0.8, 0.22) * 0.32 for m in (91, 96)], 0.06)
    s["sparkle"] = seq([bell(HZ(m + 12), 0.7, 0.16) * 0.32 for m in (84, 88, 91, 96, 93)], 0.05)
    s["clank"] = (bell(HZ(64), 0.6, 0.12) * 0.4 + bell(HZ(71.3), 0.6, 0.1) * 0.3) * 0.8
    s["rise"] = air(0.9, 300, 1800, 3000, 8) * 0.4 + tone(sweep(220, 660, 0.9), 0.9, None, harm=((1, 1.0), (2, 0.2)), attack=0.3) * np.sin(np.pi * np.linspace(0, 1, int(0.9 * SR))) * 0.12
    snap = highpass(noise(0.02, 9), 2500) * np.exp(-np.arange(int(0.02 * SR)) / (0.003 * SR))
    t = np.arange(int(0.45 * SR)) / SR
    s["snap"] = pad(snap * 1.2, int(0.45 * SR)) + tone(130 + 60 * np.exp(-t * 7) * np.sin(2 * np.pi * 21 * t), 0.45, 0.12) * 0.45
    s["fall"] = tone(sweep(700, 160, 0.8), 0.8, 0.9, attack=0.02) * 0.25 + air(0.8, 2400, 900, 300, 10) * 0.5
    st = tone(sweep(110, 50, 0.16), 0.16, 0.05)
    s["stamp"] = st + pad(lowpass(noise(0.05, 11), 2400) * np.linspace(1, 0, int(0.05 * SR)) ** 3 * 0.7, len(st))
    for k, m in enumerate((88, 91, 93, 96)):
        s[f"coin_{k}"] = bell(HZ(m + 7), 0.5, 0.09) * 0.35 + bell(HZ(m + 12.4), 0.5, 0.06) * 0.2
    cl = lowpass(noise(0.12, 12), 700) * np.exp(-np.arange(int(0.12 * SR)) / (0.025 * SR))
    s["clay"] = cl * 1.2
    s["chime"] = seq([bell(HZ(m), 1.6, 0.5) * 0.4 for m in (74, 77, 81, 86)], 0.08)
    return s


def cues(tl):
    code = ("import {soundCues} from './film/film.js'; import fs from 'node:fs';"
            "console.log(JSON.stringify(soundCues(JSON.parse(fs.readFileSync('film/timeline.json','utf8')))))")
    out = subprocess.run(["node", "--input-type=module", "-e", code], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", default="1", help="comma-separated scene numbers, or 'all'")
    ap.add_argument("--takes", default="audio/takes")
    ap.add_argument("--out", default=None, help="mix path (default film/audio/mix.wav)")
    ap.add_argument("--reuse", action="store_true", help="reuse film/timeline.json and film/audio/vo.wav (no Whisper)")
    args = ap.parse_args()
    narr = json.loads((ROOT / "audio/narration.json").read_text(encoding="utf-8"))
    scenes = sorted({l["scene"] for l in narr}) if args.scenes == "all" else [int(s) for s in args.scenes.split(",")]
    OUT.mkdir(parents=True, exist_ok=True)
    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    if args.reuse:
        tl = json.loads((ROOT / "film/timeline.json").read_text(encoding="utf-8"))
        vo, _ = sf.read(OUT / "vo.wav", dtype="float32")
    else:
        model = WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True)
        tl, vo = build_voice(model, scenes, ROOT / args.takes)
    t1 = time.perf_counter()
    total = tl["duration"]
    n = len(vo)
    sf.write(OUT / "vo.wav", vo, SR)

    sfx = make_sfx()
    fx = np.zeros((n + SR * 3, 2), dtype="float32")
    rng = np.random.default_rng(3)
    cue_list = cues(tl)
    for c in cue_list:
        x = sfx[c["name"]] * c["gain"]
        a = int(c["t"] * SR)
        pan = 0.5 + rng.uniform(-0.18, 0.18)
        fx[a:a + len(x), 0] += x[: len(fx) - a] * (1 - pan) * 1.4
        fx[a:a + len(x), 1] += x[: len(fx) - a] * pan * 1.4
    fx = fx[:n]

    import music as score
    music_stems = {}
    music, solo = score.render(tl, vo, stems=music_stems, mix_settings=CFG.get("music_mix"))
    fit = lambda x: np.pad(x[:n], ((0, max(0, n - len(x))), (0, 0)))
    music, solo = fit(music), fit(solo)
    # Poziomy muzyki liczy tools/music.py względem głosu, kwestia po kwestii.
    g = 1.0
    fx = fx * (1 - 0.6 * score.duck_envelope(vo, len(fx), tl))[:, None]
    mix = np.stack([vo, vo], 1) * 1.0 + fx * 0.32 + music
    # loudness: YouTube plays back at about -14 LUFS, so master there; the AAC encoder can lift an inter-sample peak by
    # about 3 dB, so the true peak (4x oversampled) is held at -2 dBTP to stay under -1 dBTP in the encoded file
    loud = score.lufs(mix)
    if not np.isfinite(loud):   # a silent mix (nothing to hear yet): leave it as it is
        loud = -14.0
    mix = mix * 10 ** ((-14 - loud) / 20)
    peak = np.abs(mix).max()
    if peak > 0.89:
        mix = np.tanh(mix / 0.89 * 1.0) * 0.89
    mix = true_peak_limit(mix, -2.0)
    out_path = Path(args.out) if args.out else OUT / "mix.wav"
    sf.write(out_path, mix, SR, subtype="PCM_24")
    k_master = 10 ** ((-14 - loud) / 20)
    sf.write(out_path.with_name(out_path.stem + "_music.wav"), (music * k_master).astype("float32"), SR, subtype="PCM_24")
    for name, stem in music_stems.items():
        sf.write(out_path.with_name(out_path.stem + "_music_" + name + ".wav"),
                 (fit(stem) * g * k_master).astype("float32"), SR, subtype="PCM_24")
    sf.write(out_path.with_name(out_path.stem + "_music_solo.wav"), np.clip(solo * k_master, -1, 1).astype("float32"), SR, subtype="PCM_24")
    print(f"loudness {loud:.1f} LUFS → -14 LUFS, final {score.lufs(mix):.1f} LUFS")
    (ROOT / "audio/cues.json").write_text(json.dumps(cue_list, indent=1))
    t2 = time.perf_counter()
    print(f"\nduration {total:.2f}s  cues {len(cue_list)}  mix peak {db(np.abs(mix).max()):.1f} dBFS  rms {db(np.sqrt(np.mean(mix ** 2))):.1f} dBFS")
    print(f"timing: whisper alignment {t1 - t0:.1f}s, sound design + mix {t2 - t1:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
