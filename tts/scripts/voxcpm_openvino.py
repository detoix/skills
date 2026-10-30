"""Optional Intel GPU diffusion head for the CPU-orchestrated VoxCPM2 path.

OpenVINO is imported only when this backend is probed or selected. Model exports
are local cache data; they contain model weights, never reference audio or text.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import torch

_CACHE_FORMAT = 1
_INPUT_NAMES = ("x", "mu", "t", "cond", "dt")


def _runtime(device):
    if not re.fullmatch(r"GPU(?:\.\d+)?", device):
        raise ValueError("OpenVINO requires an explicit GPU device, such as GPU or GPU.0.")
    import openvino as ov

    core = ov.Core()
    name = str(core.get_property(device, "FULL_DEVICE_NAME"))
    if "intel" not in name.lower():
        raise RuntimeError("The selected OpenVINO GPU is not an Intel GPU.")
    return ov, core


def is_available(device="GPU"):
    """Return whether the optional runtime can access the requested Intel GPU."""
    try:
        _runtime(device)
    except Exception:
        return False
    return True


def _raw_estimator(module):
    # Export the model, rather than an Inductor/torch.compile wrapper around it.
    while True:
        if hasattr(module, "_orig_mod"):
            module = module._orig_mod
        elif hasattr(module, "compiled") and hasattr(module, "module"):
            module = module.module
        else:
            return module


def _fingerprint(module, ov_version):
    """Identify actual weights, configuration and nonpersistent model buffers."""
    digest = hashlib.sha256()
    try:
        model_version = importlib.metadata.version("voxcpm")
    except importlib.metadata.PackageNotFoundError:
        model_version = "unknown"
    config = getattr(module, "config", None)
    if hasattr(config, "model_dump"):
        config = config.model_dump(mode="json")
    elif config is not None:
        config = vars(config)
    identity = {
        "format": _CACHE_FORMAT,
        "module": f"{type(module).__module__}.{type(module).__qualname__}",
        "voxcpm": model_version,
        "torch": torch.__version__,
        "openvino": ov_version,
        "config": config,
    }
    digest.update(json.dumps(identity, sort_keys=True, default=str).encode())
    for kind, tensors in (("parameter", module.named_parameters()), ("buffer", module.named_buffers())):
        for name, tensor in tensors:
            digest.update(json.dumps((kind, name, list(tensor.shape), str(tensor.dtype))).encode())
            raw = tensor.detach().cpu().contiguous().reshape(-1).view(torch.uint8).numpy()
            digest.update(memoryview(raw))
    return digest.hexdigest()


class OpenVINOEstimator(torch.nn.Module):
    """Static-shape GPU requests with a lazy, permanent CPU fallback on failure."""

    def __init__(self, module, *, device="GPU", cache_dir=None, compile_cpu=True):
        super().__init__()
        self.module = _raw_estimator(module)
        self.ov, self.core = _runtime(device)
        self.device = device
        self.compile_cpu = compile_cpu
        self.active_backend = "openvino"
        self.fallback_reason = None
        self._cpu = None
        self._requests = {}
        base = Path(cache_dir) if cache_dir else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "voxcpm" / "openvino"
        self.cache_dir = base / _fingerprint(self.module, self.ov.__version__)

    def _export(self, inputs):
        signature = [(list(value.shape), str(value.dtype)) for value in inputs]
        key = hashlib.sha256(json.dumps(signature).encode()).hexdigest()[:24]
        entry = self.cache_dir / key
        xml = entry / "model.xml"
        binary = entry / "model.bin"

        def complete():
            return xml.is_file() and binary.is_file() and binary.stat().st_size > 0 and (entry / "complete.json").is_file()

        if complete():
            return key, xml
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if entry.exists():
            raise RuntimeError("An incomplete OpenVINO export cache entry must be removed before retrying.")
        with tempfile.TemporaryDirectory(prefix=".export-", dir=self.cache_dir) as work:
            pending = Path(work) / "entry"
            pending.mkdir()
            converted = self.ov.convert_model(
                self.module, example_input=inputs, input=[list(value.shape) for value in inputs]
            )
            if len(converted.inputs) != len(_INPUT_NAMES):
                raise RuntimeError("OpenVINO conversion changed the diffusion head input interface.")
            for port, name in zip(converted.inputs, _INPUT_NAMES):
                port.get_tensor().set_names({name})
            self.ov.save_model(converted, pending / "model.xml", compress_to_fp16=False)
            (pending / "complete.json").write_text(json.dumps({"format": _CACHE_FORMAT, "inputs": signature}))
            try:
                pending.rename(entry)  # Publish XML and BIN together on the same filesystem.
            except OSError:
                if not complete():  # Another process may have published the same export first.
                    raise
        return key, xml

    def _request(self, inputs):
        signature = tuple((tuple(value.shape), value.dtype) for value in inputs)
        if signature not in self._requests:
            _, xml = self._export(inputs)
            network = self.core.compile_model(
                xml, self.device,
                {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "f16", "NUM_STREAMS": "1"},
            )
            self._requests[signature] = network.create_infer_request()
        return self._requests[signature]

    def _on_cpu(self, inputs, error=None):
        if error is not None and self.active_backend != "cpu":
            self.active_backend = "cpu"
            self.fallback_reason = f"{type(error).__name__}: {error}"
            self._requests.clear()
            print(f"OpenVINO GPU failed; continuing on CPU: {self.fallback_reason}", file=sys.stderr)
        if self._cpu is None:
            self._cpu = self.module
            if self.compile_cpu:
                try:
                    from voxcpm_fast import CompiledOrEager

                    self._cpu = CompiledOrEager(self.module)
                except Exception as exc:
                    print(f"CPU compilation unavailable; continuing eager: {type(exc).__name__}: {exc}", file=sys.stderr)
        return self._cpu(*inputs)

    def forward(self, *inputs):
        if self.active_backend == "cpu":
            return self._on_cpu(inputs)
        try:
            if len(inputs) != len(_INPUT_NAMES) or inputs[0].size(0) < 1:
                raise ValueError("The diffusion estimator requires five nonempty tensor inputs.")
            if any(value.device.type != "cpu" or value.dtype != torch.float32 for value in inputs):
                raise ValueError("OpenVINO diffusion inputs must be CPU float32 tensors.")
            count = inputs[0].size(0)
            if any(value.size(0) != count for value in inputs):
                raise ValueError("All diffusion inputs must have the same batch size.")
            size = 1 << (count - 1).bit_length()
            padded = tuple(torch.cat((value, value[-1:].expand(size - count, *value.shape[1:]))) for value in inputs) if size != count else inputs
            request = self._request(padded)
            # Append padding after the complete CFG batch, preserving both halves.
            result = request.infer({name: value.detach().contiguous().numpy() for name, value in zip(_INPUT_NAMES, padded)})
            import numpy as np

            output = np.array(result[0], copy=True)
            if output.shape != tuple(padded[0].shape) or not np.isfinite(output).all():
                raise RuntimeError("OpenVINO returned an invalid diffusion result.")
            return torch.from_numpy(output[:count])
        except Exception as exc:
            return self._on_cpu(inputs, exc)


def configure(model, *, device="GPU", cache_dir=None, compile_cpu=True):
    """Replace only the estimator on an already prepared CPU VoxCPM2 model."""
    adapter = OpenVINOEstimator(
        model.feat_decoder.estimator, device=device, cache_dir=cache_dir, compile_cpu=compile_cpu
    )
    model.feat_decoder.estimator = adapter
    return adapter
