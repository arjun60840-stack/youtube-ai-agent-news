"""
YouTube Uploader Module — AI Daily News YouTube Agent

Handles OAuth 2.0 authentication and resumable video uploads to YouTube
via the YouTube Data API v3.

Flow:
  1. Load or refresh OAuth 2.0 credentials (or run interactive consent).
  2. Build the YouTube API service client.
  3. Upload the video with resumable chunked transfer.
  4. Return metadata (video ID, URL, privacy status).

Dependencies:
  - google-auth
  - google-auth-oauthlib
  - google-api-python-client
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, HttpRequest

from src.config import Config
from src.logger import get_logger

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# OAuth scope required for uploading videos
SCOPES: List[str] = ["https://www.googleapis.com/auth/youtube.upload"]

# Resumable upload chunk size — 10 MB
_CHUNK_SIZE: int = 1024 * 1024 * 10  # 10 MiB

# Retry settings for transient upload failures
_MAX_RETRIES: int = 3
_RETRY_DELAYS: List[int] = [5, 10, 20]  # exponential backoff (seconds)

# YouTube video watch URL template
_YOUTUBE_WATCH_URL: str = "https://www.youtube.com/watch?v={video_id}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _authenticate(config: Config) -> Optional[Credentials]:
    """Obtain valid OAuth 2.0 credentials for the YouTube Data API.

    The function follows this priority:
      1. Load an existing token from ``config.youtube_token_path``.
         a. If the token is valid, use it directly.
         b. If the token is expired but refreshable, refresh it.
      2. If no usable token exists, launch the interactive OAuth consent
         flow using ``config.youtube_client_secrets``.
      3. Persist the (new or refreshed) token back to disk.

    Args:
        config: Application configuration dataclass.

    Returns:
        A valid ``Credentials`` object, or ``None`` if the client secrets
        file is missing (caller should treat this as a soft failure).
    """
    creds: Optional[Credentials] = None
    token_path: str = config.youtube_token_path

    # ------------------------------------------------------------------
    # Step 1: Try to load existing token
    # ------------------------------------------------------------------
    if os.path.isfile(token_path):
        logger.info("Loading existing YouTube token from: %s", token_path)
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as exc:
            logger.warning("Could not load token file: %s — will re-authenticate.", exc)
            creds = None

    # ------------------------------------------------------------------
    # Step 2: Refresh or run consent flow
    # ------------------------------------------------------------------
    if creds and creds.valid:
        logger.info("YouTube credentials are valid.")
        return creds

    if creds and creds.expired and creds.refresh_token:
        logger.info("YouTube token expired — attempting refresh.")
        try:
            creds.refresh(Request())
            logger.info("Token refreshed successfully.")
            _save_token(creds, token_path)
            return creds
        except Exception as exc:
            logger.warning("Token refresh failed: %s — will re-authenticate.", exc)
            creds = None

    # Need a fresh consent flow
    secrets_path: str = config.youtube_client_secrets
    if not os.path.isfile(secrets_path):
        logger.warning(
            "YouTube client secrets file not found at '%s'. "
            "Upload will be skipped. Please place your OAuth client_secret JSON "
            "at the configured path and retry.",
            secrets_path,
        )
        return None

    logger.info("Starting OAuth consent flow (browser will open).")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
        creds = flow.run_local_server(port=0)
        logger.info("OAuth consent completed successfully.")
        _save_token(creds, token_path)
        return creds
    except Exception as exc:
        logger.error("OAuth consent flow failed: %s", exc)
        return None


def _save_token(creds: Credentials, token_path: str) -> None:
    """Persist credentials to a JSON file.

    Args:
        creds:      The OAuth 2.0 credentials to save.
        token_path: Destination file path.
    """
    try:
        # Ensure parent directory exists
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())
        logger.debug("Token saved to: %s", token_path)
    except OSError as exc:
        logger.warning("Could not save token to %s: %s", token_path, exc)


def _build_youtube_service(creds: Credentials) -> Resource:
    """Construct an authorised YouTube Data API v3 service client.

    Args:
        creds: Valid OAuth 2.0 credentials.

    Returns:
        A ``googleapiclient.discovery.Resource`` for the YouTube v3 API.
    """
    service: Resource = build("youtube", "v3", credentials=creds)
    logger.debug("YouTube API service built successfully.")
    return service


def _execute_resumable_upload(
    request: HttpRequest,
    video_path: str,
) -> Dict[str, Any]:
    """Execute a resumable upload, logging chunk-level progress.

    Args:
        request:    The ``HttpRequest`` object returned by
                    ``youtube.videos().insert()``.
        video_path: Path to the video (used for logging only).

    Returns:
        The API response dict upon successful completion.

    Raises:
        HttpError: If the upload fails after exhausting retries.
    """
    response: Optional[Dict[str, Any]] = None
    retries_used: int = 0

    logger.info("Starting resumable upload for: %s", video_path)

    while response is None:
        try:
            status, response = request.next_chunk()

            if status is not None:
                progress_pct: float = status.progress() * 100
                logger.info(
                    "Upload progress: %.1f%% (%s)",
                    progress_pct,
                    video_path,
                )

        except (HttpError, OSError) as err:
            # Determine if it's retryable
            is_retryable = False
            if isinstance(err, HttpError):
                if err.resp.status in (500, 502, 503, 504):
                    is_retryable = True
            elif isinstance(err, OSError):
                # Network errors like ConnectionResetError or Timeout
                is_retryable = True

            if is_retryable and retries_used < _MAX_RETRIES:
                delay = _RETRY_DELAYS[retries_used]
                retries_used += 1
                logger.warning(
                    "Transient error during upload (%s) — retry %d/%d in %d s.",
                    type(err).__name__,
                    retries_used,
                    _MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
            else:
                # Non-retryable error or retries exhausted
                raise

    logger.info("Resumable upload completed for: %s", video_path)
    return response


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: List[str],
    config: Config,
    date_str: str,
    thumbnail_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Upload a video to YouTube with the given metadata.

    The function authenticates (or re-authenticates) using OAuth 2.0, builds
    the YouTube service, and performs a resumable upload with automatic retry
    for transient errors.

    Args:
        video_path:  Absolute path to the MP4 file to upload.
        title:       Video title (max 100 characters recommended).
        description: Video description.
        tags:        List of keyword tags.
        config:      Application configuration dataclass.
        date_str:    Date string (used only for logging context).

    Returns:
        A dict containing::

            {
                "video_id": str,
                "url": str,
                "status": str,      # e.g. "uploaded"
                "title": str,
                "privacy": str,
            }

        Returns ``None`` if the client secrets file is missing or
        authentication fails (upload is gracefully skipped).

    Raises:
        FileNotFoundError: If *video_path* does not exist.
        HttpError:         If a non-transient YouTube API error occurs.
    """
    # ------------------------------------------------------------------
    # 0. Input validation
    # ------------------------------------------------------------------
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    video_size_mb: float = os.path.getsize(video_path) / (1024 * 1024)
    logger.info(
        "Preparing YouTube upload — title='%s', file=%s (%.1f MB), date=%s",
        title,
        video_path,
        video_size_mb,
        date_str,
    )

    # ------------------------------------------------------------------
    # 1. Authenticate
    # ------------------------------------------------------------------
    creds: Optional[Credentials] = _authenticate(config)
    if creds is None:
        logger.warning(
            "YouTube authentication unavailable — skipping upload for %s.",
            date_str,
        )
        return None

    # ------------------------------------------------------------------
    # 2. Build YouTube API service
    # ------------------------------------------------------------------
    youtube: Resource = _build_youtube_service(creds)

    # Automatically append Shorts hashtags to ensure it gets routed to the Shorts feed
    # if it is a portrait video
    if getattr(config, "video_format", "landscape") == "portrait":
        if "#shorts" not in description.lower():
            description += "\n\n#shorts #youtubeshorts"
        
        lower_tags = [t.lower() for t in tags]
        if "shorts" not in lower_tags:
            tags.extend(["shorts", "youtubeshorts", "techshorts"])

    # ------------------------------------------------------------------
    # 3. Prepare request body & media
    # ------------------------------------------------------------------
    body: Dict[str, Any] = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": config.youtube_category,
        },
        "status": {
            "privacyStatus": config.youtube_privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=_CHUNK_SIZE,
    )

    # ------------------------------------------------------------------
    # 4. Insert video (initiate upload)
    # ------------------------------------------------------------------
    insert_request: HttpRequest = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # ------------------------------------------------------------------
    # 5. Execute resumable upload with retries
    # ------------------------------------------------------------------
    try:
        api_response: Dict[str, Any] = _execute_resumable_upload(
            insert_request,
            video_path,
        )
    except HttpError as http_err:
        logger.error(
            "YouTube upload failed with HTTP %d: %s",
            http_err.resp.status,
            http_err.content.decode("utf-8", errors="replace"),
        )
        raise

    # ------------------------------------------------------------------
    # 6. Build and return result
    # ------------------------------------------------------------------
    video_id: str = api_response.get("id", "unknown")
    video_url: str = _YOUTUBE_WATCH_URL.format(video_id=video_id)
    privacy: str = (
        api_response.get("status", {}).get("privacyStatus", config.youtube_privacy)
    )

    result: Dict[str, Any] = {
        "video_id": video_id,
        "url": video_url,
        "status": "uploaded",
        "title": title,
        "privacy": privacy,
    }

    logger.info(
        "YouTube upload successful! Video ID: %s | URL: %s | Privacy: %s",
        video_id,
        video_url,
        privacy,
    )

    # ------------------------------------------------------------------
    # 7. Upload Custom Thumbnail (Optional)
    # ------------------------------------------------------------------
    if thumbnail_path and os.path.isfile(thumbnail_path):
        logger.info("Setting custom thumbnail from: %s", thumbnail_path)
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            logger.info("Custom thumbnail uploaded successfully!")
        except Exception as exc:
            logger.warning("Failed to upload custom thumbnail: %s", exc)

    return result
