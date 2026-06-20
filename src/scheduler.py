"""
Scheduler Module — AI Daily News YouTube Agent

Manages a Windows Task Scheduler entry that runs the pipeline daily at
a fixed time.  Uses the built-in ``schtasks`` CLI utility (no third-party
dependencies required).

Provides three public functions:
  - ``setup_schedule(config)``   — create / overwrite the scheduled task.
  - ``remove_schedule()``        — delete the scheduled task.
  - ``check_schedule()``         — verify the task currently exists.

Note:
  ``schtasks /create`` may require **elevated (Administrator)** privileges
  depending on the Windows configuration.  The module handles permission
  errors gracefully and logs actionable guidance.
"""

from __future__ import annotations

import subprocess
from typing import List, Optional

from src.config import Config
from src.logger import get_logger

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Names of the Windows scheduled tasks
_TASK_NAMES: List[str] = [
    "AI_Daily_News_Agent_Morning",
    "AI_Daily_News_Agent_Afternoon",
    "AI_Daily_News_Agent_Evening"
]

# Scheduled times (24-hour format)
_SCHEDULE_TIMES: List[str] = ["08:00", "14:00", "20:00"]

# Schedule frequency
_SCHEDULE_FREQUENCY: str = "daily"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_schtasks(
    args: List[str],
    description: str,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute a ``schtasks`` command and return the result.

    Args:
        args:        Full argument list (including ``schtasks`` itself).
        description: Human-readable label for log messages.
        check:       If ``True``, raise ``subprocess.CalledProcessError``
                     on non-zero exit codes.

    Returns:
        The ``CompletedProcess`` result.

    Raises:
        subprocess.CalledProcessError: Only when *check* is ``True``.
    """
    logger.info("[%s] Running: %s", description, " ".join(args))

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        logger.debug(
            "[%s] schtasks exited with rc=%d\nstdout: %s\nstderr: %s",
            description,
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
    else:
        logger.debug("[%s] schtasks succeeded.", description)

    if check:
        result.check_returncode()

    return result


def _is_permission_error(stderr: str) -> bool:
    """Heuristically detect an access-denied / privilege error in schtasks output.

    Args:
        stderr: The standard-error output from the schtasks process.

    Returns:
        ``True`` if the error looks like an insufficient-permissions issue.
    """
    lowered = stderr.lower()
    permission_indicators = [
        "access is denied",
        "access denied",
        "not have permission",
        "requires elevation",
        "run as administrator",
        "error: 5",        # ERROR_ACCESS_DENIED
        "error: 0x5",
    ]
    return any(indicator in lowered for indicator in permission_indicators)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_schedule(config: Config) -> bool:
    """Create (or overwrite) 3 daily Windows scheduled tasks."""
    project_root: str = str(config.project_root)
    task_command: str = f'cmd /c cd /d {project_root} && python main.py'

    all_success = True
    for task_name, schedule_time in zip(_TASK_NAMES, _SCHEDULE_TIMES):
        cmd: List[str] = [
            "schtasks", "/create", "/tn", task_name,
            "/tr", task_command, "/sc", _SCHEDULE_FREQUENCY,
            "/st", schedule_time, "/f",
        ]
        try:
            result = _run_schtasks(cmd, f"Create {task_name}")
            if result.returncode == 0:
                logger.info(f"Task '{task_name}' created — runs at {schedule_time}.")
            else:
                combined_output: str = (result.stdout + result.stderr).strip()
                if _is_permission_error(combined_output):
                    logger.error(f"Insufficient privileges to create '{task_name}'. Please run as Administrator.")
                else:
                    logger.error(f"Failed to create '{task_name}' (rc={result.returncode}).")
                all_success = False
        except Exception as exc:
            logger.error(f"Unexpected error creating {task_name}: {exc}")
            all_success = False
            
    return all_success


def remove_schedule() -> bool:
    """Delete all scheduled tasks if they exist."""
    all_success = True
    for task_name in _TASK_NAMES:
        cmd: List[str] = ["schtasks", "/delete", "/tn", task_name, "/f"]
        try:
            result = _run_schtasks(cmd, f"Delete {task_name}")
            if result.returncode == 0:
                logger.info(f"Scheduled task '{task_name}' deleted successfully.")
            else:
                combined_output: str = (result.stdout + result.stderr).strip()
                not_found_indicators = ["does not exist", "cannot find the file", "the system cannot find", "error: the specified task name"]
                if any(ind in combined_output.lower() for ind in not_found_indicators):
                    logger.info(f"Task '{task_name}' does not exist — nothing to delete.")
                elif _is_permission_error(combined_output):
                    logger.error(f"Insufficient privileges to delete '{task_name}'. Please run as Administrator.")
                    all_success = False
                else:
                    logger.error(f"Failed to delete '{task_name}' (rc={result.returncode}).")
                    all_success = False
        except Exception as exc:
            logger.error(f"Unexpected error deleting {task_name}: {exc}")
            all_success = False
            
    return all_success


def check_schedule() -> bool:
    """Check whether all scheduled tasks currently exist."""
    all_exist = True
    for task_name in _TASK_NAMES:
        cmd: List[str] = ["schtasks", "/query", "/tn", task_name]
        try:
            result = _run_schtasks(cmd, f"Query {task_name}")
            if result.returncode == 0:
                logger.info(f"Scheduled task '{task_name}' exists.")
            else:
                combined_output: str = (result.stdout + result.stderr).strip()
                not_found_indicators = ["does not exist", "cannot find the file", "the system cannot find", "error: the specified task name"]
                if any(ind in combined_output.lower() for ind in not_found_indicators):
                    logger.info(f"Scheduled task '{task_name}' does not exist.")
                    all_exist = False
                else:
                    logger.warning(f"Unexpected schtasks output when querying '{task_name}' (rc={result.returncode}): {combined_output}")
                    all_exist = False
        except Exception as exc:
            logger.error(f"Unexpected error querying {task_name}: {exc}")
            all_exist = False
            
    return all_exist
