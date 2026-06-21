import json
from pathlib import Path
from typing import List, Dict, Any, Union

from src.logger import get_logger

logger = get_logger(__name__)

# Memory file path is in the main project directory
MEMORY_FILE = Path(__file__).resolve().parent.parent / "memory.json"

VALID_CATEGORIES = {"script", "visual", "voice", "general"}
DEFAULT_CATEGORY = "script"  # Every rule taught before category support existed
                              # was consumed exclusively by crew_writer.py's
                              # script-writing agents, so that's the correct
                              # migration target for legacy flat-string entries.


def _normalize_entry(entry: Union[str, Dict[str, Any]]) -> Dict[str, str]:
    """
    Normalize a single memory.json entry into {"category": str, "rule": str}.

    BACKWARD COMPATIBILITY: memory.json previously stored a flat list of
    plain strings (16 such rules exist in production today). Those entries
    have no category. We treat any bare string as category="script" since
    crew_writer.py was the only consumer that ever existed before this change.
    """
    if isinstance(entry, str):
        return {"category": DEFAULT_CATEGORY, "rule": entry}
    if isinstance(entry, dict) and "rule" in entry:
        category = entry.get("category", DEFAULT_CATEGORY)
        if category not in VALID_CATEGORIES:
            logger.warning(
                "Unknown memory category '%s' on rule '%s' — treating as 'general'.",
                category, entry.get("rule", "")[:60],
            )
            category = "general"
        return {"category": category, "rule": entry["rule"]}
    logger.warning("Skipping malformed memory entry: %r", entry)
    return {"category": "general", "rule": ""}


def _load_raw() -> List[Dict[str, str]]:
    """Load memory.json and normalize every entry to {"category", "rule"} dicts."""
    if not MEMORY_FILE.exists():
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error("memory.json root is not a list — ignoring contents.")
            return []
        normalized = [_normalize_entry(e) for e in data]
        return [e for e in normalized if e["rule"]]
    except Exception as e:
        logger.error("Failed to load memory file: %s", e)
        return []


def load_memory() -> List[str]:
    """
    Load ALL learned rules as a flat list of strings, regardless of category.

    UNCHANGED SIGNATURE: existing callers (crew_writer.py) keep working
    exactly as before — they get every rule's text, with no category
    filtering, matching pre-existing behavior.
    """
    return [e["rule"] for e in _load_raw()]


def load_memory_by_category(category: str) -> List[str]:
    """
    Load only the rules tagged with the given category, as a flat list of
    strings. Use this in consumers that should only see rules relevant to
    them — e.g. image_generator.py should only see category="visual" rules,
    not script-writing rules about hooks and CTAs.
    """
    if category not in VALID_CATEGORIES:
        logger.warning("load_memory_by_category called with unknown category '%s'.", category)
    return [e["rule"] for e in _load_raw() if e["category"] == category]


def save_memory(rules: List[Dict[str, str]]) -> None:
    """Save a list of {"category", "rule"} dicts to memory.json."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d rules to memory.", len(rules))
    except Exception as e:
        logger.error("Failed to save memory file: %s", e)


def add_rule(rule: str, category: str = DEFAULT_CATEGORY) -> None:
    """
    Append a single new rule to memory under the given category.

    BACKWARD COMPATIBLE: existing call sites (teacher.py, auto_learner.py)
    call add_rule(rule) with no category argument, which defaults to
    "script" — identical behavior to before this change.
    """
    if category not in VALID_CATEGORIES:
        logger.warning("add_rule called with unknown category '%s' — using 'general'.", category)
        category = "general"

    rules = _load_raw()
    if any(r["rule"] == rule and r["category"] == category for r in rules):
        logger.info("Rule already exists under category '%s', skipping duplicate: '%s'", category, rule)
        return

    rules.append({"category": category, "rule": rule})
    save_memory(rules)
    logger.info("Added new '%s' rule to memory: '%s'", category, rule)
