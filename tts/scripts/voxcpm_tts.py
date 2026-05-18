from __future__ import annotations

import argparse
import time
from pathlib import Path


DEFAULT_MODEL_ID = "openbmb/VoxCPM2"
DEFAULT_DEVICE = "cuda:0"
DEFAULT_CFG_VALUE = 2.0
DEFAULT_INFERENCE_TIMESTEPS = 20
DEFAULT_OUTPUT_PATH = Path("voxcpm_output.wav")


def _import_runtime():
    try:
        import soundfile as sf
        import torch
        from voxcpm import VoxCPM
    except ImportError as exc:
        raise RuntimeError(
            "VoxCPM2 runtime is not installed. Install it from runtime\\requirements.lock.txt."
        ) from exc
    return VoxCPM, torch, sf


def _format_cuda_status(torch_module) -> str:
    if not torch_module.cuda.is_available():
        return "CUDA unavailable"
    device_name = torch_module.cuda.get_device_name(0)
    total_memory_mib = torch_module.cuda.get_device_properties(0).total_memory // (1024 * 1024)
    allocated_mib = torch_module.cuda.memory_allocated(0) // (1024 * 1024)
    reserved_mib = torch_module.cuda.memory_reserved(0) // (1024 * 1024)
    return (
        f"CUDA device: {device_name} | total={total_memory_mib} MiB "
        f"allocated={allocated_mib} MiB reserved={reserved_mib} MiB"
    )


def require_file(path: str | None, label: str) -> Path | None:
    if not path:
        return None
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"{label} does not exist: {resolved}")
    return resolved


def resolve_prompt_text(args: argparse.Namespace) -> str | None:
    if args.prompt_text and args.prompt_file:
        raise ValueError("Use either --prompt-text or --prompt-file, not both.")
    if args.prompt_file:
        return require_file(args.prompt_file, "prompt text file").read_text(encoding="utf-8").strip()
    if args.prompt_text:
        return args.prompt_text.strip()
    return None


def validate_prompt_args(prompt_audio: Path | None, prompt_text: str | None) -> None:
    if (prompt_audio is None) != (prompt_text is None):
        raise ValueError("--prompt-audio requires --prompt-text or --prompt-file, and vice versa.")


def build_final_text(text: str, control: str | None) -> str:
    control = (control or "").strip()
    return f"({control}){text}" if control else text


def maybe_normalize_text(model, text: str, normalize: bool) -> str:
    if not normalize:
        return text
    if model.text_normalizer is None:
        from voxcpm.utils.text_normalize import TextNormalizer

        model.text_normalizer = TextNormalizer()
    return model.text_normalizer.normalize(text)


def load_model(VoxCPM, torch_module, args: argparse.Namespace):
    print("Loading VoxCPM2 with low-VRAM profile:")
    print(
        f"  model_id={args.model_id} requested_device={args.device} "
        f"optimize={args.optimize} load_denoiser={args.load_denoiser}"
    )
    print(f"  cfg_value={args.cfg_value} inference_timesteps={args.inference_timesteps}")
    print(_format_cuda_status(torch_module))
    if torch_module.cuda.is_available():
        torch_module.cuda.empty_cache()
    return VoxCPM.from_pretrained(
        args.model_id,
        optimize=args.optimize,
        load_denoiser=args.load_denoiser,
    )


def run_single(args: argparse.Namespace) -> Path:
    if not args.text:
        raise ValueError("--text is required unless --input is used for batch mode.")

    VoxCPM, torch, sf = _import_runtime()
    prompt_audio = require_file(args.prompt_audio, "prompt audio")
    reference_audio = require_file(args.reference_audio, "reference audio")
    prompt_text = resolve_prompt_text(args)
    validate_prompt_args(prompt_audio, prompt_text)

    model = None
    try:
        model = load_model(VoxCPM, torch, args)
        target_text = build_final_text(args.text, args.control)
        with torch.inference_mode():
            wav = model.generate(
                text=target_text,
                prompt_wav_path=str(prompt_audio) if prompt_audio else None,
                prompt_text=prompt_text,
                reference_wav_path=str(reference_audio) if reference_audio else None,
                cfg_value=args.cfg_value,
                inference_timesteps=args.inference_timesteps,
                normalize=args.normalize,
            )
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            raise RuntimeError(
                "VoxCPM2 ran out of GPU memory with the low-VRAM profile. "
                "Try fewer inference steps or a shorter reference clip."
            ) from exc
        raise
    finally:
        if torch.cuda.is_available():
            print(_format_cuda_status(torch))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, wav, model.tts_model.sample_rate)
    print(f"Saved VoxCPM2 audio to {output_path}")
    return output_path


def read_batch_texts(input_path: Path) -> list[str]:
    texts = [line.strip() for line in input_path.read_text(encoding="utf-8").splitlines()]
    return [text for text in texts if text]


def build_prompt_cache(model, prompt_text: str | None, prompt_audio: Path | None, reference_audio: Path | None):
    if prompt_audio is None and reference_audio is None:
        return None
    return model.tts_model.build_prompt_cache(
        prompt_text=prompt_text,
        prompt_wav_path=str(prompt_audio) if prompt_audio else None,
        reference_wav_path=str(reference_audio) if reference_audio else None,
    )


def run_batch_cached(args: argparse.Namespace) -> None:
    if not args.output_dir:
        raise ValueError("--output-dir is required with --input.")

    input_path = require_file(args.input, "input file")
    texts = read_batch_texts(input_path)
    if not texts:
        raise ValueError(f"input file is empty: {input_path}")

    VoxCPM, torch, sf = _import_runtime()
    prompt_audio = require_file(args.prompt_audio, "prompt audio")
    reference_audio = require_file(args.reference_audio, "reference audio")
    prompt_text = resolve_prompt_text(args)
    validate_prompt_args(prompt_audio, prompt_text)
    if prompt_audio is None and reference_audio is None:
        raise ValueError("cached batch requires --reference-audio or --prompt-audio with prompt text.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    model = load_model(VoxCPM, torch, args)
    loaded_at = time.perf_counter()
    prompt_cache = build_prompt_cache(model, prompt_text, prompt_audio, reference_audio)
    cache_at = time.perf_counter()
    print(f"Model loaded in {loaded_at - started:.2f}s; prompt cache built in {cache_at - loaded_at:.2f}s")

    success_count = 0
    with torch.inference_mode():
        for index, text in enumerate(texts, 1):
            item_started = time.perf_counter()
            target_text = maybe_normalize_text(model, build_final_text(text, args.control), args.normalize)
            output_file = output_dir / f"output_{index:03d}.wav"
            try:
                # VoxCPM exposes prompt-cache construction but not a public batch API that reuses it.
                generated = model.tts_model._generate_with_prompt_cache(
                    target_text=target_text,
                    prompt_cache=prompt_cache,
                    min_len=args.min_len,
                    max_len=args.max_len,
                    inference_timesteps=args.inference_timesteps,
                    cfg_value=args.cfg_value,
                    retry_badcase=True,
                    retry_badcase_max_times=args.retry_badcase_max_times,
                    retry_badcase_ratio_threshold=args.retry_badcase_ratio_threshold,
                    streaming=False,
                )
                for wav, _, _ in generated:
                    audio = wav.squeeze(0).cpu().numpy()
                    sf.write(output_file, audio, model.tts_model.sample_rate)
                    duration = len(audio) / model.tts_model.sample_rate
                    print(
                        f"Saved: {output_file} ({duration:.2f}s audio, "
                        f"{time.perf_counter() - item_started:.2f}s render)"
                    )
                    success_count += 1
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    raise RuntimeError(
                        "VoxCPM2 ran out of GPU memory during cached batch generation. "
                        "Try fewer inference steps or shorter text chunks."
                    ) from exc
                raise

    print(f"Cached batch finished: {success_count}/{len(texts)} succeeded in {time.perf_counter() - started:.2f}s")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VoxCPM2 GPU-first speech generator")
    parser.add_argument("--text", help="Text to synthesize in single-output mode")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Single-output WAV path")
    parser.add_argument("--input", help="Batch mode input text file, one target utterance per line")
    parser.add_argument("--output-dir", help="Batch mode output directory")
    parser.add_argument("--prompt-audio", help="Prompt audio file path; requires --prompt-text or --prompt-file")
    parser.add_argument("--prompt-text", help="Exact transcript of --prompt-audio")
    parser.add_argument("--prompt-file", help="UTF-8 file containing exact prompt transcript")
    parser.add_argument("--reference-audio", "--reference", dest="reference_audio", help="Reference audio file path")
    parser.add_argument("--control", help="Optional VoxCPM2 control instruction")
    parser.add_argument("--normalize", action="store_true", help="Enable VoxCPM text normalization")
    parser.add_argument("--cfg-value", type=float, default=DEFAULT_CFG_VALUE, help="Classifier-free guidance value")
    parser.add_argument("--inference-timesteps", type=int, default=DEFAULT_INFERENCE_TIMESTEPS)
    parser.add_argument("--min-len", type=int, default=2)
    parser.add_argument("--max-len", type=int, default=4096)
    parser.add_argument("--retry-badcase-max-times", type=int, default=3)
    parser.add_argument("--retry-badcase-ratio-threshold", type=float, default=6.0)
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Torch device, defaults to cuda:0")
    parser.add_argument("--optimize", action="store_true", help="Enable upstream optimize mode")
    parser.add_argument("--load-denoiser", action="store_true", help="Load the optional denoiser")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Hugging Face model id")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.input:
        run_batch_cached(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
