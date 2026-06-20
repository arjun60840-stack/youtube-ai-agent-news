import os
import json
import re
import time
import random
import requests
import subprocess
from pathlib import Path
from typing import Any, Dict, List
import urllib.request
from PIL import Image

from src.config import Config
from src.logger import get_logger

logger = get_logger(__name__)

WIDTH, HEIGHT = 1280, 720

# ======================================================================
# PROMPT SANITIZATION (BUG 2 FIX)
# ======================================================================

def _sanitize_prompt(text: str) -> str:
    """
    Strip HTML, CSS, markdown, and garbage from any text before using it 
    as a ComfyUI image prompt. Returns clean descriptive text only.
    """
    if not text:
        return "technology news presentation, photorealistic, 16:9"
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', ' ', text)
    # Remove HTML entities
    clean = re.sub(r'&[a-zA-Z]+;', ' ', clean)
    clean = re.sub(r'&#\d+;', ' ', clean)
    # Remove CSS-like styles
    clean = re.sub(r"style='[^']*'", ' ', clean)
    clean = re.sub(r'style="[^"]*"', ' ', clean)
    # Remove URLs
    clean = re.sub(r'https?://\S+', ' ', clean)
    # Remove src/alt attributes
    clean = re.sub(r'(src|alt)\s*=\s*[\'"][^\'"]*[\'"]', ' ', clean)
    # Remove markdown
    clean = clean.replace('*', '').replace('#', '').replace('`', '')
    # Remove scene/hook labels
    clean = re.sub(r'(?i)\b(scene|hook|visual|narration|subtitle)\s*\d*\s*[:\-]*', ' ', clean)
    # Collapse whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    # If after cleaning we have less than 10 chars, it's garbage
    if len(clean) < 10:
        return "technology news presentation, photorealistic, 16:9"
    return clean


def _validate_prompt(prompt: str) -> bool:
    """Returns True if prompt is usable for ComfyUI image generation."""
    if not prompt or len(prompt.strip()) < 10:
        return False
    # Reject if it still has HTML
    if re.search(r'<\w+', prompt):
        return False
    if re.search(r'style\s*=', prompt, re.IGNORECASE):
        return False
    return True


def _build_comfyui_prompt(positive_prompt: str, negative_prompt: str) -> dict:
    """Builds the JSON payload for the ComfyUI /prompt endpoint."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": random.randint(1, 999999999999999),
                "steps": 30,
                "cfg": 7.0,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "juggernautXL_ragnarok.safetensors"
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": WIDTH,
                "height": HEIGHT,
                "batch_size": 1
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive_prompt,
                "clip": ["4", 1]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["4", 1]
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ainews",
                "images": ["8", 0]
            }
        }
    }

def _get_image_from_comfyui(base_url: str, prompt_id: str) -> str:
    """Poll ComfyUI history and retrieve the generated filename."""
    history_url = f"{base_url}/history/{prompt_id}"
    for _ in range(150): # Wait up to 300 seconds (150 * 2s)
        try:
            res = requests.get(history_url)
            if res.status_code == 200:
                data = res.json()
                if prompt_id in data:
                    outputs = data[prompt_id].get("outputs", {})
                    for node_id, output_data in outputs.items():
                        if "images" in output_data and len(output_data["images"]) > 0:
                            return output_data["images"][0]["filename"]
            time.sleep(2)
        except Exception as e:
            logger.error(f"Error polling ComfyUI history: {e}")
            time.sleep(2)
    raise TimeoutError("ComfyUI generation timed out after 300 seconds.")

def _download_comfyui_image(base_url: str, filename: str, save_path: Path):
    """Download the final image from ComfyUI."""
    img_url = f"{base_url}/view?filename={filename}&type=output"
    urllib.request.urlretrieve(img_url, str(save_path))

def ensure_comfyui_running(base_url: str):
    """Ensures ComfyUI is running, starts it if offline, and verifies the model exists."""
    logger.info("Checking ComfyUI server status...")
    
    is_running = False
    try:
        res = requests.get(base_url)
        if res.status_code == 200:
            is_running = True
    except requests.exceptions.RequestException:
        pass
        
    if not is_running:
        logger.warning(f"ComfyUI is offline at {base_url}. Attempting to start automatically...")
        comfy_dir = os.path.expandvars(r"%USERPROFILE%\ComfyUI")
        cmd = 'call venv\\Scripts\\activate && start "" python main.py'
        
        try:
            subprocess.Popen(cmd, cwd=comfy_dir, shell=True)
            logger.info("Spawned ComfyUI process. Waiting up to 120 seconds...")
        except Exception as e:
            raise RuntimeError(f"Failed to start ComfyUI subprocess: {e}")
            
        start_time = time.time()
        while time.time() - start_time < 120:
            try:
                res = requests.get(base_url)
                if res.status_code == 200:
                    is_running = True
                    logger.info(f"ComfyUI came online after {int(time.time() - start_time)} seconds.")
                    break
            except requests.exceptions.RequestException:
                time.sleep(5)
                
        if not is_running:
            raise RuntimeError("ComfyUI failed to start within 120 seconds.")
            
    model_path = Path(os.path.expandvars(r"%USERPROFILE%\ComfyUI\models\checkpoints\juggernautXL_ragnarok.safetensors"))
    if not model_path.exists():
        raise FileNotFoundError(f"CRITICAL: Required image model missing at {model_path}")

def _generate_single_image(base_url: str, positive_prompt: str, save_path: Path):
    """Orchestrate generating a single image via ComfyUI."""
    negative_prompt = "Nature, Mountains, Travel, Romance, Random people, Generic AI wallpaper, Futuristic city, Unrelated technology art, anime, cartoon, text, watermark, bad quality"
    
    # ======================================================================
    # FINAL PROMPT VALIDATION (BUG 2 FIX)
    # ======================================================================
    if not _validate_prompt(positive_prompt):
        logger.warning(f"Prompt failed validation, sanitizing: {positive_prompt[:60]}...")
        positive_prompt = _sanitize_prompt(positive_prompt)
    
    workflow = _build_comfyui_prompt(positive_prompt, negative_prompt)
    payload = {"prompt": workflow}
    
    # Ensure it's running right before generating to handle mid-generation crashes
    ensure_comfyui_running(base_url)
    
    logger.info(f"Submitting ComfyUI Prompt: {positive_prompt[:80]}...")
    
    # Let exceptions bubble up. Do not catch and fallback!
    res = requests.post(f"{base_url}/prompt", json=payload)
    res.raise_for_status()
    prompt_id = res.json().get("prompt_id")
    
    filename = _get_image_from_comfyui(base_url, prompt_id)
    _download_comfyui_image(base_url, filename, save_path)
    logger.info(f"Successfully generated ComfyUI image: {save_path.name}")


def generate_scene_images(scenes: List[Dict[str, Any]], config: Config, date_str: str) -> List[Dict[str, Any]]:
    """
    Generate exactly ONE dynamic image per scene using local ComfyUI.
    Returns a list of dictionaries: [{"start": float, "end": float, "path": str}]
    """
    logger.info("Generating advanced dynamic scenes via ComfyUI Director...")
    
    out_dir = config.project_root / "assets" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    import ollama
    
    # ======================================================================
    # SANITIZE SCENE TEXT BEFORE SENDING TO DIRECTOR (BUG 2 FIX)
    # ======================================================================
    script_text = ""
    for i, scene in enumerate(scenes):
        clean_text = _sanitize_prompt(scene['text'])
        script_text += f"Scene {i} (Duration: {scene['end'] - scene['start']:.1f}s): {clean_text}\n"

    system_prompt = """You are a professional video Director AI implementing the NEWS RELEVANCE VISUAL SYSTEM.
CRITICAL RULES:
1. Every image MUST directly relate to and explain the current spoken sentence. A viewer without audio must understand the story from visuals alone.
2. For EVERY scene, you must extract: Company, Product, Feature, Person, Technology. Use these exact entities to generate the image prompt.
3. Validate your prompt: 'Does this image directly support the narration?' If NO, rewrite the prompt.
4. NEVER use generic tech art, futuristic cities, random people, or unrelated landscapes.
5. Ensure every single prompt is visually distinct but highly relevant.
6. Return ONLY a pure JSON array of objects. NO extra text before or after the JSON.

Format:
[
  {
    "scene_index": 0,
    "entities": {"Company": "Google", "Product": "Gemini", "Feature": "Update", "Person": "None", "Technology": "AI"},
    "prompt": "Google logo alongside Gemini logo, official event visual, clear branding, photorealistic"
  }
]"""

    prompt_map = {}
    
    # ======================================================================
    # DIRECTOR AI WITH RETRY (BUG 2 FIX)
    # Try twice before falling back
    # ======================================================================
    for director_attempt in range(2):
        try:
            client = ollama.Client(host=config.ollama_base_url)
            response = client.chat(
                model=config.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate exactly ONE ComfyUI prompt for each of these {len(scenes)} scenes:\n\n{script_text}"}
                ]
            )
            resp_text = response["message"]["content"].strip()
            # Strip code fences
            if resp_text.startswith("```json"):
                resp_text = resp_text[7:]
            if resp_text.startswith("```"):
                resp_text = resp_text[3:]
            if resp_text.endswith("```"):
                resp_text = resp_text[:-3]
            resp_text = resp_text.strip()
            
            scene_queries = json.loads(resp_text)
            
            for item in scene_queries:
                if "scene_index" in item and "prompt" in item:
                    clean_prompt = _sanitize_prompt(item["prompt"])
                    if _validate_prompt(clean_prompt):
                        prompt_map[item["scene_index"]] = clean_prompt
            
            if len(prompt_map) >= len(scenes) * 0.5:  # At least half the prompts are valid
                logger.info(f"Director AI generated {len(prompt_map)}/{len(scenes)} valid prompts on attempt {director_attempt + 1}.")
                break
            else:
                logger.warning(f"Director AI only produced {len(prompt_map)} valid prompts. Retrying...")
                prompt_map = {}
                
        except Exception as e:
            logger.error(f"Director AI attempt {director_attempt + 1} failed: {e}")
            prompt_map = {}

    if not prompt_map:
        logger.warning("Director AI failed completely after 2 attempts. Using per-scene keyword extraction fallback.")

    final_image_segments = []
    
    for i, scene in enumerate(scenes):
        prompt = prompt_map.get(i)
        
        if not prompt:
            # ======================================================================
            # SMART FALLBACK (BUG 2 FIX)
            # Extract real keywords from the sanitized scene text
            # ======================================================================
            clean_text = _sanitize_prompt(scene['text'])
            # Extract meaningful words (>3 chars, no stopwords)
            stopwords = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'has', 'her', 'was', 'one', 'our', 'this', 'that', 'with', 'from', 'have', 'will', 'been', 'they', 'which', 'their', 'said', 'each', 'also', 'than', 'other', 'into', 'more', 'about', 'very', 'just', 'like', 'over', 'such', 'after'}
            keywords = [w for w in clean_text.split() if len(w) > 3 and w.lower() not in stopwords][:6]
            keyword_str = ' '.join(keywords) if keywords else "technology news update"
            prompt = f"{keyword_str}, professional technology presentation, photorealistic, detailed, 16:9 aspect ratio"
            
        # Append unique seed text to prompt to force generation uniqueness
        prompt += f", dynamic angle {i+1}, distinct framing"
        
        slide_path = out_dir / f"scene_{i+1:03d}.png"
        logger.info(f"Generating image {i+1}/{len(scenes)}: {slide_path.name} | Prompt: {prompt[:80]}...")
        _generate_single_image(config.comfyui_base_url, prompt, slide_path)
        
        final_image_segments.append({
            "start": scene["start"],
            "end": scene["end"],
            "path": str(slide_path)
        })

    logger.info(f"Successfully generated {len(final_image_segments)} dynamic image segments.")
    return final_image_segments
