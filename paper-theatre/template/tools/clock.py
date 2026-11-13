#!/usr/bin/env python3
"""Stopwatch for the production: every activity lands in logs/timings.jsonl and timings.md.

    clock.py run <name> [--note "..."] -- <command ...>   time a command (stdout/stderr pass through)
    clock.py start <name> [--note "..."]                   open a manual activity (e.g. writing scene code)
    clock.py stop <name> [--note "..."]                    close it
    clock.py pause <name> / resume <name>                  pause time excluded from the activity (e.g. TTS stopped while rendering)
    clock.py add <name> <seconds> [--note "..."]           record a measured duration directly
    clock.py report                                        rewrite timings.md
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "timings.jsonl"
REPORT = ROOT / "timings.md"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write(entry):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def entries():
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def fmt(sec):
    sec = int(round(sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def activities():
    """Fold events into activities: name → start, end, paused seconds, notes, exit code."""
    acts, order = {}, []
    for e in entries():
        n = e["name"]
        if e["ev"] == "start":
            acts[n] = {"name": n, "start": e["t"], "t0": e["ts"], "end": None, "paused": 0.0, "notes": [], "code": None}
            order.append(n)
            if e.get("cmd"):
                acts[n]["cmd"] = e["cmd"]
        if e["ev"] == "add":
            acts[n] = {"name": n, "start": e["t"], "end": datetime.fromtimestamp(e["ts"] + e["sec"]).astimezone().isoformat(timespec="seconds"), "dur": e["sec"], "paused": 0.0, "notes": [e["note"]] if e.get("note") else [], "code": None}
            order.append(n)
            continue
        a = acts.get(n)
        if a is None:
            continue
        if e.get("note"):
            a["notes"].append(e["note"])
        if e["ev"] == "pause":
            a["pause_at"] = e["ts"]
        elif e["ev"] == "resume" and a.get("pause_at"):
            a["paused"] += e["ts"] - a.pop("pause_at")
        elif e["ev"] == "stop":
            a["end"] = e["t"]
            a["dur"] = e["ts"] - a["t0"] - a["paused"]
            a["code"] = e.get("code")
    return [acts[n] for n in dict.fromkeys(order)]


def report():
    rows = activities()
    out = ["# Production timings", "", "Written by `tools/clock.py` from `logs/timings.jsonl`. Paused time (e.g. TTS stopped during a render) is left out.", "",
           "| Activity | Start | End | Time | Notes |", "|---|---|---|---|---|"]
    total = 0.0
    for a in rows:
        if a.get("end") is None:
            dur = time.time() - a["t0"] - a["paused"]
            end, d = "running…", fmt(dur) + " (so far)"
        else:
            dur = a["dur"]
            end, d = a["end"][11:19], fmt(dur)
            total += dur
        notes = "; ".join(a["notes"])
        if a.get("paused"):
            notes = (notes + "; " if notes else "") + f"paused {fmt(a['paused'])}"
        if a.get("code") not in (None, 0):
            notes = (notes + "; " if notes else "") + f"exit code {a['code']}"
        out.append(f"| {a['name']} | {a['start'][5:10]} {a['start'][11:19]} | {end} | {d} | {notes} |")
    out += ["", f"Finished activities in total: **{fmt(total)}** (they can overlap, e.g. TTS in the background)."]
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    note = None
    if "--note" in rest:
        i = rest.index("--note")
        note = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    if cmd == "report":
        report()
        return 0
    name = rest[0]
    if cmd == "run":
        command = rest[rest.index("--") + 1:]
        write({"ev": "start", "name": name, "t": now(), "ts": time.time(), "note": note, "cmd": " ".join(command)})
        report()
        code = subprocess.call(command)
        write({"ev": "stop", "name": name, "t": now(), "ts": time.time(), "code": code})
        report()
        return code
    if cmd in ("start", "stop", "pause", "resume"):
        write({"ev": cmd, "name": name, "t": now(), "ts": time.time(), "note": note})
    elif cmd == "add":
        sec = float(rest[1])
        began = datetime.fromtimestamp(time.time() - sec).astimezone().isoformat(timespec="seconds")
        write({"ev": "add", "name": name, "t": began, "ts": time.time() - sec, "sec": sec, "note": note})
    else:
        print(__doc__)
        return 2
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
