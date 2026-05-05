from __future__ import annotations

from pathlib import Path

from huggingface_hub import hf_hub_download


SKILL_ROOT = Path(__file__).resolve().parent.parent
MODEL_ROOT = SKILL_ROOT / "models"
TRELLIS_ROOT = MODEL_ROOT / "Trellis2"
DINOV3_ROOT = MODEL_ROOT / "facebook" / "dinov3-vitl16-pretrain-lvd1689m"

TRELLIS_FILES = [
    "pipeline.json",
    "refiner/ss_flow_img_dit_1_3B_64_bf16.json",
    "refiner/ss_flow_img_dit_1_3B_64_bf16_Q4_K_M.gguf",
    "shape/slat_flow_img2shape_dit_1_3B_512_bf16.json",
    "shape/slat_flow_img2shape_dit_1_3B_512_bf16_Q4_K_M.gguf",
    "shape/slat_flow_img2shape_dit_1_3B_1024_bf16.json",
    "shape/slat_flow_img2shape_dit_1_3B_1024_bf16_Q4_K_M.gguf",
    "texture/slat_flow_imgshape2tex_dit_1_3B_512_bf16.json",
    "texture/slat_flow_imgshape2tex_dit_1_3B_512_bf16_Q4_K_M.gguf",
    "texture/slat_flow_imgshape2tex_dit_1_3B_1024_bf16.json",
    "texture/slat_flow_imgshape2tex_dit_1_3B_1024_bf16_Q4_K_M.gguf",
    "decoders/Stage1/ss_dec_conv3d_16l8_fp16.json",
    "decoders/Stage1/ss_dec_conv3d_16l8_fp16.safetensors",
    "decoders/Stage2/shape_dec_next_dc_f16c32_fp16.json",
    "decoders/Stage2/shape_dec_next_dc_f16c32_fp16.safetensors",
    "decoders/Stage2/tex_dec_next_dc_f16c32_fp16.json",
    "decoders/Stage2/tex_dec_next_dc_f16c32_fp16.safetensors",
    "encoders/shape_enc_next_dc_f16c32_fp16.json",
    "encoders/shape_enc_next_dc_f16c32_fp16.safetensors",
]

DINOV3_FILES = [
    "model.safetensors",
    "config.json",
    "preprocessor_config.json",
]


def download_many(repo_id: str, files: list[str], local_dir: Path) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    for rel_path in files:
        print(f"Downloading {repo_id}:{rel_path}")
        hf_hub_download(
            repo_id=repo_id,
            filename=rel_path,
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
        )


def main() -> int:
    download_many("Aero-Ex/Trellis2-GGUF", TRELLIS_FILES, TRELLIS_ROOT)
    download_many(
        "PIA-SPACE-LAB/dinov3-vitl-pretrain-lvd1689m",
        DINOV3_FILES,
        DINOV3_ROOT,
    )
    print("All requested model files are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
