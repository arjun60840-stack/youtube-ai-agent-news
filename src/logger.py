"""
Logging Configuration Module for AI Daily News YouTube Agent.

Provides a dual-handler logging setup:
    1. **File handler** — writes DEBUG-level (and above) messages to a
       date-stamped log file under the project's ``logs/`` directory.
    2. **Console handler** — prints INFO-level (and above) messages to
       ``stderr`` with ANSI colour codes for quick visual scanning.

Usage:
    from src.logger import setup_logging, get_logger

    # Call once at application startup
    setup_logging(logs_dir=Path("logs"), date_str="2026-06-01")

    # Then anywhere in your code
    logger = get_logger(__name__)
    logger.info("Pipeline started")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


# ======================================================================
# ANSI colour codes for console output
# ======================================================================

class _AnsiColours:
    """
    Container for ANSI escape sequences used to colourise log levels
    in terminal output.  Falls back gracefully on terminals that do not
    support colour (the sequences are simply ignored).
    """

    RESET: str = "\033[0m"
    BOLD: str = "\033[1m"
    DIM: str = "\033[2m"

    # Level → colour mapping
    DEBUG: str = "\033[36m"      # Cyan
    INFO: str = "\033[32m"       # Green
    WARNING: str = "\033[33m"    # Yellow
    ERROR: str = "\033[31m"      # Red
    CRITICAL: str = "\033[41m"   # Red background


# Mapping from log-level name → ANSI colour prefix
_LEVEL_COLOURS: dict[str, str] = {
    "DEBUG": _AnsiColours.DEBUG,
    "INFO": _AnsiColours.INFO,
    "WARNING": _AnsiColours.WARNING,
    "ERROR": _AnsiColours.ERROR,
    "CRITICAL": _AnsiColours.CRITICAL,
}


# ======================================================================
# Custom coloured formatter
# ======================================================================

class _ColouredFormatter(logging.Formatter):
    """
    A ``logging.Formatter`` subclass that wraps the level name in ANSI
    colour codes so that different severities are visually distinct in
    the console.
    """

    def __init__(self, fmt: str, datefmt: str) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        # Inject colour around the level name
        colour: str = _LEVEL_COLOURS.get(record.levelname, "")
        record.levelname = (
            f"{colour}{record.levelname}{_AnsiColours.RESET}"
        )
        return super().format(record)


# ======================================================================
# Public API
# ======================================================================

# Sentinel to prevent adding handlers more than once when
# ``setup_logging`` is called multiple times (e.g. in tests).
_LOGGING_CONFIGURED: bool = False


def setup_logging(logs_dir: Path, date_str: str) -> logging.Logger:
    """
    Configure the root logger with file and console handlers.

    If this function is called more than once during the same process,
    subsequent calls are silently skipped to avoid duplicate log lines.

    Args:
        logs_dir: Absolute or relative path to the ``logs/`` directory.
                  Will be created if it does not exist.
        date_str: Date string (e.g. ``"2026-06-01"``) used to name the
                  daily log file (``logs/2026-06-01.log``).

    Returns:
        logging.Logger: The root logger instance, fully configured.
    """
    global _LOGGING_CONFIGURED  # noqa: PLW0603

    # Guard against duplicate handlers -----------------------------------
    if _LOGGING_CONFIGURED:
        return logging.getLogger()

    # Ensure the log directory exists ------------------------------------
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Shared format strings ----------------------------------------------
    log_format: str = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"

    # --- Root logger ----------------------------------------------------
    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # capture everything; handlers filter

    # --- File handler (DEBUG level) -------------------------------------
    log_file: Path = logs_dir / f"{date_str}.log"
    file_handler: logging.FileHandler = logging.FileHandler(
        filename=str(log_file),
        mode="a",           # append — safe for re-runs on the same day
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(fmt=log_format, datefmt=date_format)
    )

    # --- Console handler (INFO level, coloured) -------------------------
    console_handler: logging.StreamHandler = logging.StreamHandler(
        stream=sys.stderr,
    )
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        _ColouredFormatter(fmt=log_format, datefmt=date_format)
    )

    # Attach handlers to root logger -------------------------------------
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Mark as configured so we don't add duplicate handlers --------------
    _LOGGING_CONFIGURED = True

    root_logger.debug(
        "Logging initialised — file: %s | console: INFO", log_file
    )

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Convenience wrapper around ``logging.getLogger``.

    Returns a child logger whose records propagate to the root logger
    configured by ``setup_logging``.  Safe to call before
    ``setup_logging`` — messages will simply be buffered by Python's
    default last-resort handler until the root logger is set up.

    Args:
        name: Hierarchical logger name, typically ``__name__``.

    Returns:
        logging.Logger: Named logger instance.
    """
    return logging.getLogger(name)
