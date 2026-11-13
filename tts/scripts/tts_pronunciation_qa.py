#!/usr/bin/env python3
"""Pronunciation QA for generated TTS chunks."""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


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


def resolve_audio_path(tts_dir: Path, chunk: dict[str, Any], index: int) -> Path | None:
    candidates: list[Path] = []
    chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
    if chunk_id:
        candidates.extend(
            [
                tts_dir / f"{chunk_id}.wav",
                tts_dir / f"{chunk_id.lower()}.wav",
                tts_dir / f"{chunk_id.upper()}.wav",
            ]
        )
    candidates.append(tts_dir / f"T{index + 1:02d}.wav")
    candidates.append(tts_dir / f"output_{index + 1:03d}.wav")
    for candidate in candidates:
        if candidate.exists():
            return candidate
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
        raise RuntimeError("No ASR backend available. Install/import WhisperX or whisper before running pronunciation QA.") from exc


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


def pronunciation_key(word: str, language: str) -> str:
    """Conservative Polish spelling equivalences, not a full phoneme converter.

    Keep c/k, s/sz, n/ń and other articulation differences distinct. Nasal
    vowels split only before stops/affricates; final ą stays nasal.
    """
    word = unicodedata.normalize("NFC", word).casefold()
    if language != "pl":
        return word
    word = word.replace("ó", "u").replace("ch", "h")
    word = re.sub(r"([ąę])(?=ć|dź|ci|dzi)", lambda m: "oń" if m[1] == "ą" else "eń", word)
    word = re.sub(r"([ąę])(?=[pb])", lambda m: "om" if m[1] == "ą" else "em", word)
    word = re.sub(r"([ąę])(?=[tdkgc])", lambda m: "on" if m[1] == "ą" else "en", word)
    word = re.sub(r"([ąę])(?=[lł])", lambda m: "o" if m[1] == "ą" else "e", word)
    word = re.sub(r"ę$", "e", word)
    word = re.sub(r"n(?=ć|dź|ci|dzi)", "ń", word)
    # Single symbols keep affricates intact when devoicing a final cluster.
    for spelling, symbol in (("dż", "J"), ("dź", "Q"), ("dz", "D"), ("cz", "C"), ("sz", "S")):
        word = word.replace(spelling, symbol)
    devoicing = str.maketrans({"b": "p", "d": "t", "g": "k", "w": "f", "z": "s", "ż": "S", "ź": "ś", "J": "C", "Q": "ć", "D": "c"})
    return re.sub(r"[bdgwzżźJQDptkfsścćCSh]+$", lambda m: m[0].translate(devoicing), word)


def compare_text(expected: str, actual: str, language: str = "pl") -> dict[str, Any]:
    """Report every unresolved word edit, even in an otherwise identical line.

    A mismatch is a request to review the audio, not proof of bad speech.
    Forced-alignment probabilities and sentence similarity cannot waive it.
    """
    expected_tokens = tokenize(expected)
    actual_tokens = tokenize(actual)
    expected_keys = [pronunciation_key(w, language) for w in expected_tokens]
    actual_keys = [pronunciation_key(w, language) for w in actual_tokens]
    alignment = []
    differences = []
    matcher = SequenceMatcher(None, expected_keys, actual_keys, autojunk=False)
    for tag, i, end_i, j, end_j in matcher.get_opcodes():
        if tag == "equal":
            for a, b in zip(range(i, end_i), range(j, end_j)):
                alignment.append({"kind": "exact" if expected_tokens[a] == actual_tokens[b] else "phonetic",
                                  "expected_index": a + 1, "actual_index": b + 1,
                                  "expected": expected_tokens[a], "actual": actual_tokens[b]})
        elif (tag == "replace" and "".join(expected_keys[i:end_i]) == "".join(actual_keys[j:end_j])):
            alignment.append({"kind": "word_boundary", "expected_index": i + 1, "actual_index": j + 1,
                              "expected": " ".join(expected_tokens[i:end_i]), "actual": " ".join(actual_tokens[j:end_j])})
        else:
            for offset in range(max(end_i - i, end_j - j)):
                a, b = i + offset, j + offset
                entry = {"kind": "replace" if a < end_i and b < end_j else "missing" if a < end_i else "extra",
                         "expected_index": a + 1 if a < end_i else None,
                         "actual_index": b + 1 if b < end_j else None,
                         "expected": expected_tokens[a] if a < end_i else "",
                         "actual": actual_tokens[b] if b < end_j else ""}
                alignment.append(entry)
                differences.append(entry)
    return {
        "expected_normalized": " ".join(expected_tokens),
        "actual_normalized": " ".join(actual_tokens),
        "expected_word_count": len(expected_tokens),
        "actual_word_count": len(actual_tokens),
        "word_alignment": alignment,
        "word_differences": differences,
        "missing_words": [d["expected"] for d in differences if d["expected"]],
        "extra_words": [d["actual"] for d in differences if d["actual"]],
        "passed": not differences,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ASR pronunciation QA on clean TTS chunks.")
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
    script_path = Path(args.script).resolve() if args.script else project_dir / "script.json"
    tts_dir = Path(args.tts_dir).resolve() if args.tts_dir else project_dir / "tts" / "clean"
    output_path = Path(args.output).resolve() if args.output else project_dir / "manifests" / "tts-pronunciation-qa.json"

    report: dict[str, Any] = {
        "script": str(script_path),
        "tts_dir": str(tts_dir),
        "output": str(output_path),
        "status": "error",
        "chunks": [],
        "errors": [],
    }

    try:
        script = load_json(script_path)
        chunks = script if isinstance(script, list) else script.get("tts_chunks") if isinstance(script, dict) else None
        if not isinstance(chunks, list) or not chunks:
            raise ValueError("script must be a non-empty narration list or contain a tts_chunks array")
        metadata = script.get("metadata", {}) if isinstance(script, dict) else {}
        language = args.language or str(metadata.get("language") or "").strip()
        if not language:
            raise ValueError("language is required via --language or metadata.language")

        backend_name, backend = import_asr_backend()
        if backend_name == "whisperx":
            transcribe = make_whisperx_transcriber(backend, language, args.model, args.device, args.compute_type)
        else:
            transcribe = make_whisper_transcriber(backend, language, args.model)
        report["language"] = language
        report["backend"] = backend_name
        report["policy"] = "Every unresolved word edit requires audio review; ASR is not proof of a pronunciation error."

        any_failed = False
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                report["errors"].append(f"tts_chunks[{index}] must be an object")
                any_failed = True
                continue
            chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or f"T{index + 1:02d}")
            expected = str(chunk.get("check_text") or chunk.get("voice_text") or chunk.get("say") or "").strip()
            audio_path = resolve_audio_path(tts_dir, chunk, index)
            if not expected:
                report["errors"].append(f"{chunk_id}: missing check_text, voice_text or say")
                any_failed = True
                continue
            if audio_path is None:
                report["errors"].append(f"{chunk_id}: missing clean TTS wav")
                any_failed = True
                continue

            actual = transcribe(audio_path)

            comparison = compare_text(expected, actual, language)
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

        report["status"] = "error" if report["errors"] else "review" if any_failed else "pass"
        write_json(output_path, report)
        if report["status"] != "pass":
            print(f"TTS pronunciation QA {report['status']}: {output_path}", file=sys.stderr)
            return 2 if report["errors"] else 1
        print(f"TTS pronunciation QA passed: {output_path}")
        return 0
    except Exception as exc:
        report["errors"].append(str(exc))
        report["status"] = "error"
        write_json(output_path, report)
        print(f"TTS pronunciation QA error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
