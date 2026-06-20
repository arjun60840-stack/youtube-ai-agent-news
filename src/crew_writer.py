import json
import logging
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from crewai import Agent, Task, Crew, Process, LLM

from src.config import Config
from src.news_collector import NewsStory
from src.script_writer import ScriptData
from src.master_prompt import MASTER_DIRECTOR_PROMPT

logger = logging.getLogger(__name__)

# ======================================================================
# SCRIPT SANITIZATION & VALIDATION (BUG 1 FIX)
# ======================================================================

def sanitize_script(script_text: str) -> str:
    """
    Aggressively remove HTML, markdown, scene labels, and any non-spoken
    formatting from LLM output. This is the LAST LINE OF DEFENSE against
    hallucinated HTML scripts reaching the voice/image pipeline.
    """
    if not script_text:
        return ""
    # 1. Remove ALL HTML tags (covers <div>, <p>, <img>, <br>, <strong>, etc.)
    clean = re.sub(r'<[^>]+>', ' ', script_text)
    # 2. Remove HTML entities
    clean = re.sub(r'&[a-zA-Z]+;', ' ', clean)
    clean = re.sub(r'&#\d+;', ' ', clean)
    # 3. Remove CSS-like inline styles that survive tag stripping
    clean = re.sub(r"style='[^']*'", ' ', clean)
    clean = re.sub(r'style="[^"]*"', ' ', clean)
    # 4. Remove URLs
    clean = re.sub(r'https?://\S+', ' ', clean)
    # 5. Remove markdown formatting
    clean = clean.replace('*', '')
    clean = clean.replace('#', '')
    clean = clean.replace('`', '')
    # 6. Remove "Scene X:" / "Hook:" / "Visual:" labels
    clean = re.sub(r'(?i)\b(scene|hook|visual|narration|subtitle|image prompt)\s*\d*\s*[:\-]*', ' ', clean)
    # 7. Remove placeholder image references
    clean = re.sub(r'src=[\'"][^\'"]*[\'"]', ' ', clean)
    clean = re.sub(r'alt=[\'"][^\'"]*[\'"]', ' ', clean)
    # 8. Collapse multiple spaces and newlines into single space
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def validate_script(script_text: str) -> bool:
    """
    Returns True if the script is valid spoken text.
    Returns False if it contains HTML, is too short, or is gibberish.
    """
    if not script_text or len(script_text.strip()) < 50:
        logger.error(f"Script validation FAILED: too short ({len(script_text)} chars)")
        return False
    # Check for HTML tags
    if re.search(r'<(div|p|img|br|span|strong|h[1-6]|a|ul|li|table|td|tr)\b', script_text, re.IGNORECASE):
        logger.error("Script validation FAILED: contains HTML tags")
        return False
    # Check for CSS
    if re.search(r'style\s*=\s*[\'"]', script_text, re.IGNORECASE):
        logger.error("Script validation FAILED: contains CSS styles")
        return False
    # Check for img src
    if re.search(r'src\s*=\s*[\'"]', script_text, re.IGNORECASE):
        logger.error("Script validation FAILED: contains image sources")
        return False
    return True


def sanitize_thumbnail_text(text: str) -> str:
    """Sanitize thumbnail text: strip HTML, limit to 5 words, ASCII-safe."""
    if not text:
        return "TECH NEWS TODAY"
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'[^\w\s]', '', clean)
    words = clean.split()[:5]
    result = ' '.join(words).upper().strip()
    return result if len(result) > 3 else "TECH NEWS TODAY"


class ScriptOutputSchema(BaseModel):
    titles: List[str] = Field(description="5 Catchy SEO YouTube Titles")
    hook: str = Field(description="Massive, high-energy hook in first 5 seconds")
    script: str = Field(description="The final validated Hinglish script (>=90% Hindi). MUST be plain spoken text only. NO HTML, NO markdown, NO formatting.")
    storyboard: str = Field(description="Scene-by-scene storyboard")
    voiceover_script: str = Field(description="Voiceover pacing and tone notes")
    editing_instructions: str = Field(description="Instructions for cuts, zoom effects, B-roll")
    subtitle_file_instruction: str = Field(description="Instructions for subtitle syncing")
    thumbnail_prompt: str = Field(description="High CTR thumbnail concept")
    seo_package: str = Field(description="SEO strategy summary")
    final_production_checklist: str = Field(description="Checklist for final checks")
    description: str = Field(description="YouTube Description including Summary, Impact, CTA, Keywords, Hashtags")
    tags: List[str] = Field(description="SEO tags")
    hashtags: List[str] = Field(description="hashtags")
    thumbnail_text: str = Field(description="Thumbnail text, maximum 5 words, PLAIN TEXT ONLY")
    pinned_comment: str = Field(description="Topic-specific pinned comment to encourage discussion")


def _build_script_data(data: dict) -> ScriptData:
    """Build ScriptData from raw dict with sanitization applied to all fields."""
    script = sanitize_script(data.get("script", ""))
    thumbnail_text = sanitize_thumbnail_text(data.get("thumbnail_text", ""))
    
    return ScriptData(
        script=script,
        titles=data.get("titles", ["AI Tech News"]),
        description=data.get("description", ""),
        tags=data.get("tags", []),
        hashtags=data.get("hashtags", []),
        hook=data.get("hook", ""),
        storyboard=data.get("storyboard", ""),
        voiceover_script=data.get("voiceover_script", ""),
        editing_instructions=data.get("editing_instructions", ""),
        subtitle_file_instruction=data.get("subtitle_file_instruction", ""),
        thumbnail_prompt=data.get("thumbnail_prompt", ""),
        seo_package=data.get("seo_package", ""),
        final_production_checklist=data.get("final_production_checklist", ""),
        thumbnail_text=thumbnail_text,
        pinned_comment=data.get("pinned_comment", ""),
    )


def generate_script_crew(
    news_stories: List[NewsStory],
    config: Config,
    date_str: str,
) -> ScriptData:
    """
    Generate a YouTube news script using a CrewAI multi-agent team.
    """
    logger.info("Initializing CrewAI Agents with Ollama (%s)", config.ollama_model)

    output_path = config.scripts_dir / f"{date_str}_crew.json"
    
    # ======================================================================
    # CACHE VALIDATION (BUG 5 FIX)
    # Load cache ONLY if script inside is valid (no HTML garbage)
    # ======================================================================
    if output_path.exists():
        logger.info(f"Found cached script at {output_path}, validating...")
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            script_data = _build_script_data(data)
            
            if validate_script(script_data.script):
                logger.info("Cached script is VALID. Using it.")
                return script_data
            else:
                logger.warning("Cached script is INVALID (contains HTML/garbage). DELETING cache and regenerating.")
                output_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to load cached script: {e}. Deleting and regenerating.")
            output_path.unlink(missing_ok=True)

    llm = LLM(
        model=f"ollama/{config.ollama_model}",
        base_url=config.ollama_base_url
    )

    from src.memory import load_memory
    learned_rules = load_memory()
    memory_string = ""
    if learned_rules:
        memory_string = "\n\nUSER'S LEARNED PREFERENCES (YOU MUST OBEY THESE STRICTLY):\n"
        for i, rule in enumerate(learned_rules, 1):
            memory_string += f"{i}. {rule}\n"

    # ---------------------------------------------------------
    # 1. Define the Agents
    # ---------------------------------------------------------
    research_agent = Agent(
        role="Research Agent",
        goal="Select ONE highest-scoring tech story from the provided news.",
        backstory=MASTER_DIRECTOR_PROMPT + memory_string,
        verbose=True,
        allow_delegation=False,
        llm=llm
    )
    
    fact_check_agent = Agent(
        role="Fact Check Agent",
        goal="Verify facts of the selected story. Ensure no rumors or leaks.",
        backstory=MASTER_DIRECTOR_PROMPT + memory_string,
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    scriptwriter = Agent(
        role="Qwen3 Script Writer",
        goal="Write the initial news script focusing on facts. OUTPUT MUST BE PLAIN SPOKEN TEXT. NO HTML. NO MARKDOWN. NO FORMATTING.",
        backstory=MASTER_DIRECTOR_PROMPT + memory_string,
        verbose=True,
        allow_delegation=False,
        llm=llm
    )
    
    humanizer = Agent(
        role="Script Humanizer",
        goal="Rewrite the script to sound exactly like Technical Guruji or Tech Burner. MUST be 90% Hindi. OUTPUT PLAIN SPOKEN TEXT ONLY. ABSOLUTELY NO HTML TAGS, NO <div>, NO <p>, NO <img>.",
        backstory=MASTER_DIRECTOR_PROMPT + "\nFOCUS: Inject emotion, 'Dosto', curiosity loops, and flow. English ONLY for Company/Product/Tech names.\nCRITICAL: Your output must be PLAIN SPOKEN TEXT. If you output any HTML tags, the entire pipeline will crash." + memory_string,
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    director = Agent(
        role="Scene Planner & Image Prompt Generator",
        goal="Design the visual storyboard and generate ComfyUI image prompts.",
        backstory=MASTER_DIRECTOR_PROMPT + memory_string,
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    seo_specialist = Agent(
        role="SEO Agent",
        goal="Optimize the title, generate 5 titles, SEO description, and thumbnail text. Thumbnail text must be maximum 5 plain words.",
        backstory=MASTER_DIRECTOR_PROMPT + memory_string,
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    # ---------------------------------------------------------
    # Prepare the Input Data
    # ---------------------------------------------------------
    stories_text = ""
    for idx, story in enumerate(news_stories, start=1):
        stories_text += f"\nStory {idx}: {story.title} (Source: {story.source})\nSummary: {story.summary}\nLink: {story.link}\n"

    # ---------------------------------------------------------
    # 2. Define the Tasks
    # ---------------------------------------------------------
    task_research = Task(
        description=f"Analyze these tech news stories ({date_str}):\n{stories_text}\nScore every story out of 100 based on: Freshness, Search Demand, Virality, Indian Audience Interest, Engagement Potential. Choose the absolute highest scoring story.",
        expected_output="A deep-dive research report on the ONE highest scoring story, including its score breakdown.",
        agent=research_agent
    )

    task_fact_check = Task(
        description="Verify facts of the selected story. Ensure no rumors or unverified leaks.",
        expected_output="Verified facts for the story.",
        agent=fact_check_agent
    )

    task_write = Task(
        description="Write the raw base script for the verified story. CRITICAL: Target between 130 and 160 words. Output PLAIN SPOKEN TEXT ONLY. No HTML tags. No <div>. No <p>. No markdown. Just spoken words.",
        expected_output="A raw base script in PLAIN TEXT format. No HTML. Word count between 130 and 160 words.",
        agent=scriptwriter
    )
    
    task_humanize = Task(
        description="Take the base script and HUMANIZE it. Make it sound like a viral YouTuber. 90% Hindi, 10% English. Target between 130 and 160 words. NO internal markdown like 'Scene 1' or '*'. NO HTML TAGS. PLAIN SPOKEN WORDS ONLY.",
        expected_output="A passionate humanized script. >=90% Hindi. PLAIN TEXT ONLY. Word count between 130 and 160 words.",
        agent=humanizer
    )

    task_direct = Task(
        description="Using the Humanized Script, design a scene-by-scene storyboard. Generate explicit ComfyUI image prompts for each scene using Juggernaut XL style.",
        expected_output="A complete visual storyboard with detailed ComfyUI prompts.",
        agent=director
    )

    task_seo = Task(
        description="Generate 5 catchy titles, an SEO Hindi description, and assemble all parts into the final JSON output. thumbnail_text must be maximum 5 PLAIN WORDS (no HTML).",
        expected_output="Final structured JSON output.",
        agent=seo_specialist,
        output_json=ScriptOutputSchema
    )

    # ---------------------------------------------------------
    # 3. Form the Crew and Execute
    # ---------------------------------------------------------
    crew = Crew(
        agents=[research_agent, fact_check_agent, scriptwriter, humanizer, director, seo_specialist],
        tasks=[task_research, task_fact_check, task_write, task_humanize, task_direct, task_seo],
        process=Process.sequential,
        memory=False,
        verbose=True
    )

    logger.info("Starting CrewAI execution. This will take some time as agents collaborate...")
    result = crew.kickoff()

    output_path = config.scripts_dir / f"{date_str}_crew.json"
    
    try:
        if hasattr(result, "to_dict"):
            data = result.to_dict()
        elif isinstance(result, dict):
            data = result
        else:
            data = json.loads(str(result))
            
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        script_data = _build_script_data(data)
        
        # ======================================================================
        # POST-GENERATION VALIDATION (BUG 1 FIX)
        # If the script STILL has HTML after sanitization, reject it entirely
        # ======================================================================
        if not validate_script(script_data.script):
            logger.error("CRITICAL: Generated script failed validation even after sanitization. Deleting cache.")
            output_path.unlink(missing_ok=True)
            raise ValueError("Script generation produced invalid output (HTML/garbage). Retrying.")
            
        return script_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse CrewAI output as JSON: {e}")
        raise ValueError(f"CrewAI output was not valid JSON: {e}")
    except Exception as e:
        logger.error(f"Failed to process CrewAI output: {e}")
        raise
