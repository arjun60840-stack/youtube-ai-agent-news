import os
import time
import json
import logging
import urllib.request
import requests
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import base64

from src.config import Config
from src.script_writer_v2 import ScriptDataV2, SceneData
from src.image_generator import ensure_comfyui_running

logger = logging.getLogger(__name__)

# ComfyUI Image Dimensions
WIDTH = 1280
HEIGHT = 720

def _get_image_from_comfyui(base_url: str, prompt_id: str) -> str:
    """Poll ComfyUI for generation completion and return filename."""
    history_url = f"{base_url}/history/{prompt_id}"
    while True:
        try:
            res = requests.get(history_url)
            res.raise_for_status()
            data = res.json()
            if prompt_id in data:
                outputs = data[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    if "images" in node_output:
                        return node_output["images"][0]["filename"]
        except Exception as e:
            logger.error(f"Error polling ComfyUI history: {e}")
        time.sleep(2)

def _download_comfyui_image(base_url: str, filename: str, save_path: Path):
    """Download the final image from ComfyUI."""
    img_url = f"{base_url}/view?filename={filename}&type=output"
    urllib.request.urlretrieve(img_url, str(save_path))

def _build_comfyui_prompt(positive: str, negative: str, width: int, height: int) -> dict:
    """Build a basic ComfyUI workflow payload."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 6,
                "denoise": 1,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "seed": int(time.time()),
                "steps": 20
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "juggernautXL_ragnarok.safetensors"}
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": height, "width": width}
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": positive}
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": negative}
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]}
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "scene", "images": ["8", 0]}
        }
    }

def validate_image_with_moondream(image_path: Path, narration: str, config: Config) -> bool:
    """Use Ollama's moondream vision model to validate the image matches the narration."""
    import ollama
    
    logger.info(f"Validating image with moondream: {image_path.name}")
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            
        client = ollama.Client(host=config.ollama_base_url)
        
        prompt = (
            f"Does this image clearly explain or depict the following narration: '{narration}'? "
            f"Answer ONLY 'YES' or 'NO'."
        )
        
        response = client.generate(
            model="moondream",
            prompt=prompt,
            images=[image_bytes]
        )
        
        answer = response['response'].strip().upper()
        logger.info(f"Moondream validation result: {answer}")
        
        if "NO" in answer:
            return False
        return True
    except Exception as e:
        logger.warning(f"Failed to validate image with moondream: {e}. Defaulting to True.")
        return True

def _fix_prompt_if_forbidden(prompt: str, config: Config) -> str:
    """Check for forbidden human keywords and ask Ollama to rewrite if found."""
    forbidden_words = {"person", "man", "woman", "portrait", "speaker", "microphone", "businessman", "businesswoman", "human", "people"}
    
    prompt_lower = prompt.lower()
    found_words = [w for w in forbidden_words if w in prompt_lower]
    
    if not found_words:
        return prompt
        
    logger.warning(f"Forbidden words found in prompt {found_words}. Regenerating prompt...")
    
    try:
        import ollama
        client = ollama.Client(host=config.ollama_base_url)
        system_instruction = (
            "You are a strict technical prompt engineer. The user will give you an image prompt that contains humans. "
            "Rewrite the prompt to REMOVE all humans. Focus entirely on official company branding, software interfaces, "
            "product dashboards, technology diagrams, and product renders. Return ONLY the new rewritten prompt. "
            "Do NOT include any commentary."
        )
        response = client.generate(
            model=config.ollama_model,
            system=system_instruction,
            prompt=f"Rewrite this to remove humans: {prompt}"
        )
        new_prompt = response['response'].strip()
        logger.info(f"Rewritten prompt: {new_prompt}")
        return new_prompt
    except Exception as e:
        logger.error(f"Failed to regenerate prompt: {e}")
        # Fallback: manually strip the words or just replace the whole thing
        return "High quality software dashboard interface, abstract technology background, cinematic lighting"

def generate_scene_images_v2(script_data: ScriptDataV2, config: Config, date_str: str) -> List[str]:
    """
    Generate ONE dynamic image per scene using local ComfyUI.
    Returns a list of image paths.
    """
    out_dir = config.project_root / "assets" / "scenes" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Clear stale
    for stale in out_dir.glob("scene_*.png"):
        stale.unlink()
        
    image_paths = []
    
    negative_prompt = (
        "person, man, woman, portrait, speaker, microphone, businessman, businesswoman, "
        "human, people, face, Nature, Mountains, Travel, Romance, Random people, "
        "Generic AI wallpaper, Futuristic city, Unrelated technology art, anime, cartoon, text, watermark, bad quality"
    )
    
    ensure_comfyui_running(config.comfyui_base_url)
    
    for scene in script_data.scenes:
        prompt = _fix_prompt_if_forbidden(scene.image_prompt, config)
        save_path = out_dir / f"scene_{scene.scene_number:03d}.png"
        
        # Max 3 attempts per image
        valid_image = False
        for attempt in range(3):
            logger.info(f"Generating image {scene.scene_number} (Attempt {attempt+1}/3)")
            workflow = _build_comfyui_prompt(prompt, negative_prompt, WIDTH, HEIGHT)
            payload = {"prompt": workflow}
            
            try:
                res = requests.post(f"{config.comfyui_base_url}/prompt", json=payload)
                res.raise_for_status()
                prompt_id = res.json().get("prompt_id")
                
                filename = _get_image_from_comfyui(config.comfyui_base_url, prompt_id)
                _download_comfyui_image(config.comfyui_base_url, filename, save_path)
                logger.info(f"Successfully generated ComfyUI image: {save_path.name}")
                
                # Validation
                if validate_image_with_moondream(save_path, scene.narration, config):
                    valid_image = True
                    break
                else:
                    logger.warning(f"Image {scene.scene_number} failed validation. Retrying...")
                    
            except Exception as e:
                logger.error(f"ComfyUI generation failed for scene {scene.scene_number}: {e}")
                time.sleep(5)
                
        if not valid_image:
            logger.error(f"Failed to generate valid image for scene {scene.scene_number} after 3 attempts. Proceeding anyway.")
            
        if save_path.exists():
            image_paths.append(str(save_path))
            
    logger.info(f"Successfully generated {len(image_paths)} images.")
    return image_paths
