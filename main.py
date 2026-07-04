"""
AI Daily News YouTube Agent V2 — Main Entry Point

Orchestrates the automated Hindi Tech News pipeline:
    1. Collect trending tech news from Google News RSS (1 Story)
    2. Generate script scenes via Ollama
    3. Synthesise narration audio via Sarvam AI
    4. Generate branded images via ComfyUI (validated with moondream)
    5. Assemble video and ASS subtitles via FFmpeg
    6. Upload to YouTube
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT: Path = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import Config, load_config
from src.logger import get_logger, setup_logging
from src.news_collector import collect_news, NewsStory
from src.script_writer_v2 import generate_script_v2, pick_best_story, ScriptDataV2
from src.voice_generator_v2 import generate_voice_v2, SceneAudioResult
from src.image_generator_v2 import generate_scene_images_v2, generate_thumbnail_v2
from src.video_generator_v2 import generate_video_v2
from src.quality_reviewer_v2 import review_video_v2
from src.youtube_uploader import upload_video

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai_news_agent",
        description="AI Daily News YouTube Agent V2"
    )
    parser.add_argument("--skip-upload", action="store_true", default=False)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--portrait", action="store_true", help="Generate a vertical YouTube Short (9:16)")
    parser.add_argument("--channel", type=str, default="tech_news", help="Which channel configuration to run")
    parser.add_argument("--schedule", action="store_true", help="Setup daily scheduled tasks")
    parser.add_argument("--unschedule", action="store_true", help="Remove scheduled tasks")
    parser.add_argument("--check-schedule", action="store_true", help="Check if scheduled tasks exist")
    return parser

def run_pipeline(config: Config, date_str: str, skip_upload: bool = False) -> None:
    logger = get_logger("pipeline")
    logger.info("=" * 60)
    logger.info(f"  AI DAILY NEWS YOUTUBE AGENT V2 - {config.channel_name}")
    logger.info("  Date: %s", date_str)
    logger.info("=" * 60)

    # 1. News Collection
    logger.info("STEP 1/6 — Collecting News")
    stories = collect_news(config, date_str)
    if not stories:
        logger.critical("No news found. Aborting.")
        return
    story = pick_best_story(stories, config)
    logger.info(f"Selected Story: {story.title}")

    # 2. Script Generation
    logger.info("STEP 2/6 — Generating Script V2")
    script_data = generate_script_v2(story, config, date_str)
    
    # 3. Voice Generation
    logger.info("STEP 3/6 — Generating Voice (Sarvam AI)")
    audio_results = generate_voice_v2(script_data, config, date_str)
    
    # 4. Image Generation
    logger.info("STEP 4/6 — Generating Images (ComfyUI)")
    image_paths = generate_scene_images_v2(script_data, config, date_str)
    thumbnail_path = generate_thumbnail_v2(script_data, config, date_str)

    # 5. Quality Review
    logger.info("STEP 5/6 — Quality Review")
    review = review_video_v2(script_data, audio_results, image_paths, config)
    if not review.passed:
        logger.critical(f"Quality Review failed: {review.feedback}")
        return

    # 6. Video Assembly
    logger.info("STEP 6/6 — Assembling Video (FFmpeg)")
    video_path = generate_video_v2(image_paths, audio_results, script_data, config, date_str)

    # 7. YouTube Upload
    if skip_upload:
        logger.info("Upload skipped via --skip-upload.")
    else:
        logger.info("STEP 7/7 — Uploading to YouTube")
        full_description = f"{config.channel_name} Today! 🇮🇳\n\n{script_data.description}"
        if script_data.hashtags:
            full_description += "\n\n" + " ".join(script_data.hashtags)
            
        # Add hashtags to title (YouTube limit is 100 characters)
        title_with_tags = script_data.title
        if script_data.hashtags:
            for tag in script_data.hashtags[:3]:
                # Add tag if it fits within the 100 character limit
                if len(title_with_tags) + len(tag) + 1 <= 95: 
                    title_with_tags += f" {tag}"
                    
        result = upload_video(
            video_path=video_path,
            title=title_with_tags,
            description=full_description,
            tags=script_data.tags,
            config=config,
            date_str=date_str,
            thumbnail_path=thumbnail_path,
        )
        if result:
            logger.info(f"Upload successful: {result.get('url')}")
        else:
            logger.warning("Upload failed or missing credentials.")

def main():
    parser = _build_parser()
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    config = load_config(args.channel)
    if args.portrait:
        config.video_format = "portrait"
        
    setup_logging(config.logs_dir, date_str)
    
    logger = get_logger("main")
    
    if args.schedule:
        from src.scheduler import setup_schedule
        setup_schedule(config)
        return
        
    if args.unschedule:
        from src.scheduler import remove_schedule
        remove_schedule()
        return
        
    if args.check_schedule:
        from src.scheduler import check_schedule
        check_schedule()
        return

    try:
        run_pipeline(config, date_str, args.skip_upload)
    except Exception as e:
        logger.critical("Pipeline crashed!", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
