# VRAM Optimization for TRELLIS.2 (6GB GPUs)

The RTX 4050 (6GB) requires careful VRAM management to run TRELLIS.2 efficiently.

## Core Optimizations
1.  **GGUF Quantization**: Always use the `Q4_K_M` quantization level. It provides the best balance between quality and memory footprint (~4GB for the DiT models).
2.  **Attention Backend**: Force `xformers`. It reduces memory overhead during self-attention and cross-attention stages.
3.  **CUDA Memory Allocator**: Use `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` to prevent memory fragmentation, which often leads to OOM errors on smaller cards.

## Inference Parameters
- **Target Resolution**: 512 is the sweet spot. 1024 resolution is possible but may require closing all other GPU-heavy apps (browsers, Discord, etc.).
- **Batch Size**: Always keep batch size at 1.
- **Precision**: The GGUF loader handles quantization, but ensuring the rest of the pipeline uses `bf16` or `fp16` for non-GGUF parts (like the vision encoder) is critical.

## System Settings
- Ensure the Windows **Hardware-Accelerated GPU Scheduling (HAGS)** is enabled in System > Display > Graphics.
- Close ComfyUI or other Stable Diffusion instances before running this standalone skill.
