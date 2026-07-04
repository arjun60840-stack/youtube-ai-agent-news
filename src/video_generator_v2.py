import os
import random
import logging
import subprocess
from pathlib import Path
from typing import List

from src.config import Config
from src.script_writer_v2 import ScriptDataV2
from src.voice_generator_v2 import SceneAudioResult

logger = logging.getLogger(__name__)

def _generate_ass_subtitles(script_data: ScriptDataV2, audio_results: List[SceneAudioResult], save_path: Path, config: Config):
    """Generate an ASS subtitle file from the V2 script scenes and precise audio durations."""
    
    is_portrait = getattr(config, "video_format", "landscape") == "portrait"
    play_res_x = 720 if is_portrait else 1280
    play_res_y = 1280 if is_portrait else 720
    font_size = 42 if is_portrait else 54
    margin_v = 150 if is_portrait else 50
    
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def format_ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds % 1) * 100))
        if cs == 100:
            cs = 99
        return f"{h:01d}:{m:02d}:{s:02d}.{cs:02d}"

    lines = [ass_header]
    current_time = 0.0
    
    for scene, audio in zip(script_data.scenes, audio_results):
        start_time_str = format_ass_time(current_time)
        current_time += audio.duration
        end_time_str = format_ass_time(current_time)
        
        text = scene.subtitle.replace('\n', ' ').strip()
        lines.append(f"Dialogue: 0,{start_time_str},{end_time_str},Default,,0,0,0,,{text}\n")
        
    with open(save_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    logger.info(f"Generated ASS subtitle file: {save_path}")

def generate_video_v2(
    image_paths: List[str],
    audio_results: List[SceneAudioResult],
    script_data: ScriptDataV2,
    config: Config,
    date_str: str
) -> str:
    """
    Assemble the final video using FFmpeg.
    Applies dynamic pan/zoom to images, concatenates audio, and burns ASS subtitles.
    """
    if len(image_paths) != len(audio_results):
        raise ValueError(f"Mismatch: {len(image_paths)} images but {len(audio_results)} audio files.")
        
    videos_dir = config.videos_dir
    videos_dir.mkdir(parents=True, exist_ok=True)
    
    out_video = videos_dir / f"{date_str}_final_video.mp4"
    ass_path = videos_dir / f"{date_str}.ass"
    
    _generate_ass_subtitles(script_data, audio_results, ass_path, config)
    
    ffmpeg_cmd = [config.ffmpeg_path, "-y"]
    
    # 1. Add all inputs
    for img in image_paths:
        ffmpeg_cmd.extend(["-loop", "1", "-i", str(img)])
    for aud in audio_results:
        ffmpeg_cmd.extend(["-i", aud.audio_path])
        
    # 2. Build filter_complex
    filter_complex = []
    video_streams = []
    audio_streams = []
    
    # We have N images and N audio files
    for i in range(len(image_paths)):
        duration = audio_results[i].duration
        
        # Pan & Zoom effects
        zoom_speed = random.uniform(0.0005, 0.0015)
        zoom_in = random.choice([True, False])
        
        if zoom_in:
            z_expr = f"min(zoom+{zoom_speed:.5f},1.5)"
        else:
            z_expr = f"max(1.5-{zoom_speed:.5f}*time,1.0)"
            
        pan_x = random.choice(["x", "iw/2-(iw/zoom/2)", "(iw-iw/zoom)/2"])
        pan_y = random.choice(["y", "ih/2-(ih/zoom/2)", "(ih-ih/zoom)/2"])
        
        # Trim visual to exact audio duration + crossfade buffer (we won't crossfade for simplicity, just exact cut)
        scale_res = "720x1280" if getattr(config, "video_format", "landscape") == "portrait" else "1280x720"
        vf = f"[{i}:v]zoompan=z='{z_expr}':x='{pan_x}':y='{pan_y}':d=25*{duration}:s={scale_res},trim=duration={duration}[v{i}];"
        filter_complex.append(vf)
        video_streams.append(f"[v{i}]")
        
        # Audio is directly used
        audio_streams.append(f"[{i + len(image_paths)}:a]")
        
    # Concatenate video
    concat_v = f"{''.join(video_streams)}concat=n={len(image_paths)}:v=1:a=0[outv_raw];"
    filter_complex.append(concat_v)
    
    # Concatenate audio
    concat_a = f"{''.join(audio_streams)}concat=n={len(image_paths)}:v=0:a=1[outa];"
    filter_complex.append(concat_a)
    
    # Subtitles - ensure path is escaped for FFmpeg filter
    escaped_ass_path = str(ass_path).replace('\\', '\\\\').replace(':', '\\:')
    burn_subs = f"[outv_raw]ass='{escaped_ass_path}'[outv]"
    filter_complex.append(burn_subs)
    
    ffmpeg_cmd.extend(["-filter_complex", "".join(filter_complex)])
    ffmpeg_cmd.extend(["-map", "[outv]", "-map", "[outa]"])
    
    # Encoding settings
    ffmpeg_cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(out_video)
    ])
    
    logger.info("=" * 60)
    logger.info("FFMPEG VIDEO ASSEMBLY COMMAND")
    logger.info(" ".join(ffmpeg_cmd))
    logger.info("=" * 60)
    
    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        logger.info(f"Video generated successfully: {out_video}")
        return str(out_video)
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed!\nStdout: {e.stdout}\nStderr: {e.stderr}")
        raise RuntimeError("FFmpeg assembly failed.")
