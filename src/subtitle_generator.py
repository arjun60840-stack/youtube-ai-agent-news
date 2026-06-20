import os
from pathlib import Path
from typing import Any, Dict, List

from src.config import Config
from src.logger import get_logger

logger = get_logger(__name__)

def _format_time(seconds: float) -> str:
    """Format seconds into ASS time format: H:MM:SS.cs"""
    h = int(seconds / 3600)
    m = int((seconds % 3600) / 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_dynamic_subtitles(word_timestamps: List[Dict[str, Any]], config: Config, date_str: str) -> str:
    """
    Generate dynamic, word-by-word highlighted ASS subtitles.
    (Alex Hormozi style - Yellow highlight on active word)
    """
    out_dir = config.videos_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ass_path = out_dir / f"{date_str}.ass"
    
    logger.info("Generating dynamic ASS subtitles with word highlighting")
    
    # ASS Header
    ass_content = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 1",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Impact,110,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,50,50,600,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    # Group words into chunks of max 4-5 words
    chunks = []
    current_chunk = []
    
    for wt in word_timestamps:
        current_chunk.append(wt)
        
        # End chunk if it gets too long, or at sentence end
        is_end = wt["word"].endswith('.') or wt["word"].endswith('!') or wt["word"].endswith('?') or wt["word"].endswith(',')
        if len(current_chunk) >= 5 or is_end:
            chunks.append(current_chunk)
            current_chunk = []
            
    if current_chunk:
        chunks.append(current_chunk)
        
    # Generate ASS dialogue lines
    for chunk in chunks:
        if not chunk: continue
        
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]
        
        # We need to duplicate the line for every single word, changing the highlight
        for i, active_wt in enumerate(chunk):
            active_start = active_wt["start"]
            # Active word ends when the next word starts (or chunk ends)
            active_end = chunk[i+1]["start"] if i + 1 < len(chunk) else chunk_end
            
            line_parts = []
            for j, wt in enumerate(chunk):
                word_text = wt["word"]
                if i == j:
                    # Highlight active word in Yellow (\c&H00FFFF&) and scale up slightly
                    line_parts.append(f"{{\\c&H00FFFF&\\fscx110\\fscy110}}{word_text}{{\\c&HFFFFFF&\\fscx100\\fscy100}}")
                else:
                    line_parts.append(word_text)
                    
            full_text = " ".join(line_parts)
            ass_content.append(f"Dialogue: 0,{_format_time(active_start)},{_format_time(active_end)},Default,,0,0,0,,{full_text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_content))
        
    logger.info(f"Dynamic subtitles saved to {ass_path}")
    return str(ass_path)
