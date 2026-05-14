#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_FONT = "Arial"
DEFAULT_WORDS_PER_PHRASE = 4
DEFAULT_MAX_UNTIMED_RATIO = 0.08
DEFAULT_MAX_CAPTION_BRIDGE_GAP_SECONDS = 0.35
DEFAULT_MIN_CAPTION_EVENT_SECONDS = 0.08


def media_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidate = Path(userprofile) / "Documents" / "FFmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / f"{name}.exe"
        if candidate.exists():
            return str(candidate)
    return name


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def ffprobe_duration(path: Path) -> float:
    cmd = [
        media_tool("ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]
    proc = run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe duration failed for {path}: {proc.stderr.strip()}")
    return float(proc.stdout.strip())


def ffprobe_video(path: Path) -> dict[str, Any]:
    cmd = [
        media_tool("ffprobe"),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    proc = run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe video failed for {path}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    stream = data["streams"][0]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "duration": float(data["format"]["duration"]),
    }


def load_script_segments(script_path: Path, audio_duration: float) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    data = json.loads(script_path.read_text(encoding="utf-8-sig"))
    tts_chunks = data.get("tts_chunks") or []
    if not tts_chunks:
        raise ValueError("script.json must contain tts_chunks for caption timing")

    segments = data.get("segments") or []
    if not segments:
        raise ValueError("script.json must contain segments for written narration")
    narration_by_segment: dict[str, str] = {}
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(f"script.json segments[{index}] must be an object")
        segment_id = segment.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            raise ValueError(f"script.json segments[{index}] is missing segment_id")
        narration = str(segment.get("narration", "")).strip()
        if not narration:
            raise ValueError(f"script.json segment {segment_id!r} has empty narration")
        narration_by_segment[segment_id] = narration

    manifest_path = script_path.parent / "manifests" / "final-audio-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"final audio manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    manifest_chunks = manifest.get("tts_chunks")
    if not isinstance(manifest_chunks, list) or not manifest_chunks:
        raise ValueError("final-audio-manifest.json must contain a non-empty tts_chunks array")

    timing_by_chunk: dict[str, dict[str, float]] = {}
    for index, item in enumerate(manifest_chunks):
        if not isinstance(item, dict):
            raise ValueError(f"final audio manifest tts_chunks[{index}] must be an object")
        chunk_id = item.get("chunk")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError(f"final audio manifest tts_chunks[{index}] is missing chunk")
        if "timeline_start_seconds" not in item:
            raise ValueError(f"final audio manifest chunk {chunk_id!r} is missing timeline_start_seconds")
        if "duration_seconds" not in item:
            raise ValueError(f"final audio manifest chunk {chunk_id!r} is missing duration_seconds")
        start = float(item["timeline_start_seconds"])
        duration = float(item["duration_seconds"])
        if start < 0:
            raise ValueError(f"final audio manifest chunk {chunk_id!r} has negative timeline_start_seconds")
        if duration <= 0:
            raise ValueError(f"final audio manifest chunk {chunk_id!r} has non-positive duration_seconds")
        end = start + duration
        if end - audio_duration > 0.25:
            raise ValueError(
                f"final audio manifest chunk {chunk_id!r} ends at {end:.3f}s beyond audio duration {audio_duration:.3f}s"
            )
        timing_by_chunk[chunk_id] = {"start": start, "end": end, "duration": duration}

    transcript_parts: list[str] = []
    align_segments: list[dict[str, Any]] = []
    alignment_segments: list[dict[str, Any]] = []
    for chunk in tts_chunks:
        if not isinstance(chunk, dict):
            raise ValueError("script.json tts_chunks entries must be objects")
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("script.json tts_chunks entry is missing chunk_id")
        segment_ids = chunk.get("segment_ids")
        if not isinstance(segment_ids, list) or not segment_ids:
            raise ValueError(f"script.json chunk {chunk_id!r} must contain non-empty segment_ids for written narration")
        missing_segments = [segment_id for segment_id in segment_ids if segment_id not in narration_by_segment]
        if missing_segments:
            raise ValueError(f"script.json chunk {chunk_id!r} references missing segment narration: {missing_segments}")
        text = " ".join(narration_by_segment[segment_id] for segment_id in segment_ids)
        if chunk_id not in timing_by_chunk:
            raise ValueError(f"final-audio-manifest.json is missing timing for script chunk {chunk_id!r}")
        timing = timing_by_chunk[chunk_id]
        start = timing["start"]
        end = timing["end"]
        transcript_parts.append(text)
        align_segments.append({"start": start, "end": end, "text": text})
        alignment_segments.append(
            {
                "chunk_id": chunk_id,
                "start": start,
                "end": end,
                "source": "final-audio-manifest",
            }
        )
    return (
        " ".join(transcript_parts),
        align_segments,
        {
            "alignment_source": "final-audio-manifest",
            "final_audio_manifest": str(manifest_path),
            "alignment_segments": alignment_segments,
        },
    )


def load_transcript(transcript_path: Path, audio_duration: float) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    text = transcript_path.read_text(encoding="utf-8-sig").strip()
    return text, [{"start": 0.0, "end": audio_duration, "text": text}], {
        "alignment_source": "transcript",
        "final_audio_manifest": None,
        "alignment_segments": [{"chunk_id": None, "start": 0.0, "end": audio_duration, "source": "transcript"}],
    }


def flatten_whisperx_words(result: dict[str, Any]) -> list[dict[str, Any]]:
    words = result.get("word_segments") or []
    if not words:
        for segment in result.get("segments") or []:
            words.extend(segment.get("words") or [])
    out = []
    for item in words:
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        rec = {"word": word}
        if "start" in item and item["start"] is not None:
            rec["start"] = float(item["start"])
        if "end" in item and item["end"] is not None:
            rec["end"] = float(item["end"])
        if "score" in item and item["score"] is not None:
            rec["score"] = float(item["score"])
        out.append(rec)
    return out


def align_with_whisperx(
    audio_path: Path,
    align_segments: list[dict[str, Any]],
    language: str,
    align_model: str | None,
    device: str,
    model_dir: str | None,
) -> list[dict[str, Any]]:
    try:
        import whisperx  # type: ignore
    except Exception as exc:
        raise RuntimeError("WhisperX is not installed in this Python environment") from exc

    audio = whisperx.load_audio(str(audio_path))
    model_a, metadata = whisperx.load_align_model(
        language_code=language,
        device=device,
        model_name=align_model,
        model_dir=model_dir,
    )
    result = whisperx.align(
        align_segments,
        model_a,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )
    return flatten_whisperx_words(result)


def load_words_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("word_segments") or data.get("words") or data.get("segments") or []
    words: list[dict[str, Any]] = []
    if data and isinstance(data[0], dict) and "words" in data[0]:
        for segment in data:
            words.extend(segment.get("words") or [])
    else:
        words = list(data)
    return [
        {"word": str(w["word"]), "start": float(w["start"]), "end": float(w["end"]), **({"score": w["score"]} if "score" in w else {})}
        for w in words
        if str(w.get("word", "")).strip()
    ]


def validate_words(words: list[dict[str, Any]], max_untimed_ratio: float) -> tuple[int, int]:
    total = len(words)
    untimed = 0
    prev_end = -math.inf
    for idx, word in enumerate(words):
        if "start" not in word or "end" not in word:
            untimed += 1
            continue
        start = float(word["start"])
        end = float(word["end"])
        if end <= start:
            raise ValueError(f"Invalid word timing at index {idx}: end <= start")
        if start + 0.02 < prev_end:
            raise ValueError(f"Non-monotonic word timing at index {idx}")
        prev_end = max(prev_end, end)
    ratio = untimed / total if total else 1.0
    if ratio > max_untimed_ratio:
        raise ValueError(f"Too many untimed words: {untimed}/{total} ({ratio:.1%})")
    return total, untimed


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        s += 1
        cs -= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ")


def hex_to_ass_style_color(value: str) -> str:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        raise ValueError(f"Invalid hex color: {value}")
    rr = clean[0:2]
    gg = clean[2:4]
    bb = clean[4:6]
    return f"&H00{bb}{gg}{rr}".upper()


def hex_to_ass_override_color(value: str) -> str:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        raise ValueError(f"Invalid hex color: {value}")
    rr = clean[0:2]
    gg = clean[2:4]
    bb = clean[4:6]
    return f"&H{bb}{gg}{rr}&".upper()


def starts_new_caption_phrase(
    previous_word: dict[str, Any],
    current_word: dict[str, Any],
    max_phrase_gap_seconds: float,
) -> bool:
    # Workaround: WhisperX provides word timings, not caption phrase boundaries.
    # Reset phrases at sentence/gap boundaries so ASS display text does not pull
    # the first word of the next sentence into the previous on-screen phrase.
    if str(previous_word.get("word", "")).rstrip().endswith((".", "!", "?", ":")):
        return True
    if "end" not in previous_word or "start" not in current_word:
        return False
    return float(current_word["start"]) - float(previous_word["end"]) > max_phrase_gap_seconds


def phrase_bounds(
    index: int,
    words: list[dict[str, Any]],
    words_per_phrase: int,
    max_phrase_gap_seconds: float,
) -> tuple[int, int]:
    start = 0
    count = 0
    for idx in range(0, index + 1):
        if idx > 0 and (count >= words_per_phrase or starts_new_caption_phrase(words[idx - 1], words[idx], max_phrase_gap_seconds)):
            start = idx
            count = 0
        count += 1

    end = index + 1
    while end < len(words) and end - start < words_per_phrase:
        if starts_new_caption_phrase(words[end - 1], words[end], max_phrase_gap_seconds):
            break
        end += 1
    return start, end


def phrase_text(words: list[dict[str, Any]], active_index: int, start: int, end: int, active_color: str) -> str:
    parts = []
    for idx in range(start, end):
        word = ass_escape(str(words[idx]["word"]))
        if idx == active_index:
            parts.append(r"{\c" + active_color + r"\fscx112\fscy112}" + word + r"{\rCaption}")
        else:
            parts.append(word)
    return " ".join(parts)


def next_timed_word_start(words: list[dict[str, Any]], index: int) -> float | None:
    for next_word in words[index + 1 :]:
        if "start" not in next_word:
            continue
        return float(next_word["start"])
    return None


def bridged_caption_end(
    words: list[dict[str, Any]],
    index: int,
    max_bridge_gap_seconds: float,
    min_event_seconds: float,
) -> float:
    event_start = float(words[index]["start"])
    natural_end = float(words[index]["end"])
    event_end = max(natural_end, event_start + min_event_seconds)
    next_start = next_timed_word_start(words, index)
    if next_start is None or next_start <= event_start:
        return event_end

    if next_start <= event_end:
        return max(next_start, event_start + 0.02)

    if next_start - event_end <= max_bridge_gap_seconds:
        return next_start

    return event_end


def write_ass(
    words: list[dict[str, Any]],
    ass_path: Path,
    width: int,
    height: int,
    words_per_phrase: int,
    font: str,
    font_size: int,
    primary_color: str,
    active_color: str,
    margin_v: int,
    max_bridge_gap_seconds: float,
    min_event_seconds: float,
) -> None:
    primary_ass = hex_to_ass_style_color(primary_color)
    active_style_ass = hex_to_ass_style_color(active_color)
    active_override_ass = hex_to_ass_override_color(active_color)
    outline = "&H00000000"
    back = "&H80000000"
    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{font_size},{primary_ass},{active_style_ass},{outline},{back},-1,0,0,0,100,100,0,0,1,5,2,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for idx, word in enumerate(words):
        if "start" not in word or "end" not in word:
            continue
        start, end = phrase_bounds(idx, words, words_per_phrase, max_bridge_gap_seconds)
        text = phrase_text(words, idx, start, end, active_override_ass)
        event_end = bridged_caption_end(words, idx, max_bridge_gap_seconds, min_event_seconds)
        lines.append(f"Dialogue: 0,{ass_time(float(word['start']))},{ass_time(event_end)},Caption,,0,0,0,,{text}\n")
    ass_path.write_text("".join(lines), encoding="utf-8")


def burn_ass(video_path: Path, ass_path: Path, output_path: Path, project_dir: Path) -> None:
    rel_ass = ass_path.relative_to(project_dir).as_posix()
    cmd = [
        media_tool("ffmpeg"),
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"ass={rel_ass}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "copy",
        str(output_path),
    ]
    proc = run(cmd, cwd=project_dir)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg ASS burn-in failed:\n{proc.stderr}")


def build_manifest(
    args: argparse.Namespace,
    video_meta: dict[str, Any],
    output_meta: dict[str, Any] | None,
    total: int,
    untimed: int,
    alignment_info: dict[str, Any],
) -> dict[str, Any]:
    return {
        "audio": str(args.audio),
        "video": str(args.video) if args.video else None,
        "output": str(args.output) if args.output else None,
        "script": str(args.script) if args.script else None,
        "transcript": str(args.transcript) if args.transcript else None,
        "words_json_input": str(args.words_json) if args.words_json else None,
        "language": args.language,
        "backend": "provided-words" if args.words_json else "whisperx-align",
        "alignment_source": alignment_info.get("alignment_source"),
        "final_audio_manifest": alignment_info.get("final_audio_manifest"),
        "alignment_segments": alignment_info.get("alignment_segments", []),
        "style": "phrase-plus-active-word-highlight",
        "words_per_phrase": args.words_per_phrase,
        "max_caption_bridge_gap_seconds": args.max_caption_bridge_gap,
        "min_caption_event_seconds": args.min_caption_event_duration,
        "total_words": total,
        "untimed_words": untimed,
        "base_video": video_meta,
        "captioned_video": output_meta,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and burn modern word-by-word reel captions.")
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--script", type=Path)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--words-json", type=Path, help="Use existing word timings instead of WhisperX alignment.")
    parser.add_argument("--language", default="pl")
    parser.add_argument("--align-model")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--model-dir")
    parser.add_argument("--words-per-phrase", type=int, default=DEFAULT_WORDS_PER_PHRASE)
    parser.add_argument("--font", default=DEFAULT_FONT)
    parser.add_argument("--font-size", type=int, default=76)
    parser.add_argument("--primary-color", default="#ffffff")
    parser.add_argument("--active-color", default="#facc15")
    parser.add_argument("--margin-v", type=int, default=420)
    parser.add_argument("--max-untimed-ratio", type=float, default=DEFAULT_MAX_UNTIMED_RATIO)
    parser.add_argument("--max-caption-bridge-gap", type=float, default=DEFAULT_MAX_CAPTION_BRIDGE_GAP_SECONDS)
    parser.add_argument("--min-caption-event-duration", type=float, default=DEFAULT_MIN_CAPTION_EVENT_SECONDS)
    parser.add_argument("--skip-burn", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    captions_dir = project_dir / "captions"
    manifests_dir = project_dir / "manifests"
    captions_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    audio_path = args.audio.resolve()
    audio_duration = ffprobe_duration(audio_path)

    if args.words_json:
        transcript = ""
        align_segments: list[dict[str, Any]] = []
        alignment_info = {
            "alignment_source": "provided-words",
            "final_audio_manifest": None,
            "alignment_segments": [],
        }
        words = load_words_json(args.words_json.resolve())
    else:
        if args.script:
            transcript, align_segments, alignment_info = load_script_segments(args.script.resolve(), audio_duration)
        elif args.transcript:
            transcript, align_segments, alignment_info = load_transcript(args.transcript.resolve(), audio_duration)
        else:
            raise ValueError("Provide --script, --transcript, or --words-json")
        if not transcript.strip():
            raise ValueError("Transcript is empty")
        words = align_with_whisperx(
            audio_path=audio_path,
            align_segments=align_segments,
            language=args.language,
            align_model=args.align_model,
            device=args.device,
            model_dir=args.model_dir,
        )

    total, untimed = validate_words(words, args.max_untimed_ratio)
    words_path = captions_dir / "words.json"
    words_path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.video:
        video_meta = ffprobe_video(args.video.resolve())
        width = int(video_meta["width"])
        height = int(video_meta["height"])
    else:
        video_meta = {"width": 1080, "height": 1920, "duration": audio_duration}
        width = 1080
        height = 1920

    ass_path = captions_dir / "captions.ass"
    write_ass(
        words=words,
        ass_path=ass_path,
        width=width,
        height=height,
        words_per_phrase=args.words_per_phrase,
        font=args.font,
        font_size=args.font_size,
        primary_color=args.primary_color,
        active_color=args.active_color,
        margin_v=args.margin_v,
        max_bridge_gap_seconds=args.max_caption_bridge_gap,
        min_event_seconds=args.min_caption_event_duration,
    )

    output_meta = None
    if not args.skip_burn:
        if not args.video or not args.output:
            raise ValueError("--video and --output are required unless --skip-burn is set")
        burn_ass(args.video.resolve(), ass_path, args.output.resolve(), project_dir)
        output_meta = ffprobe_video(args.output.resolve())
        if video_meta and (
            output_meta["width"] != video_meta["width"]
            or output_meta["height"] != video_meta["height"]
            or abs(output_meta["duration"] - video_meta["duration"]) > 0.15
        ):
            raise RuntimeError("Captioned output metadata differs materially from base video")

    manifest = build_manifest(args, video_meta, output_meta, total, untimed, alignment_info)
    (manifests_dir / "captions-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"words": str(words_path), "ass": str(ass_path), "output": str(args.output) if args.output else None}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
