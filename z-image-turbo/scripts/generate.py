import os
import torch
import argparse
import uuid
from PIL import Image
from diffusers import ZImagePipeline, ZImageImg2ImgPipeline

def generate_image(prompt, base_image_path=None, strength=0.6, output_path=None, steps=8, negative_prompt=None, model_id="Tongyi-MAI/Z-Image-Turbo", width=None, height=None):
    """
    Generates an image from a prompt (and optionally a base image) with RTX 4050 6GB VRAM optimizations.
    """
    if output_path is None:
        output_path = f"generated_{uuid.uuid4().hex[:8]}.png"
    
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Check for local model folder first
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_model_path = os.path.join(os.path.dirname(script_dir), "models", "z-image-turbo")
    
    if os.path.exists(local_model_path):
        model_to_load = local_model_path
        print(f"Loading model from local directory: {local_model_path}")
    else:
        model_to_load = model_id
        print(f"Model not found locally. Loading from Hugging Face: {model_id}")
    
    # Determine which pipeline to use
    pipeline_class = ZImageImg2ImgPipeline if base_image_path else ZImagePipeline
    print(f"Initializing {pipeline_class.__name__} for {model_to_load}...")
    
    try:
        # Load with bfloat16 for memory efficiency
        pipe = pipeline_class.from_pretrained(
            model_to_load, 
            torch_dtype=torch.bfloat16,
            use_safetensors=True,
            local_files_only=os.path.exists(local_model_path)
        )

        # Mandatory memory offloading for 6GB VRAM
        pipe.enable_sequential_cpu_offload()
        
        # VAE optimizations
        if hasattr(pipe, "vae"):
            pipe.vae.enable_slicing()
            pipe.vae.enable_tiling()

        # Prepare arguments
        kwargs = {
            "prompt": prompt,
            "guidance_scale": 0.0,
            "num_inference_steps": steps
        }
        if width:
            kwargs["width"] = width
        if height:
            kwargs["height"] = height
        
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        if base_image_path:
            print(f"Using base image: {base_image_path} with strength: {strength} and steps: {steps}")
            init_image = Image.open(base_image_path).convert("RGB")
            kwargs["image"] = init_image
            kwargs["strength"] = strength

        print(f"Generating image...")
        image = pipe(**kwargs).images[0]

        image.save(output_path)
        print(f"Image saved to: {output_path}")
        return output_path

    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        error_msg = "Error: CUDA Out of Memory. 6GB VRAM is insufficient for this operation even with offloading."
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error during generation: {str(e)}"
        print(error_msg)
        return error_msg

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Z-Image-Turbo Generation Tool")
    parser.add_argument("--prompt", type=str, required=True, help="The prompt for image generation")
    parser.add_argument("--image", type=str, default=None, help="Path to base image for img2img")
    parser.add_argument("--strength", type=float, default=0.6, help="Strength of the img2img transformation (0.0 to 1.0)")
    parser.add_argument("--steps", type=int, default=8, help="Number of inference steps")
    parser.add_argument("--neg", type=str, default=None, help="Negative prompt")
    parser.add_argument("--output", type=str, default=None, help="Output file path (.png)")
    parser.add_argument("--model", type=str, default="Tongyi-MAI/Z-Image-Turbo", help="Model ID")
    parser.add_argument("--width", type=int, default=None, help="Output width in pixels")
    parser.add_argument("--height", type=int, default=None, help="Output height in pixels")
    
    args = parser.parse_args()
    generate_image(args.prompt, args.image, args.strength, args.output, args.steps, args.neg, args.model, args.width, args.height)
