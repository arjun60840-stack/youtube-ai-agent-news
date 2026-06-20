"""
Script Writer Module for AI Daily News YouTube Agent.

Generates a professional YouTube news script, title, description, tags,
and hashtags by prompting a local Llama 3 model via the Ollama Python
client.  Includes retry logic with exponential back-off and a regex
fallback for JSON extraction when the LLM wraps its response in
markdown code fences.

Pipeline:
    1. Build a detailed system + user prompt from the collected news
       stories.
    2. Call the Ollama chat API (up to 3 attempts).
    3. Parse the structured JSON response.
    4. Persist the result to ``config.scripts_dir / {date_str}.json``.

Usage:
    from src.config import load_config
    from src.news_collector import collect_news
    from src.script_writer import generate_script

    config = load_config()
    stories = collect_news(config, "2026-06-01")
    script_data = generate_script(stories, config, "2026-06-01")
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import ollama  # type: ignore[import-untyped]

from src.config import Config
from src.logger import get_logger
from src.news_collector import NewsStory
from src.memory import load_memory

# Module-level logger
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Retry configuration
_MAX_RETRIES: int = 3
_BACKOFF_SECONDS: List[int] = [2, 4, 8]  # exponential back-off schedule


# ======================================================================
# Data model
# ======================================================================

@dataclass
class ScriptData:
    """
    Container for all artefacts produced by the script-generation step.

    Attributes:
        script:      The narration script text (150-225 words,
                     ~60-90 seconds when read aloud).
        title:       Catchy YouTube video title (≤ 100 characters).
        description: YouTube video description with story links.
        tags:        10-15 SEO keyword tags.
        hashtags:    3-5 hashtags for social sharing.
    """

    script: str
    description: str
    titles: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)
    hook: str = field(default="")
    storyboard: str = field(default="")
    voiceover_script: str = field(default="")
    editing_instructions: str = field(default="")
    subtitle_file_instruction: str = field(default="")
    thumbnail_prompt: str = field(default="")
    seo_package: str = field(default="")
    final_production_checklist: str = field(default="")
    thumbnail_text: str = field(default="")
    pinned_comment: str = field(default="")


# ======================================================================
# Prompt construction
# ======================================================================

def _build_system_prompt() -> str:
    """
    Return the system-level instruction for the LLM.

    The prompt instructs the model to act as a professional YouTube
    news scriptwriter and to return a strictly valid JSON object.
    """
    prompt = (
        "You are an expert AI Video Production Agent.\n"
        "Your job is to create highly engaging, professional-quality videos optimized for YouTube, Instagram Reels, TikTok, and Facebook.\n\n"
        "For every topic, follow these steps in your mind:\n"
        "STEP 1: Research - Collect accurate information and find trending angles.\n"
        "STEP 2: Script Writing - Create a strong hook in the first 5 seconds, use simple language, include curiosity gaps, end with a clear CTA, and format scene-by-scene.\n"
        "STEP 3: Storyboard - Plan Scene Number, Duration, Visuals, Camera, Text, Sound, Transitions.\n"
        "STEP 4: AI Voiceover - Write a voiceover script matching tone to topic.\n"
        "STEP 5: Video Editing - Plan cuts, transitions, zoom effects, motion graphics, and B-roll.\n"
        "STEP 6: Subtitles - Plan subtitle highlights and syncing.\n"
        "STEP 7: Visual Design - Plan colors, icons, and animations.\n"
        "STEP 8: Audio Enhancement - Plan background music and balancing.\n"
        "STEP 9: Thumbnail Creation - Create text, concept, and an image generation prompt.\n"
        "STEP 10: SEO Optimization - Generate title, description, tags, hashtags, chapters.\n"
        "STEP 11: Quality Check - Check grammar, factual accuracy, pacing, and engagement.\n\n"
        "IMPORTANT RULES:\n"
        "1. The actual 'script' field MUST be an energetic YouTube Shorts script (STRICTLY under 110 words) in **Hinglish** (e.g. 'Dosto, aaj ki news...').\n"
        "2. Keep the text on the screen (title, description, storyboard) in pure English.\n\n"
    )

    # Inject learned memory guidelines if any exist
    rules = load_memory()
    if rules:
        prompt += "CRITICAL LEARNED GUIDELINES (YOU MUST FOLLOW THESE AT ALL COSTS):\n"
        for i, rule in enumerate(rules, 1):
            prompt += f"{i}. {rule}\n"
        prompt += "\n"

    prompt += (
        "OUTPUT FORMAT — respond with **only** a valid JSON object "
        "(no markdown, no commentary) containing exactly these keys:\n"
        '  "title"                      — Video Title\n'
        '  "hook"                       — The Hook\n'
        '  "script"                     — The Full Script (in Hinglish, under 110 words)\n'
        '  "storyboard"                 — The detailed storyboard\n'
        '  "voiceover_script"           — The Voiceover Script notes\n'
        '  "editing_instructions"       — Video Editing instructions\n'
        '  "subtitle_file_instruction"  — Subtitle instructions\n'
        '  "thumbnail_prompt"           — Thumbnail Prompt\n'
        '  "seo_package"                — SEO Package summary\n'
        '  "final_production_checklist" — Final Production Checklist\n'
        '  "description"                — YouTube Description\n'
        '  "tags"                       — Array of SEO tags\n'
        '  "hashtags"                   — Array of hashtags\n'
    )
    return prompt


def _build_user_prompt(
    stories: List[NewsStory],
    date_str: str,
) -> str:
    """
    Build the user-turn prompt that presents the day's news stories
    to the LLM.

    Args:
        stories:  List of ``NewsStory`` instances collected today.
        date_str: Human-readable date (e.g. ``"2026-06-01"``).

    Returns:
        str: Formatted prompt string.
    """
    stories_text: str = ""
    for idx, story in enumerate(stories, start=1):
        stories_text += (
            f"\n--- Story {idx} ---\n"
            f"Title: {story.title}\n"
            f"Source: {story.source}\n"
            f"Summary: {story.summary}\n"
            f"Link: {story.link}\n"
            f"Published: {story.published}\n"
        )

    return (
        f"Today's date is {date_str}.\n\n"
        f"Here are today's top AI and technology news stories:\n"
        f"{stories_text}\n\n"
        "Using the stories above, generate the YouTube script, title, "
        "description, tags, and hashtags as specified. Remember to output "
        "ONLY valid JSON."
    )


# ======================================================================
# Response parsing
# ======================================================================

def _clean_json_response(raw: str) -> str:
    """
    Strip markdown code fences (````json … ````) that LLMs often wrap
    around JSON output.

    Args:
        raw: Raw text response from the LLM.

    Returns:
        str: Cleaned string that should be parseable as JSON.
    """
    cleaned: str = raw.strip()

    # Remove opening ```json or ``` fence
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)

    # Remove closing ``` fence
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    return cleaned.strip()


def _extract_json_block(raw: str) -> Optional[str]:
    """
    Attempt to locate a JSON object within the raw response using a
    brace-matching heuristic.

    Args:
        raw: Raw LLM response text.

    Returns:
        Optional[str]: The extracted JSON substring, or ``None`` if no
                       balanced braces are found.
    """
    start: int = raw.find("{")
    if start == -1:
        return None

    depth: int = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]

    return None


def _regex_fallback(raw: str) -> Dict[str, Any]:
    """
    Last-resort extraction: use regex to pull individual fields from a
    malformed LLM response.

    This is invoked only when normal JSON parsing and brace-matching
    both fail.

    Args:
        raw: Raw LLM response text.

    Returns:
        Dict[str, Any]: Best-effort dictionary with extracted fields.

    Raises:
        ValueError: If the script field cannot be extracted at all.
    """
    logger.warning("Falling back to regex extraction from LLM response")

    result: Dict[str, Any] = {
        "script": "",
        "title": "",
        "description": "",
        "tags": [],
        "hashtags": [],
    }

    # --- script --------------------------------------------------------
    script_match = re.search(
        r'"script"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL
    )
    if script_match:
        result["script"] = script_match.group(1).replace('\\"', '"')
    else:
        raise ValueError(
            "Could not extract 'script' field from LLM response "
            "even with regex fallback."
        )

    # --- title ---------------------------------------------------------
    title_match = re.search(
        r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', raw
    )
    if title_match:
        result["title"] = title_match.group(1).replace('\\"', '"')

    # --- description ---------------------------------------------------
    desc_match = re.search(
        r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL
    )
    if desc_match:
        result["description"] = desc_match.group(1).replace('\\"', '"')

    # --- tags (try to find a JSON array) -------------------------------
    tags_match = re.search(r'"tags"\s*:\s*(\[[^\]]*\])', raw)
    if tags_match:
        try:
            result["tags"] = json.loads(tags_match.group(1))
        except json.JSONDecodeError:
            result["tags"] = []

    # --- hashtags ------------------------------------------------------
    hashtags_match = re.search(r'"hashtags"\s*:\s*(\[[^\]]*\])', raw)
    if hashtags_match:
        try:
            result["hashtags"] = json.loads(hashtags_match.group(1))
        except json.JSONDecodeError:
            result["hashtags"] = []

    return result


def _parse_response(raw: str) -> ScriptData:
    """
    Parse the LLM's raw text response into a ``ScriptData`` instance.

    Parsing strategy (in order):
        1. Strip markdown fences → ``json.loads``.
        2. Brace-match extraction → ``json.loads``.
        3. Regex field-by-field extraction.

    Args:
        raw: Raw text response from the Ollama chat API.

    Returns:
        ScriptData: Validated and populated dataclass.

    Raises:
        ValueError: If all parsing strategies fail.
    """
    # --- Attempt 1: clean & parse directly ----------------------------
    cleaned: str = _clean_json_response(raw)
    try:
        data: Dict[str, Any] = json.loads(cleaned)
        logger.debug("JSON parsed successfully on first attempt")
        return ScriptData(
            script=data.get("script", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            hashtags=data.get("hashtags", []),
            hook=data.get("hook", ""),
            storyboard=data.get("storyboard", ""),
            voiceover_script=data.get("voiceover_script", ""),
            editing_instructions=data.get("editing_instructions", ""),
            subtitle_file_instruction=data.get("subtitle_file_instruction", ""),
            thumbnail_prompt=data.get("thumbnail_prompt", ""),
            seo_package=data.get("seo_package", ""),
            final_production_checklist=data.get("final_production_checklist", ""),
        )
    except json.JSONDecodeError:
        logger.debug("Direct JSON parse failed; trying brace extraction")

    # --- Attempt 2: brace-matching extraction -------------------------
    json_block: Optional[str] = _extract_json_block(raw)
    if json_block:
        try:
            data = json.loads(json_block)
            logger.debug("JSON parsed via brace extraction")
            return ScriptData(
                script=data.get("script", ""),
                title=data.get("title", ""),
                description=data.get("description", ""),
                tags=data.get("tags", []),
                hashtags=data.get("hashtags", []),
                hook=data.get("hook", ""),
                storyboard=data.get("storyboard", ""),
                voiceover_script=data.get("voiceover_script", ""),
                editing_instructions=data.get("editing_instructions", ""),
                subtitle_file_instruction=data.get("subtitle_file_instruction", ""),
                thumbnail_prompt=data.get("thumbnail_prompt", ""),
                seo_package=data.get("seo_package", ""),
                final_production_checklist=data.get("final_production_checklist", ""),
            )
        except json.JSONDecodeError:
            logger.debug("Brace-extracted block is not valid JSON")

    # --- Attempt 3: regex fallback ------------------------------------
    data = _regex_fallback(raw)
    return ScriptData(
        script=data.get("script", ""),
        title=data.get("title", ""),
        description=data.get("description", ""),
        tags=data.get("tags", []),
        hashtags=data.get("hashtags", []),
        hook=data.get("hook", ""),
        storyboard=data.get("storyboard", ""),
        voiceover_script=data.get("voiceover_script", ""),
        editing_instructions=data.get("editing_instructions", ""),
        subtitle_file_instruction=data.get("subtitle_file_instruction", ""),
        thumbnail_prompt=data.get("thumbnail_prompt", ""),
        seo_package=data.get("seo_package", ""),
        final_production_checklist=data.get("final_production_checklist", ""),
    )


# ======================================================================
# Public API
# ======================================================================

def generate_script(
    news_stories: List[NewsStory],
    config: Config,
    date_str: str,
) -> ScriptData:
    """
    Generate a YouTube news script from today's collected stories.

    Calls the Ollama chat API with a carefully crafted prompt and
    parses the structured JSON response.  Retries up to 3 times with
    exponential back-off on transient failures.

    Args:
        news_stories: List of ``NewsStory`` instances to base the
                      script on (typically 5 stories).
        config:       Application configuration (provides Ollama
                      connection details and output paths).
        date_str:     ISO-format date string for file naming and
                      prompt context.

    Returns:
        ScriptData: Generated script, title, description, tags, and
                    hashtags.

    Raises:
        RuntimeError: If script generation fails after all retries.
    """
    logger.info("Generating script for %s using %s", date_str, config.ollama_model)

    # Build prompts ----------------------------------------------------
    system_prompt: str = _build_system_prompt()
    user_prompt: str = _build_user_prompt(news_stories, date_str)

    # Create the Ollama client -----------------------------------------
    client: ollama.Client = ollama.Client(host=config.ollama_base_url)

    last_error: Optional[Exception] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.info("Ollama API call — attempt %d/%d", attempt, _MAX_RETRIES)

        try:
            # ----- Call the LLM ----------------------------------------
            response = client.chat(
                model=config.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            # Extract the assistant's reply text -----------------------
            raw_content: str = response["message"]["content"]
            logger.debug(
                "Received %d chars from Ollama", len(raw_content)
            )

            # ----- Parse into ScriptData ------------------------------
            script_data: ScriptData = _parse_response(raw_content)

            # Quick sanity check — the script should not be empty
            if not script_data.script.strip():
                raise ValueError("LLM returned an empty 'script' field")

            logger.info(
                "Script generated — title: '%s' (%d words)",
                script_data.title[:80],
                len(script_data.script.split()),
            )

            # ----- Persist to JSON ------------------------------------
            _save_script(script_data, config, date_str)

            return script_data

        except Exception as exc:
            last_error = exc
            logger.warning(
                "Attempt %d failed: %s", attempt, exc
            )

            if attempt < _MAX_RETRIES:
                wait: int = _BACKOFF_SECONDS[attempt - 1]
                logger.info("Retrying in %d seconds …", wait)
                time.sleep(wait)

    # All retries exhausted --------------------------------------------
    msg: str = (
        f"Script generation failed after {_MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
    logger.error(msg)
    raise RuntimeError(msg)


# ======================================================================
# Internal helpers
# ======================================================================

def _save_script(
    script_data: ScriptData,
    config: Config,
    date_str: str,
) -> None:
    """
    Serialise ``script_data`` to a JSON file in the scripts directory.

    Args:
        script_data: The generated script artefacts.
        config:      Application configuration.
        date_str:    Date string for file naming.
    """
    output_path: Path = config.scripts_dir / f"{date_str}.json"

    try:
        output_path.write_text(
            json.dumps(asdict(script_data), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Saved script to %s", output_path)
    except OSError as exc:
        logger.error("Failed to write script JSON: %s", exc)
        raise
