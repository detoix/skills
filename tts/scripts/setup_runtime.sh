#!/usr/bin/env bash
# Create or refresh the skill-local runtime at <skill>/.venv.
# TORCH_BACKEND picks the PyTorch build; default is CUDA when an NVIDIA GPU is present, else cpu.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$SKILL_DIR/.venv"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }

if [ -z "${TORCH_BACKEND:-}" ]; then
  if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then TORCH_BACKEND=auto; else TORCH_BACKEND=cpu; fi
fi

[ -x "$VENV/bin/python" ] || uv venv "$VENV" --python 3.11

uv pip install --python "$VENV/bin/python" \
  --torch-backend "$TORCH_BACKEND" \
  "voxcpm==2.0.3" "wetext==0.1.2" "whisperx==3.8.5" torch torchaudio soundfile

"$VENV/bin/python" -c "
import voxcpm, whisperx, soundfile, torch
print('runtime ready:', '$VENV/bin/python')
print('torch', torch.__version__, '| cuda', torch.cuda.is_available())
"
