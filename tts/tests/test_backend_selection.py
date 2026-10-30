"""Backend routing tests; no model, audio files or accelerator are required.

Run from the skill folder with:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("tts_cli_under_test", SCRIPTS / "voxcpm_tts.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load the skill's speech generator")
tts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tts)


class BackendSelectionTests(unittest.TestCase):
    def setUp(self):
        self.gpu_probe = Mock(return_value=True)
        self.openvino = types.ModuleType("voxcpm_openvino")
        self.openvino.is_available = self.gpu_probe
        self.modules = patch.dict(sys.modules, {"voxcpm_openvino": self.openvino})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    @staticmethod
    def torch_runtime(cuda=False):
        return types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=Mock(return_value=cuda)))

    @staticmethod
    def options(device="auto", rows=4, openvino_device="GPU"):
        return argparse.Namespace(device=device, rows=rows, openvino_device=openvino_device)

    def test_auto_prefers_cuda_when_available(self):
        backend = tts.select_backend(self.torch_runtime(cuda=True), self.options())
        self.assertEqual(backend, "cuda")
        self.gpu_probe.assert_not_called()

    def test_auto_prefers_openvino_without_cuda(self):
        for rows in [1, 4]:
            with self.subTest(rows=rows):
                backend = tts.select_backend(self.torch_runtime(), self.options(rows=rows))
                self.assertEqual(backend, "openvino")

    def test_auto_uses_cpu_without_a_compatible_intel_gpu(self):
        self.gpu_probe.return_value = False
        self.assertEqual(tts.select_backend(self.torch_runtime(), self.options()), "cpu")

    def test_auto_uses_cpu_if_optional_backend_module_is_unavailable(self):
        with patch.dict(sys.modules, {"voxcpm_openvino": None}):
            self.assertEqual(tts.select_backend(self.torch_runtime(), self.options()), "cpu")

    def test_auto_uses_cpu_if_gpu_discovery_fails(self):
        self.gpu_probe.side_effect = RuntimeError("GPU driver could not initialize")
        self.assertEqual(tts.select_backend(self.torch_runtime(), self.options()), "cpu")

    def test_explicit_cpu_overrides_both_gpu_options(self):
        for cuda in [False, True]:
            with self.subTest(cuda=cuda):
                backend = tts.select_backend(self.torch_runtime(cuda=cuda), self.options(device="cpu"))
                self.assertEqual(backend, "cpu")
        self.gpu_probe.assert_not_called()

    def test_explicit_openvino_overrides_cuda(self):
        backend = tts.select_backend(self.torch_runtime(cuda=True), self.options(device="openvino"))
        self.assertEqual(backend, "openvino")
        self.gpu_probe.assert_called_once()

    def test_selected_openvino_device_is_probed(self):
        tts.select_backend(self.torch_runtime(), self.options(openvino_device="GPU.1"))
        self.gpu_probe.assert_called_once_with(device="GPU.1")

    def test_explicit_openvino_explains_unavailable_backend(self):
        self.gpu_probe.return_value = False
        with self.assertRaisesRegex(RuntimeError, "(?i)openvino|intel.*gpu") as raised:
            tts.select_backend(self.torch_runtime(), self.options(device="openvino"))
        self.assertIn("OPENVINO=1", str(raised.exception))

    def test_explicit_openvino_explains_missing_optional_module(self):
        with patch.dict(sys.modules, {"voxcpm_openvino": None}):
            with self.assertRaisesRegex(RuntimeError, "(?i)openvino"):
                tts.select_backend(self.torch_runtime(), self.options(device="openvino"))

    def test_explicit_cuda_requires_cuda_support(self):
        for device in ["cuda", "cuda:1"]:
            with self.subTest(device=device):
                with self.assertRaisesRegex(RuntimeError, "(?i)cuda"):
                    tts.select_backend(self.torch_runtime(), self.options(device=device))

    def test_explicit_cuda_bypasses_intel_gpu_detection(self):
        self.assertEqual(
            tts.select_backend(self.torch_runtime(cuda=True), self.options(device="cuda:1")), "cuda"
        )
        self.gpu_probe.assert_not_called()

    def test_unknown_device_is_rejected(self):
        with self.assertRaises(ValueError):
            tts.select_backend(self.torch_runtime(), self.options(device="unsupported"))

    def test_cli_defaults_to_hardware_selection(self):
        args = tts.build_arg_parser().parse_args([])
        self.assertEqual(args.device, "auto")
        self.assertEqual(args.openvino_device, "GPU")

    def test_cuda_loader_receives_an_explicit_cuda_device(self):
        args = tts.build_arg_parser().parse_args(["--device", "cuda:1"])
        args.device = "cuda:1"
        runtime = self.torch_runtime(cuda=True)
        runtime.cuda.get_device_name = Mock(return_value="CUDA accelerator")
        runtime.cuda.get_device_properties = Mock(return_value=types.SimpleNamespace(total_memory=1024**3))
        runtime.cuda.memory_allocated = Mock(return_value=0)
        runtime.cuda.memory_reserved = Mock(return_value=0)
        runtime.cuda.empty_cache = Mock()
        voxcpm = types.SimpleNamespace(from_pretrained=Mock())
        with contextlib.redirect_stdout(io.StringIO()):
            tts.load_model(voxcpm, runtime, args)
        self.assertEqual(voxcpm.from_pretrained.call_args.kwargs.get("device"), "cuda:1")


@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "Adapter tests require the skill's PyTorch runtime")
class OpenVINOAdapterTests(unittest.TestCase):
    """Exercise tensor handling and failures with a tiny CPU-only head."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        import torch

        spec = importlib.util.spec_from_file_location("tts_openvino_under_test", SCRIPTS / "voxcpm_openvino.py")
        cls.backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.backend)
        cls.torch = torch
        cls.np = np

    def setUp(self):
        torch = self.torch

        class TinyHead(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.ones(1))
                self.register_buffer("offset", torch.zeros(1), persistent=False)
                self.calls = 0

            def forward(self, *inputs):
                self.calls += 1
                return inputs[0] + self.weight + self.offset

        self.head = TinyHead()
        self.core = Mock()
        self.ov = types.SimpleNamespace(__version__="test-runtime")
        self.runtime = patch.object(self.backend, "_runtime", return_value=(self.ov, self.core))
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.adapter = self.backend.OpenVINOEstimator(self.head, cache_dir=directory.name, compile_cpu=False)
        self.request = Mock()
        self.request.infer.side_effect = lambda inputs: {0: inputs["x"] + 1}
        self.adapter._request = Mock(return_value=self.request)

    def inputs(self, count):
        torch = self.torch
        return (
            torch.arange(count * 4, dtype=torch.float32).reshape(count, 2, 2),
            torch.arange(count * 8, dtype=torch.float32).reshape(count, 8),
            torch.arange(count, dtype=torch.float32),
            torch.arange(count * 4, dtype=torch.float32).reshape(count, 2, 2) + 100,
            torch.zeros(count, dtype=torch.float32),
        )

    def test_cfg_order_is_preserved_when_every_input_is_padded(self):
        inputs = self.inputs(6)
        result = self.adapter(*inputs)
        passed = self.request.infer.call_args.args[0]
        self.assertEqual(tuple(passed), ("x", "mu", "t", "cond", "dt"))
        for name, original in zip(passed, inputs):
            self.assertEqual(passed[name].shape[0], 8)
            self.np.testing.assert_array_equal(passed[name][:6], original.numpy())
            self.np.testing.assert_array_equal(passed[name][6:], original[-1:].expand(2, *original.shape[1:]).numpy())
        self.torch.testing.assert_close(result, inputs[0] + 1)
        self.assertEqual(result.shape[0], 6)

    def test_active_batch_can_shrink_without_returning_padding(self):
        for count in [8, 6, 4, 2]:
            with self.subTest(count=count):
                inputs = self.inputs(count)
                result = self.adapter(*inputs)
                self.assertEqual(tuple(result.shape), tuple(inputs[0].shape))
                self.torch.testing.assert_close(result, inputs[0] + 1)
        self.assertEqual(self.adapter.active_backend, "openvino")
        self.assertEqual(self.head.calls, 0)

    def test_returned_audio_features_own_their_memory(self):
        buffer = self.np.zeros((2, 2, 2), dtype=self.np.float32)

        def infer(_inputs):
            buffer[:] += 1
            return {0: buffer}

        self.request.infer.side_effect = infer
        first = self.adapter(*self.inputs(2))
        before = first.clone()
        self.adapter(*self.inputs(2))
        self.torch.testing.assert_close(first, before)
        self.assertTrue(self.np.all(buffer == 2))

    def assert_permanent_cpu_fallback(self):
        inputs = self.inputs(2)
        with contextlib.redirect_stderr(io.StringIO()) as warnings:
            first = self.adapter(*inputs)
            second = self.adapter(*inputs)
        self.torch.testing.assert_close(first, inputs[0] + 1)
        self.torch.testing.assert_close(second, inputs[0] + 1)
        self.assertEqual(self.adapter.active_backend, "cpu")
        self.assertEqual(self.request.infer.call_count, 1)
        self.assertEqual(self.head.calls, 2)
        self.assertEqual(warnings.getvalue().count("continuing on CPU"), 1)

    def test_inference_failure_falls_back_once_and_keeps_using_cpu(self):
        self.request.infer.side_effect = RuntimeError("GPU inference failed")
        self.assert_permanent_cpu_fallback()

    def test_nonfinite_gpu_result_falls_back_to_cpu(self):
        self.request.infer.side_effect = lambda _inputs: {0: self.np.full((2, 2, 2), self.np.nan, dtype=self.np.float32)}
        self.assert_permanent_cpu_fallback()

    def test_wrong_shape_gpu_result_falls_back_to_cpu(self):
        self.request.infer.side_effect = lambda _inputs: {0: self.np.zeros((2, 2, 1), dtype=self.np.float32)}
        self.assert_permanent_cpu_fallback()

    def test_cache_identity_changes_with_weights_buffers_and_runtime(self):
        before = self.backend._fingerprint(self.head, "runtime-a")
        with self.torch.no_grad():
            self.head.weight.add_(1)
        changed_weight = self.backend._fingerprint(self.head, "runtime-a")
        self.head.offset.add_(1)
        changed_buffer = self.backend._fingerprint(self.head, "runtime-a")
        changed_runtime = self.backend._fingerprint(self.head, "runtime-b")
        self.assertEqual(len({before, changed_weight, changed_buffer, changed_runtime}), 4)

    def test_optional_runtime_discovery_failure_is_unavailable(self):
        with patch.object(self.backend, "_runtime", side_effect=ImportError("Optional runtime missing")):
            self.assertFalse(self.backend.is_available())


if __name__ == "__main__":
    unittest.main()
