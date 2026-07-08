import os
import re
import json
import base64
import requests
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from src.config import Config
from src.logger import get_logger
from src.script_writer_v2 import ScriptDataV2

logger = get_logger(__name__)

@dataclass
    
class SceneAudioResult:
    scene_number: int
    audio_path: str
    duration: float

def _clean_text_for_tts(script_text: str) -> str:
    """Apply strict cleaning rules before passing text to TTS."""
    cleaned = script_text
    
    # Remove code blocks
    cleaned = re.sub(r'```.*?```', ' ', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'`[^`]+`', ' ', cleaned)
    
    # Remove HTML
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    cleaned = re.sub(r'&[a-zA-Z]+;', ' ', cleaned)
    cleaned = re.sub(r'&#\d+;', ' ', cleaned)
    
    # Remove URLs
    cleaned = re.sub(r'https?://\S+|www\.\S+', ' ', cleaned)
    
    # Remove special characters (# * @ [] () {} | ; : \ / etc)
    cleaned = re.sub(r'[*_@\[\](){}|#;:\\/`~^<>]', ' ', cleaned)
    
    # Strip random scene labels if they somehow slipped in
    cleaned = re.sub(r'(?i)scene\s*\d+[:\-]', ' ', cleaned)
    
    # Normalize spaces
    cleaned = re.sub(r'\s-\s', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned.strip()

def _call_sarvam_api(text: str, api_key: str) -> bytes:
    """Call Sarvam TTS API and return raw wav bytes."""
    url = "https://api.sarvam.ai/text-to-speech"
    
    # Voice Profile: Professional Indian tech news presenter
    # - Rahul: Energetic, confident male voice
    # - Pace 1.25: Slightly faster (~170-180 wpm) but clear delivery
    # - Temperature 0.7: Natural expressiveness, avoids monotone
    # - 48kHz: Studio-quality audio output
    payload = {
        "inputs": [text],
        "target_language_code": "hi-IN",
        "speaker": "rahul",
        "pace": 1.25,
        "speech_sample_rate": 48000,
        "enable_preprocessing": True,
        "model": "bulbul:v3",
        "temperature": 0.7
    }
    
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            break
        except requests.exceptions.ConnectionError as e:
            if attempt == max_retries - 1:
                raise e
            import time
            time.sleep(2)
            
    if response.status_code != 200:
        logger.error(f"Sarvam API failed: {response.text}")
        raise Exception(f"Sarvam API error: {response.status_code}")
        
    data = response.json()
    if "audios" not in data or not data["audios"]:
        raise Exception("Sarvam API returned no audio.")
        
    return base64.b64decode(data["audios"][0])

def _get_wav_duration(wav_path: str) -> float:
    """Get exact duration of a WAV file in seconds."""
    with wave.open(wav_path, 'rb') as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return frames / float(rate)

def generate_voice_v2(script_data: ScriptDataV2, config: Config, date_str: str) -> List[SceneAudioResult]:
    """
    Generate independent TTS audio files for EACH scene using Sarvam AI.
    Returns a list of scene audio results with exact durations.
    """
    audio_dir: Path = config.audio_dir / date_str
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("VOICE GENERATOR V2 — Starting Sarvam TTS for date '%s'", date_str)
    logger.info("=" * 60)
    
    if not config.sarvam_api_key:
        logger.warning("SARVAM_API_KEY is empty in config! Audio generation will fail.")
        
    results = []
    
    for scene in script_data.scenes:
        cleaned_text = _clean_text_for_tts(scene.narration)
        if not cleaned_text:
            continue
            
        audio_path = audio_dir / f"scene_{scene.scene_number:03d}.wav"
        
        # Simple local caching to save API calls during retries
        if audio_path.exists() and audio_path.stat().st_size > 0:
            duration = _get_wav_duration(str(audio_path))
            results.append(SceneAudioResult(
                scene_number=scene.scene_number,
                audio_path=str(audio_path),
                duration=duration
            ))
            logger.info(f"Using cached audio for scene {scene.scene_number} ({duration:.2f}s)")
            continue
            
        logger.info(f"Generating audio for scene {scene.scene_number}: {cleaned_text[:50]}...")
        
        try:
            audio_bytes = _call_sarvam_api(cleaned_text, config.sarvam_api_key)
            with open(audio_path, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            logger.error(f"Sarvam TTS Error on scene {scene.scene_number}: {e}")
            logger.info("Falling back to edge-tts...")
            import subprocess
            tmp_mp3 = str(audio_path).replace(".wav", ".mp3")
            cmd = [
                "python", "-m", "edge_tts",
                f"--voice={config.tts_voice}",
                f"--rate={config.tts_rate}",
                f"--pitch={config.tts_pitch}",
                f"--text={cleaned_text}",
                f"--write-media={tmp_mp3}"
            ]
            subprocess.run(cmd, check=True)
            ffmpeg_cmd = [
                config.ffmpeg_path,
                "-y", "-i", tmp_mp3,
                "-acodec", "pcm_s16le",
                "-ar", "48000",
                str(audio_path)
            ]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.remove(tmp_mp3)
                
        duration = _get_wav_duration(str(audio_path))
        results.append(SceneAudioResult(
            scene_number=scene.scene_number,
            audio_path=str(audio_path),
            duration=duration
        ))
        logger.info(f"Saved audio for scene {scene.scene_number} ({duration:.2f}s)")
            
    return results
