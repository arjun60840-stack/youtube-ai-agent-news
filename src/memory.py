import json
from pathlib import Path
from typing import List

from src.logger import get_logger

logger = get_logger(__name__)

# Memory file path is in the main project directory
MEMORY_FILE = Path(__file__).resolve().parent.parent / "memory.json"

def load_memory() -> List[str]:
    """Load the learned guidelines from memory.json."""
    if not MEMORY_FILE.exists():
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        logger.error("Failed to load memory file: %s", e)
        return []

def save_memory(rules: List[str]) -> None:
    """Save the learned guidelines to memory.json."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d rules to memory.", len(rules))
    except Exception as e:
        logger.error("Failed to save memory file: %s", e)

def add_rule(rule: str) -> None:
    """Append a single new rule to memory."""
    rules = load_memory()
    if rule not in rules:
        rules.append(rule)
        save_memory(rules)
        logger.info("Added new rule to memory: '%s'", rule)
