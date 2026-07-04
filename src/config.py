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
    # Google News "Technology" topic feed
    (
        "https://news.google.com/rss/topics/"
        "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB"
        "?hl=en-US&gl=US&ceid=US:en"
    ),
    # Google News "World News" topic feed
    (
        "https://news.google.com/rss/topics/"
        "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB"
        "?hl=en-US&gl=US&ceid=US:en"
    ),
    # Google News search: "artificial intelligence"
    (
        "https://news.google.com/rss/search"
        "?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en"
    ),
    # Google News search: "world news"
    (
        "https://news.google.com/rss/search"
        "?q=world+news&hl=en-US&gl=US&ceid=US:en"
    ),
]

# ---------------------------------------------------------------------------
# Allowed topics for Hindi Tech & World News
# ---------------------------------------------------------------------------
ALLOWED_TOPICS: List[str] = [
    "AI", "OpenAI", "ChatGPT", "Google", "Gemini", "Microsoft",
    "Apple", "Android", "iPhone", "NVIDIA", "Cybersecurity",
    "Technology Launches", "Software Updates", "World News",
    "Global Events", "International Relations", "Science & Space"
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
    gemini_api_keys: List[str] = field(default_factory=list)
    active_gemini_key_index: int = 0
    gemini_model: str = "gemini-2.5-flash"
    
    ollama_model: str = "llama3:8b"
    ollama_base_url: str = "http://localhost:11434"
    
    def get_current_gemini_key(self) -> str:
        if not self.gemini_api_keys:
            return ""
        return self.gemini_api_keys[self.active_gemini_key_index]
        
    def rotate_gemini_key(self) -> bool:
        """Rotates to the next Gemini API key if available. Returns True if successfully rotated."""
        if not self.gemini_api_keys or len(self.gemini_api_keys) <= 1:
            return False
        
        old_key = self.get_current_gemini_key()
        self.active_gemini_key_index = (self.active_gemini_key_index + 1) % len(self.gemini_api_keys)
        new_key = self.get_current_gemini_key()
        return old_key != new_key
    
    
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
    
    # ------------------------------------------------------------------
    # Channel Context
    # ------------------------------------------------------------------
    channel_id: str = "default"
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
    # RSS feeds, Topics & Video Settings
    # ------------------------------------------------------------------
    rss_feeds: List[str] = field(default_factory=lambda: list(DEFAULT_RSS_FEEDS))
    allowed_topics: List[str] = field(default_factory=lambda: list(ALLOWED_TOPICS))
    video_format: str = "landscape"  # "landscape" or "portrait"
    use_real_images: bool = False  # Fetch real images from web instead of AI generation


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
        # Isolate outputs by channel_id
        channel_base = self.project_root / self.channel_id
        
        self.news_dir = channel_base / "news"
        self.scripts_dir = channel_base / "scripts"
        self.audio_dir = channel_base / "audio"
        self.images_dir = channel_base / "images"
        self.videos_dir = channel_base / "videos"
        self.logs_dir = channel_base / "logs"
        
        # We can leave config_dir pointing to the global config folder if we want,
        # but youtube secrets are isolated by channel directory anyway
        self.config_dir = self.project_root / "channels" / self.channel_id

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

def load_config(channel_name: str = "tech_news") -> Config:
    """
    Build a ``Config`` instance from environment variables and channel-specific JSON.

    Reads a ``.env`` file located at the project root for global keys,
    then reads ``channels/{channel_name}/config.json`` for channel overrides.

    Args:
        channel_name: Name of the channel directory in `channels/`

    Returns:
        Config: Fully initialised configuration object.
    """
    import json
    project_root: Path = Path(__file__).resolve().parent.parent
    dotenv_path: Path = project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path)

    def _env(var: str, default: str) -> str:
        value = os.getenv(var)
        return value if value else default

    raw_gemini_keys: str | None = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY")
    gemini_api_keys: List[str] = []
    if raw_gemini_keys:
        gemini_api_keys = [k.strip() for k in raw_gemini_keys.split(",") if k.strip()]

    # Setup channel paths
    channel_dir = project_root / "channels" / channel_name
    channel_dir.mkdir(parents=True, exist_ok=True)
    
    # Load channel config overrides
    channel_config_path = channel_dir / "config.json"
    channel_data = {}
    if channel_config_path.exists():
        try:
            with open(channel_config_path, "r", encoding="utf-8") as f:
                channel_data = json.load(f)
        except Exception as e:
            print(f"Failed to load channel config {channel_config_path}: {e}")

    # Fallback to env or defaults if not in channel_data
    rss_feeds = channel_data.get("rss_feeds")
    if not rss_feeds:
        raw_feeds = os.getenv("RSS_FEEDS")
        if raw_feeds:
            rss_feeds = [url.strip() for url in raw_feeds.split(",") if url.strip()]
        else:
            rss_feeds = list(DEFAULT_RSS_FEEDS)
            
    allowed_topics = channel_data.get("allowed_topics", list(ALLOWED_TOPICS))
    
    # Check for channel-specific client secrets
    client_secrets = channel_dir / "client_secrets.json"
    if not client_secrets.exists():
        # Fallback to old global location
        client_secrets = project_root / "config" / "client_secrets.json"
        
    token_path = channel_dir / "youtube_token.json"
    if not token_path.exists():
        # Fallback to old global location
        token_path = project_root / "config" / "youtube_token.json"
    return Config(
        project_root=project_root,
        gemini_api_keys=gemini_api_keys,
        gemini_model=_env("GEMINI_MODEL", "gemini-2.5-flash"),
        ollama_model=channel_data.get("ollama_model", _env("OLLAMA_MODEL", "llama3:8b")),
        ollama_base_url=channel_data.get("ollama_base_url", _env("OLLAMA_BASE_URL", "http://localhost:11434")),
        sarvam_api_key=_env("SARVAM_API_KEY", ""),
        comfyui_base_url=_env("COMFYUI_BASE_URL", "http://127.0.0.1:8188"),
        tts_voice=channel_data.get("tts_voice", _env("TTS_VOICE", "en-IN-PrabhatNeural")),
        tts_rate=channel_data.get("tts_rate", _env("TTS_RATE", "+10%")),
        tts_pitch=channel_data.get("tts_pitch", _env("TTS_PITCH", "+0Hz")),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY", ""),
        elevenlabs_voice_id=channel_data.get("elevenlabs_voice_id", _env("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")),
        youtube_client_secrets=str(client_secrets),
        youtube_token_path=str(token_path),
        youtube_privacy=channel_data.get("youtube_privacy", _env("YOUTUBE_PRIVACY", "private")),
        youtube_category=channel_data.get("youtube_category", _env("YOUTUBE_CATEGORY", "28")),
        channel_name=channel_data.get("channel_name", channel_name.replace("_", " ").title()),
        channel_id=channel_name,
        ffmpeg_path=_env("FFMPEG_PATH", "ffmpeg"),
        rss_feeds=rss_feeds,
        allowed_topics=allowed_topics,
        video_format=channel_data.get("video_format", _env("VIDEO_FORMAT", "landscape")),
        use_real_images=channel_data.get("use_real_images", False),
    )
