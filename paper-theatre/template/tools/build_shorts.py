#!/usr/bin/env python3
"""Build vertical shorts from the selected narration of the approved full film.

    python tools/build_shorts.py [--only NAME] [--skip-asr] [--qa-only]

film.json -> "shorts" names each short: {"title": "...", "parts": [[line id, first word or null, last word or null], ...],
"mood": music mood (optional; default: the mood of the first part's chapter), "close": {"text": "...", "take":
"audio/shorts/<name>_close.wav"} (optional: a closing line of the short's own, e.g. pointing to the full film)}.
A part can start later in its line or end at a word, at a sentence boundary. The parts come from film/audio/vo.wav
(the arranged, levelled master); a closing line is narrated by the tts skill like any take (its provenance in
audio/shorts/provenance.json) and trimmed and levelled here as the film's takes are. Nothing is generated here. For each short this writes film/short_<name>/ (timeline, voice, mix, stems,
provenance, recogniser check) and out/short_<name>.<language>.srt; the picture is film/shorts/shorts.js, rendered
with  node tools/render.mjs --page "short.html?name=<name>" --audio film/short_<name>/mix.wav --out out/short_<name>_v1.mp4
"""
import argparse
import copy
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_audio as audio
import music as score

SR = 48000
LEAD, GAP, OUTRO = 0.12, 0.20, 3.8   # silence before the first line, between parts, ending card after the last
CFG = json.loads((ROOT / "film.json").read_text(encoding="utf-8"))
SHORTS = CFG.get("shorts", {})


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def latest_film():
    versions = sorted(ROOT.glob(f"out/{CFG['slug']}_v*.mp4"), key=lambda p: int(re.sub(r"\D", "", p.stem.rsplit("_v", 1)[-1]) or 0))
    return versions[-1] if versions else None


def source_inputs():
    timeline_path, manifest_path, provenance_path = ROOT / "film/timeline.json", ROOT / "audio/manifest.json", ROOT / "audio/provenance.json"
    full = json.loads(timeline_path.read_text(encoding="utf-8"))
    manifests = {item["id"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8"))["takes"]}
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))["takes"]
    narration = {item["id"]: item for item in json.loads((ROOT / "audio/narration.json").read_text(encoding="utf-8"))}
    voice_path = ROOT / "film/audio/vo.wav"
    voice, sr = sf.read(voice_path, dtype="float32")
    assert sr == SR and voice.ndim == 1 and np.isfinite(voice).all()
    evidence = {}
    for sid in {part[0] for edit in SHORTS.values() for part in edit["parts"]}:
        selected = manifests[sid]
        digest = sha(ROOT / selected["take"])
        assert digest == selected["sha256"], f"Selected recording differs from manifest: {sid}"
        assert sid in provenance and digest == provenance[sid]["sha256"], f"Provenance hash differs: {sid}"
        assert selected["text"] == provenance[sid]["text"] == narration[sid]["say"], sid
        evidence[sid] = {"selected_take": selected["take"], "selected_take_sha256": digest,
                         "selected_take_provenance": provenance[sid],
                         "source_raw_trim_seconds": selected["trim_seconds"],
                         "source_processed_duration": selected["duration_trimmed"]}
    film = latest_film()
    source = {"film": str(film.relative_to(ROOT)) if film else None, "film_sha256": sha(film) if film else None,
              "timeline": "film/timeline.json", "timeline_sha256": sha(timeline_path),
              "voice_master": "film/audio/vo.wav", "voice_master_sha256": sha(voice_path),
              "manifest_sha256": sha(manifest_path), "provenance_sha256": sha(provenance_path),
              "processing": "Reuse the arranged, levelled voice master, including its approved pause edits; no tempo or pitch change."}
    return {item["id"]: item for item in full["lines"]}, voice, evidence, source


def edit_voice(name, source_lines, source_voice, evidence, source):
    edit = SHORTS[name]
    lines, clips, used = [], [], []
    position = round(LEAD * SR)
    clean = lambda w: w.lower().lstrip('„"(«')
    for sid, first_word, last_word in edit["parts"]:
        original = source_lines[sid]
        words = copy.deepcopy(original["words"])
        start, stop = original["start"], original["end"]
        if last_word:
            last = next(i for i, word in enumerate(words) if clean(word["w"]).startswith(last_word.lower()))
            words = words[:last + 1]
            stop = min(original["end"], words[-1]["e"] + 0.14)
        if first_word:
            first = next(i for i, word in enumerate(words) if clean(word["w"]).startswith(first_word.lower()))
            words = words[first:]
            start = max(original["start"], words[0]["s"] - 0.08)
        a, b = round(start * SR), round(stop * SR)
        clip = source_voice[a:b].copy()
        fade = min(round(0.006 * SR), len(clip) // 2)
        clip[:fade] *= np.linspace(0, 1, fade)
        clip[-fade:] *= np.linspace(1, 0, fade)
        offset = position / SR - a / SR
        corrections = []
        # a word aligned over a silent onset moves to the first audible 5 ms frame, only within its own interval
        frame = round(0.005 * SR)
        rms = np.sqrt(np.mean(clip[:len(clip) // frame * frame].reshape(-1, frame) ** 2, axis=1))
        gate = max(0.002, float(np.max(rms)) * 0.035)
        for word in words:
            local_start = max(0.0, word["s"] - a / SR)
            local_end = max(local_start, min(len(clip) / SR, word["e"] - a / SR))
            lo, hi = max(0, int(local_start / 0.005)), min(len(rms), int(np.ceil(local_end / 0.005)))
            hot = np.flatnonzero(rms[lo:hi] > gate)
            if len(hot) and (lo + hot[0]) * 0.005 - local_start > 0.16:
                corrected = max(local_start, (lo + hot[0]) * 0.005 - 0.02)
                corrections.append({"word": word["w"], "source_start": word["s"], "corrected_source_start": round(a / SR + corrected, 4)})
                word["s"] = a / SR + corrected
            word["s"] = round(max(position / SR, word["s"] + offset), 4)
            word["e"] = round(min((position + len(clip)) / SR, word["e"] + offset), 4)
            assert word["e"] >= word["s"], word
        end = (position + len(clip)) / SR
        lines.append({"id": sid, "scene": 1, "source_scene": original["scene"], "text": " ".join(w["w"] for w in words),
                      "start": round(position / SR, 4), "end": round(end, 4), "words": words})
        clips.append((position, clip))
        used.append({"id": sid, **copy.deepcopy(evidence[sid]), "voice_master_interval_seconds": [a / SR, b / SR],
                     "short_interval_seconds": [position / SR, end], "boundary_fades_seconds": 0.006, "word_onset_corrections": corrections})
        position += len(clip) + round(GAP * SR)
    if edit.get("close"):
        line, clip, record = close_line(name, edit["close"], position)
        lines.append(line)
        clips.append((position, clip))
        used.append(record)
        position += len(clip) + round(GAP * SR)
    length = position - round(GAP * SR) + round(OUTRO * SR)
    voice = np.zeros(length, dtype="float32")
    for position, clip in clips:
        voice[position:position + len(clip)] += clip
    timeline = {"fps": 30, "duration": round(length / SR, 6), "short": name, "music_breaks": [],
                "outro_start": round(lines[-1]["end"] + 0.2, 4), "lines": lines}
    proof = {"title": edit["title"], "source": source, "takes": used,
             "output": {"duration": length / SR, "sample_rate": SR, "lead_seconds": LEAD, "interline_gap_seconds": GAP, "outro_seconds": OUTRO}}
    return timeline, voice, proof


def close_line(name, close, position):
    """The short's own closing line: trimmed, pauses tidied and levelled like the film's takes; words from the recogniser."""
    import asr
    path = ROOT / close["take"]
    provenance_path = ROOT / "audio/shorts/provenance.json"
    records = json.loads(provenance_path.read_text(encoding="utf-8"))["takes"] if provenance_path.exists() else {}
    digest = sha(path)
    record = next((r for r in records.values() if r.get("sha256") == digest), None)
    assert record and record.get("text") == close["text"], f"{close['take']}: no provenance with this file's hash and text"
    raw = audio.load_take(path)
    bounds = audio.trim_bounds(raw)
    x = audio.trim(raw)
    x, seg = audio.tidy_pauses(x, audio.CFG.get("pause_cap", 0.62), audio.CFG.get("pause_keep", 0.5), with_map=True)
    x, gain = audio.level(x, audio.VOICE_RMS)
    (heard,), _ = asr.transcribe([path], verbose=False)
    off, dur = bounds[0] / SR, len(x) / SR
    words_heard = [audio.Heard(w["w"], min(audio.map_time(max(w["s"] - off, 0.0), seg), dur), min(audio.map_time(max(w["e"] - off, 0.0), seg), dur))
                   for w in heard["words"]]
    times, literal, ratio = audio.word_times(words_heard, close["text"], dur)
    assert len(times) == len(close["text"].split()), f"{name}_close: word times do not match the words of the closing line"
    words = [{"w": w, "s": round(position / SR + s, 4), "e": round(position / SR + e, 4)} for w, s, e in times]
    line = {"id": f"{name}_close", "scene": 1, "source_scene": None, "text": close["text"],
            "start": round(position / SR, 4), "end": round(position / SR + dur, 4), "words": words, "close": True}
    proof = {"id": line["id"], "selected_take": close["take"], "selected_take_sha256": digest, "selected_take_provenance": record,
             "gain_db": round(float(audio.db(gain)), 2), "asr": literal, "asr_match": round(ratio, 3),
             "short_interval_seconds": [line["start"], line["end"]]}
    return line, x.astype("float32"), proof


def make_music(name, tl, vo, source_lines):
    cfg = copy.deepcopy(CFG["music"])
    first = source_lines[SHORTS[name]["parts"][0][0]]
    mood = SHORTS[name].get("mood") or cfg["plan"][str(first["scene"])]
    pack = score.Pack(cfg, cfg["palette"])
    n = len(vo)
    bed = np.zeros((n, 2), dtype="float32")
    foreground = np.zeros_like(bed)
    # one mood under the whole short, in whole phrases, ending at a phrase end just before the closing cadence
    x, form = score.arrange(pack, mood, tl["outro_start"], mood in set(cfg.get("variants_safe", [])), 0.5,
                            every=cfg.get("variant_every", {}).get(mood, 3))
    score.add(bed, score.fades(x, fade_in=0.12), 0.0)
    bed = score.level_bed(bed, vo, tl, 21.0, 0.0).astype("float32")
    # the closing card gets the motif's complete ending cadence, only after the narrator
    start = tl["outro_start"]
    room = n - round(start * SR)
    ending = pack.read("motyw", "ekran")
    ending = ending[-room:] if len(ending) >= room else np.pad(ending, ((room - len(ending), 0), (0, 0)))
    score.add(foreground, score.fades(score.level_cue(ending, target_db=-26.0), fade_in=0.09, fade_out=0.45), start)
    mask = np.pad(score.active_mask(vo), (0, n - len(score.active_mask(vo))))
    proof = {"palette": cfg["palette"], "package": str(pack.root), "sources_sha256": pack.used, "mood": mood, "form": form["form"],
             "foreground": [{"start": start, "module": "motyw/ekran (ending cadence)"}],
             "voice_over_bed_db": float(20 * np.log10(score.rms(vo[mask]) / score.rms(bed[mask])))}
    return bed, foreground, proof


def make_effects(name, voice):
    code = ("import fs from 'node:fs'; import {soundCues} from './film/shorts/shorts.js'; "
            f"console.log(JSON.stringify(soundCues ? soundCues(JSON.parse(fs.readFileSync('film/short_{name}/timeline.json','utf8'))) : []))")
    events = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", code], cwd=ROOT, text=True))
    out = np.zeros((len(voice), 2), dtype="float32")
    if not events:
        return out, events
    sounds = audio.make_sfx()
    for event in events:
        score.add(out, np.repeat(sounds[event["name"]][:, None], 2, axis=1) * float(event.get("gain", 1)), event["t"])
    active = np.pad(score.active_mask(voice), (0, len(voice) - len(score.active_mask(voice))))
    if np.any(active) and score.rms(out[active]) > 1e-9:
        out *= min(0.22, score.rms(voice[active]) / (10 ** (24 / 20) * score.rms(out[active])))
    out *= (1 - 0.45 * score.duck_envelope(voice, len(voice)))[:, None]
    return out, events


def finalize_mix(out, vo, bed, foreground, effects):
    raw = np.repeat(vo[:, None], 2, axis=1) + bed + foreground + effects
    mixed = audio.true_peak_limit(raw * 10 ** ((-14 - score.lufs(raw)) / 20), ceiling_db=-3.0)
    for _ in range(2):
        delta = -14 - score.lufs(mixed)
        if abs(delta) < 0.05:
            break
        mixed = audio.true_peak_limit(mixed * 10 ** (delta / 20), ceiling_db=-3.0)
    assert np.isfinite(mixed).all()
    sf.write(out / "mix_next.wav", mixed, SR, subtype="PCM_24")
    (out / "mix_next.wav").replace(out / "mix.wav")
    for stem, x in (("music_bed", bed), ("music_foreground", foreground), ("effects", effects)):
        sf.write(out / f"{stem}.wav", x, SR, subtype="PCM_24")
    return {"integrated_lufs_estimate": score.lufs(mixed), "sample_peak_dbfs": audio.db(np.abs(mixed).max()),
            "true_peak_limiter_ceiling_db": -3.0, "clipped_samples": int(np.sum(np.abs(mixed) >= 1)), "mix_sha256": sha(out / "mix.wav")}


def asr_check(out, tl, voice):
    """Recognise each line of the short with the film's recogniser and keep the literal hypothesis."""
    import asr
    folder = out / "lines"
    folder.mkdir(exist_ok=True)
    paths = []
    for line in tl["lines"]:
        f = folder / f"{line['id']}.wav"
        sf.write(f, voice[round(line["start"] * SR):round(line["end"] * SR)], SR, subtype="PCM_24")
        paths.append(f)
    results, _ = asr.transcribe(paths, verbose=False)
    norm = lambda text: re.sub(r"[^\w]+", " ", text.lower()).strip()
    records = []
    for line, r in zip(tl["lines"], results):
        sim = difflib.SequenceMatcher(None, norm(line["text"]), norm(r["text"])).ratio()
        records.append({"id": line["id"], "expected_caption_text": line["text"], "free_asr": r["text"],
                        "character_similarity": round(sim, 3), "short_interval_seconds": [line["start"], line["end"]]})
        print(f"ASR {line['id']} {sim:.2f}: {r['text']}", flush=True)
    write_json(out / "asr.json", {"model": asr.MODEL, "voice_sha256": sha(out / "vo.wav"), "takes": records,
                                  "note": "Literal hypotheses of the film recogniser; the source recordings were checked with the film."})


def write_srt(path, tl):
    def stamp(t):
        ms = round(max(0, t) * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    blocks = []
    for line in tl["lines"]:
        chunk = []
        for i, w in enumerate(line["words"]):
            chunk.append(w)
            nxt = line["words"][i + 1] if i + 1 < len(line["words"]) else None
            phrase = " ".join(x["w"] for x in chunk)
            if nxt is None or len(chunk) >= 6 or len(phrase) + len(nxt["w"]) + 1 > 42 or re.search(r"[.!?;:]$", w["w"]):
                start = chunk[0]["s"]
                end = min(line["end"] + 0.04, max(w["e"], start + 0.25))
                if nxt:
                    end = min(end, nxt["s"])
                blocks.append(f"{len(blocks) + 1}\n{stamp(start)} --> {stamp(end)}\n{phrase}")
                chunk = []
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=list(SHORTS) or None)
    parser.add_argument("--skip-asr", action="store_true")
    parser.add_argument("--qa-only", action="store_true", help="check the existing short voice without rebuilding audio")
    args = parser.parse_args()
    if not SHORTS:
        sys.exit('film.json has no "shorts": name each short with its title and parts first')
    source_lines, source_voice, evidence, source = source_inputs()
    for name in ([args.only] if args.only else SHORTS):
        out = ROOT / f"film/short_{name}"
        if args.qa_only:
            vo, sr = sf.read(out / "vo.wav", dtype="float32")
            asr_check(out, json.loads((out / "timeline.json").read_text(encoding="utf-8")), vo)
            continue
        out.mkdir(parents=True, exist_ok=True)
        tl, vo, proof = edit_voice(name, source_lines, source_voice, evidence, source)
        write_json(out / "timeline.json", tl)
        write_srt(ROOT / f"out/short_{name}.{CFG['language']}.srt", tl)
        sf.write(out / "vo.wav", vo, SR, subtype="PCM_24")
        bed, foreground, music_proof = make_music(name, tl, vo, source_lines)
        effects, cues = make_effects(name, vo)
        metrics = finalize_mix(out, vo, bed, foreground, effects)
        proof["output"].update(metrics, voice_sha256=sha(out / "vo.wav"), timeline_sha256=sha(out / "timeline.json"))
        write_json(out / "provenance.json", proof)
        write_json(out / "music_manifest.json", music_proof)
        write_json(out / "sound_cues.json", cues)
        print(f"{name}: {tl['duration']:.3f}s, {metrics['integrated_lufs_estimate']:.2f} LUFS, peak {metrics['sample_peak_dbfs']:.2f} dBFS, "
              f"voice/bed {music_proof['voice_over_bed_db']:.1f} dB, music {'+'.join(music_proof['form'])}", flush=True)
        print(f'   picture: node tools/render.mjs --page "short.html?name={name}" --audio film/short_{name}/mix.wav --out out/short_{name}_v1.mp4')
        if not args.skip_asr:
            asr_check(out, tl, vo)


if __name__ == "__main__":
    main()
