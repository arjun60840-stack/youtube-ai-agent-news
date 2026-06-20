"""
Analytics Engine Module — AI Daily News YouTube Agent

This module represents the Self-Learning Feedback Loop.
It analyzes past video performance (Views, CTR, Retention), critiques the past scripts using the local LLM,
and dynamically adds new learning rules to `memory.json` so the channel continuously improves.
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Any

import ollama

from src.config import Config
from src.logger import get_logger
from src.memory import add_rule

logger = get_logger(__name__)

def _simulate_youtube_metrics(script_title: str) -> Dict[str, float]:
    """
    Simulate fetching YouTube Data & Analytics API metrics.
    In a fully authenticated production environment, this would call:
    youtube.videos().list(id=..., part="statistics")
    """
    # Simulate somewhat realistic metrics based on string length hash (deterministic simulation)
    seed = sum(ord(c) for c in script_title)
    random.seed(seed)
    
    views = random.randint(100, 15000)
    ctr = round(random.uniform(2.5, 12.0), 1)
    retention = round(random.uniform(30.0, 75.0), 1)
    
    return {
        "views": views,
        "ctr_percent": ctr,
        "retention_percent": retention,
        "performance_score": views + (ctr * 100) + (retention * 50)
    }

def run_learning_loop(config: Config) -> None:
    """
    Analyze past videos and use the LLM to generate new constraints for the next video.
    """
    logger.info("Starting Analytics Engine & Self-Learning Loop...")
    
    # 1. Fetch the last 3 uploaded scripts
    scripts: List[Dict[str, Any]] = []
    try:
        script_files = sorted(config.scripts_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in script_files[:3]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if "script" in data and "title" in data:
                    scripts.append(data)
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"Could not load past scripts for analysis: {e}")
        return

    if not scripts:
        logger.info("Not enough past videos to perform analytics yet.")
        return

    # 2. Get the most recent script to analyze
    target_script = scripts[0]
    metrics = _simulate_youtube_metrics(target_script["title"])
    
    logger.info(f"Analyzed Last Video: '{target_script['title']}'")
    logger.info(f"Metrics: Views={metrics['views']}, CTR={metrics['ctr_percent']}%, Retention={metrics['retention_percent']}%")
    
    # If performance is amazing, we don't need to change much.
    if metrics['performance_score'] > 10000:
        logger.info("Performance is excellent. No new learning rules required right now.")
        return

    # 3. LLM Critique (The actual self-learning)
    logger.info("Performance is suboptimal. Initiating LLM Critique to learn...")
    
    prompt = f"""
    You are an expert YouTube Channel Strategist.
    We uploaded a Tech YouTube Shorts video but the retention was only {metrics['retention_percent']}% and CTR was {metrics['ctr_percent']}%.
    
    Here was the script we used:
    "{target_script['script']}"
    
    Here was the title we used:
    "{target_script['title']}"
    
    Provide EXACTLY ONE short, highly specific instruction (under 20 words) on how to improve the script, pacing, or hook for the next video to increase retention and CTR. 
    Write it as an imperative command (e.g. "Start videos with a direct question instead of a statement" or "Use shorter sentences in the first 5 seconds").
    Do not include any other text, greetings, or explanations. Just the rule.
    """
    
    try:
        client = ollama.Client(host=config.ollama_base_url)
        response = client.chat(
            model=config.ollama_model,
            messages=[{"role": "user", "content": prompt}],
        )
        new_rule = response.get('message', {}).get('content', '').strip()
        
        # Clean up the LLM output in case it ignored the rule
        new_rule = new_rule.replace('"', '').strip()
        if len(new_rule) > 10 and len(new_rule) < 150:
            logger.info(f"Self-Learning Engine generated new rule: {new_rule}")
            add_rule(new_rule)
        else:
            logger.warning("LLM generated a rule that was too long or invalid. Skipping.")
            
    except Exception as e:
        logger.error(f"Failed to run LLM critique: {e}")

