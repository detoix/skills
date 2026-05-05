---
name: z-image-turbo
description: High-speed, low-VRAM image generation using the 'Z-Image-Turbo' model. Optimized for 6GB VRAM GPUs (like RTX 4050). Use when an agent needs to generate high-quality images quickly from a text prompt while staying within strict memory limits.
---

# Z-Image-Turbo

This skill provides an agentic interface for the `Tongyi-MAI/Z-Image-Turbo` model, optimized for low-VRAM hardware.

## Features
- **RTX 4050 Optimized**: Uses `bfloat16`, sequential CPU offloading, and VAE tiling/slicing to fit within 6GB VRAM.
- **Fast Generation**: Specifically tuned for 8 inference steps with 0.0 guidance scale.

## Usage

### 1. Setup Environment
Ensure you have the required dependencies installed in a virtual environment:
```bash
pip install -r requirements.txt
```

### 2. Download Models
Before generating images, download the model files to the local `models` directory:
```bash
python scripts/download_models.py
```

### 3. Generate Image (Text-to-Image)
Run the generation script. It will automatically detect and use the local models:
```bash
python scripts/generate.py --prompt "A futuristic city in the style of cyberpunk" --output "city.png"
```

### 4. Transform Image (Image-to-Image)
Modify an existing image by providing a base image and a transformation strength (0.0 to 1.0):
```bash
python scripts/generate.py --prompt "A futuristic city in the style of cyberpunk, sunset" --image "city.png" --strength 0.6 --output "city_transformed.png"
```

## Hardware Requirements
- **VRAM**: Minimum 6GB (NVIDIA RTX 4050 or better recommended).
- **Format**: `bfloat16` is used for 40-series cards; will fallback or error on older hardware if `bfloat16` is not supported.

## Safe Defaults
- `guidance_scale`: 0.0 (required by model)
- `num_inference_steps`: 8 (required by model)
- `torch_dtype`: `torch.bfloat16`
