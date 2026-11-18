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

HAS_AUDIO_RUNTIME = all(importlib.util.find_spec(name) for name in ("numpy", "soundfile"))


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
        self.args = ["--library", str(self.root), "--lines", str(self.lines_path),
                     "--native-config", str(self.root / "native.json")]

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

    def test_explicit_python_options_select_python_with_native_runtime_present(self):
        import native_narration

        (self.root / "native.json").write_text("{}")
        out = ["--out", str(self.root / "takes")]
        with patch.object(narrate, "generate") as generate_python, patch.object(native_narration, "generate") as generate_native:
            self.assertEqual(self.call(out), 0)
            generate_native.assert_called_once()
            generate_python.assert_not_called()
            generate_native.reset_mock()
            for options in (["--device", "auto"], ["--rows", "4"], ["--openvino-device", "GPU.0"],
                            ["--openvino-cache-dir", str(self.root / "cache")], ["--no-compile"]):
                with self.subTest(options=options):
                    self.assertEqual(self.call(out + options), 0)
                    generate_python.assert_called_once()
                    generate_native.assert_not_called()
                    generate_python.reset_mock()
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                        self.call(out + ["--engine", "native"] + options)
                    generate_python.assert_not_called()
                    generate_native.assert_not_called()

    @unittest.skipUnless(HAS_AUDIO_RUNTIME, "Needs NumPy and SoundFile")
    def test_native_batch_keeps_completed_take_when_engine_fails_later(self):
        import numpy as np
        import soundfile as sf

        sample = self.root / "bank/sample.wav"
        sf.write(sample, np.full(4800, 0.1), 48000, subtype="PCM_24")
        self.bank["quiet"]["sha256"] = narrate.sha(sample)
        (self.root / "bank/bank.json").write_text(json.dumps(self.bank))
        engine = self.root / "engine"
        engine.write_text(f"#!{sys.executable}\n" + """\
import json, shutil, sys, wave
from pathlib import Path

assert sys.argv[1] == '--batch'
assert '--batch-rows' not in sys.argv
requests = [json.loads(row) for row in Path(sys.argv[2]).read_text(encoding='utf-8').splitlines()]
first, second = requests
assert first['text'] == 'Pierwsze zdanie.' and first['seed'] == 5000
assert second['text'] == 'Drugie zdanie.' and second['seed'] == 5001
assert first['prompt_wav'] == second['prompt_wav']
with wave.open(first['prompt_wav']) as prompt:
    assert prompt.getsampwidth() == 2
print('custom component backend=Vulkan0', file=sys.stderr, flush=True)
shutil.copyfile(first['prompt_wav'], first['output'])
print('voxcpm2-batch-complete 1', flush=True)
print('test second request failure', file=sys.stderr, flush=True)
sys.exit(1)
""", encoding="utf-8")
        engine.chmod(0o755)
        (self.root / "model.gguf").write_bytes(b"model")
        config = self.root / "native.json"
        config.write_text(json.dumps({"executable": "engine", "base_model": "model.gguf",
                                      "acoustic_model": "model.gguf", "batch": True,
                                      "backend_marker": "custom component backend=Vulkan0"}))
        out = self.root / "takes"
        with self.assertRaisesRegex(RuntimeError, "test second request failure"):
            self.call(["--engine", "native", "--out", str(out)])

        take = json.loads((out / "provenance.json").read_text())["takes"]["first"]
        self.assertEqual(take["sha256"], narrate.sha(out / "output_001.wav"))
        self.assertEqual(take["generation"]["prompt_cli"]["converted_from"], "PCM_24")
        self.assertEqual(take["generation"]["batch_rows"], 1)
        self.assertFalse((out / "output_002.wav").exists())
        self.assertFalse(list(out.glob(".native-*")))

    @unittest.skipUnless(HAS_AUDIO_RUNTIME, "Needs NumPy and SoundFile")
    def test_native_batch_pairs_requests_and_records_unpaired_takes(self):
        import numpy as np
        import soundfile as sf

        sample = self.root / "bank/sample.wav"
        sf.write(sample, np.full(4800, 0.1), 48000, subtype="PCM_16")
        self.bank["quiet"]["sha256"] = narrate.sha(sample)
        self.bank["calm"] = dict(self.bank["quiet"], text="Another sample text.")
        (self.root / "bank/bank.json").write_text(json.dumps(self.bank))
        self.lines[1]["mood"] = "calm"
        self.lines.append({"id": "third", "say": "Trzecie zdanie.", "mood": "quiet"})
        self.lines_path.write_text(json.dumps(self.lines))

        engine = self.root / "engine"
        engine.write_text(f"#!{sys.executable}\n" + """\
import json, shutil, sys
from pathlib import Path

assert sys.argv[1] == '--batch'
requests = [json.loads(row) for row in Path(sys.argv[2]).read_text(encoding='utf-8').splitlines()]
if len(requests) == 3:
    batch_rows = sys.argv.index('--batch-rows')
    assert sys.argv[batch_rows + 1] == '2'
    assert [Path(row['output']).name for row in requests] == [
        'output_001.wav', 'output_003.wav', 'output_002.wav']
    assert [row['seed'] for row in requests] == [4294967295, 1, 0]
else:
    assert len(requests) == 1
    assert '--batch-rows' not in sys.argv
    assert Path(requests[0]['output']).name == 'output_003.wav'
    assert requests[0]['seed'] == 1
for number, row in enumerate(requests, 1):
    shutil.copyfile(row['prompt_wav'], row['output'])
    print(f'voxcpm2-batch-complete {number}', flush=True)
""", encoding="utf-8")
        engine.chmod(0o755)
        (self.root / "model.gguf").write_bytes(b"model")
        (self.root / "native.json").write_text(json.dumps({
            "executable": "engine", "base_model": "model.gguf",
            "acoustic_model": "model.gguf", "batch": True, "batch_rows": 2,
        }))

        out = self.root / "takes"
        self.assertEqual(self.call(["--out", str(out), "--seed", "-1"]), 0)
        self.assertEqual(sorted(p.name for p in out.glob("*.wav")), [
            "output_001.wav", "output_002.wav", "output_003.wav"])
        takes = json.loads((out / "provenance.json").read_text())["takes"]
        for take_id, rows, lane, partner, seed in (
            ("first", 2, 1, "third", 4294967295), ("third", 2, 2, "first", 1), ("second", 1, None, None, 0),
        ):
            with self.subTest(take=take_id):
                generation = takes[take_id]["generation"]
                self.assertEqual(generation["invocation"], "batch")
                self.assertEqual(generation["batch_rows"], rows)
                self.assertEqual(generation.get("batch_lane"), lane)
                self.assertEqual(generation.get("batch_partner"), partner)
                self.assertEqual(generation["seed"], seed)
                self.assertEqual(generation["inference_timesteps"], 30)

        retakes = self.root / "retakes"
        self.assertEqual(self.call(["--ids", "third", "--out", str(retakes), "--seed", "-1"]), 0)
        self.assertEqual([p.name for p in retakes.glob("*.wav")], ["output_003.wav"])
        take = json.loads((retakes / "provenance.json").read_text())["takes"]["third"]
        self.assertEqual(take["generation"]["batch_rows"], 1)
        self.assertNotIn("batch_partner", take["generation"])

    @unittest.skipUnless(HAS_AUDIO_RUNTIME, "Needs NumPy and SoundFile")
    def test_native_batch_rows_require_supported_configuration(self):
        config = self.root / "native.json"
        out = self.root / "takes"
        for invalid in (True, 2.0, "2", 0, 3):
            with self.subTest(rows=invalid):
                config.write_text(json.dumps({"batch": True, "batch_rows": invalid}))
                with self.assertRaisesRegex(ValueError, "batch_rows must be 1 or 2"):
                    self.call(["--out", str(out)])
        config.write_text(json.dumps({"batch_rows": 2}))
        self.assertEqual(self.call(["--plan"]), 0)
        with self.assertRaisesRegex(ValueError, "batch_rows=2 requires batch=true"):
            self.call(["--out", str(out)])
        self.assertFalse(out.exists())

    @unittest.skipUnless(HAS_AUDIO_RUNTIME, "Needs NumPy and SoundFile")
    def test_silent_sample_is_rejected_before_library_write(self):
        import numpy as np
        import soundfile as sf
        clip = self.root / "silent.wav"
        sf.write(clip, np.zeros(1000), 48000)
        a = argparse.Namespace(add_mood="new", sample=str(clip), text="Sample.", direction="quiet")
        with self.assertRaisesRegex(ValueError, "audible"):
            narrate.add_mood(a, self.root)
        self.assertFalse((self.root / "bank/new.wav").exists())

    @unittest.skipUnless(HAS_AUDIO_RUNTIME, "Needs NumPy and SoundFile")
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


    @unittest.skipUnless(HAS_AUDIO_RUNTIME and importlib.util.find_spec("scipy"), "Needs NumPy, SoundFile and SciPy")
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
