"""
AI Daily News YouTube Agent — Main Entry Point

Orchestrates the full automated pipeline:
    1. Collect trending tech news from Google News RSS
    2. Generate a professional YouTube script via Ollama (llama3:8b)
    3. Synthesise narration audio with edge-tts
    4. Generate branded image slides with Pillow
    5. Create styled subtitles (ASS format)
    6. Assemble final 1920×1080 MP4 video with FFmpeg
    7. Upload to YouTube via Data API v3

Usage:
    python main.py                  # Run the full pipeline
    python main.py --skip-upload    # Skip YouTube upload
    python main.py --schedule       # Set up Windows Task Scheduler (daily 7 AM)
    python main.py --date 2026-06-01  # Re-run for a specific date
    python main.py --unschedule     # Remove the scheduled task

Author: AI Daily News Agent
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so `src` package imports work
# when invoked directly (python main.py) from any working directory.
# ---------------------------------------------------------------------------
_PROJECT_ROOT: Path = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Local imports (deferred after path fix)
# ---------------------------------------------------------------------------
from src.config import Config, load_config
from src.logger import get_logger, setup_logging
from src.news_collector import NewsStory, collect_news
from src.crew_writer import generate_script_crew, ScriptData
from src.voice_generator import VoiceResult, generate_voice
from src.audio_aligner import align_audio, split_into_scenes
from src.subtitle_generator import generate_dynamic_subtitles
from src.image_generator import generate_scene_images
from src.video_generator import generate_video
from src.youtube_uploader import upload_video
from src.scheduler import setup_schedule, remove_schedule, check_schedule
from src.teacher import process_text, process_voice
from src.analytics_engine import run_learning_loop


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="ai_news_agent",
        description=(
            "AI Daily News YouTube Agent — Fully automated pipeline that "
            "collects tech news, writes scripts with AI, generates voice, "
            "creates videos, and uploads to YouTube."
        ),
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        default=False,
        help="Run the full pipeline but skip the YouTube upload step.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Override the pipeline date (YYYY-MM-DD format). "
            "Defaults to today's date."
        ),
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        default=False,
        help="Set up a Windows Task Scheduler job to run daily at 7:00 AM.",
    )
    parser.add_argument(
        "--unschedule",
        action="store_true",
        default=False,
        help="Remove the Windows Task Scheduler job.",
    )
    parser.add_argument(
        "--check-schedule",
        action="store_true",
        default=False,
        help="Check if the scheduled task exists.",
    )
    parser.add_argument(
        "--teach",
        type=str,
        default=None,
        help="Teach the AI a new rule via text (e.g., --teach \"Always say hello\").",
    )
    parser.add_argument(
        "--teach-voice",
        action="store_true",
        default=False,
        help="Teach the AI a new rule using your microphone.",
    )
    parser.add_argument(
        "--capcut-mode",
        action="store_true",
        default=False,
        help="Stop after generating assets (Audio, Images, Subs) so you can manually edit in CapCut.",
    )
    return parser


# ---------------------------------------------------------------------------
# Pipeline steps — each wrapped in its own error handler
# ---------------------------------------------------------------------------

def _step_collect_news(
    config: Config,
    date_str: str,
    logger: Any,
) -> List[NewsStory]:
    """Step 1: Collect trending tech news from RSS feeds."""
    logger.info("=" * 60)
    logger.info("STEP 1/7 — Collecting News")
    logger.info("=" * 60)

    stories: List[NewsStory] = collect_news(config, date_str)

    logger.info("Collected %d news stories:", len(stories))
    for i, story in enumerate(stories, 1):
        logger.info("  %d. %s (%s)", i, story.title[:80], story.source)

    return stories


def _step_generate_script(
    stories: List[NewsStory],
    config: Config,
    date_str: str,
    logger: Any,
) -> ScriptData:
    """Step 2: Generate YouTube script using Ollama LLM."""
    logger.info("=" * 60)
    logger.info("STEP 2/7 — Generating Script via CrewAI (%s)", config.ollama_model)
    logger.info("=" * 60)

    script_data: ScriptData = generate_script_crew(stories, config, date_str)

    logger.info("Script generated successfully:")
    logger.info("  Title:    %s", script_data.titles[0] if script_data.titles else "Untitled")
    logger.info("  Words:    ~%d", len(script_data.script.split()))
    logger.info("  Tags:     %d", len(script_data.tags))
    logger.info("  Hashtags: %s", ", ".join(script_data.hashtags))

    return script_data


def _step_generate_voice(
    script_text: str,
    config: Config,
    date_str: str,
    logger: Any,
) -> VoiceResult:
    """Step 3: Generate narration audio with edge-tts."""
    logger.info("=" * 60)
    logger.info("STEP 3/7 — Generating Voice Narration (%s)", config.tts_voice)
    logger.info("=" * 60)

    voice_result: VoiceResult = generate_voice(script_text, config, date_str)

    logger.info("Voice generated successfully:")
    logger.info("  Audio:     %s", voice_result.audio_path)
    logger.info("  Subtitles: %s", voice_result.subtitle_path)

    return voice_result


def _step_generate_slides(
    scenes: List[Dict[str, Any]],
    config: Config,
    date_str: str,
    logger: Any,
) -> List[Dict[str, Any]]:
    """Step 4: Generate dynamic scene images using LLM logic."""
    logger.info("=" * 60)
    logger.info("STEP 4/7 — Generating Scene Images")
    logger.info("=" * 60)

    image_segments: List[Dict[str, Any]] = generate_scene_images(scenes, config, date_str)

    logger.info("Generated %d dynamic image segments.", len(image_segments))

    return image_segments


def _step_generate_subtitles(
    word_timestamps: List[Dict[str, Any]],
    config: Config,
    date_str: str,
    logger: Any,
) -> str:
    """Step 5: Generate styled ASS subtitles for FFmpeg."""
    logger.info("=" * 60)
    logger.info("STEP 5/7 — Generating Subtitles")
    logger.info("=" * 60)

    ass_path: str = generate_dynamic_subtitles(word_timestamps, config, date_str)

    logger.info("Subtitles generated: %s", ass_path)

    return ass_path


def _step_generate_video(
    image_segments: List[Dict[str, Any]],
    audio_path: str,
    subtitle_path: str,
    config: Config,
    date_str: str,
    logger: Any,
) -> str:
    """Step 6: Assemble final MP4 video with FFmpeg."""
    logger.info("=" * 60)
    logger.info("STEP 6/7 — Assembling Video with FFmpeg")
    logger.info("=" * 60)

    video_path: str = generate_video(
        image_segments=image_segments,
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        config=config,
        date_str=date_str,
    )

    logger.info("Video assembled: %s", video_path)

    return video_path


def _step_upload_youtube(
    video_path: str,
    script_data: ScriptData,
    config: Config,
    date_str: str,
    logger: Any,
) -> Optional[Dict[str, Any]]:
    """Step 7: Upload video to YouTube."""
    logger.info("=" * 60)
    logger.info("STEP 7/7 — Uploading to YouTube")
    logger.info("=" * 60)

    # Verify assets before uploading (Quality Control Rule)
    if not Path(video_path).exists() or Path(video_path).stat().st_size == 0:
        logger.critical("ABORT UPLOAD: Final video asset is missing or empty.")
        return None
    if not script_data.titles or not script_data.description:
        logger.critical("ABORT UPLOAD: Metadata (Title/Description) is missing.")
        return None

    full_description = f"One New Technology at a Time, Building a Stronger India Together. 🇮🇳\n\n{script_data.description}"
    if script_data.hashtags:
        full_description += "\n\n" + " ".join(script_data.hashtags)

    result: Optional[Dict[str, Any]] = upload_video(
        video_path=video_path,
        title=script_data.titles[0],
        description=full_description,
        tags=script_data.tags,
        config=config,
        date_str=date_str,
    )

    if result:
        logger.info("Upload successful!")
        logger.info("  Video ID:  %s", result.get("video_id", "N/A"))
        logger.info("  URL:       %s", result.get("url", "N/A"))
        logger.info("  Status:    %s", result.get("status", "N/A"))
    else:
        logger.warning(
            "YouTube upload returned None — likely missing credentials. "
            "Video saved locally at: %s",
            video_path,
        )

    return result


def run_pipeline(
    config: Config,
    date_str: str,
    skip_upload: bool = False,
    capcut_mode: bool = False,
) -> None:
    """
    Execute the full AI Daily News pipeline with V2 Self Improvement Loop.
    """
    logger = get_logger("pipeline")

    logger.info("=" * 60)
    logger.info("  AI DAILY NEWS YOUTUBE AGENT V2")
    logger.info("  Date: %s", date_str)
    logger.info("  Channel: %s", config.channel_name)
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Step 0: Analytics & Self-Learning Loop
    # ------------------------------------------------------------------
    logger.info("STEP 0/7 — Running Analytics & Self-Learning Loop")
    try:
        run_learning_loop(config)
    except Exception as exc:
        logger.error("Learning loop failed (non-critical): %s", exc)
    logger.info("-" * 60)

    # ------------------------------------------------------------------
    # Step 1: Collect news (CRITICAL — cannot continue without news)
    # ------------------------------------------------------------------
    try:
        stories = _step_collect_news(config, date_str, logger)
    except Exception as exc:
        logger.critical("News collection failed — pipeline cannot continue: %s", exc)
        logger.debug(traceback.format_exc())
        raise SystemExit(1) from exc

    from src.quality_reviewer import review_video_metadata
    from src.video_generator import generate_thumbnail

    script_data = None
    voice_result = None
    word_timestamps = None
    scenes = None
    image_segments = None
    subtitle_path = None
    video_path = None

    for attempt in range(1, 6):
        logger.info("=" * 60)
        logger.info(f"SELF IMPROVEMENT LOOP: ATTEMPT {attempt}/5")
        logger.info("=" * 60)

        try:
            # Attempt strategies
            if attempt == 1 or attempt == 5:
                # Attempt 1: Generate / Attempt 5: Final Optimization
                if attempt == 5: logger.info("Final Optimization Attempt...")
                script_data = _step_generate_script(stories, config, f"{date_str}_v{attempt}", logger)
                voice_result = _step_generate_voice(script_data.script, config, f"{date_str}_v{attempt}", logger)
                word_timestamps = align_audio(voice_result.audio_path, script_data.script)
                scenes = split_into_scenes(word_timestamps)
                image_segments = _step_generate_slides(scenes, config, f"{date_str}_v{attempt}", logger)
            
            elif attempt == 2:
                # Attempt 2: Fix Visuals
                logger.info("Attempt 2: Fixing Visuals")
                image_segments = _step_generate_slides(scenes, config, f"{date_str}_v{attempt}", logger)
                
            elif attempt == 3:
                # Attempt 3: Fix Voice
                logger.info("Attempt 3: Fixing Voice")
                voice_result = _step_generate_voice(script_data.script, config, f"{date_str}_v{attempt}", logger)
                word_timestamps = align_audio(voice_result.audio_path, script_data.script)
                scenes = split_into_scenes(word_timestamps)
                image_segments = _step_generate_slides(scenes, config, f"{date_str}_v{attempt}", logger)
                
            elif attempt == 4:
                # Attempt 4: Fix Pacing
                logger.info("Attempt 4: Fixing Pacing")
                word_timestamps = align_audio(voice_result.audio_path, script_data.script)
                scenes = split_into_scenes(word_timestamps)
                image_segments = _step_generate_slides(scenes, config, f"{date_str}_v{attempt}", logger)

            if len(image_segments) < len(scenes):
                logger.error(f"Missing images. Generated {len(image_segments)} / {len(scenes)}.")
                continue

            # Quality Review
            score = review_video_metadata(script_data, image_segments, scenes, config)
            
            if score.overall_score >= 90:
                logger.info(f"Video passed Quality Review with score {score.overall_score}. Proceeding to render.")
                break
            else:
                logger.warning(f"Video failed Quality Review with score {score.overall_score}. Feedback: {score.feedback}")
                if attempt == 5:
                    logger.critical("Max attempts reached. Aborting pipeline to protect channel quality.")
                    raise SystemExit(1)
                continue

        except Exception as exc:
            logger.error(f"Error during attempt {attempt}: {exc}")
            if attempt == 5:
                raise SystemExit(1) from exc

    # ------------------------------------------------------------------
    # Step 5: Generate subtitles
    # ------------------------------------------------------------------
    try:
        subtitle_path = _step_generate_subtitles(word_timestamps, config, date_str, logger)
    except Exception as exc:
        logger.critical("Subtitle generation failed: %s", exc)
        raise SystemExit(1) from exc

    if capcut_mode:
        logger.info("=" * 60)
        logger.info("STEP 6/7 — Video Assembly SKIPPED (--capcut-mode active)")
        logger.info("  Audio: %s", voice_result.audio_path)
        return

    # ------------------------------------------------------------------
    # Step 6: Assemble video
    # ------------------------------------------------------------------
    try:
        video_path = _step_generate_video(image_segments, voice_result.audio_path, subtitle_path, config, date_str, logger)
    except Exception as exc:
        logger.critical("Video generation failed: %s", exc)
        raise SystemExit(1) from exc
        
    # Generate Thumbnail
    if image_segments and script_data.thumbnail_text:
        generate_thumbnail(image_segments[0]["path"], script_data.thumbnail_text, config, date_str)

    # ------------------------------------------------------------------
    # Step 7: Upload to YouTube (optional)
    # ------------------------------------------------------------------
    if skip_upload:
        logger.info("=" * 60)
        logger.info("STEP 7/7 — YouTube upload SKIPPED (--skip-upload flag)")
        logger.info("Video saved locally: %s", video_path)
    else:
        try:
            _step_upload_youtube(video_path, script_data, config, date_str, logger)
        except Exception as exc:
            logger.error("YouTube upload failed: %s", exc)

    logger.info("=" * 60)
    logger.info("  PIPELINE COMPLETE")
    logger.info("  Date:  %s", date_str)
    logger.info("  Video: %s", video_path)
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate action."""
    parser = _build_parser()
    args = parser.parse_args()

    # Load configuration
    config: Config = load_config()

    # Determine date string
    date_str: str = args.date or datetime.now().strftime("%Y-%m-%d")

    # Initialize logging
    setup_logging(config.logs_dir, date_str)
    logger = get_logger("main")

    # ------------------------------------------------------------------
    # Handle scheduling commands (no pipeline needed)
    # ------------------------------------------------------------------
    if args.schedule:
        logger.info("Setting up Windows Task Scheduler...")
        success = setup_schedule(config)
        if success:
            logger.info("Scheduled task created — will run daily at 7:00 AM.")
        else:
            logger.error("Failed to create scheduled task.")
        return

    if args.unschedule:
        logger.info("Removing Windows Task Scheduler job...")
        success = remove_schedule()
        if success:
            logger.info("Scheduled task removed.")
        else:
            logger.error("Failed to remove scheduled task.")
        return

    if args.check_schedule:
        exists = check_schedule()
        if exists:
            logger.info("Scheduled task 'AI_Daily_News_Agent' EXISTS.")
        else:
            logger.info("Scheduled task 'AI_Daily_News_Agent' does NOT exist.")
        return

    # ------------------------------------------------------------------
    # Handle teaching commands (no pipeline needed)
    # ------------------------------------------------------------------
    if args.teach:
        process_text(args.teach, config)
        return

    if args.teach_voice:
        process_voice(config)
        return

    # ------------------------------------------------------------------
    # Run the full pipeline
    # ------------------------------------------------------------------
    try:
        run_pipeline(
            config=config,
            date_str=date_str,
            skip_upload=args.skip_upload,
            capcut_mode=args.capcut_mode,
        )
    except SystemExit:
        raise  # Re-raise SystemExit from critical failures
    except Exception as exc:
        logger.critical("Unexpected pipeline error: %s", exc)
        logger.critical(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
