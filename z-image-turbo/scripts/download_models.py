import os
from diffusers import DiffusionPipeline
import torch

def download_model(model_id="Tongyi-MAI/Z-Image-Turbo", target_dir="models/z-image-turbo"):
    """
    Downloads the model and saves it locally within the skill directory.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    save_path = os.path.join(project_root, target_dir)
    
    print(f"Downloading model {model_id} to {save_path}...")
    
    # We download using the same settings we'll use for inference to ensure compatibility
    pipe = DiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        use_safetensors=True
    )
    
    pipe.save_pretrained(save_path)
    print(f"Model successfully saved to {save_path}")

if __name__ == "__main__":
    download_model()
