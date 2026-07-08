"""
run_all.py — Sequential Multi-Channel Pipeline Runner

Runs Channel 1 (tech_news as a Short) first, then Channel 2 (channel_2).
Designed to be triggered automatically on Windows startup.
Includes network wait, internet check, and error logging.
"""

import subprocess
import sys
import os
import time
import logging
import urllib.request
from datetime import datetime

# Hardcoded Python path to avoid sys.executable issues when launched from Startup
PYTHON = r"C:\Python314\python.exe"
PROJECT_DIR = r"C:\Users\ARJUN\.gemini\antigravity\scratch\ai_news_agent"
MAIN_PY = os.path.join(PROJECT_DIR, "main.py")
LOG_FILE = os.path.join(PROJECT_DIR, "startup_pipeline.log")

# Setup logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)


def wait_for_internet(max_wait=120):
    """Wait until internet is available, checking every 5 seconds."""
    logging.info(f"Checking internet connectivity (max wait: {max_wait}s)...")
    start = time.time()
    while time.time() - start < max_wait:
        try:
            urllib.request.urlopen("https://www.google.com", timeout=5)
            logging.info("Internet connection confirmed!")
            return True
        except Exception:
            elapsed = int(time.time() - start)
            logging.info(f"No internet yet... ({elapsed}s elapsed)")
            time.sleep(5)
    logging.error("Could not establish internet connection. Aborting.")
    return False


def run_pipeline(channel, extra_args=None):
    """Run main.py for a specific channel and wait for completion."""
    cmd = [PYTHON, MAIN_PY, "--channel", channel]
    if extra_args:
        cmd.extend(extra_args)

    logging.info(f"Starting pipeline: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Stream output to both console and log
    for line in process.stdout:
        line = line.rstrip()
        if line:
            logging.info(f"[{channel}] {line}")

    process.wait()
    if process.returncode != 0:
        logging.error(f"Pipeline '{channel}' FAILED with exit code {process.returncode}")
        return False
    logging.info(f"Pipeline '{channel}' completed successfully!")
    return True


if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info(f"AI DAILY NEWS AGENT — AUTO PIPELINE START")
    logging.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 60)

    # Step 1: Wait for internet
    if not wait_for_internet():
        sys.exit(1)

    # Step 2: Run Channel 1 (tech_news) as a YouTube Short
    logging.info("=" * 60)
    logging.info("PIPELINE 1: tech_news (YouTube Short)")
    logging.info("=" * 60)
    success1 = run_pipeline("tech_news", ["--portrait"])

    if not success1:
        logging.error("Pipeline 1 failed! Continuing to Pipeline 2 anyway...")

    # Step 3: Run Channel 2 (channel_2) as landscape video
    logging.info("=" * 60)
    logging.info("PIPELINE 2: channel_2 (Landscape Video)")
    logging.info("=" * 60)
    success2 = run_pipeline("channel_2")

    if not success2:
        logging.error("Pipeline 2 failed!")

    # Summary
    logging.info("=" * 60)
    logging.info(f"RESULTS: Channel 1={'OK' if success1 else 'FAILED'} | Channel 2={'OK' if success2 else 'FAILED'}")
    logging.info("=" * 60)

    sys.exit(0 if (success1 and success2) else 1)
