#!/usr/bin/env python3
"""Pronunciation QA for generated TTS chunks before LatentSync."""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

YOUTUBE_AUTOPIPELINE_SCRIPTS = Path(__file__).resolve().parents[2] / "youtube-autopipeline" / "scripts"
if str(YOUTUBE_AUTOPIPELINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(YOUTUBE_AUTOPIPELINE_SCRIPTS))

from production_metrics import end_stage, start_stage


DEFAULT_MIN_WORD_RECALL = 0.85
DEFAULT_MIN_SEQUENCE_RATIO = 0.78


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("P") or char in string.punctuation:
            chars.append(" ")
        else:
            chars.append(char)
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


def resolve_audio_path(tts_dir: Path, chunk: dict[str, Any], index: int, sorted_wavs: list[Path]) -> Path | None:
    candidates: list[Path] = []
    chunk_id = str(chunk.get("chunk_id") or "").strip()
    if chunk_id:
        candidates.extend(
            [
                tts_dir / f"{chunk_id}.wav",
                tts_dir / f"{chunk_id.lower()}.wav",
                tts_dir / f"{chunk_id.upper()}.wav",
            ]
        )
    candidates.append(tts_dir / f"T{index + 1:02d}.wav")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if index < len(sorted_wavs):
        return sorted_wavs[index]
    return None


def import_asr_backend() -> tuple[str, Any]:
    try:
        import whisperx  # type: ignore

        return "whisperx", whisperx
    except Exception:
        pass
    try:
        import whisper  # type: ignore

        return "whisper", whisper
    except Exception as exc:
        raise RuntimeError("No ASR backend available. Install/import WhisperX or whisper before LatentSync QA.") from exc


def make_whisperx_transcriber(whisperx: Any, language: str, model_name: str, device: str, compute_type: str) -> Any:
    try:
        model = whisperx.load_model(model_name, device=device, compute_type=compute_type, language=language)
    except TypeError:
        model = whisperx.load_model(model_name, device=device, compute_type=compute_type)

    def transcribe(audio_path: Path) -> str:
        audio = whisperx.load_audio(str(audio_path))
        try:
            result = model.transcribe(audio, batch_size=8, language=language)
        except TypeError:
            result = model.transcribe(audio, batch_size=8)
        return " ".join(str(segment.get("text", "")).strip() for segment in result.get("segments", [])).strip()

    return transcribe


def make_whisper_transcriber(whisper: Any, language: str, model_name: str) -> Any:
    model = whisper.load_model(model_name)

    def transcribe(audio_path: Path) -> str:
        try:
            result = model.transcribe(str(audio_path), language=language)
        except TypeError:
            result = model.transcribe(str(audio_path))
        return str(result.get("text", "")).strip()

    return transcribe


def compare_text(expected: str, actual: str) -> dict[str, Any]:
    expected_tokens = tokenize(expected)
    actual_tokens = tokenize(actual)
    expected_counter = Counter(expected_tokens)
    actual_counter = Counter(actual_tokens)
    missing_counter = expected_counter - actual_counter
    extra_counter = actual_counter - expected_counter
    missing = list(missing_counter.elements())
    extra = list(extra_counter.elements())
    recall = 1.0
    if expected_tokens:
        recall = 1.0 - (sum(missing_counter.values()) / len(expected_tokens))
    ratio = SequenceMatcher(None, expected_tokens, actual_tokens).ratio() if expected_tokens or actual_tokens else 1.0
    passed = recall >= DEFAULT_MIN_WORD_RECALL and ratio >= DEFAULT_MIN_SEQUENCE_RATIO
    return {
        "expected_normalized": " ".join(expected_tokens),
        "actual_normalized": " ".join(actual_tokens),
        "expected_word_count": len(expected_tokens),
        "actual_word_count": len(actual_tokens),
        "word_recall": round(recall, 4),
        "sequence_ratio": round(ratio, 4),
        "missing_words": missing,
        "extra_words": extra,
        "passed": passed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ASR pronunciation QA on clean TTS chunks before LatentSync.")
    parser.add_argument("--project-dir", default=".", help="Project directory.")
    parser.add_argument("--script", help="Path to script.json. Defaults to <project-dir>/script.json.")
    parser.add_argument("--tts-dir", help="Directory with clean TTS chunks. Defaults to <project-dir>/tts/clean.")
    parser.add_argument("--language", help="ASR language code. Defaults to script metadata.language.")
    parser.add_argument("--output", help="Output report path. Defaults to <project-dir>/manifests/tts-pronunciation-qa.json.")
    parser.add_argument("--model", default="small", help="ASR model name for WhisperX/whisper.")
    parser.add_argument("--device", default="cpu", help="WhisperX device.")
    parser.add_argument("--compute-type", default="int8", help="WhisperX compute type.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    qa_record = start_stage(
        project_dir,
        "tts_pronunciation_qa",
        command=["tts_pronunciation_qa.py"],
        metadata={"model": args.model, "device": args.device, "compute_type": args.compute_type},
    )
    script_path = Path(args.script).resolve() if args.script else project_dir / "script.json"
    tts_dir = Path(args.tts_dir).resolve() if args.tts_dir else project_dir / "tts" / "clean"
    output_path = Path(args.output).resolve() if args.output else project_dir / "manifests" / "tts-pronunciation-qa.json"

    report: dict[str, Any] = {
        "script": str(script_path),
        "tts_dir": str(tts_dir),
        "output": str(output_path),
        "status": "fail",
        "chunks": [],
        "errors": [],
    }

    try:
        script = load_json(script_path)
        chunks = script.get("tts_chunks") if isinstance(script, dict) else None
        if not isinstance(chunks, list) or not chunks:
            raise ValueError("script.json must contain a non-empty tts_chunks array")
        language = args.language or str(script.get("metadata", {}).get("language") or "").strip()
        if not language:
            raise ValueError("language is required via --language or metadata.language")

        sorted_wavs = sorted(tts_dir.glob("*.wav"))
        backend_name, backend = import_asr_backend()
        if backend_name == "whisperx":
            transcribe = make_whisperx_transcriber(backend, language, args.model, args.device, args.compute_type)
        else:
            transcribe = make_whisper_transcriber(backend, language, args.model)
        report["language"] = language
        report["backend"] = backend_name
        report["thresholds"] = {
            "min_word_recall": DEFAULT_MIN_WORD_RECALL,
            "min_sequence_ratio": DEFAULT_MIN_SEQUENCE_RATIO,
        }

        any_failed = False
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                report["errors"].append(f"tts_chunks[{index}] must be an object")
                any_failed = True
                continue
            chunk_id = str(chunk.get("chunk_id") or f"T{index + 1:02d}")
            expected = str(chunk.get("voice_text") or "").strip()
            audio_path = resolve_audio_path(tts_dir, chunk, index, sorted_wavs)
            if not expected:
                report["errors"].append(f"{chunk_id}: missing voice_text")
                any_failed = True
                continue
            if audio_path is None:
                report["errors"].append(f"{chunk_id}: missing clean TTS wav")
                any_failed = True
                continue

            actual = transcribe(audio_path)

            comparison = compare_text(expected, actual)
            if not comparison["passed"]:
                any_failed = True
            report["chunks"].append(
                {
                    "chunk_id": chunk_id,
                    "audio": str(audio_path),
                    "expected": expected,
                    "asr_transcript": actual,
                    **comparison,
                }
            )

        report["status"] = "fail" if any_failed or report["errors"] else "pass"
        write_json(output_path, report)
        if report["status"] != "pass":
            print(f"TTS pronunciation QA failed: {output_path}", file=sys.stderr)
            end_stage(project_dir, qa_record, status="fail", return_code=1, metadata={"chunks": len(report["chunks"]), "errors": len(report["errors"])})
            return 1
        print(f"TTS pronunciation QA passed: {output_path}")
        end_stage(project_dir, qa_record, status="pass", return_code=0, metadata={"chunks": len(report["chunks"])})
        return 0
    except Exception as exc:
        report["errors"].append(str(exc))
        write_json(output_path, report)
        print(f"TTS pronunciation QA failed: {exc}", file=sys.stderr)
        end_stage(project_dir, qa_record, status="error", return_code=1, error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
