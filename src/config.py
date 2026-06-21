"""
Configuration Module for AI Daily News YouTube Agent.

This module provides centralized configuration management for the entire
application pipeline. It uses Python dataclasses for type-safe configuration
and loads environment variables from a .env file via python-dotenv.

Configuration covers:
    - Ollama LLM settings (model, base URL)
    - Text-to-Speech voice parameters (voice, rate, pitch)
    - YouTube upload settings (secrets, token, privacy, category)
    - Channel branding (name)
    - FFmpeg binary path
    - RSS feed URLs for news collection
    - Derived project directory paths (auto-created on init)

Usage:
    from src.config import load_config
    config = load_config()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Default RSS feed URLs — Google News technology & AI topic feeds
# ---------------------------------------------------------------------------
DEFAULT_RSS_FEEDS: List[str] = [
    # Google News "Technology" topic feed (English, US)
    (
        "https://news.google.com/rss/topics/"
        "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB"
        "?hl=en-US&gl=US&ceid=US:en"
    ),
    # Google News search: "artificial intelligence"
    (
        "https://news.google.com/rss/search"
        "?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en"
    ),
    # Google News search: "technology news"
    (
        "https://news.google.com/rss/search"
        "?q=technology+news&hl=en-US&gl=US&ceid=US:en"
    ),
]

# ---------------------------------------------------------------------------
# Allowed topics for Hindi Tech News
# ---------------------------------------------------------------------------
ALLOWED_TOPICS: List[str] = [
    "AI", "OpenAI", "ChatGPT", "Google", "Gemini", "Microsoft",
    "Apple", "Android", "iPhone", "NVIDIA", "Cybersecurity",
    "Technology Launches", "Software Updates"
]


@dataclass
class Config:
    """
    Application-wide configuration container.

    All fields have sensible defaults so the agent works out-of-the-box
    on a fresh clone. Override any value by setting the corresponding
    environment variable (see ``load_config``).

    Attributes:
        project_root:           Absolute path to the repository root.
        ollama_model:           Ollama model tag to use for script generation.
        ollama_base_url:        Base URL of the Ollama HTTP API.
        tts_voice:              Microsoft Edge TTS voice identifier.
        tts_rate:               TTS speaking-rate adjustment string.
        tts_pitch:              TTS pitch adjustment string.
        youtube_client_secrets: Relative path to the OAuth 2.0 client secrets
                                JSON file (relative to project_root).
        youtube_token_path:     Relative path to the cached OAuth token JSON.
        youtube_privacy:        Default privacy status for uploads
                                ('private', 'unlisted', or 'public').
        youtube_category:       YouTube video category ID.
                                28 = "Science & Technology".
        channel_name:           Display name used in branding / metadata.
        ffmpeg_path:            System path or alias for the FFmpeg binary.
        rss_feeds:              List of RSS/Atom feed URLs to scrape.

    Derived paths (set in ``__post_init__``):
        news_dir, scripts_dir, audio_dir, images_dir,
        videos_dir, logs_dir, config_dir
    """

    # ------------------------------------------------------------------
    # Core paths & LLM
    # ------------------------------------------------------------------
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
    )
    ollama_model: str = "qwen2.5"
    ollama_base_url: str = "http://localhost:11434"
    
    # ------------------------------------------------------------------
    # Sarvam AI TTS
    # ------------------------------------------------------------------
    sarvam_api_key: str = ""
    
    # ------------------------------------------------------------------
    # ComfyUI Image Generation
    # ------------------------------------------------------------------
    comfyui_base_url: str = "http://127.0.0.1:8188"

    # ------------------------------------------------------------------
    # Text-to-Speech
    # ------------------------------------------------------------------
    tts_voice: str = "en-US-GuyNeural"
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM" # Rachel default

    # ------------------------------------------------------------------
    # YouTube upload
    # ------------------------------------------------------------------
    youtube_client_secrets: str = "config/client_secrets.json"
    youtube_token_path: str = "config/youtube_token.json"
    youtube_privacy: str = "private"
    youtube_category: str = "28"  # Science & Technology

    # ------------------------------------------------------------------
    # Channel branding
    # ------------------------------------------------------------------
    channel_name: str = "AI Daily News"

    # ------------------------------------------------------------------
    # FFmpeg
    # ------------------------------------------------------------------
    ffmpeg_path: str = "ffmpeg"

    # ------------------------------------------------------------------
    # RSS feeds & Topics
    # ------------------------------------------------------------------
    rss_feeds: List[str] = field(default_factory=lambda: list(DEFAULT_RSS_FEEDS))
    allowed_topics: List[str] = field(default_factory=lambda: list(ALLOWED_TOPICS))

    # ------------------------------------------------------------------
    # Derived directory paths (populated in __post_init__)
    # ------------------------------------------------------------------
    news_dir: Path = field(init=False)
    scripts_dir: Path = field(init=False)
    audio_dir: Path = field(init=False)
    images_dir: Path = field(init=False)
    videos_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    config_dir: Path = field(init=False)

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        """
        Derive output directory paths from ``project_root`` and ensure
        every directory exists on disk.

        Directory layout under *project_root*::

            output/
            ├── news/        ← raw JSON scraped stories
            ├── scripts/     ← generated video scripts
            ├── audio/       ← TTS audio files
            ├── images/      ← generated thumbnail / frame images
            └── videos/      ← final rendered MP4 files
            logs/            ← daily rotating log files
            config/          ← OAuth secrets & tokens
        """
        # Build paths --------------------------------------------------
        self.news_dir = self.project_root / "news"
        self.scripts_dir = self.project_root / "scripts"
        self.audio_dir = self.project_root / "audio"
        self.images_dir = self.project_root / "images"
        self.videos_dir = self.project_root / "videos"
        self.logs_dir = self.project_root / "logs"
        self.config_dir = self.project_root / "config"

        # Create every directory (idempotent) --------------------------
        for directory in (
            self.news_dir,
            self.scripts_dir,
            self.audio_dir,
            self.images_dir,
            self.videos_dir,
            self.logs_dir,
            self.config_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


# ======================================================================
# Factory function
# ======================================================================

def load_config() -> Config:
    """
    Build a ``Config`` instance from environment variables.

    Reads a ``.env`` file located at the project root (if present) and
    then overrides dataclass defaults with any matching env vars.

    Environment variable mapping (all optional):
        OLLAMA_MODEL, OLLAMA_BASE_URL,
        TTS_VOICE, TTS_RATE, TTS_PITCH,
        YOUTUBE_CLIENT_SECRETS, YOUTUBE_TOKEN_PATH,
        YOUTUBE_PRIVACY, YOUTUBE_CATEGORY,
        CHANNEL_NAME, FFMPEG_PATH,
        RSS_FEEDS  (comma-separated list of URLs)

    Returns:
        Config: Fully initialised configuration object with all
                directories created on disk.
    """
    # Determine project root first so we can find .env
    project_root: Path = Path(__file__).resolve().parent.parent

    # Load .env from the project root (silently skip if missing)
    dotenv_path: Path = project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path)

    # ------------------------------------------------------------------
    # Helper: read an env var, returning *default* when unset / empty
    # ------------------------------------------------------------------
    def _env(var: str, default: str) -> str:
        value: str | None = os.getenv(var)
        return value if value else default

    # ------------------------------------------------------------------
    # Parse RSS_FEEDS: expect a comma-separated string in the env var
    # ------------------------------------------------------------------
    raw_feeds: str | None = os.getenv("RSS_FEEDS")
    if raw_feeds:
        rss_feeds: List[str] = [
            url.strip() for url in raw_feeds.split(",") if url.strip()
        ]
    else:
        rss_feeds = list(DEFAULT_RSS_FEEDS)

    # ------------------------------------------------------------------
    # Construct and return the Config dataclass
    # ------------------------------------------------------------------
    return Config(
        project_root=project_root,
        ollama_model=_env("OLLAMA_MODEL", "qwen2.5"),
        ollama_base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434"),
        sarvam_api_key=_env("SARVAM_API_KEY", ""),
        comfyui_base_url=_env("COMFYUI_BASE_URL", "http://127.0.0.1:8188"),
        tts_voice=_env("TTS_VOICE", "en-IN-PrabhatNeural"),
        tts_rate=_env("TTS_RATE", "+10%"),
        tts_pitch=_env("TTS_PITCH", "+0Hz"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY", ""),
        elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        youtube_client_secrets=_env(
            "YOUTUBE_CLIENT_SECRETS", "config/client_secrets.json"
        ),
        youtube_token_path=_env(
            "YOUTUBE_TOKEN_PATH", "config/youtube_token.json"
        ),
        youtube_privacy=_env("YOUTUBE_PRIVACY", "private"),
        youtube_category=_env("YOUTUBE_CATEGORY", "28"),
        channel_name=_env("CHANNEL_NAME", "AI Daily News"),
        ffmpeg_path=_env("FFMPEG_PATH", "ffmpeg"),
        rss_feeds=rss_feeds,
    )
