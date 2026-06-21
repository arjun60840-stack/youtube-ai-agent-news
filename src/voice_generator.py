import os
import re
import json
import base64
import requests
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from src.config import Config
from src.logger import get_logger

logger = get_logger(__name__)

@dataclass
class VoiceResult:
    audio_path: str
    subtitle_path: str
    word_timestamps: List[Dict[str, Any]] = field(default_factory=list)

def _clean_text_for_tts(script_text: str) -> str:
    """
    Apply strict cleaning rules before passing text to TTS.
    BUG 5 FIX: Now also strips HTML tags, CSS, and img references.
    """
    cleaned = script_text
    
    # FIRST: Strip ALL HTML tags (this is the most critical fix)
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    
    # Remove HTML entities
    cleaned = re.sub(r'&[a-zA-Z]+;', ' ', cleaned)
    cleaned = re.sub(r'&#\d+;', ' ', cleaned)
    
    # Remove CSS inline styles
    cleaned = re.sub(r"style='[^']*'", ' ', cleaned)
    cleaned = re.sub(r'style="[^"]*"', ' ', cleaned)
    
    # Remove src/alt attributes
    cleaned = re.sub(r'(src|alt)\s*=\s*[\'"][^\'"]*[\'"]', ' ', cleaned)
    
    # Remove URLs
    cleaned = re.sub(r'https?://\S+|www\.\S+', '', cleaned)
    
    # Remove internal system words
    for word in ["Scene 1", "Scene 2", "Scene 3", "Scene 4", "Scene 5", "Scene 6", "Scene 7", "Scene 8", "Scene 9", "Scene 10", "Hook", "Visual", "Narration", "Voice", "Subtitle", "Text", "Audio", "Image Prompt"]:
        cleaned = re.compile(re.escape(word) + r'\s*[:\-]*', re.IGNORECASE).sub('', cleaned)
        
    # Remove all formatting symbols
    cleaned = re.sub(r'[*_@\[\](){}|#;:\n]', ' ', cleaned)
    
    # Remove isolated hyphens
    cleaned = re.sub(r'\s-\s', ' ', cleaned)
    
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned.strip()

def _call_sarvam_api(text: str, api_key: str) -> str:
    """Call Sarvam TTS API and return base64 audio."""
    url = "https://api.sarvam.ai/text-to-speech"
    
    payload = {
        "inputs": [text],
        "target_language_code": "hi-IN",
        "speaker": "amit",
        "pace": 1.1,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
        "model": "bulbul:v3"
    }
    
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key
    }
    
    logger.info("Sending request to Sarvam API...")
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code != 200:
        logger.error(f"Sarvam API failed: {response.text}")
        raise Exception(f"Sarvam API error: {response.status_code}")
        
    data = response.json()
    if "audios" not in data or not data["audios"]:
        raise Exception("Sarvam API returned no audio.")
        
    return data["audios"][0]

import wave

def _chunk_text(text: str, max_length: int = 450) -> List[str]:
    """Splits text into chunks under max_length, preferring sentence boundaries."""
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ""
    
    for s in sentences:
        if len(current_chunk) + len(s) < max_length:
            current_chunk += s + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(s) >= max_length:
                # Force split if single sentence exceeds limit
                import textwrap
                wrapped = textwrap.wrap(s, max_length)
                for w in wrapped[:-1]:
                    chunks.append(w)
                current_chunk = wrapped[-1] + " "
            else:
                current_chunk = s + " "
                
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks

def _concat_wavs(wav_paths: List[Path], output_path: Path):
    """Concatenates multiple WAV files into a single WAV file."""
    data = []
    for w in wav_paths:
        with wave.open(str(w), 'rb') as w_file:
            data.append([w_file.getparams(), w_file.readframes(w_file.getnframes())])
            
    if not data:
        return
        
    with wave.open(str(output_path), 'wb') as output:
        output.setparams(data[0][0])
        for i in range(len(data)):
            output.writeframes(data[i][1])

def generate_voice(script_text: str, config: Config, date_str: str) -> VoiceResult:
    """
    Generate TTS audio using Sarvam AI API.
    """
    if not script_text.strip():
        raise ValueError("Script text is empty.")

    audio_dir: Path = config.audio_dir
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path: Path = audio_dir / f"{date_str}.wav"
    srt_path: Path = audio_dir / f"{date_str}.srt"
    
    logger.info("=" * 60)
    logger.info("VOICE GENERATOR — Starting Sarvam TTS for date '%s'", date_str)
    logger.info("=" * 60)
    
    # NOTE: Caching by date_str alone is unsafe — the self-improvement loop in
    # main.py calls generate_voice() multiple times per date_str with DIFFERENT
    # script_data (attempts 1/3/5 each regenerate the script). A stale cache
    # here used to return word_timestamps=[], which let Whisper align the NEW
    # script text against OLD leftover audio downstream. That mismatch is the
    # root cause of "visuals don't match narration". Caching by date_str is
    # disabled. If you want caching, key it off a hash of script_text instead.
    cleaned_script = _clean_text_for_tts(script_text)
    
    if not config.sarvam_api_key:
        logger.warning("SARVAM_API_KEY is empty in config! Audio generation will fail.")
        
    try:
        chunks = _chunk_text(cleaned_script)
        logger.info(f"Script split into {len(chunks)} chunks to satisfy Sarvam API limits.")
        
        chunk_paths = []
        for i, chunk in enumerate(chunks):
            base64_audio = _call_sarvam_api(chunk, config.sarvam_api_key)
            audio_bytes = base64.b64decode(base64_audio)
            
            chunk_path = audio_dir / f"{date_str}_chunk_{i}.wav"
            with open(chunk_path, "wb") as f:
                f.write(audio_bytes)
            chunk_paths.append(chunk_path)
            
        logger.info(f"Concatenating {len(chunk_paths)} audio chunks...")
        _concat_wavs(chunk_paths, audio_path)
        
        # Cleanup chunks
        for cp in chunk_paths:
            if cp.exists():
                cp.unlink()
            
        logger.info(f"Sarvam TTS audio saved successfully to: {audio_path}")
        
        # Write empty SRT to trigger fallback in subtitle_generator.py
        srt_path.write_text("", encoding="utf-8")
        
        return VoiceResult(
            audio_path=str(audio_path),
            subtitle_path=str(srt_path),
            word_timestamps=[]
        )
    except Exception as e:
        logger.error(f"Sarvam TTS Error: {e}")
        raise e

