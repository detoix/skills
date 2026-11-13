#!/usr/bin/env python3
"""Assemble the film score from a configured library of recorded modules.

film.json -> "music" opisuje, jaki klimat gra pod którą kwestią; "palette" wybiera paletę,
a "borrow" pozwala zaczerpnąć wybrany klimat z innej palety biblioteki.

Dwie szyny, jak w szablonie:
  - podkład (bed): pętle klimatu pod narracją, poziom liczony kwestia po kwestii względem głosu; krótkie pauzy mostkowane,
    w pauzach dłuższych niż HOLD_GAP podkład wychodzi o `pause_db`;
  - pierwszy plan (foreground): sygnał po tytule, przejścia między scenami, oddechy po mocnych kwestiach, ekran końcowy.
    Gra na swoim poziomie w ciszy, ustępuje mowie, gdyby na nią zachodził.
Join modules at bar lines and use a compatible key and tempo across each palette.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
ROOT = Path(__file__).resolve().parent.parent
WIPE_LEAD = 0.55   # wipe → first line of a scene (film/film.js WIPE_LEAD)
BREATH = 2.4       # a pause at least this long is a scored break
END_SCREEN = 8.0   # a tail after the last line longer than this is the end screen, scored to the end (not a break)
END_FADE = 3.0     # the score fades over the last seconds of the film only
HOLD_GAP = 0.9     # shorter pauses between lines keep the bed at its speech level
JOIN = 0.015       # przenikanie na kresce taktowej
ENTRY_LEAD = 1.0   # wejście podkładu przed pierwszą kwestią sceny


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Pack:
    """Dostęp do modułów palety z zapisem pochodzenia."""

    def __init__(self, cfg, palette):
        self.root = (ROOT / cfg["package"]).resolve()
        self.palette = palette
        self.borrow = cfg.get("borrow", {})   # klimat z drugiej palety: film.json -> music.borrow
        self.cache = {}
        self.used = {}

    def path(self, mood, kind):
        p = self.borrow.get(mood, self.palette)
        names = {
            "petla": f"{mood}/{mood}_petla_{p}_02_petla_A_4takty.wav",
            "wejscie": f"{mood}/{mood}_warianty_{p}_04_wejscie_1takt.wav",
            "oddech": f"{mood}/{mood}_warianty_{p}_05_oddech_1takt.wav",
            "oddech2": f"{mood}/{mood}_warianty_{p}_06_oddech_2takty.wav",
            "wariant": f"{mood}/{mood}_warianty_{p}_07_wariant_B_4takty.wav",
            "koniec": f"{mood}/{mood}_warianty_{p}_08_zakonczenie.wav",
            "sygnal": f"motyw/motyw_{p}_02_sygnal.wav",
            "tytul": f"motyw/motyw_{p}_03_tytul.wav",
            "ekran": f"motyw/motyw_{p}_04_ekran_koncowy.wav",
        }
        if mood == "przejscia":
            return self.root / p / "przejscia" / f"przejscia_{p}_przejscie_{kind}.wav"
        return self.root / p / names[kind]

    def read(self, mood, kind):
        path = self.path(mood, kind)
        if path not in self.cache:
            x, sr = sf.read(path, dtype="float32", always_2d=True)
            assert sr == SR and x.shape[1] == 2, path
            self.cache[path] = x
            self.used[str(path.relative_to(self.root))] = _sha(path)
        return self.cache[path]


def fades(x, fade_in=0.0, fade_out=0.0):
    y = x.copy()
    a, b = int(fade_in * SR), int(fade_out * SR)
    if a:
        y[:a] *= (np.sin(np.linspace(0, np.pi / 2, a)) ** 2)[:, None]
    if b:
        y[-b:] *= (np.cos(np.linspace(0, np.pi / 2, b)) ** 2)[:, None]
    return y


def add(bus, x, t):
    i = max(0, int(round(t * SR)))
    n = min(len(x), len(bus) - i)
    if n > 0:
        bus[i:i + n] += x[:n]


def sequence(pack, mood, frames, safe_variants, entry=True, turn=0, every=3):
    """Forma segmentu: [wejście] A A B A A B … przycięta do długości; moduły łączone na kreskach taktowych."""
    parts = []
    if entry and safe_variants:
        parts.append(pack.read(mood, "wejscie"))
    n = turn
    while sum(len(p) for p in parts) < frames + SR:
        use_b = safe_variants and n % every == every - 1
        parts.append(pack.read(mood, "wariant" if use_b else "petla"))
        n += 1
    j = int(JOIN * SR)
    out = parts[0]
    ramp = np.linspace(0, 1, j)[:, None]
    for p in parts[1:]:
        mid = out[-j:] * (1 - ramp) + p[:j] * ramp
        out = np.concatenate([out[:-j], mid, p[j:]])
    return out[:frames]


def plan_segments(tl, cfg):
    """Odcinki podkładu: jeden klimat na rozdział (film.json -> music.plan: numer rozdziału -> klimat).
    Klimat zmienia się tylko na karcie rozdziału; sąsiednie rozdziały mogą mieć ten sam."""
    lines = sorted(tl["lines"], key=lambda l: l["start"])
    plan = {int(k): v for k, v in cfg["plan"].items()}
    segs = []
    for i, line in enumerate(lines):
        if i and lines[i - 1]["scene"] == line["scene"]:
            continue
        if line["scene"] not in plan:
            raise ValueError(f"music plan: rozdział {line['scene']} nie ma klimatu")
        segs.append({"start": 0.0 if i == 0 else line["start"] - ENTRY_LEAD, "mood": plan[line["scene"]], "entry": True, "first": line["id"]})
    scene_end = {}
    for line in lines:
        scene_end[line["scene"]] = max(scene_end.get(line["scene"], 0), line["end"])
    by_id = {l["id"]: l for l in lines}
    for s in segs:
        s["end"] = scene_end[by_id[s["first"]]["scene"]] + 0.35
        s["crossfade_out"] = False
    return segs

def level_cue(x, target_db=-21.5, limit_db=6.0):
    """Przejścia z jednego nagrania różnią się głośnością nawet o 10 dB; wyrównanie do wspólnego poziomu, bez ściskania dynamiki."""
    body = x[: max(1, len(x) - int(0.4 * SR))]
    gain = np.clip(target_db - 20 * np.log10(rms(body)), -limit_db, limit_db)
    return x * 10 ** (gain / 20)


def active_mask(vo):
    hop = int(0.01 * SR)
    k = len(vo) // hop
    rms = np.sqrt(np.mean(vo[: k * hop].reshape(k, hop) ** 2, axis=1))
    gate = max(10 ** (-42 / 20), float(np.percentile(rms, 99)) * 0.06)
    return np.repeat(rms > gate, hop)[: len(vo)]


def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, dtype="float64") ** 2)) + 1e-12)


def level_bed(bed, vo, tl, target_db, pause_db):
    """Poziom podkładu: krzywa pasażowa z kwestii. Pauzy krótsze niż HOLD_GAP nie ruszają poziomu."""
    lines = sorted(tl["lines"], key=lambda l: l["start"])
    mask = active_mask(vo)
    mono = bed.mean(1)
    desired = []
    for l in lines:
        a, b = int(l["start"] * SR), int(l["end"] * SR)
        m = mask[a:b]
        if m.sum() < SR * 0.2:
            desired.append(None)
            continue
        desired.append(rms(vo[a:b][m]) / (rms(bed[a:b][m]) * 10 ** (target_db / 20)))
    known = [d for d in desired if d is not None]
    base = float(np.median(known)) if known else 1.0
    desired = [base if d is None else d for d in desired]
    # wyrównanie między kwestiami tego samego odcinka: bez skoków większych niż 1,5 dB na kwestię
    db = 20 * np.log10(np.array(desired))
    for i in range(1, len(db)):
        db[i] = np.clip(db[i], db[i - 1] - 1.5, db[i - 1] + 1.5) if lines[i]["scene"] == lines[i - 1]["scene"] else db[i]
    grid = np.arange(0, len(bed) / SR + 0.01, 0.01)
    curve = np.full(len(grid), 20 * np.log10(base) + pause_db)
    for i, l in enumerate(lines):
        curve[(grid >= l["start"] - 0.05) & (grid <= l["end"] + 0.05)] = db[i]
        if i + 1 < len(lines) and lines[i + 1]["start"] - l["end"] < HOLD_GAP:
            curve[(grid > l["end"]) & (grid < lines[i + 1]["start"])] = max(db[i], db[i + 1])
        elif i + 1 < len(lines):
            curve[(grid > l["end"] + 0.05) & (grid < lines[i + 1]["start"] - 0.05)] = max(db[i], db[i + 1]) + pause_db
    from scipy.ndimage import gaussian_filter1d
    curve = gaussian_filter1d(curve, sigma=9, mode="nearest")
    # mowa zawsze wygrywa: krzywa nie przekracza poziomu kwestii na jej początku i końcu
    for i, l in enumerate(lines):
        idx = (grid >= l["start"]) & (grid <= l["end"])
        curve[idx] = np.minimum(curve[idx], db[i] + 0.5)
    gain = 10 ** (np.interp(np.arange(len(bed)) / SR, grid, curve) / 20)
    return bed * gain[:, None]


def compose(tl, cfg, pack):
    """Układa podkład i pierwszy plan; zwraca szyny (bez wyrównania do głosu) i listę zdarzeń."""
    n = int(tl["duration"] * SR) + SR
    bed = np.zeros((n, 2), dtype="float32")
    fg = np.zeros((n, 2), dtype="float32")
    events = []
    safe = set(cfg.get("variants_safe", []))
    turn = {}
    for seg in plan_segments(tl, cfg):
        frames = int((seg["end"] - seg["start"]) * SR) + int(0.5 * SR)
        mood = seg["mood"]
        x = sequence(pack, mood, frames, mood in safe, entry=seg["entry"], turn=turn.get(mood, 0), every=cfg.get("variant_every", {}).get(mood, 3))
        turn[mood] = turn.get(mood, 0) + 1
        x = fades(x, fade_in=0.008 if seg["entry"] else 0.25, fade_out=0.5)
        add(bed, x, seg["start"])
        events.append({"bus": "bed", "t": round(seg["start"], 3), "mood": mood, "until": round(seg["end"], 3), "entry": seg["entry"]})
    lines = sorted(tl["lines"], key=lambda l: l["start"])
    ends = {}
    for l in lines:
        ends[l["scene"]] = l
    scenes = sorted(ends)
    k = 0
    for s in scenes[:-1]:
        last = ends[s]
        t = last["end"] + 0.2
        if s == scenes[0]:
            x = pack.read("motyw", "sygnal")
            add(fg, x * 10 ** (cfg["title_db"] / 20), t)
            events.append({"bus": "fg", "t": round(t, 3), "cue": "sygnal"})
        else:
            gesture = cfg["transitions"][k % len(cfg["transitions"])]
            k += 1
            x = level_cue(pack.read("przejscia", gesture))
            add(fg, x * 10 ** (cfg["transition_db"] / 20), t)
            events.append({"bus": "fg", "t": round(t, 3), "cue": f"przejscie_{gesture}"})
    # oddechy: pauzy wpisane do film.json -> music.breaths {kwestia po pauzie: moduł klimatu}
    by_id = {l["id"]: (i, l) for i, l in enumerate(lines)}
    for line_id, mood in cfg.get("breaths", {}).items():
        if line_id not in by_id:   # budowa części filmu, np. pilot sceny 1
            continue
        i, l = by_id[line_id]
        gap_start, gap_end = lines[i - 1]["end"], l["start"]
        x = pack.read(mood, "oddech")
        room = int((gap_end - gap_start - 0.15) * SR)
        y = fades(x[:min(room, len(x))], fade_in=0.005, fade_out=0.35)
        add(fg, y * 10 ** (cfg["breath_db"] / 20), gap_start + 0.1)
        events.append({"bus": "fg", "t": round(gap_start + 0.1, 3), "cue": f"oddech {mood}", "before": line_id})
    # ekran końcowy: dwa takty motywu i zakończenie, razem około 14 s; gra do końca filmu
    last = lines[-1]
    head = pack.read("motyw", "tytul")[: len(pack.read("motyw", "sygnal"))]
    tail = pack.read("motyw", "ekran")
    j = int(0.05 * SR)
    ramp = np.linspace(0, 1, j)[:, None]
    outro = np.concatenate([head[:-j], head[-j:] * (1 - ramp) + tail[:j] * ramp, tail[j:]])
    t = last["end"] + 0.25
    room = int((tl["duration"] - t) * SR)
    outro = outro[:room] if len(outro) > room else outro
    fade_len = min(int(END_FADE * SR), len(outro))
    if len(outro) >= room:
        outro = fades(outro, fade_out=END_FADE)
    add(fg, outro * 10 ** (cfg["outro_db"] / 20), t)
    events.append({"bus": "fg", "t": round(t, 3), "cue": "motyw: 2 takty + zakończenie", "seconds": round(len(outro) / SR, 2)})
    return bed, fg, events


def music_breaks(tl):
    """Absolute scored windows; an explicitly empty list means no scored breaks."""
    if "music_breaks" in tl:
        windows = tl["music_breaks"]
    else:
        lines = sorted(tl["lines"], key=lambda line: line["start"])
        windows = [{"start": a["end"], "end": b["start"]}
                   for a, b in zip(lines, lines[1:]) if b["start"] - a["end"] >= BREATH]
        if lines and tl["duration"] - lines[-1]["end"] >= BREATH:
            windows.append({"start": lines[-1]["end"], "end": tl["duration"]})
    result = []
    for window in windows:
        a, b = float(window["start"]), float(window["end"])
        if not np.isfinite([a, b]).all() or not 0 <= a < b <= tl["duration"]:
            raise ValueError("music_breaks must be finite windows within the timeline")
        result.append((a, b))
    return sorted(result)


def break_bed_gain(tl, n, db=-12.0, fade_seconds=0.25):
    """Additional bed attenuation, including the ending; never raise the bed."""
    if not np.isfinite([db, fade_seconds]).all() or db > 0 or fade_seconds <= 0:
        raise ValueError("bed_break_db must be non-positive and break_fade_seconds positive")
    gain = np.ones(n, dtype="float32")
    depth = 10 ** (db / 20)
    for start, end in music_breaks(tl):
        if end >= tl["duration"] - 0.05 and end - start > END_SCREEN:
            continue                              # the end screen: its level is set in render()
        a, b = max(0, int(start * SR)), min(n, int(end * SR))
        if b <= a:
            continue
        t = np.arange(b - a) / SR
        fade = min(fade_seconds, (end - start) / 2)
        amount = np.minimum(np.clip(t / fade, 0, 1), np.clip((end - start - t) / fade, 0, 1))
        amount = 0.5 - 0.5 * np.cos(np.pi * amount)
        gain[a:b] = np.minimum(gain[a:b], 1 - (1 - depth) * amount)
    return gain


def duck_foreground(m, duck):
    """Pierwszy plan ustępuje tylko mowie: -12 dB pod narracją, poza nią gra na swoim poziomie."""
    return m * (1 - 0.75 * duck)[:, None]




def render(tl, vo, stems=None, mix_settings=None):
    """Miks podkładu i pierwszego planu z nagrań pakietu, poziomy względem głosu. Zwraca miks i partyturę bez wyrównania."""
    settings = mix_settings or {}
    cfg = json.loads((ROOT / "film.json").read_text(encoding="utf-8"))["music"]
    palette = cfg["palette"]
    pack = Pack(cfg, palette)
    bed, fg, events = compose(tl, cfg, pack)
    solo = bed + fg
    n = min(len(bed), len(vo))
    bed, fg = bed[:n], fg[:n]
    vo = vo[:n]
    bed = level_bed(bed, vo, tl, cfg["voice_over_bed_db"], cfg["pause_db"])
    # Bez stałego wycinania środka pasma: przez nie muzyki nie było słychać.
    bed = bed * break_bed_gain(tl, len(bed), settings.get("bed_break_db", -12.0),
                               settings.get("break_fade_seconds", 0.25))[:, None]
    fg = duck_foreground(fg, duck_envelope(vo, len(fg), tl))
    if stems is not None:
        stems["bed"] = bed.astype("float32")
        stems["foreground"] = fg.astype("float32")
    manifest = {"palette": palette, "package": str(pack.root), "sources_sha256": pack.used, "events": events,
                "voice_over_bed_db": cfg["voice_over_bed_db"], "pause_db": cfg["pause_db"]}
    (ROOT / "audio/music_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return (bed + fg).astype("float32"), solo.astype("float32")


HOLD = 2.0       # pauses shorter than this (between words, between lines of one passage) keep the music down
LEAD_IN = 0.35   # the dip starts this long before the narrator does (offline, so it can look ahead)
RAMP_DN = 0.5    # seconds to go down, raised-cosine
RAMP_UP = 1.0    # seconds to come back up, raised-cosine


def duck_envelope(vo, n, tl=None):
    """0..1 'a passage of narration is running' envelope, phrase-level like a mixer's hand on the fader.

    Speech is detected per 10 ms, then every pause shorter than HOLD is bridged, so the music never moves
    between words or between the lines of one passage. The dip begins LEAD_IN before the voice and is a
    RAMP_DN fade; after the passage the music comes back over RAMP_UP. Sample-aligned, length n.
    """
    hop = int(0.01 * SR)
    frames = len(vo) // hop
    rms = np.sqrt(np.mean(vo[: frames * hop].reshape(frames, hop) ** 2, axis=1))
    speech = rms > 0.006
    active = speech.copy()
    # bridge short pauses (hold)
    idx = np.flatnonzero(active)
    if len(idx):
        jumps = np.flatnonzero(np.diff(idx) > 1)
        for j in jumps:
            a, b = idx[j], idx[j + 1]
            if (b - a) * 0.01 < HOLD:
                active[a:b] = True
    # passages → raised-cosine fades, starting LEAD_IN early
    env = np.zeros(frames)
    edges = np.diff(np.concatenate([[0], active.astype(int), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    dn, up, lead = int(RAMP_DN / 0.01), int(RAMP_UP / 0.01), int(LEAD_IN / 0.01)
    ramp = lambda k: 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k))
    for s, e in zip(starts, ends):
        a = max(0, s - lead)
        env[a:e] = 1.0
        r0 = max(0, a - dn + 1)
        env[r0:a] = np.maximum(env[r0:a], ramp(a - r0 + 1)[:-1] if a > r0 else [])
        r1 = min(frames, e + up)
        env[e:r1] = np.maximum(env[e:r1], ramp(up)[::-1][: r1 - e])
    # Override holds only inside actual silence in intentional scored windows.
    if tl is not None:
        for start, end in music_breaks(tl):
            a = max(0, int(np.ceil(start / 0.01)))
            b = min(frames, int(end / 0.01))
            silent = ~speech[a:b]
            edges = np.diff(np.r_[0, silent.astype(int), 0])
            for left, right in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
                left, right = a + left, a + right
                count = right - left
                fade = min(max(1, int(0.2 / 0.01)), count // 2)
                local = np.zeros(count)
                if fade:
                    if left > 0 and env[left - 1] > 0:
                        local[:fade] = (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fade))) * env[left - 1]
                    if right < frames and env[right] > 0:
                        local[-fade:] = np.maximum(local[-fade:],
                            (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))) * env[right])
                elif count:
                    local[:] = max(env[left - 1] if left else 0, env[right] if right < frames else 0)
                env[left:right] = local
        env[speech] = 1.0
    duck = np.repeat(env, hop)
    return np.pad(duck, (0, max(0, n - len(duck))))[:n]


# ---------- loudness (ITU-R BS.1770) ----------
def lufs(x):
    """Integrated loudness of a stereo (n, 2) or mono signal at 48 kHz."""
    x = np.atleast_2d(x.T).T if x.ndim == 1 else x
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1, -2, 1], [1, -1.99004745483398, 0.99007225036621]
    k = signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=0), axis=0)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    ms = np.array([np.sum(np.mean(k[i:i + blk] ** 2, axis=0)) for i in range(0, len(k) - blk, hop)])
    ld = -0.691 + 10 * np.log10(ms + 1e-12)
    ms = ms[ld > -70]
    rel = -0.691 + 10 * np.log10(ms.mean()) - 10
    ms = ms[-0.691 + 10 * np.log10(ms) > rel]
    return float(-0.691 + 10 * np.log10(ms.mean()))


def preflight():
    """Przegląd biblioteki przed produkcją: czego z planu filmu brakuje i które pętle mogą zniknąć pod głosem."""
    import soundfile as sf
    cfg = json.loads((ROOT / "film.json").read_text(encoding="utf-8"))["music"]
    pack = Pack(cfg, cfg["palette"])
    safe = set(cfg.get("variants_safe", []))
    need = [("motyw", "sygnal"), ("motyw", "tytul"), ("motyw", "ekran")] + [("przejscia", g) for g in cfg.get("transitions", [])]
    for mood in sorted(set(cfg.get("plan", {}).values())):
        need += [(mood, "petla")] + ([(mood, "wejscie"), (mood, "wariant")] if mood in safe else [])
    need += [(mood, "oddech") for mood in sorted(set(cfg.get("breaths", {}).values()))]
    missing, dark, invalid = [], [], []
    for mood, kind in need:
        path = pack.root / pack.path(mood, kind)
        if not path.exists():
            missing.append(f"{mood}/{kind}")
        else:
            try:
                x, sr = sf.read(path, always_2d=True)
                if sr != SR or x.shape[1] != 2 or not len(x) or not np.isfinite(x).all():
                    invalid.append(f"{mood}/{kind} (wymagane niepuste stereo {SR} Hz)")
                    continue
                if kind in ("petla", "wariant"):
                    mono = x.mean(1)
                    spec = np.abs(np.fft.rfft(mono)) ** 2
                    high = 10 * np.log10(spec[np.fft.rfftfreq(len(mono), 1 / sr) >= 500].sum() / (spec.sum() + 1e-12) + 1e-12)
                    if high < -20:
                        dark.append(f"{mood}/{kind} ({high:.0f} dB powyżej 500 Hz)")
            except (OSError, RuntimeError) as exc:
                invalid.append(f"{mood}/{kind} ({exc})")
    print(f"sprawdzono {len(need)} modułów palety {cfg['palette']}")
    print("brakuje (uzupełnij z biblioteki albo skillem yue-music):", ", ".join(missing) or "nic")
    print("nieprawidłowe nagrania:", ", ".join(invalid) or "nic")
    print("mogą zniknąć pod głosem (posłuchaj pod narracją):", ", ".join(dark) or "nic")
    return 2 if missing or invalid else 0


if __name__ == "__main__":
    sys.exit(preflight())
