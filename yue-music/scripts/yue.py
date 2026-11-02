#!/usr/bin/env python3
"""Install, check, and run a self-contained YuE2 C++ music runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time

from runtime_support import (IS_WINDOWS, binary_path, collect_build_artifacts, lock,
                             process_options, runtime_env, stop_process)

SKILL = Path(__file__).resolve().parent.parent
ENGINE_REPO = "https://github.com/ServeurpersoCom/yue2.cpp.git"
ENGINE_REV = "8af01740686824ffd4a1839a457954f42e2a8ce7"
VAE = "YuE2-Vae-F32.gguf"
BINARIES = ("yue-synth", "yue-plan", "yue-server")
INSTALLER_VERSION = 4
PATCHES = ("cpu-threads.patch", "cpu-blas.patch", "nar-attention.patch")


def patch_fingerprints():
    return {name: hashlib.sha256((SKILL / "assets" / name).read_bytes()).hexdigest() for name in PATCHES}


def synthesis_settings(args):
    mode = args.nar_attention
    if mode == "auto":
        mode = "tiled-gemm" if args.device.lower().startswith("vulkan") else "flash"
    return {"nar_attention": mode, "nar_query_tile": args.nar_query_tile}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def run(command, **kwargs):
    print("Running:", " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, **kwargs)


def model_files(root, model=None):
    manifest = read_json(SKILL / "assets/models.json")
    backbones = [entry for entry in manifest["files"] if entry["name"] != VAE]
    if model is None:
        installed = [entry for entry in backbones if (root / "models" / entry["name"]).is_file()]
        if len(installed) != 1:
            raise ValueError("Select --model before the subcommand: " + ", ".join(entry["name"] for entry in backbones))
        selected = installed[0]
    else:
        selected = next((entry for entry in backbones if entry["name"] == model), None)
        if selected is None:
            raise ValueError(f"Unknown model: {model}. See assets/models.json.")
    return [selected, next(entry for entry in manifest["files"] if entry["name"] == VAE)]


def verify_models(root, full=False, model=None):
    for entry in model_files(root, model):
        path = root / "models" / entry["name"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise ValueError(f"Missing or incomplete model: {entry['name']}. Run setup.")
        with path.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                raise ValueError(f"Invalid GGUF: {entry['name']}")
            if full:
                stream.seek(0)
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise ValueError(f"SHA-256 mismatch: {entry['name']}. Remove the incomplete file and rerun setup.")
                print("SHA-256 OK:", entry["name"], flush=True)


def check(root, full=False, binaries_only=False, model=None):
    if not binaries_only:
        verify_models(root, full, model)
    for name in BINARIES:
        path = binary_path(root, name)
        if not path.is_file() or (not IS_WINDOWS and not os.access(path, os.X_OK)):
            raise ValueError(f"Missing executable {path.name}. Run setup.")
        result = subprocess.run([str(path)], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env=runtime_env(root))
        if result.returncode != 1 or "Usage:" not in result.stderr:
            raise ValueError(f"Executable or dependency check failed: {name}: {result.stderr.strip()}")
    message = "Native binaries ready." if binaries_only else "Runtime ready."
    print(message, "No model inference was performed.")


def ensure_models(root, model=None):
    models = root / "models"
    models.mkdir(exist_ok=True)
    manifest = read_json(SKILL / "assets/models.json")
    base = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}"
    for entry in model_files(root, model):
        target = models / entry["name"]
        if not target.exists() or target.stat().st_size != entry["size"]:
            run(["curl", "--fail", "--location", "--retry", "3", "--continue-at", "-", "--output", target, f"{base}/{entry['name']}"])
    if not (models / "LICENSE").is_file():
        run(["curl", "--fail", "--location", "--retry", "3", "--output", models / "LICENSE", f"{base}/LICENSE"])
    verify_models(root, full=True, model=model)


def setup(args, root):
    mkl = Path(args.mkl_root).expanduser().resolve() if args.mkl_root else None
    if mkl and sys.platform != "linux":
        raise ValueError("--mkl-root currently supports GNU C++ on Linux only.")
    if mkl and not mkl.is_dir():
        raise ValueError("mkl-root must be an existing MKL installation directory.")
    configuration = {"installer_version": INSTALLER_VERSION, "engine_revision": ENGINE_REV,
                     "platform": sys.platform, "architecture": platform.machine(),
                     "backend": args.backend, "blas": bool(mkl or args.blas == "on"),
                     "blas_vendor": "Intel10_64lp" if mkl else args.blas_vendor if args.blas == "on" else None,
                     "mkl_root": str(mkl) if mkl else None}
    installed = read_json(root / "install.json") if (root / "install.json").is_file() else {}
    reuse = (not args.rebuild and binary_path(root, "yue-synth").exists()
             and all(installed.get(key) == value for key, value in configuration.items()))
    tools = [] if reuse else ["git", "cmake"]
    if not reuse and not IS_WINDOWS:
        tools.append("c++")
    if not args.build_only:
        tools.extend(("curl", "ffmpeg", "ffprobe"))
    needed = [name for name in tools if not shutil.which(name)]
    if needed:
        raise ValueError("Missing native tools: " + ", ".join(needed) + ". See references/runtime.md for installation.")
    if reuse:
        with lock(root):
            if not args.build_only:
                ensure_models(root, model=getattr(args, "model", None))
            check(root, binaries_only=args.build_only, model=getattr(args, "model", None))
        return
    with lock(root):
        engine = root / "engine"
        if not engine.exists():
            run(["git", "clone", "--no-checkout", ENGINE_REPO, engine])
            run(["git", "-C", engine, "config", "core.autocrlf", "false"])
            run(["git", "-C", engine, "checkout", "--detach", ENGINE_REV])
        revision = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
        if revision != ENGINE_REV:
            raise ValueError("Existing engine has a different revision. Use a new --runtime directory to preserve it.")
        run(["git", "-C", engine, "submodule", "update", "--init", "--depth", "1"])
        for name in PATCHES:
            patch = SKILL / "assets" / name
            applicable = subprocess.run(["git", "-C", str(engine), "apply", "--check", str(patch)], capture_output=True)
            if applicable.returncode == 0:
                run(["git", "-C", engine, "apply", patch])
            else:
                reverse = subprocess.run(["git", "-C", str(engine), "apply", "--reverse", "--check", str(patch)], capture_output=True)
                if reverse.returncode:
                    raise ValueError(f"Bundled patch {name} does not match this checkout; preserve it and inspect its diff.")

        if not args.build_only:
            ensure_models(root, model=getattr(args, "model", None))

        profile = f"{args.backend}-{'mkl' if mkl else args.blas_vendor if args.blas == 'on' else 'native'}"
        build = root / "build" / profile
        options = ["cmake", "-S", engine, "-B", build, "-DCMAKE_BUILD_TYPE=Release", "-DGGML_NATIVE=ON",
                   f"-DGGML_CUDA={'ON' if args.backend == 'cuda' else 'OFF'}",
                   f"-DGGML_VULKAN={'ON' if args.backend == 'vulkan' else 'OFF'}",
                   "-DHTTPLIB_USE_OPENSSL_IF_AVAILABLE=OFF", "-DHTTPLIB_USE_BROTLI_IF_AVAILABLE=OFF",
                   "-DHTTPLIB_USE_ZLIB_IF_AVAILABLE=OFF", "-DCMAKE_BUILD_RPATH_USE_ORIGIN=ON",
                   f"-DCMAKE_PROJECT_ggml_INCLUDE={(SKILL / 'assets/backend-options.cmake').as_posix()}",
                   f"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE={build.as_posix()}",
                   f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_RELEASE={build.as_posix()}"]
        if mkl:
            options += ["-DGGML_BLAS=ON", "-DGGML_BLAS_VENDOR=Intel10_64lp", f"-DYUE_MKL_ROOT={mkl}"]
        else:
            options += [f"-DGGML_BLAS={'ON' if args.blas == 'on' else 'OFF'}",
                        f"-DGGML_BLAS_VENDOR={args.blas_vendor}", "-DYUE_MKL_ROOT="]
        run(options)
        run(["cmake", "--build", build, "--config", "Release", "--target", *BINARIES, "--parallel", str(args.jobs)])
        destination = root / "bin"
        pending = root / ".bin-pending"
        if pending.exists():
            shutil.rmtree(pending)
        pending.mkdir()
        for path in collect_build_artifacts(build):
            shutil.copy2(path, pending / path.name, follow_symlinks=False)
        backup = None
        if destination.exists():
            backups = root / "backups"
            backups.mkdir(exist_ok=True)
            backup = backups / f"bin-{time.time_ns()}"
            destination.rename(backup)
        try:
            pending.rename(destination)
            check(root, binaries_only=args.build_only, model=getattr(args, "model", None))
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            if backup:
                backup.rename(destination)
            raise
        write_json(root / "install.json", {**configuration,
                   "installed_at": datetime.now(timezone.utc).isoformat(), "thread_override": "YUE_THREADS"})


def request_data(args, replay):
    if args.request:
        request = read_json(args.request)
    else:
        request = {"style": args.style, "lyrics": args.lyrics or "[Instrumental]", "cot": "off",
                   "duration": 10.0, "steps": 12, "cfg_scale": 1.0, "peak_clip": 0,
                   "output_format": "wav24", "lm_batch_size": 1, "synth_batch_size": 1}
    if not isinstance(request, dict):
        raise ValueError("Request must be a JSON object.")
    lyrics_file = getattr(args, "lyrics_file", None)
    if lyrics_file is not None:
        request["lyrics"] = lyrics_file.read_text(encoding="utf-8-sig")
    elif args.lyrics is not None:
        request["lyrics"] = args.lyrics
    for field in ("duration", "steps"):
        value = getattr(args, field)
        if value is not None:
            request[field] = value
    if args.seed is not None:
        request["lm_seed"] = request["seed"] = args.seed
    if replay and not request.get("semantic_tokens"):
        raise ValueError("Replay requires the generated audio.json containing semantic_tokens.")
    if not request.get("style") and not request.get("lyrics"):
        raise ValueError("Supply a style or lyrics.")
    duration = request.setdefault("duration", 10.0)
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 360:
        raise ValueError("Duration must be finite and between 0 and 360 seconds.")
    steps = request.setdefault("steps", 12)
    if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 128:
        raise ValueError("Steps must be an integer between 1 and 128.")
    if request.get("lm_batch_size", 1) != 1 or request.get("synth_batch_size", 1) != 1:
        raise ValueError("This launcher runs one track at a time.")
    if request.get("output_format", "wav24") != "wav24":
        raise ValueError("This launcher preserves 24-bit WAV. Set output_format to wav24.")
    request["output_format"] = "wav24"
    return request


def generate(args, root, replay=False):
    request = request_data(args, replay)
    synthesis = synthesis_settings(args)
    adapters = request.get("adapters", [])
    if not isinstance(adapters, list):
        raise ValueError("Request adapters must be an array of objects with name and scale.")
    if adapters and args.adapters_dir is None:
        raise ValueError("Request names adapters; supply --adapters-dir so they can be loaded.")
    adapters_dir = args.adapters_dir.expanduser().resolve() if args.adapters_dir else None
    if adapters_dir and not adapters_dir.is_dir():
        raise ValueError("adapters-dir must be an existing directory.")
    for adapter in adapters:
        if not isinstance(adapter, dict) or not isinstance(adapter.get("name"), str) or not adapter["name"]:
            raise ValueError("Each adapter needs a nonempty name matching a directory entry.")
        name = adapter["name"]
        if Path(name).name != name or name in (".", "..") or not (adapters_dir / name).exists():
            raise ValueError(f"Adapter entry not found in adapters-dir: {name}")
        scale = adapter.get("scale", 1.0)
        if not isinstance(scale, (int, float)) or isinstance(scale, bool) or not math.isfinite(scale):
            raise ValueError(f"Adapter scale must be finite: {name}")
    if args.device == "BLAS":
        raise ValueError("Use --device CPU-BLAS to enable BLAS with CPU fallback.")
    out = Path(args.out_dir).expanduser().resolve()
    # Dry runs have no filesystem, network, model-loading, or runtime-check side effects.
    if args.dry_run:
        print(json.dumps({"runtime": str(root), "out_dir": str(out), "request": request,
                          "threads": args.threads, "device": args.device, "max_seq": args.max_seq,
                          "clamp_fp16": args.clamp_fp16, "model": args.model, **synthesis,
                          "adapters_dir": str(adapters_dir) if adapters_dir else None}, indent=2))
        return
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory is not empty. Choose a new take directory.")
    model = model_files(root, args.model)[0]["name"]
    check(root, model=model)
    with lock(root):
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "request-input.json", request)
        command = [str(binary_path(root, "yue-synth")), "--device", args.device,
                   "--model", str(root / "models" / model), "--vae", str(root / "models" / VAE),
                   "--request", str(out / "request-input.json"), "--out", str(out / "audio.wav"),
                   "--score", str(out / "score.abc"), "--tokens", str(out / "semantic.tokens.csv"),
                   "--latent", str(out / "acoustic.vae")]
        if args.max_seq:
            command += ["--max-seq", str(args.max_seq)]
        if args.clamp_fp16:
            command += ["--clamp-fp16"]
        if adapters_dir:
            command += ["--adapters", str(adapters_dir)]
        if not IS_WINDOWS and shutil.which("nice"):
            command = ["nice", "-n", "19", *command]
        if not IS_WINDOWS and shutil.which("ionice"):
            command = ["ionice", "-c", "3", *command]
        start = time.monotonic()
        status = "failed"
        returncode = None
        try:
            with (out / "generation.log").open("w", encoding="utf-8") as log:
                env = runtime_env(root, args.threads)
                env["YUE_NAR_ATTENTION"] = synthesis["nar_attention"]
                env["YUE_NAR_QUERY_TILE"] = str(synthesis["nar_query_tile"])
                process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                           **process_options())
                try:
                    for line in process.stdout:
                        print(line, end="", flush=True)
                        log.write(line)
                        log.flush()
                    returncode = process.wait()
                except BaseException:
                    stop_process(process)
                    raise
            if returncode:
                raise ValueError(f"Generation exited with {returncode}; inspect generation.log.")
            status = "complete"
        finally:
            write_json(out / "run-info.json", {"status": status, "returncode": returncode,
                       "wall_seconds": round(time.monotonic() - start, 3), "threads": args.threads,
                       "device": args.device, "model": model, "request": request, "clamp_fp16": args.clamp_fp16,
                       **synthesis, "runtime_patches": patch_fingerprints(), "max_seq": args.max_seq,
                       "adapters_dir": str(adapters_dir) if adapters_dir else None,
                       "engine_revision": ENGINE_REV, "model_revision": read_json(SKILL / "assets/models.json")["revision"],
                       "listening_review": "not performed"})
        from inspect_audio import inspect_audio
        report = inspect_audio(out / "audio.wav", out / "acoustic.vae")
        write_json(out / "quality-check.json", report)
        if not report["technical_pass"]:
            raise ValueError("Audio was saved but technical checks failed; inspect quality-check.json.")
        print("Saved:", out / "audio.wav")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=None, help="Override the skill's ignored .runtime directory")
    parser.add_argument("--model", help="Backbone filename from assets/models.json; may be omitted when exactly one is installed")
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("setup", help="Download and build; never generate audio")
    install.add_argument("--backend", choices=("cpu", "cuda", "vulkan"), default="cpu")
    install.add_argument("--jobs", type=int, default=1)
    install.add_argument("--blas", choices=("on", "off"), default="off")
    install.add_argument("--blas-vendor", choices=("OpenBLAS", "Apple"), default="OpenBLAS")
    install.add_argument("--mkl-root", help="GNU/Linux MKL root; enables GNU-threaded LP64 BLAS")
    install.add_argument("--build-only", action="store_true", help="Build native tools without downloading model weights")
    install.add_argument("--rebuild", action="store_true")
    ready = commands.add_parser("check", help="Verify runtime without inference")
    ready.add_argument("--hash", action="store_true")
    ready.add_argument("--binaries-only", action="store_true", help="Check native tools without requiring model weights")
    for name in ("generate", "replay"):
        sub = commands.add_parser(name)
        sources = sub.add_mutually_exclusive_group(required=True)
        sources.add_argument("--request", type=Path)
        if name == "generate":
            sources.add_argument("--style")
        lyrics = sub.add_mutually_exclusive_group()
        lyrics.add_argument("--lyrics")
        if name == "generate":
            lyrics.add_argument("--lyrics-file", type=Path, help="Read lyrics directly from a UTF-8 text file")
        sub.add_argument("--duration", type=float)
        sub.add_argument("--steps", type=int)
        sub.add_argument("--seed", type=int)
        sub.add_argument("--threads", type=int, default=2)
        sub.add_argument("--device", default="CPU")
        sub.add_argument("--clamp-fp16", action="store_true", help="Clamp hidden states to FP16 range")
        sub.add_argument("--adapters-dir", type=Path, help="Directory containing named LoRA adapter files or folders")
        sub.add_argument("--nar-attention", choices=("auto", "flash", "tiled-gemm"), default="auto",
                         help="NAR attention: auto uses tiled GEMM on Vulkan, flash elsewhere; AR attention is unchanged")
        sub.add_argument("--nar-query-tile", type=int, choices=(128, 256, 512), default=256,
                         help="Query rows per tiled GEMM block; all keys remain visible")
        sub.add_argument("--max-seq", type=int)
        sub.add_argument("--out-dir", required=True, type=Path)
        sub.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = (args.runtime or SKILL / ".runtime").expanduser().resolve()
    if hasattr(args, "threads") and not 1 <= args.threads <= 256:
        parser.error("threads must be between 1 and 256")
    if hasattr(args, "jobs") and args.jobs < 1:
        parser.error("jobs must be positive")
    if hasattr(args, "max_seq") and args.max_seq is not None and args.max_seq < 256:
        parser.error("max-seq must be at least 256")
    if args.command == "setup":
        if hasattr(os, "nice"):
            os.nice(19)
        setup(args, root)
    elif args.command == "check":
        check(root, args.hash, args.binaries_only, model=args.model)
    else:
        generate(args, root, args.command == "replay")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Error: {exc}")
    except KeyboardInterrupt:
        sys.exit("Interrupted; completed files and logs were preserved.")
