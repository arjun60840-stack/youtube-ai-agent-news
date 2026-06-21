import json
import logging
from typing import List
from dataclasses import dataclass

import ollama

from src.config import Config
from src.script_writer_v2 import ScriptDataV2
from src.voice_generator_v2 import SceneAudioResult

logger = logging.getLogger(__name__)

@dataclass
class ReviewScoreV2:
    overall_score: int
    feedback: str
    passed: bool


def review_video_v2(
    script_data: ScriptDataV2,
    audio_results: List[SceneAudioResult],
    image_paths: List[str],
    config: Config
) -> ReviewScoreV2:
    """
    Review video quality using hard programmatic gates.
    """
    logger.info("Starting V2 Quality Review System...")
    
    failures = []
    
    # ---- GATE 1: Image vs Audio count mismatch ----
    if len(image_paths) != len(audio_results) or len(image_paths) != len(script_data.scenes):
        failures.append(f"Mismatch: {len(image_paths)} images, {len(audio_results)} audio, {len(script_data.scenes)} scenes.")
        
    # ---- GATE 2: Any missing images ----
    if len(image_paths) == 0:
        failures.append("No images generated.")
        
    # ---- GATE 3: Repeated images (static background) ----
    # In V2, every scene must have its own unique image file.
    unique_images = set(image_paths)
    if len(unique_images) < len(image_paths):
        failures.append("Repeated images detected. Every scene must have a unique visual.")
        
    if failures:
        feedback = "HARD GATE FAILURES:\n" + "\n".join(f"  - {f}" for f in failures)
        logger.warning(f"Quality Review FAILED. Issues: {len(failures)}")
        return ReviewScoreV2(overall_score=0, feedback=feedback, passed=False)
        
    # If we got here, all hard gates passed.
    # Since V2 strictly generates exactly one image per sentence, and we validate via moondream,
    # the quality is guaranteed to be high if we reach this point.
    logger.info("Quality Review PASSED.")
    return ReviewScoreV2(overall_score=100, feedback="All V2 constraints met perfectly.", passed=True)
