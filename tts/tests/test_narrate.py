"""Library planning and narration contracts, with no voice model or accelerator."""
import argparse
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import narrate


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "voice.wav").write_bytes(b"reference")
        (self.root / "bank").mkdir()
        (self.root / "bank/sample.wav").write_bytes(b"approved sample")
        self.bank = {"quiet": {"file": "bank/sample.wav", "text": "Sample text.", "sha256": narrate.sha(self.root / "bank/sample.wav")}}
        (self.root / "bank/bank.json").write_text(json.dumps(self.bank))
        self.lines = [{"id": "first", "say": "Pierwsze zdanie.", "direction": "quiet", "mood": "quiet"},
                      {"id": "second", "say": "Drugie zdanie.", "direction": "quiet", "mood": "quiet"}]
        self.lines_path = self.root / "lines.json"
        self.lines_path.write_text(json.dumps(self.lines))
        self.args = ["--library", str(self.root), "--lines", str(self.lines_path)]

    def call(self, extra):
        with contextlib.redirect_stdout(io.StringIO()):
            return narrate.main(self.args + extra)

    def test_plan_reads_only_and_never_generates(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(narrate, "generate") as generate:
            self.assertEqual(self.call(["--plan"]), 0)
        generate.assert_not_called()
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_mood_prevents_narration(self):
        with patch.object(narrate, "generate") as generate:
            self.assertEqual(self.call(["--mood", "missing", "--out", str(self.root / "takes")]), 2)
        generate.assert_not_called()
        self.assertFalse((self.root / "takes").exists())

    def test_changed_or_missing_sample_and_reference_fail_preflight(self):
        (self.root / "bank/sample.wav").write_bytes(b"replaced")
        self.assertEqual(self.call(["--plan"]), 2)
        (self.root / "bank/sample.wav").unlink()
        self.assertEqual(self.call(["--plan"]), 2)
        (self.root / "voice.wav").unlink()
        self.assertEqual(self.call(["--plan"]), 2)

    def test_unknown_ids_and_duplicate_ids_are_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call(["--ids", "typo", "--plan"])
        self.lines[1]["id"] = "first"
        self.lines_path.write_text(json.dumps(self.lines))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call(["--plan"])

    def test_retake_keeps_original_number_and_only_selected_lines(self):
        with patch.object(narrate, "generate") as generate:
            self.assertEqual(self.call(["--ids", "second", "--out", "retakes"]), 0)
        args, root, bank, groups, index = generate.call_args.args
        self.assertEqual([l["id"] for l in groups["quiet"]], ["second"])
        self.assertEqual(index["second"], 2)

    def test_plan_cannot_add_a_mood(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            narrate.main(["--library", str(self.root), "--plan", "--add-mood", "new"])
        self.assertFalse((self.root / "bank/new.wav").exists())

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "Needs skill audio runtime")
    def test_silent_sample_is_rejected_before_library_write(self):
        import numpy as np
        import soundfile as sf
        clip = self.root / "silent.wav"
        sf.write(clip, np.zeros(1000), 48000)
        a = argparse.Namespace(add_mood="new", sample=str(clip), text="Sample.", direction="quiet")
        with self.assertRaisesRegex(ValueError, "audible"):
            narrate.add_mood(a, self.root)
        self.assertFalse((self.root / "bank/new.wav").exists())

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "Needs skill audio runtime")
    def test_fallback_provenance_matches_selected_bytes_and_actual_backend(self):
        import numpy as np
        estimator = types.SimpleNamespace(active_backend="openvino", fallback_reason=None)
        tts = types.SimpleNamespace(feat_decoder=types.SimpleNamespace(estimator=estimator), sample_rate=48000,
                                    build_prompt_cache=Mock(return_value="cache"))
        model = types.SimpleNamespace(tts_model=tts)
        fast = types.ModuleType("voxcpm_fast")
        fast.prepare = Mock()
        fast.CompiledOrEager = Mock()
        class Audio:
            def numpy(self): return np.zeros(4800)
            def __len__(self): return 4800
        def generated(*args, **kwargs):
            estimator.active_backend = "cpu"
            estimator.fallback_reason = "test failure"
            yield 0, Audio(), {"attempts": 1}
        fast.generate_many = generated
        backend = types.ModuleType("voxcpm_openvino")
        backend.is_available = Mock(return_value=True)
        backend.configure = Mock()
        torch = types.ModuleType("torch")
        torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        torch.inference_mode = contextlib.nullcontext
        voxcpm = types.ModuleType("voxcpm")
        voxcpm.VoxCPM = types.SimpleNamespace(from_pretrained=Mock(return_value=model))
        modules = {"torch": torch, "voxcpm": voxcpm, "voxcpm_fast": fast, "voxcpm_openvino": backend}
        with patch.dict(sys.modules, modules):
            self.assertEqual(self.call(["--ids", "second", "--out", str(self.root / "takes"),
                                        "--provenance", str(self.root / "manifests/provenance.json")]), 0)
        take = json.loads((self.root / "manifests/provenance.json").read_text())["takes"]["second"]
        self.assertEqual(take["sha256"], narrate.sha(self.root / "takes/output_002.wav"))
        self.assertEqual(take["generation"]["device"], "cpu")
        self.assertTrue(take["generation"]["mixed_backend_possible"])
        self.assertIsNone(take["generation"]["precision"])
        self.assertEqual(voxcpm.VoxCPM.from_pretrained.call_count, 1)


    @unittest.skipUnless(importlib.util.find_spec("numpy"), "Needs skill audio runtime")
    def test_comparison_resamples_stereo_and_preserves_duration(self):
        import numpy as np
        import soundfile as sf
        import compare_takes
        old, new = self.root / "old", self.root / "new"
        old.mkdir()
        new.mkdir()
        sf.write(old / "output_002.wav", np.ones((24000, 2)) * 0.1, 24000)
        sf.write(new / "output_002.wav", np.ones(48000) * 0.1, 48000)
        whisper = types.ModuleType("faster_whisper")
        model = types.SimpleNamespace(hf_tokenizer=None, transcribe=lambda *a, **k: ([types.SimpleNamespace(text="Drugie zdanie.")], None))
        whisper.WhisperModel = Mock(return_value=model)
        tokenizer = types.ModuleType("faster_whisper.tokenizer")
        tokenizer.Tokenizer = Mock(return_value=None)
        confidence = types.ModuleType("word_confidence")
        confidence.score = Mock(return_value=[])
        with patch.dict(sys.modules, {"faster_whisper": whisper, "faster_whisper.tokenizer": tokenizer, "word_confidence": confidence}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(compare_takes.main(["--lines", str(self.lines_path), "--old", str(old), "--new", str(new)]), 0)
        info = sf.info(new / "comparison.wav")
        self.assertEqual((info.samplerate, info.channels, info.frames), (48000, 1, 144000))


if __name__ == "__main__":
    unittest.main()
