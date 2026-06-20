import whisper
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

def align_audio(audio_path: str, script_text: str = None) -> List[Dict[str, Any]]:
    """
    Extract exact word-level timestamps from an audio file using Whisper.
    If script_text is provided, proportionally aligns the original script words 
    to the Whisper timestamps to prevent cross-alphabet transcription (e.g. Urdu/Devanagari).
    Returns a list of dictionaries: [{'word': str, 'start': float, 'end': float}]
    """
    logger.info(f"Loading Whisper model for word alignment...")
    # Load base model. It is small enough to run on CPU quickly but accurate enough for alignment.
    model = whisper.load_model("base")
    
    logger.info(f"Transcribing and aligning audio: {audio_path}")
    # We set word_timestamps=True to get exactly what we need
    result = model.transcribe(audio_path, word_timestamps=True)
    
    word_timestamps = []
    
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            word_timestamps.append({
                "word": word_info["word"].strip(),
                "start": word_info["start"],
                "end": word_info["end"]
            })
            
    if script_text and word_timestamps:
        script_words = script_text.split()
        w_len = len(word_timestamps)
        s_len = len(script_words)
        
        aligned_words = []
        for i, s_word in enumerate(script_words):
            # Proportional mapping
            w_idx_start = int((i / s_len) * w_len)
            w_idx_end = int(((i + 1) / s_len) * w_len)
            
            w_idx_start = min(w_idx_start, w_len - 1)
            w_idx_end = min(max(w_idx_end, w_idx_start + 1), w_len)
            
            start = word_timestamps[w_idx_start]["start"]
            end = word_timestamps[w_idx_end - 1]["end"]
            
            aligned_words.append({
                "word": s_word,
                "start": start,
                "end": end
            })
        word_timestamps = aligned_words
        logger.info(f"Proportionally aligned {s_len} script words to {w_len} Whisper timestamps.")
            
    logger.info(f"Successfully aligned {len(word_timestamps)} words.")
    return word_timestamps

def split_into_scenes(word_timestamps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups words into scenes.
    Hook section (< 10s): 1-2 seconds per image (target ~1.5s)
    Body section (>= 10s): 2-3 seconds per image (target ~2.5s)
    Splits on punctuation if possible, otherwise hard cut when max duration is reached.
    """
    scenes = []
    current_scene = {"text": "", "start": 0.0, "end": 0.0, "words": []}
    
    for i, wt in enumerate(word_timestamps):
        if not current_scene["words"]:
            current_scene["start"] = wt["start"]
            
        current_scene["words"].append(wt)
        current_scene["text"] += wt["word"] + " "
        current_scene["end"] = wt["end"]
        
        duration = current_scene["end"] - current_scene["start"]
        is_hook = current_scene["start"] < 10.0
        
        target_duration = 1.0 if is_hook else 1.5
        max_duration = 1.5 if is_hook else 2.0
        
        is_end_of_sentence = wt["word"].endswith('.') or wt["word"].endswith('!') or wt["word"].endswith('?') or wt["word"].endswith(',')
        
        # Hard cut if max duration exceeded, or soft cut if target reached and end of sentence
        if (duration >= max_duration) or (duration >= target_duration and is_end_of_sentence):
            scenes.append(current_scene)
            current_scene = {"text": "", "start": 0.0, "end": 0.0, "words": []}
            
    if current_scene["words"]:
        scenes.append(current_scene)
        
    logger.info(f"Split audio into {len(scenes)} visual scenes. Expected: 15-30.")
    return scenes
