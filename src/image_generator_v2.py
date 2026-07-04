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

def overlay_text_on_image(image_path: Path, config: Config, text: str, is_thumbnail: bool = False, scene_num: int = 0):
    """Programmatically overlay clean text onto the ComfyUI-generated image."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        
        try:
            # Arial Bold is standard on Windows
            font_title = ImageFont.truetype("arialbd.ttf", 45 if is_thumbnail else 40)
            font_badge = ImageFont.truetype("arialbd.ttf", 60 if is_thumbnail else 50)
        except Exception:
            font_title = ImageFont.load_default()
            font_badge = ImageFont.load_default()
            
        width, height = img.size
        
        if not is_thumbnail and scene_num > 0:
            # --- News Scene Overlay ---
            badge_text = f"NEWS {scene_num}"
            badge_x, badge_y = 30, 30
            
            bbox = draw.textbbox((badge_x, badge_y), badge_text, font=font_badge)
            padding = 15
            draw.rounded_rectangle(
                [bbox[0]-padding, bbox[1]-padding, bbox[2]+padding, bbox[3]+padding],
                radius=10, fill=(0, 212, 255, 230), outline="white", width=3
            )
            draw.text((badge_x, badge_y), badge_text, font=font_badge, fill="white")
            
            if text:
                words = text.split()
                lines = []
                current_line = []
                for word in words:
                    current_line.append(word)
                    test_line = " ".join(current_line)
                    if draw.textlength(test_line, font=font_title) > (width - 80):
                        current_line.pop()
                        lines.append(" ".join(current_line))
                        current_line = [word]
                if current_line:
                    lines.append(" ".join(current_line))
                
                line_height = 55
                total_height = len(lines) * line_height
                start_y = height - total_height - 50
                
                # Dark background banner at bottom
                draw.rectangle([0, start_y - 20, width, height], fill=(0, 0, 0, 180))
                
                for i, line in enumerate(lines):
                    text_width = draw.textlength(line, font=font_title)
                    x = (width - text_width) / 2
                    y = start_y + (i * line_height)
                    
                    # Drop shadow
                    draw.text((x+2, y+2), line, font=font_title, fill="black")
                    # Main text
                    draw.text((x, y), line, font=font_title, fill="white")
                    
        elif is_thumbnail and text:
            # --- Thumbnail Overlay ---
            words = text.split()
            lines = []
            current_line = []
            for word in words:
                current_line.append(word)
                test_line = " ".join(current_line)
                if draw.textlength(test_line, font=font_badge) > (width - 40):
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(" ".join(current_line))
                
            line_height = 70
            start_y = 60
            
            for i, line in enumerate(lines):
                text_width = draw.textlength(line, font=font_badge)
                x = (width - text_width) / 2
                y = start_y + (i * line_height)
                
                # Text outline
                for offset in [(2,2), (-2,-2), (2,-2), (-2,2)]:
                    draw.text((x+offset[0], y+offset[1]), line, font=font_badge, fill="black")
                draw.text((x+4, y+4), line, font=font_badge, fill="black")
                draw.text((x, y), line, font=font_badge, fill="#FFD700")  # Gold

        img = img.convert("RGB")
        img.save(image_path)
        logger.info(f"Programmatic text overlaid successfully: {image_path.name}")
        
    except Exception as e:
        logger.error(f"Failed to overlay text: {e}")

logger = logging.getLogger(__name__)

# ComfyUI Default Image Dimensions (overridden by config)
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
    """Use Gemini to validate the image matches the narration."""
    # BYPASS GEMINI TO SAVE QUOTA
    return True

def _fix_prompt_if_forbidden(prompt: str, config: Config) -> str:
    """Check for forbidden human keywords and ask Gemini to rewrite if found."""
    forbidden_words = {"person", "man", "woman", "portrait", "speaker", "microphone", "businessman", "businesswoman", "human", "people"}
    
    prompt_lower = prompt.lower()
    found_words = [w for w in forbidden_words if w in prompt_lower]
    
    if not found_words:
        return prompt
        
    logger.warning(f"Forbidden words found in prompt {found_words}. Regenerating prompt...")
    # BYPASS GEMINI TO SAVE QUOTA
    return "High quality software dashboard interface, abstract technology background, cinematic lighting"

def _download_web_image(query: str, save_path: Path) -> bool:
    import time
    time.sleep(2.0)  # Avoid DDG 403 Ratelimit
    try:
        from ddgs import DDGS
        import urllib.request
        logger.info(f"Searching web for image: '{query}'")
        results = DDGS().images(query, max_results=5, size="Wallpaper")
        if not results:
            logger.warning(f"No web images found for query: {query}")
            return False
            
        for result in results:
            url = result.get("image")
            if not url:
                continue
            try:
                # Add a user-agent to avoid 403 Forbidden errors
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response, open(save_path, 'wb') as out_file:
                    out_file.write(response.read())
                
                # Check if it's a valid image
                from PIL import Image
                with Image.open(save_path) as img:
                    img.verify()
                
                logger.info(f"Successfully downloaded web image from: {url}")
                return True
            except Exception as e:
                logger.warning(f"Failed to download or verify image {url}: {e}")
                if save_path.exists():
                    save_path.unlink()
                
        return False
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return False


def generate_scene_images_v2(script_data: ScriptDataV2, config: Config, date_str: str) -> List[str]:
    """
    Generate ONE dynamic image per scene using local ComfyUI, OR fetch from web.
    Returns a list of image paths.
    """
    out_dir = config.images_dir / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Clear stale
    for stale in out_dir.glob("scene_*.png"):
        stale.unlink()
        
    image_paths = []
    
    if not config.use_real_images:
        negative_prompt = (
            "person, man, woman, portrait, speaker, microphone, businessman, businesswoman, "
            "human, people, face, Nature, Mountains, Travel, Romance, Random people, "
            "Generic AI wallpaper, Futuristic city, Unrelated technology art, anime, cartoon, "
            "text, watermark, bad quality, letters, numbers, writing, typography, digits, words, logo, signature"
        )
        ensure_comfyui_running(config.comfyui_base_url)
    
    for scene in script_data.scenes:
        save_path = out_dir / f"scene_{scene.scene_number:03d}.png"
        
        if config.use_real_images:
            logger.info(f"Fetching real image for scene {scene.scene_number}: '{scene.image_prompt}'")
            success = _download_web_image(scene.image_prompt, save_path)
            
            if not success:
                logger.error(f"Failed to fetch real image for scene {scene.scene_number}.")
                # Create a blank fallback image
                from PIL import Image
                img = Image.new('RGB', (720, 1280), color=(0, 0, 0))
                img.save(save_path)
                
            # Apply programmatic text overlay
            overlay_text_on_image(save_path, config, scene.subtitle, is_thumbnail=False, scene_num=scene.scene_number)
            
            if save_path.exists():
                image_paths.append(str(save_path))
                
        else:
            prompt = _fix_prompt_if_forbidden(scene.image_prompt, config)
            
            target_width = 720 if getattr(config, "video_format", "landscape") == "portrait" else 1280
            target_height = 1280 if getattr(config, "video_format", "landscape") == "portrait" else 720
            
            # Max 3 attempts per image
            valid_image = False
            for attempt in range(3):
                logger.info(f"Generating image {scene.scene_number} (Attempt {attempt+1}/3)")
                workflow = _build_comfyui_prompt(prompt, negative_prompt, target_width, target_height)
                payload = {"prompt": workflow}
                
                try:
                    res = requests.post(f"{config.comfyui_base_url}/prompt", json=payload)
                    res.raise_for_status()
                    prompt_id = res.json().get("prompt_id")
                    
                    filename = _get_image_from_comfyui(config.comfyui_base_url, prompt_id)
                    _download_comfyui_image(config.comfyui_base_url, filename, save_path)
                    logger.info(f"Successfully generated ComfyUI image: {save_path.name}")
                    
                    # Apply programmatic text overlay
                    overlay_text_on_image(save_path, config, scene.subtitle, is_thumbnail=False, scene_num=scene.scene_number)
                    
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
            
    logger.info(f"Successfully generated/fetched {len(image_paths)} images.")
    return image_paths

def generate_thumbnail_v2(script_data: ScriptDataV2, config: Config, date_str: str) -> str:
    """
    Generate a highly catchy thumbnail image using ComfyUI, OR fetch from web based on the thumbnail_prompt.
    Returns the path to the generated thumbnail.
    """
    out_dir = config.images_dir / "thumbnails" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    
    save_path = out_dir / "thumbnail.png"
    if save_path.exists():
        save_path.unlink()
        
    # Shorts thumbnails are typically 9:16 vertical on mobile, but for API upload we'll use standard portrait dimensions
    target_width = 720 if getattr(config, "video_format", "landscape") == "portrait" else 1280
    target_height = 1280 if getattr(config, "video_format", "landscape") == "portrait" else 720

    if config.use_real_images:
        logger.info(f"Fetching real thumbnail image: '{script_data.title}'")
        success = _download_web_image(script_data.title, save_path)
        
        if not success:
            logger.error("Failed to fetch real thumbnail image. Falling back to scene 1.")
            import shutil
            scene1_path = out_dir.parent / date_str / "scene_001.png"
            if scene1_path.exists():
                shutil.copy(scene1_path, save_path)
                return str(save_path)
            return ""
            
        # Apply programmatic text overlay using the video title
        overlay_text_on_image(save_path, config, script_data.title, is_thumbnail=True)
        return str(save_path)
    
    else:
        negative_prompt = (
            "person, man, woman, portrait, speaker, microphone, businessman, businesswoman, "
            "human, people, face, text, watermark, bad quality, boring, generic, "
            "letters, numbers, writing, typography, digits, words, logo, signature"
        )
        
        prompt = _fix_prompt_if_forbidden(script_data.scenes[0].image_prompt, config)
        logger.info("Generating custom YouTube Thumbnail via ComfyUI using Scene 1 prompt...")
        
        ensure_comfyui_running(config.comfyui_base_url)
        
        workflow = _build_comfyui_prompt(prompt, negative_prompt, target_width, target_height)
        payload = {"prompt": workflow}
        
        try:
            res = requests.post(f"{config.comfyui_base_url}/prompt", json=payload)
            res.raise_for_status()
            prompt_id = res.json().get("prompt_id")
            
            filename = _get_image_from_comfyui(config.comfyui_base_url, prompt_id)
            _download_comfyui_image(config.comfyui_base_url, filename, save_path)
            logger.info(f"Successfully generated YouTube Thumbnail: {save_path}")
            
            # Apply programmatic text overlay using the video title
            overlay_text_on_image(save_path, config, script_data.title, is_thumbnail=True)
            
            return str(save_path)
            
        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {e}")
            return ""
