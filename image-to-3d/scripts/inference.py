from __future__ import annotations

import argparse
import gc
import os
import sys
from pathlib import Path

os.environ.setdefault("ATTN_BACKEND", "xformers")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CORE_PATH = SCRIPT_DIR / "trellis2_core"
SHIMS_PATH = SCRIPT_DIR / "standalone_shims"
MODEL_ROOT = SKILL_ROOT / "models"
TRELLIS_ROOT = MODEL_ROOT / "Trellis2"
DINOV3_ROOT = MODEL_ROOT / "facebook" / "dinov3-vitl16-pretrain-lvd1689m"

for path in (SHIMS_PATH, CORE_PATH):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import o_voxel
import torch
import trimesh
import numpy as np
from PIL import Image
from rembg import new_session, remove as remove_background
from trellis2_gguf.pipelines import Trellis2ImageTo3DPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone TRELLIS.2 GGUF image-to-3D runner."
    )
    parser.add_argument("--input", required=True, help="Input image path.")
    parser.add_argument("--output", default="output.glb", help="Output mesh path.")
    parser.add_argument(
        "--pipeline-type",
        choices=["512", "1024", "1024_cascade", "1536_cascade"],
        default="1024_cascade",
        help="Generation pipeline. 1024_cascade with GGUF Q4_K_M and low_vram works on 6 GB GPUs.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed.")
    parser.add_argument(
        "--sparse-steps", type=int, default=12, help="Sparse structure steps."
    )
    parser.add_argument(
        "--shape-steps", type=int, default=12, help="Shape latent steps."
    )
    parser.add_argument(
        "--texture-steps", type=int, default=12, help="Texture latent steps."
    )
    parser.add_argument(
        "--sparse-structure-resolution",
        type=int,
        default=32,
        help="Sparse structure grid size.",
    )
    parser.add_argument(
        "--max-num-tokens",
        type=int,
        default=49152,
        help="Token cap for cascade modes.",
    )
    parser.add_argument(
        "--max-views",
        type=int,
        default=4,
        help="Multi-view cap used by the conditioning stack.",
    )
    parser.add_argument(
        "--sampler",
        choices=["euler", "heun", "rk4", "rk5"],
        default="euler",
        help="Sampler family.",
    )
    parser.add_argument(
        "--texture-size",
        type=int,
        default=1024,
        choices=[512, 1024, 2048, 4096],
        help="Export texture resolution for textured outputs.",
    )
    parser.add_argument(
        "--target-face-num",
        type=int,
        default=500_000,
        help="Decimation target for textured export.",
    )
    parser.add_argument(
        "--device",
        choices=["cuda", "cpu"],
        default="cuda",
        help="Execution device.",
    )
    parser.add_argument(
        "--keep-models-loaded",
        action="store_true",
        help="Keep models resident in memory between stages.",
    )
    parser.add_argument(
        "--disable-low-vram",
        action="store_true",
        help="Disable low-VRAM mode. Only do this on larger GPUs.",
    )
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="Skip built-in background removal / resize preprocessing.",
    )
    parser.add_argument(
        "--mesh-only",
        action="store_true",
        help="Skip texture latent generation and export a plain mesh.",
    )
    parser.add_argument(
        "--disable-tiled-decoder",
        action="store_true",
        help="Disable tiled decoding during mesh reconstruction.",
    )
    return parser.parse_args()


def ensure_required_files() -> None:
    required = [
        TRELLIS_ROOT / "pipeline.json",
        TRELLIS_ROOT / "refiner" / "ss_flow_img_dit_1_3B_64_bf16_Q4_K_M.gguf",
        TRELLIS_ROOT / "shape" / "slat_flow_img2shape_dit_1_3B_512_bf16_Q4_K_M.gguf",
        TRELLIS_ROOT / "shape" / "slat_flow_img2shape_dit_1_3B_1024_bf16_Q4_K_M.gguf",
        TRELLIS_ROOT
        / "texture"
        / "slat_flow_imgshape2tex_dit_1_3B_512_bf16_Q4_K_M.gguf",
        TRELLIS_ROOT
        / "texture"
        / "slat_flow_imgshape2tex_dit_1_3B_1024_bf16_Q4_K_M.gguf",
        TRELLIS_ROOT / "decoders" / "Stage1" / "ss_dec_conv3d_16l8_fp16.safetensors",
        TRELLIS_ROOT
        / "decoders"
        / "Stage2"
        / "shape_dec_next_dc_f16c32_fp16.safetensors",
        TRELLIS_ROOT
        / "decoders"
        / "Stage2"
        / "tex_dec_next_dc_f16c32_fp16.safetensors",
        TRELLIS_ROOT / "encoders" / "shape_enc_next_dc_f16c32_fp16.safetensors",
        DINOV3_ROOT / "model.safetensors",
        DINOV3_ROOT / "config.json",
        DINOV3_ROOT / "preprocessor_config.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        lines = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            "Missing required model files. Run `python scripts/download_models.py` first.\n"
            f"{lines}"
        )


def configure_torch(device: str) -> torch.device:
    if device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA was requested but torch.cuda.is_available() is false."
            )
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.set_float32_matmul_precision("high")
        return torch.device("cuda")
    return torch.device("cpu")


def build_pipeline(device: torch.device, low_vram: bool, keep_models_loaded: bool):
    pipeline = Trellis2ImageTo3DPipeline.from_pretrained(
        str(TRELLIS_ROOT),
        keep_models_loaded=keep_models_loaded,
        enable_gguf=True,
        gguf_quant="Q4_K_M",
    )
    pipeline._pretrained_args["image_cond_model"]["args"]["model_name"] = str(
        DINOV3_ROOT
    )
    pipeline.low_vram = low_vram

    if device.type == "cuda":
        if low_vram:
            pipeline.cuda()
        else:
            pipeline.to(device)
    else:
        pipeline.to(device)

    return pipeline


def load_image(path: Path) -> Image.Image:
    image = Image.open(path)
    return image.convert("RGBA") if image.mode == "RGBA" else image.convert("RGB")


def preprocess_image_for_trellis(image: Image.Image) -> Image.Image:
    has_alpha = False
    if image.mode == "RGBA":
        alpha = np.array(image)[:, :, 3]
        has_alpha = not np.all(alpha == 255)

    max_size = max(image.size)
    scale = min(1.0, 1024 / max_size)
    if scale < 1:
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.Resampling.LANCZOS,
        )

    rgba = image.convert("RGBA")
    if not has_alpha:
        session = new_session("u2net")
        rgba = remove_background(image.convert("RGB"), session=session)

    rgba_np = np.array(rgba)
    alpha = rgba_np[:, :, 3]
    bbox = np.argwhere(alpha > int(0.8 * 255))
    if bbox.size == 0:
        return image.convert("RGB")

    x_min = int(np.min(bbox[:, 1]))
    y_min = int(np.min(bbox[:, 0]))
    x_max = int(np.max(bbox[:, 1]))
    y_max = int(np.max(bbox[:, 0]))
    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2
    size = int(max(x_max - x_min, y_max - y_min))
    crop_box = (
        int(center_x - size // 2),
        int(center_y - size // 2),
        int(center_x + size // 2),
        int(center_y + size // 2),
    )
    cropped = rgba.crop(crop_box)
    cropped_np = np.array(cropped).astype(np.float32) / 255.0
    rgb = cropped_np[:, :, :3] * cropped_np[:, :, 3:4]
    return Image.fromarray((rgb * 255).astype(np.uint8))


def export_textured_mesh(
    mesh, output_path: Path, pipeline_type: str, texture_size: int, target_face_num: int
) -> None:
    export_resolution = 512 if pipeline_type == "512" else 1024

    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    gc.collect()

    textured = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices,
        faces=mesh.faces,
        attr_volume=mesh.attrs,
        coords=mesh.coords,
        attr_layout=mesh.layout,
        grid_size=export_resolution,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=target_face_num,
        texture_size=texture_size,
        remesh=False,
        use_tqdm=True,
        verbose=True,
    )
    file_type = output_path.suffix.lstrip(".").lower() or "glb"
    textured.export(output_path, file_type=file_type)


def export_plain_mesh(mesh, output_path: Path) -> None:
    plain = trimesh.Trimesh(
        vertices=mesh.vertices.detach().cpu().numpy(),
        faces=mesh.faces.detach().cpu().numpy(),
        process=False,
    )
    file_type = output_path.suffix.lstrip(".").lower() or "glb"
    plain.export(output_path, file_type=file_type)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input image not found: {input_path}")

    ensure_required_files()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    device = configure_torch(args.device)
    low_vram = not args.disable_low_vram
    pipeline = build_pipeline(
        device=device,
        low_vram=low_vram,
        keep_models_loaded=args.keep_models_loaded,
    )

    image = load_image(input_path)
    if not args.no_preprocess:
        image = preprocess_image_for_trellis(image)
    sparse_params = {"steps": args.sparse_steps}
    shape_params = {"steps": args.shape_steps}
    texture_params = {"steps": args.texture_steps}

    print(f"Running TRELLIS.2 GGUF on {device} with pipeline `{args.pipeline_type}`")
    mesh = pipeline.run(
        image=image,
        seed=args.seed,
        pipeline_type=args.pipeline_type,
        sparse_structure_sampler_params=sparse_params,
        shape_slat_sampler_params=shape_params,
        tex_slat_sampler_params=texture_params,
        preprocess_image=False,
        max_num_tokens=args.max_num_tokens,
        sparse_structure_resolution=args.sparse_structure_resolution,
        max_views=args.max_views,
        generate_texture_slat=not args.mesh_only,
        use_tiled=not args.disable_tiled_decoder,
        sampler=args.sampler,
    )[0]

    if args.mesh_only:
        print("Exporting plain mesh...")
        export_plain_mesh(mesh, output_path)
    else:
        print("Baking textured GLB/mesh...")
        export_textured_mesh(
            mesh=mesh,
            output_path=output_path,
            pipeline_type=args.pipeline_type,
            texture_size=args.texture_size,
            target_face_num=args.target_face_num,
        )

    if device.type == "cuda":
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    gc.collect()
    print(f"Saved {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
