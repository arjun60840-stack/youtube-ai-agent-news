"""
Video Generator Module — AI Daily News YouTube Agent

BUG 4 FIX: Thumbnail text is now sanitized before being passed to FFmpeg.
"""

import re
import subprocess
import random
from pathlib import Path
from typing import Any, Dict, List

from src.config import Config
from src.logger import get_logger

logger = get_logger(__name__)

def generate_video(
    image_segments: List[Dict[str, Any]], 
    audio_path: str, 
    subtitle_path: str, 
    config: Config, 
    date_str: str
) -> str:
    """
    Assemble the final video using FFmpeg.
    Applies randomized Ken Burns zoom/pan to dynamic image segments, concats them, 
    adds audio, and burns dynamic subtitles.
    """
    logger.info("Starting advanced dynamic FFmpeg video assembly...")
    
    out_path = config.videos_dir / f"{date_str}.mp4"
    if out_path.exists():
        out_path.unlink()
        
    inputs = []
    filter_chains = []
    
    # Define a few reliable Ken Burns effects for 1080x1920
    effects = [
        "z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'", # Slow center zoom in
        "z='min(zoom+0.002,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",  # Faster center zoom in
        "z='min(zoom+0.001,1.5)':x='iw/2-(iw/zoom/2)':y='ih/3-(ih/zoom/3)'",  # Zoom in towards top
        "z='if(eq(on,1),1.2,zoom-0.0015)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" # Slow center zoom out
    ]
    
    for i, seg in enumerate(image_segments):
        duration = seg["end"] - seg["start"]
        frames = int(duration * 30) # 30 fps
        
        inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(seg["path"])])
        
        # Pick a random effect to keep visuals dynamic
        effect = random.choice(effects)
        
        # Ensure correct resolution to avoid zoompan issues
        chain = f"[{i}:v]scale=1080:1920,zoompan={effect}:d={frames}:s=1080x1920:fps=30[v{i}]"
        filter_chains.append(chain)
        
    # Concat all video streams
    # Using direct concat for snappy fast cuts (2-3s per scene)
    concat_inputs = "".join([f"[v{i}]" for i in range(len(image_segments))])
    concat_filter = f"{concat_inputs}concat=n={len(image_segments)}:v=1:a=0[vconcat]"
    filter_chains.append(concat_filter)
    
    # Add subtitles
    safe_sub_path = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
    sub_filter = f"[vconcat]ass='{safe_sub_path}'[vout]"
    filter_chains.append(sub_filter)
    
    full_filtergraph = ";".join(filter_chains)
    
    cmd = [
        config.ffmpeg_path,
        "-y"
    ]
    
    cmd.extend(inputs)
    cmd.extend([
        "-i", str(audio_path),
        "-filter_complex", full_filtergraph,
        "-map", "[vout]",
        "-map", f"{len(image_segments)}:a", # The audio file is the last input
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-shortest",
        str(out_path)
    ])
    
    logger.debug(f"FFmpeg command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"Successfully generated final video: {out_path}")
        return str(out_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed with error:\n{e.stderr}")
        raise RuntimeError("Video generation failed") from e


def _sanitize_ffmpeg_text(text: str) -> str:
    """
    BUG 4 FIX: Sanitize text for FFmpeg drawtext filter.
    Removes HTML, special chars, limits length.
    """
    if not text:
        return "TECH NEWS"
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Remove characters that break FFmpeg filter parsing
    clean = re.sub(r"[':;\\{}()\[\]<>\"#@&]", '', clean)
    # Limit to 5 words
    words = clean.split()[:5]
    result = ' '.join(words).strip()
    # Escape remaining special chars for FFmpeg
    result = result.replace("'", "\\'")
    return result if len(result) > 2 else "TECH NEWS"


def generate_thumbnail(
    image_path: str,
    thumbnail_text: str,
    config: Config,
    date_str: str
) -> str:
    """
    Generate a high-CTR YouTube thumbnail using FFmpeg to overlay the 5-word thumbnail_text.
    """
    logger.info("Generating YouTube Thumbnail...")
    out_path = config.images_dir / f"{date_str}_thumbnail.jpg"
    
    # ======================================================================
    # BUG 4 FIX: Sanitize thumbnail text before FFmpeg
    # ======================================================================
    safe_text = _sanitize_ffmpeg_text(thumbnail_text)
    logger.info(f"Thumbnail text (sanitized): '{safe_text}'")
    
    text_filter = (
        f"drawtext=text='{safe_text}':font='Impact':fontsize=140:fontcolor=white:"
        "x=(w-text_w)/2:y=h-text_h-100:"
        "borderw=8:bordercolor=black:shadowcolor=black:shadowx=5:shadowy=5"
    )
    
    cmd = [
        config.ffmpeg_path,
        "-y",
        "-i", str(image_path),
        "-vf", text_filter,
        str(out_path)
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"Successfully generated thumbnail: {out_path}")
        return str(out_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"Thumbnail generation failed: {e.stderr}")
        # Return base image if text burning fails
        return str(image_path)
