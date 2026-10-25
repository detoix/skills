#!/usr/bin/env python3
"""Compare takes of one line word by word: how well does each script word fit the audio, according to Whisper?

    word_confidence.py --text "Co zapisywali Mykeńczycy?" --language pl take_a.wav take_b.wav [--model small] [--json out.json]

Whisper (faster-whisper) is given the script text itself and returns the probability of every token of it, given
the audio and the words before it (forced alignment). A word that was garbled, swallowed or read with another
language's rules ("Co" read as "Ko") scores low even when free transcription guesses it from context. The free
transcription is printed too: a different first word there is the clearest sign of a wrong start.

Read the numbers comparatively, take against take of the same line. They also drop for reasons unrelated to the
voice: numbers written as words where Whisper would write digits, rare names, a spelling the speaker did not use.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

LOW, BAD = 0.5, 0.2


def canonical(tok, tokens: list[int]) -> list[int]:
    """Merge a bare-space token into the next one (' ', 't' -> ' t'). The BPE sometimes splits a word that way,
    Whisper never writes it so, and the forced probability of such a split is near zero however clear the word is."""
    out, i = [], 0
    while i < len(tokens):
        if tok.decode([tokens[i]]) == " " and i + 1 < len(tokens):
            merged = tok.encode(" " + tok.decode([tokens[i + 1]]))
            if len(merged) == 1:
                out.append(merged[0])
                i += 2
                continue
        out.append(tokens[i])
        i += 1
    return out


def score(model, tok, audio16: np.ndarray, text: str) -> list[dict]:
    feats = model.feature_extractor(audio16)
    enc = model.encode(feats[:, : model.feature_extractor.nb_max_frames])
    tokens = canonical(tok, tok.encode(" " + text.strip()))
    # <|notimestamps|> after language and task: without it the model expects a timestamp first,
    # which pulls down the probability of the first word, the very word this check is most often about
    res = model.model.align(enc, tok.sot_sequence + [tok.no_timestamps], [tokens], feats.shape[-1] - 1, median_filter_width=7)[0]
    probs = np.array(res.text_token_probs)
    words, word_tokens = tok.split_to_word_tokens(tokens + [tok.eot])
    out, i = [], 0
    for w, t in zip(words[:-1], word_tokens[:-1]):
        p = probs[i : i + len(t)]
        i += len(t)
        if any(c.isalnum() for c in w):  # punctuation is style, not pronunciation
            out.append({"word": w.strip(), "p": round(float(np.exp(np.mean(np.log(np.maximum(p, 1e-6))))), 3)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Word-level Whisper confidence of takes of the same line.")
    ap.add_argument("files", nargs="+", help="WAV takes of the same line")
    ap.add_argument("--text", required=True, help="The line as written (instructions in parentheses are dropped)")
    ap.add_argument("--language", required=True, help="Whisper language code, e.g. pl")
    ap.add_argument("--model", default="small", help="faster-whisper model; use one size for every comparison")
    ap.add_argument("--json", help="Write the scores here")
    args = ap.parse_args()

    import soundfile as sf
    from faster_whisper import WhisperModel
    from faster_whisper.tokenizer import Tokenizer
    from scipy import signal

    text = args.text.split(")", 1)[1] if args.text.startswith("(") else args.text
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    tok = Tokenizer(model.hf_tokenizer, True, task="transcribe", language=args.language)
    report = {}
    for f in args.files:
        x, sr = sf.read(f, dtype="float32")
        x = x.mean(1) if x.ndim > 1 else x
        x16 = signal.resample_poly(x, 16000, sr).astype("float32")
        words = score(model, tok, x16, text)
        segs, _ = model.transcribe(x16, language=args.language, beam_size=5, condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segs)
        report[f] = {"words": words, "heard": heard}
        marked = " ".join(
            w["word"] if w["p"] >= LOW else f"[{w['word']} {w['p']:.2f}]" if w["p"] >= BAD else f"[[{w['word']} {w['p']:.2f}]]"
            for w in words
        )
        print(f"{Path(f).name}: first '{words[0]['word']}' {words[0]['p']:.2f}\n   {marked}\n   heard: {heard}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
