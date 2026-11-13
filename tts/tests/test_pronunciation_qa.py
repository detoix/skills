"""Pronunciation regressions; no models or network needed."""
import sys
import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tts_pronunciation_qa import compare_text, resolve_audio_path
import tts_pronunciation_qa as qa


class WordComparisonTests(unittest.TestCase):
    def test_single_wrong_word_cannot_hide_in_long_line(self):
        expected = "Zaczęło się od zabawy. Duńscy chłopcy rzucali z proc kamieniami w wał. Dołączyli starsi i zabawa zamieniła się w bitwę."
        result = compare_text(expected, expected.replace("proc", "prog"))
        self.assertFalse(result["passed"])
        self.assertEqual([(d["expected_index"], d["expected"], d["actual"]) for d in result["word_differences"]], [(9, "proc", "prog")])

    def test_polish_spelling_equivalences(self):
        for expected, heard in [("Gród", "Grud"), ("Bóg", "Buk"), ("gród", "grut"),
                                ("kąt", "kont"), ("ręce", "rence"), ("dąb", "domp"),
                                ("wzięła", "wzieła"), ("się", "sie"), ("chór", "hur")]:
            with self.subTest(expected=expected, heard=heard):
                result = compare_text(expected, heard)
                self.assertTrue(result["passed"], result)
                self.assertEqual(result["word_alignment"][0]["kind"], "phonetic")

    def test_articulation_changes_are_not_normalized_away(self):
        for expected, heard in [("proc", "prok"), ("co", "ko"), ("kasa", "kasza"),
                                ("koń", "kon"), ("kąt", "kot"), ("są", "sa"), ("robią", "robio")]:
            with self.subTest(expected=expected, heard=heard):
                self.assertFalse(compare_text(expected, heard)["passed"])

    def test_missing_extra_repeated_and_reordered_words_need_review(self):
        for heard in ["Bóg białego konia", "Bóg miał też białego konia", "Bóg miał miał białego konia", "Bóg białego miał konia"]:
            with self.subTest(heard=heard):
                self.assertFalse(compare_text("Bóg miał białego konia", heard)["passed"])

    def test_normalization_is_language_specific(self):
        self.assertFalse(compare_text("Bóg", "Buk", "en")["passed"])

    def test_case_and_punctuation_are_not_pronunciation(self):
        self.assertTrue(compare_text("Bóg miał konia!", "bóg miał konia.")["passed"])

    def test_asr_word_boundaries_do_not_require_a_retake(self):
        self.assertTrue(compare_text("Na kredowym klifie", "Nakredowym klifie")["passed"])

    def test_a_different_number_is_never_ignored(self):
        self.assertFalse(compare_text("W 1848 roku", "W 1849 roku")["passed"])

    def test_empty_recognition_reports_missing_words(self):
        self.assertEqual([d["kind"] for d in compare_text("Bóg miał konia", "")["word_differences"]], ["missing"] * 3)

    def test_narration_list_runs_word_check_and_writes_review_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script, report = root / "lines.json", root / "report.json"
            script.write_text(json.dumps([{"id": "proc", "say": "Rzucali z proc."}]))
            (root / "output_001.wav").write_bytes(b"audio")
            args = argparse.Namespace(project_dir=tmp, script=str(script), tts_dir=tmp,
                                      output=str(report), language="pl", model="small", device="cpu", compute_type="int8")
            with patch.object(qa, "parse_args", return_value=args), patch.object(qa, "import_asr_backend", return_value=("whisperx", object())), patch.object(qa, "make_whisperx_transcriber", return_value=lambda p: "Rzucali z prog."), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(qa.main(), 1)
            result = json.loads(report.read_text())
            self.assertEqual(result["status"], "review")
            self.assertEqual(result["chunks"][0]["word_differences"][0]["expected"], "proc")

    def test_missing_named_audio_is_not_replaced_by_arbitrary_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "unrelated.wav").write_bytes(b"audio")
            self.assertIsNone(resolve_audio_path(root, {"chunk_id": "missing"}, 0))


if __name__ == "__main__":
    unittest.main()
