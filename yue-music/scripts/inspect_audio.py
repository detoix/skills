#!/usr/bin/env python3
"""Inspect an audio file without making claims about its musical quality.

Uses ffprobe for metadata and streams decoded float32 PCM from ffmpeg.
An optional latent file is interpreted as little-endian raw float32.
"""

from __future__ import annotations

import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import BinaryIO, Iterator


NEAR_FULL_SCALE = 0.99999
SILENCE_RMS_DBFS = -60.0


def _float_chunks(stream: BinaryIO) -> Iterator[array]:
    pending = b""
    while True:
        block = stream.read(65536)
        if not block:
            break
        block = pending + block
        usable = len(block) - len(block) % 4
        pending = block[usable:]
        values = array("f")
        values.frombytes(block[:usable])
        if sys.byteorder != "little":
            values.byteswap()
        yield values
    if pending:
        raise ValueError("Raw float32 data has an incomplete final value")


def _dbfs(value: float) -> float | None:
    return 20.0 * math.log10(value) if value > 0.0 else None


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def inspect_audio(path: str | Path, latents: str | Path | None = None) -> dict:
    """Return technical measurements; stream decoding to keep memory bounded.

    ``technical_pass`` checks successful complete decoding, finite PCM,
    nonempty duration, metadata consistency, and a signal above -60 dBFS RMS.
    When supplied, latents must also be nonempty, aligned and finite.
    Full-scale counts are measurements, not automatic clipping failures.
    Musical quality, vocal presence and suitability require listening.
    """
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bits_per_sample,duration:format=duration,size",
            "-of", "json", str(source),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=30,
    )
    if probe.returncode:
        raise RuntimeError(f"ffprobe failed: {probe.stderr.strip()}")
    metadata = json.loads(probe.stdout)
    streams = metadata.get("streams", [])
    if not streams:
        raise ValueError("The file has no audio stream")
    stream = streams[0]
    sample_rate = int(stream.get("sample_rate", 0))
    channels = int(stream.get("channels", 0))
    if sample_rate <= 0 or channels <= 0:
        raise ValueError("Invalid audio sample rate or channel count")
    container = metadata.get("format", {})
    reported_duration = (
        _positive_float(stream.get("duration"))
        or _positive_float(container.get("duration"))
    )

    sample_count = finite_count = nonfinite_count = near_full_count = 0
    square_sum = peak = 0.0
    longest_peak_run = peak_run = 0
    frame_peak = 0.0
    with tempfile.TemporaryFile() as error_log:
        decoder = subprocess.Popen(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-threads", "1",
                "-i", str(source), "-map", "0:a:0", "-vn",
                "-f", "f32le", "-acodec", "pcm_f32le", "-",
            ],
            stdout=subprocess.PIPE, stderr=error_log,
        )
        try:
            assert decoder.stdout is not None
            for values in _float_chunks(decoder.stdout):
                for value in values:
                    sample_count += 1
                    if math.isfinite(value):
                        finite_count += 1
                        magnitude = abs(value)
                        square_sum += value * value
                        peak = max(peak, magnitude)
                        frame_peak = max(frame_peak, magnitude)
                        near_full_count += magnitude >= NEAR_FULL_SCALE
                    else:
                        nonfinite_count += 1
                    if sample_count % channels == 0:
                        peak_run = peak_run + 1 if frame_peak >= NEAR_FULL_SCALE else 0
                        longest_peak_run = max(longest_peak_run, peak_run)
                        frame_peak = 0.0
            decoder.stdout.close()
            decode_returncode = decoder.wait()
        except BaseException:
            decoder.kill()
            decoder.wait()
            raise
        error_log.seek(0)
        decode_error = error_log.read().decode("utf-8", errors="replace").strip()

    frames = sample_count // channels
    decoded_duration = frames / sample_rate
    rms = math.sqrt(square_sum / finite_count) if finite_count else 0.0
    rms_dbfs = _dbfs(rms)
    duration_matches = (
        reported_duration is None
        or abs(decoded_duration - reported_duration) <= max(0.1, reported_duration * 0.01)
    )
    checks = {
        "decode_succeeded": decode_returncode == 0 and not decode_error,
        "nonempty_audio": frames > 0,
        "complete_channel_frames": sample_count % channels == 0,
        "finite_pcm": nonfinite_count == 0 and finite_count > 0,
        "duration_consistent_with_metadata": duration_matches,
        "signal_above_silence_threshold": rms_dbfs is not None and rms_dbfs > SILENCE_RMS_DBFS,
    }
    report = {
        "path": str(source),
        "codec_name": stream.get("codec_name"),
        "sample_rate": sample_rate,
        "channels": channels,
        "bits_per_sample": int(stream.get("bits_per_sample", 0)),
        "file_size_bytes": source.stat().st_size,
        "reported_duration_seconds": reported_duration,
        "duration_seconds": decoded_duration,
        "decoded_frames": frames,
        "decoded_samples": sample_count,
        "finite_pcm": checks["finite_pcm"],
        "non_finite_pcm_samples": nonfinite_count,
        "rms_dbfs": rms_dbfs,
        "peak_dbfs": _dbfs(peak),
        "near_full_scale_threshold": NEAR_FULL_SCALE,
        "near_full_scale_samples": near_full_count,
        "longest_near_full_scale_run_frames": longest_peak_run,
        "longest_near_full_scale_run_seconds": longest_peak_run / sample_rate,
        "silence_rms_threshold_dbfs": SILENCE_RMS_DBFS,
        "decode_error": decode_error or None,
        "checks": checks,
        "listening_review": "not_performed",
    }

    if latents is not None:
        latent_path = Path(latents).expanduser().resolve()
        latent_count = latent_nonfinite = 0
        latent_aligned = True
        with latent_path.open("rb") as data:
            try:
                for values in _float_chunks(data):
                    latent_count += len(values)
                    latent_nonfinite += sum(not math.isfinite(value) for value in values)
            except ValueError:
                latent_aligned = False
        checks["latent_file_aligned"] = latent_aligned
        checks["nonempty_latents"] = latent_count > 0
        checks["finite_latents"] = latent_nonfinite == 0 and latent_count > 0
        report["latents"] = {
            "path": str(latent_path),
            "float_values": latent_count,
            "non_finite_values": latent_nonfinite,
            "float32_aligned": latent_aligned,
            "finite": checks["finite_latents"],
        }

    report["technical_pass"] = all(checks.values())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="Audio file to inspect")
    parser.add_argument("--latents", type=Path, help="Optional raw little-endian float32 latent file")
    parser.add_argument("--output", type=Path, help="Also write the JSON report to this file")
    args = parser.parse_args()
    try:
        report = inspect_audio(args.audio, args.latents)
        rendered = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        return 0 if report["technical_pass"] else 1
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Audio inspection failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
