#!/usr/bin/env python3
"""Append production timing events for local video pipeline runs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIMINGS_RELATIVE_PATH = Path("manifests") / "production-timings.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def gpu_snapshot() -> dict[str, Any]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"available": False, "reason": "nvidia-smi not found"}
    query = "name,memory.total,memory.used,utilization.gpu"
    try:
        completed = subprocess.run(
            [
                nvidia_smi,
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    if completed.returncode != 0:
        return {"available": False, "reason": completed.stderr.strip() or "nvidia-smi failed"}
    devices = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        name, total_mib, used_mib, utilization = parts
        devices.append(
            {
                "name": name,
                "memory_total_mib": _int_or_none(total_mib),
                "memory_used_mib": _int_or_none(used_mib),
                "utilization_gpu_percent": _int_or_none(utilization),
            }
        )
    return {"available": True, "devices": devices}


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def command_for_log(command: list[str] | tuple[str, ...] | None) -> list[str] | None:
    if command is None:
        return None
    return [str(part) for part in command]


def infer_stage(command: list[str] | tuple[str, ...] | None, fallback: str = "production_command") -> str:
    if not command:
        return fallback
    executable = Path(str(command[0])).name.lower()
    joined = " ".join(str(part).lower() for part in command)
    if "latentsync" in joined:
        return "latentsync"
    if "voxcpm" in joined or "moss" in joined or "omnivoice" in joined or "tts" in joined:
        return "tts"
    if "z_image" in joined or "z-image" in joined or "generate.py" in joined:
        return "generated_image"
    if "record_broll" in joined or "playwright" in joined:
        return "webpage_record"
    if "render_board" in joined:
        return "synthetic_motion_render"
    if "compose_video" in joined:
        return "base_render"
    if "generate_reel_captions" in joined:
        return "captions"
    if executable in {"ffmpeg.exe", "ffmpeg"}:
        return "ffmpeg"
    return fallback


def start_stage(
    project_dir: Path | str,
    stage: str,
    *,
    command: list[str] | tuple[str, ...] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "run_id": uuid.uuid4().hex,
        "event": "stage_start",
        "stage": stage,
        "timestamp_utc": utc_now(),
        "perf_counter": time.perf_counter(),
        "pid": os.getpid(),
        "command": command_for_log(command),
        "metadata": metadata or {},
        "gpu": gpu_snapshot(),
    }
    append_event(project_dir, _public_record(record))
    return record


def end_stage(
    project_dir: Path | str,
    record: dict[str, Any],
    *,
    status: str,
    return_code: int | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    duration = time.perf_counter() - float(record.get("perf_counter", time.perf_counter()))
    event = {
        "run_id": record.get("run_id"),
        "event": "stage_end",
        "stage": record.get("stage"),
        "timestamp_utc": utc_now(),
        "duration_seconds": round(duration, 3),
        "pid": os.getpid(),
        "status": status,
        "return_code": return_code,
        "error": error,
        "command": record.get("command"),
        "metadata": metadata or {},
        "gpu": gpu_snapshot(),
    }
    append_event(project_dir, event)


def append_event(project_dir: Path | str, event: dict[str, Any]) -> None:
    path = Path(project_dir).resolve() / TIMINGS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "perf_counter"}
