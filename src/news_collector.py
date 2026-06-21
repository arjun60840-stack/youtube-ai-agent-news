"""
News Collection Module for AI Daily News YouTube Agent.

Fetches trending technology and AI stories from Google News RSS feeds,
de-duplicates near-identical headlines using fuzzy string matching, and
persists the top stories as a date-stamped JSON file.

Pipeline:
    1. Iterate over every RSS feed URL in ``config.rss_feeds``.
    2. Parse each feed with ``feedparser``.
    3. Extract title, summary (HTML-stripped), source, published date,
       and link from every entry.
    4. De-duplicate stories whose titles are ≥ 70 % similar
       (``difflib.SequenceMatcher``).
    5. Sort by published date (newest first) and keep the top 5.
    6. Serialise to JSON under ``config.news_dir``.

Usage:
    from src.config import load_config
    from src.news_collector import collect_news

    config = load_config()
    stories = collect_news(config, date_str="2026-06-01")
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List

import feedparser  # type: ignore[import-untyped]

from src.config import Config
from src.logger import get_logger

# Module-level logger
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Two titles with a similarity ratio above this threshold are treated
# as duplicates and the later occurrence is dropped.
_DUPLICATE_THRESHOLD: float = 0.7

# Maximum number of stories to return after de-duplication.
# V2 Rule: One video = one news story.
_MAX_STORIES: int = 1


# ======================================================================
# Data model
# ======================================================================

@dataclass
class NewsStory:
    """
    A single news story extracted from an RSS feed entry.

    Attributes:
        title:     Headline text (HTML already stripped).
        summary:   Short description / lead paragraph (HTML stripped).
        source:    Publisher or source name (e.g. "TechCrunch").
        published: Publication timestamp as a human-readable string.
        link:      Canonical URL to the full article.
    """

    title: str
    summary: str
    source: str
    published: str
    link: str


# ======================================================================
# Internal helpers
# ======================================================================

def _strip_html(text: str) -> str:
    """
    Remove HTML / XML tags from *text* using a simple regex.

    This is intentionally lightweight — we do not need a full HTML
    parser for the short plain-text snippets returned by Google News.

    Args:
        text: Raw string that may contain HTML markup.

    Returns:
        str: Plain-text string with all ``<…>`` sequences removed.
    """
    return re.sub(r"<[^>]+>", "", text).strip()


def _get_past_titles(config: Config) -> List[str]:
    """Retrieve the titles of the last 30 generated scripts to prevent duplicates."""
    past_titles = []
    try:
        script_files = sorted(config.scripts_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in script_files[:30]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if "title" in data:
                    past_titles.append(data["title"])
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not load past titles for duplicate protection: {e}")
    return past_titles

def _is_duplicate(
    title: str,
    existing_titles: List[str],
    threshold: float = _DUPLICATE_THRESHOLD,
) -> bool:
    """
    Check whether *title* is a near-duplicate of any title in
    *existing_titles* using ``difflib.SequenceMatcher``.

    Args:
        title:           The candidate headline to test.
        existing_titles: Headlines already accepted into the results.
        threshold:       Similarity ratio above which two titles are
                         considered duplicates (default 0.7).

    Returns:
        bool: ``True`` if *title* is a duplicate of an existing title.
    """
    for existing in existing_titles:
        ratio: float = SequenceMatcher(
            None,
            title.lower(),
            existing.lower(),
        ).ratio()
        if ratio > threshold:
            return True
    return False


def _parse_entry(entry: Any) -> NewsStory:
    """
    Convert a single ``feedparser`` entry dict into a ``NewsStory``.

    Google News feeds embed the publisher name in the title after a
    " - " separator; we try to split on that to extract the source.

    Args:
        entry: A ``feedparser.FeedParserDict`` entry object.

    Returns:
        NewsStory: Populated dataclass instance.
    """
    # --- Title & source ------------------------------------------------
    raw_title: str = entry.get("title", "Untitled")

    # Google News titles look like: "Headline text - Source Name"
    if " - " in raw_title:
        parts = raw_title.rsplit(" - ", 1)
        title: str = parts[0].strip()
        source: str = parts[1].strip()
    else:
        title = raw_title.strip()
        source = entry.get("source", {}).get("title", "Unknown")

    # --- Summary (strip HTML) ------------------------------------------
    raw_summary: str = entry.get("summary", "")
    summary: str = _strip_html(raw_summary) if raw_summary else ""

    # --- Published date ------------------------------------------------
    published: str = entry.get("published", "Unknown")

    # --- Link ----------------------------------------------------------
    link: str = entry.get("link", "")

    return NewsStory(
        title=title,
        summary=summary,
        source=source,
        published=published,
        link=link,
    )


def _sort_stories_newest_first(stories: List[NewsStory]) -> List[NewsStory]:
    """
    Sort stories by their ``published`` field in descending order.

    ``feedparser`` normalises dates to RFC-2822 strings which sort
    lexicographically in most cases.  For robustness we attempt to
    parse with ``feedparser._parse_date`` and fall back to raw string
    comparison.

    Args:
        stories: Unsorted list of ``NewsStory`` instances.

    Returns:
        List[NewsStory]: New list sorted newest-first.
    """
    import time

    def _sort_key(story: NewsStory) -> float:
        """Return a Unix timestamp for sorting, 0.0 on failure."""
        try:
            parsed = feedparser._parse_date(story.published)  # type: ignore[attr-defined]
            if parsed:
                return time.mktime(parsed)
        except Exception:
            pass
        return 0.0

    return sorted(stories, key=_sort_key, reverse=True)


# ======================================================================
# Public API
# ======================================================================

def collect_news(config: Config, date_str: str) -> List[NewsStory]:
    """
    Fetch, de-duplicate, and persist trending AI / tech news stories.

    Workflow:
        1. Fetch all configured RSS feeds.
        2. Parse each entry into a ``NewsStory``.
        3. Skip near-duplicate headlines (≥ 70 % similarity).
        4. Sort remaining stories newest-first.
        5. Keep the top 5.
        6. Save the result to ``config.news_dir / {date_str}.json``.

    Args:
        config:   Application configuration (provides feed URLs and
                  output directory paths).
        date_str: ISO-format date string (``YYYY-MM-DD``) used to
                  name the output JSON file.

    Returns:
        List[NewsStory]: Up to 5 unique, sorted news stories.

    Raises:
        ValueError: If no stories could be collected from any feed.
    """
    logger.info("Starting news collection for %s", date_str)
    
    output_path: Path = config.news_dir / f"{date_str}.json"
    if output_path.exists():
        logger.info("Found cached news for %s, skipping network collection.", date_str)
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [NewsStory(**item) for item in data]
        except Exception as e:
            logger.warning("Failed to load cached news: %s. Will re-fetch.", e)

    all_stories: List[NewsStory] = []
    accepted_titles: List[str] = _get_past_titles(config)

    # ------------------------------------------------------------------
    # 1. Fetch & parse every RSS feed
    # ------------------------------------------------------------------
    for feed_url in config.rss_feeds:
        logger.debug("Fetching feed: %s", feed_url)

        try:
            feed = feedparser.parse(feed_url)

            # Check for HTTP-level errors reported by feedparser
            if feed.bozo and not feed.entries:
                logger.warning(
                    "Feed returned bozo error: %s — %s",
                    feed_url,
                    feed.get("bozo_exception", "unknown error"),
                )
                continue

            logger.info(
                "Fetched %d entries from %s",
                len(feed.entries),
                feed_url,
            )

            for entry in feed.entries:
                story: NewsStory = _parse_entry(entry)

                # --- De-duplication -----------------------------------
                if _is_duplicate(story.title, accepted_titles):
                    logger.debug(
                        "Skipping duplicate: '%s'", story.title[:80]
                    )
                    continue

                # --- Topic Filtering ----------------------------------
                topic_match = False
                text_to_check = (story.title + " " + story.summary).lower()
                for topic in config.allowed_topics:
                    if topic.lower() in text_to_check:
                        topic_match = True
                        break
                
                if not topic_match:
                    logger.debug("Skipping off-topic story: '%s'", story.title[:80])
                    continue

                accepted_titles.append(story.title)
                all_stories.append(story)

        except Exception as exc:
            logger.error(
                "Failed to fetch/parse feed %s: %s", feed_url, exc
            )
            continue

    # ------------------------------------------------------------------
    # 2. Validate we found something
    # ------------------------------------------------------------------
    if not all_stories:
        msg: str = (
            f"No news stories could be collected for {date_str}. "
            "Check network connectivity and RSS feed URLs in config."
        )
        logger.error(msg)
        raise ValueError(msg)

    # ------------------------------------------------------------------
    # 3. Sort newest-first and cap at _MAX_STORIES
    # ------------------------------------------------------------------
    sorted_stories: List[NewsStory] = _sort_stories_newest_first(all_stories)
    top_stories: List[NewsStory] = sorted_stories[:_MAX_STORIES]

    logger.info(
        "Collected %d unique stories, keeping top %d",
        len(all_stories),
        len(top_stories),
    )

    # ------------------------------------------------------------------
    # 4. Persist to JSON
    # ------------------------------------------------------------------
    output_path: Path = config.news_dir / f"{date_str}.json"

    serialisable: List[Dict[str, Any]] = [asdict(s) for s in top_stories]

    try:
        output_path.write_text(
            json.dumps(serialisable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Saved news stories to %s", output_path)
    except OSError as exc:
        logger.error("Failed to write news JSON: %s", exc)
        raise

    return top_stories
