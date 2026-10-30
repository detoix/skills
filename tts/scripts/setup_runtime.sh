#!/usr/bin/env bash
# Create or refresh the skill-local runtime at <skill>/.venv.
# TORCH_BACKEND picks PyTorch; OPENVINO=auto|1|0 controls the optional Intel GPU backend.
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

TTS_INSTALL_OPENVINO=0
case "${OPENVINO:-auto}" in
  1) TTS_INSTALL_OPENVINO=1 ;;
  0) ;;
  auto)
    for TTS_GPU_VENDOR in /sys/class/drm/renderD*/device/vendor; do
      if [ -r "$TTS_GPU_VENDOR" ] && [ "$(cat "$TTS_GPU_VENDOR")" = "0x8086" ]; then
        TTS_INSTALL_OPENVINO=1
        break
      fi
    done
    ;;
  *) echo 'OPENVINO must be auto, 1, or 0.' >&2; exit 1 ;;
esac
if [ "$TTS_INSTALL_OPENVINO" = 1 ]; then
  uv pip install --python "$VENV/bin/python" "openvino==2026.4.1"
fi

"$VENV/bin/python" -c "
import voxcpm, whisperx, soundfile, torch
print('runtime ready:', '$VENV/bin/python')
print('torch', torch.__version__, '| cuda', torch.cuda.is_available())
"
