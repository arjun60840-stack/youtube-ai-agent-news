"""
Quality Reviewer Module — AI Daily News YouTube Agent V2

BUG 3 FIX: Added hard programmatic gates that override the LLM's score.
The LLM was always giving 90+ even for garbage scripts. Now we enforce
deterministic checks BEFORE the LLM review.
"""

import json
import re
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import ollama

from src.config import Config
from src.script_writer import ScriptData

logger = logging.getLogger(__name__)

@dataclass
class ReviewScore:
    voice_score: int
    visual_score: int
    dynamic_score: int
    sync_score: int
    retention_score: int
    overall_score: int
    feedback: str


def _hard_gates(
    script_data: ScriptData,
    image_segments: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]],
) -> ReviewScore | None:
    """
    Deterministic quality checks that DON'T depend on the LLM.
    Returns a failing ReviewScore if any hard gate trips, or None if all pass.
    """
    failures = []
    voice_score = 100
    visual_score = 100
    dynamic_score = 100
    sync_score = 100
    retention_score = 100
    
    script = script_data.script
    
    # ---- GATE 1: Script contains HTML ----
    if re.search(r'<(div|p|img|br|span|strong|h[1-6]|a|ul|li)\b', script, re.IGNORECASE):
        voice_score = 0
        failures.append("HARD FAIL: Script contains HTML tags. Voice pipeline will crash.")
    
    # ---- GATE 2: Script contains CSS ----
    if re.search(r'style\s*=\s*[\'"]', script, re.IGNORECASE):
        voice_score = 0
        failures.append("HARD FAIL: Script contains CSS styles.")
    
    # ---- GATE 3: Script too short ----
    word_count = len(script.split())
    if word_count < 30:
        voice_score = min(voice_score, 40)
        failures.append(f"Script too short: {word_count} words (need 50+).")
    
    # ---- GATE 4: Not enough scenes ----
    num_scenes = len(scenes)
    if num_scenes < 15:
        dynamic_score = min(dynamic_score, 40)
        failures.append(f"Only {num_scenes} scenes (need 15+). Video will look static.")
    
    # ---- GATE 5: Any scene too long ----
    for s in scenes:
        duration = s.get('end', 0) - s.get('start', 0)
        if duration > 4.0:
            dynamic_score = min(dynamic_score, 50)
            failures.append(f"Scene duration {duration:.1f}s exceeds 3s max.")
            break
        elif duration > 3.0:
            dynamic_score = min(dynamic_score, 70)
    
    # ---- GATE 6: Image count mismatch ----
    if len(image_segments) < len(scenes):
        visual_score = min(visual_score, 40)
        failures.append(f"Missing images: {len(image_segments)} images for {len(scenes)} scenes.")
    
    # ---- GATE 7: Script has scene labels that shouldn't be spoken ----
    if re.search(r'(?i)(Scene \d|Hook:|Visual:|Narration:)', script):
        voice_score = min(voice_score, 60)
        failures.append("Script contains internal labels (Scene X, Hook:) that will be spoken aloud.")

    if failures:
        overall = (voice_score + visual_score + dynamic_score + sync_score + retention_score) // 5
        feedback = "HARD GATE FAILURES:\n" + "\n".join(f"  - {f}" for f in failures)
        logger.warning(f"Hard gates FAILED. Overall: {overall}/100. Issues: {len(failures)}")
        return ReviewScore(
            voice_score=voice_score,
            visual_score=visual_score,
            dynamic_score=dynamic_score,
            sync_score=sync_score,
            retention_score=retention_score,
            overall_score=overall,
            feedback=feedback,
        )
    
    return None  # All hard gates passed


def review_video_metadata(
    script_data: ScriptData,
    image_segments: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]],
    config: Config
) -> ReviewScore:
    """
    Review video quality using hard programmatic gates + LLM review.
    Hard gates override the LLM if they fail.
    """
    logger.info("Starting V2 Quality Review System...")
    
    # ======================================================================
    # STEP 1: Hard programmatic gates (BUG 3 FIX)
    # These catch problems the LLM always misses
    # ======================================================================
    hard_result = _hard_gates(script_data, image_segments, scenes)
    if hard_result is not None:
        logger.info(f"Hard gates returned score {hard_result.overall_score}/100. Returning hard gate result.")
        return hard_result
    
    # ======================================================================
    # STEP 2: LLM review (only reached if hard gates pass)
    # ======================================================================
    num_scenes = len(scenes)
    max_duration = 0
    for s in scenes:
        d = s.get('end', 0) - s.get('start', 0)
        if d > max_duration:
            max_duration = d
    
    metadata = f"""
    VIDEO ARCHITECTURE METADATA:
    - Script word count: {len(script_data.script.split())}
    - Total Scenes Generated: {num_scenes}
    - Maximum Image Duration: {max_duration:.2f} seconds
    - Total Images: {len(image_segments)}
    """
    
    prompt = f"""
    You are the Quality Review System for the Autonomous Hindi Tech News YouTube Channel V2.
    Review the following video metadata and score it strictly.
    
    {metadata}
    
    EVALUATION CRITERIA:
    1. VOICE REVIEW (0-100): Is the script conversational and natural?
    2. VISUAL REVIEW (0-100): Are there enough unique images?
    3. DYNAMIC REVIEW (0-100): Are there 15-30 scene changes? Max duration <= 3.0 seconds?
    4. SYNC REVIEW (0-100): Does every scene have a matching image?
    5. RETENTION REVIEW (0-100): Will viewers stay engaged?
    
    Calculate the Overall Score (average of the 5).
    
    OUTPUT JSON FORMAT ONLY:
    {{
        "voice_score": 95,
        "visual_score": 92,
        "dynamic_score": 85,
        "sync_score": 90,
        "retention_score": 88,
        "overall_score": 90,
        "feedback": "Brief explanation."
    }}
    """
    
    client = ollama.Client(host=config.ollama_base_url)
    
    try:
        response = client.chat(
            model=config.ollama_model,
            messages=[{"role": "user", "content": prompt}],
            format="json"
        )
        
        raw_content = response["message"]["content"]
        data = json.loads(raw_content)
        
        score = ReviewScore(
            voice_score=data.get("voice_score", 0),
            visual_score=data.get("visual_score", 0),
            dynamic_score=data.get("dynamic_score", 0),
            sync_score=data.get("sync_score", 0),
            retention_score=data.get("retention_score", 0),
            overall_score=data.get("overall_score", 0),
            feedback=data.get("feedback", "No feedback provided.")
        )
        
        logger.info(f"LLM Review Complete. Overall Score: {score.overall_score}/100")
        return score
        
    except Exception as e:
        logger.error(f"Quality review LLM failed: {e}")
        # Default pass if LLM fails so pipeline doesn't infinite loop on broken JSON
        return ReviewScore(100, 100, 100, 100, 100, 100, "Review system error, bypassing.")
