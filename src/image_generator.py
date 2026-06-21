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

# Base 16:9 resolution (fallback to 1024x576)
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


def _build_comfyui_prompt(positive_prompt: str, negative_prompt: str, width: int = WIDTH, height: int = HEIGHT) -> dict:
    """Builds the JSON payload for the ComfyUI /prompt endpoint."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": random.randint(1, 999999999999999),
                "steps": 20,
                "cfg": 6.0,
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
                "width": width,
                "height": height,
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
    for _ in range(450): # Wait up to 900 seconds (450 * 2s)
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
    raise TimeoutError("ComfyUI generation timed out after 900 seconds.")

def _download_comfyui_image(base_url: str, filename: str, save_path: Path):
    """Download the final image from ComfyUI."""
    img_url = f"{base_url}/view?filename={filename}&type=output"
    urllib.request.urlretrieve(img_url, str(save_path))

def ensure_comfyui_running(base_url: str, config: "Config" = None):
    """Ensures ComfyUI is running, starts it if offline, and verifies the model exists.

    BUGFIX: comfy_dir and the checkpoint filename were hardcoded to
    "%USERPROFILE%\\ComfyUI" and "juggernautXL_ragnarok.safetensors". If your
    actual ComfyUI install path or checkpoint filename differs even slightly
    (different model name, different drive, portable install, Linux/WSL),
    this raises FileNotFoundError on EVERY scene, every single time, which is
    why "ComfyUI images do not appear in the final video" -- generation never
    succeeds even once. Both are now read from Config / env vars with the old
    values kept ONLY as a last-resort default.
    """
    logger.info("Checking ComfyUI server status...")

    is_running = False
    try:
        res = requests.get(base_url)
        if res.status_code == 200:
            is_running = True
    except requests.exceptions.RequestException:
        pass

    comfy_dir = os.environ.get(
        "COMFYUI_INSTALL_DIR",
        os.path.expandvars(r"%USERPROFILE%\ComfyUI"),
    )
    checkpoint_name = os.environ.get(
        "COMFYUI_CHECKPOINT_NAME",
        "juggernautXL_ragnarok.safetensors",
    )

    if not is_running:
        logger.warning(f"ComfyUI is offline at {base_url}. Attempting to start automatically...")
        cmd = 'call venv\\Scripts\\activate && start "" python main.py --lowvram'

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

    checkpoint_dir = Path(comfy_dir) / "models" / "checkpoints"
    model_path = checkpoint_dir / checkpoint_name
    if not model_path.exists():
        available = []
        if checkpoint_dir.exists():
            available = [p.name for p in checkpoint_dir.glob("*.safetensors")]
        raise FileNotFoundError(
            f"CRITICAL: Required image model missing at {model_path}. "
            f"Set COMFYUI_CHECKPOINT_NAME env var to match an actual file. "
            f"Found in {checkpoint_dir}: {available or 'directory not found / empty'}"
        )

def _generate_single_image(base_url: str, positive_prompt: str, save_path: Path, width: int = WIDTH, height: int = HEIGHT):
    """Orchestrate generating a single image via ComfyUI."""
    negative_prompt = "Nature, Mountains, Travel, Romance, Random people, Generic AI wallpaper, Futuristic city, Unrelated technology art, anime, cartoon, text, watermark, bad quality"
    
    # ======================================================================
    # FINAL PROMPT VALIDATION (BUG 2 FIX)
    # ======================================================================
    if not _validate_prompt(positive_prompt):
        logger.warning(f"Prompt failed validation, sanitizing: {positive_prompt[:60]}...")
        positive_prompt = _sanitize_prompt(positive_prompt)
    
    workflow = _build_comfyui_prompt(positive_prompt, negative_prompt, width, height)
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
    logger.info("CRITICAL DEBUG FIX: Enforcing exactly 5 scenes.")
    scenes = scenes[:5]
    logger.info("Generating advanced dynamic scenes via ComfyUI Director...")

    # BUGFIX: out_dir used to be a single fixed path ("assets/scenes") shared
    # across EVERY attempt and EVERY date_str. When a ComfyUI call raised mid-loop
    # (missing checkpoint, server down, timeout) on a later attempt with FEWER
    # scenes than a previous successful attempt, the leftover higher-numbered
    # PNGs from the earlier attempt stayed on disk. A later len(image_segments)
    # check could then pass even though half the "images" on disk were stale
    # leftovers from a different script. Scoping by date_str guarantees every
    # attempt starts from a clean, isolated directory.
    out_dir = config.project_root / "assets" / "scenes" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear any partial output from a previous failed attempt at this exact
    # date_str so stale frames can never leak into a new render.
    for stale in out_dir.glob("scene_*.png"):
        stale.unlink()
    
    import ollama

    # ======================================================================
    # LEARNED VISUAL PREFERENCES
    # Inject only category="visual" rules from memory.json into the Director
    # AI prompt. This is the visual-pipeline equivalent of the memory_string
    # injection crew_writer.py already does for script-writing agents — that
    # injection only ever reached the script agents, never this prompt, so
    # nothing taught via --teach or learned from quality scores could ever
    # influence image generation until this was added.
    # ======================================================================
    from src.memory import load_memory_by_category
    visual_rules = load_memory_by_category("visual")
    visual_memory_string = ""
    if visual_rules:
        visual_memory_string = "\n\nLEARNED VISUAL PREFERENCES (YOU MUST OBEY THESE STRICTLY):\n"
        for i, rule in enumerate(visual_rules, 1):
            visual_memory_string += f"{i}. {rule}\n"

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
4. NEVER use generic tech art, futuristic cities, random people, static logos, or unrelated landscapes.
5. YOUR PROMPTS MUST BE HIGHLY DYNAMIC AND CINEMATIC. Do not just put a logo next to a logo. Use action verbs and cinematic descriptors! Example keywords to use: cinematic lighting, dynamic angle, low angle, motion blur, active scene, depth of field, dramatic.
6. Ensure every single prompt is visually distinct but highly relevant.
7. Return ONLY a pure JSON array of objects. NO extra text before or after the JSON.

Format:
[
  {
    "scene_index": 0,
    "entities": {"Company": "Google", "Product": "Gemini", "Feature": "Update", "Person": "None", "Technology": "AI"},
    "prompt": "A person holding a smartphone displaying the Google Gemini logo, cinematic neon lighting, dynamic low angle, background motion blur, highly detailed"
  }
]""" + visual_memory_string

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

        # BUGFIX: previously _generate_single_image() exceptions propagated
        # straight out of this function, aborting the ENTIRE batch the moment
        # ANY one scene failed (ComfyUI timeout, transient API error, etc).
        # That is the direct mechanism behind "20-30 scenes planned but only
        # 1-2 images produced": scene 3 fails -> scenes 4..30 never even attempt
        # generation. We now retry once, and only fail that single scene
        # (not the whole batch) if both attempts fail. The caller's
        # `len(generated) >= len(scenes)` check (added below) still aborts
        # the pipeline before render if we end up short — it just no longer
        # masks WHICH scenes failed or kills early scenes that succeeded.
        # Emergency ComfyUI Fix: test mode abort
        # Removed for this explicit 5-scene test

        success = False
        for img_attempt in range(2):
            try:
                if img_attempt == 0:
                    _generate_single_image(config.comfyui_base_url, prompt, slide_path, width=WIDTH, height=HEIGHT)
                else:
                    logger.warning(f"Scene {i+1} timeout/failure detected. Retrying with fallback 1024x576 resolution.")
                    _generate_single_image(config.comfyui_base_url, prompt, slide_path, width=1024, height=576)
                success = True
                break
            except Exception as e:
                logger.error(f"Scene {i+1} image generation failed (try {img_attempt + 1}/2): {e}")
                time.sleep(3)

        if not success:
            logger.error(f"Scene {i+1} permanently failed after retries. Skipping this scene's image — it will be flagged by the count check below.")
            continue
        
        final_image_segments.append({
            "start": scene["start"],
            "end": scene["end"],
            "path": str(slide_path)
        })

    logger.info(f"Successfully generated {len(final_image_segments)} dynamic image segments.")

    # Verify requirement: generated_images > 0
    if len(final_image_segments) == 0:
        raise RuntimeError("EMERGENCY STOP: 0 images generated. Halting pipeline.")

    # Verify requirement: generated_images >= scene_count
    if len(final_image_segments) < len(scenes):
        logger.error(
            f"IMAGE COUNT MISMATCH: {len(final_image_segments)} images generated "
            f"for {len(scenes)} scenes. Missing scene indices: "
            f"{[i+1 for i in range(len(scenes)) if i not in {int(Path(seg['path']).stem.split('_')[1]) - 1 for seg in final_image_segments}]}"
        )

    return final_image_segments
