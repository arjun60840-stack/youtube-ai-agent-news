import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from ollama import Client

from src.config import Config
from src.news_collector import NewsStory

logger = logging.getLogger(__name__)


class SceneData(BaseModel):
    scene_number: int = Field(description="Sequential scene number")
    narration: str = Field(description="Spoken text in Hindi (with English tech terms)")
    subtitle: str = Field(description="Short, punchy on-screen text (max 5 words)")
    image_prompt: str = Field(description="Detailed image prompt matching the narration precisely")


class ScriptDataV2(BaseModel):
    title: str = Field(description="YouTube Video Title (SEO optimized, English)")
    description: str = Field(description="YouTube Description")
    tags: List[str] = Field(description="SEO tags")
    hashtags: List[str] = Field(description="Hashtags")
    pinned_comment: str = Field(description="Pinned comment to encourage discussion")
    scenes: List[SceneData] = Field(description="Ordered list of visual scenes")


MASTER_PROMPT = """You are the narrator of a professional Indian technology YouTube channel.
Your job is to explain technology news in a natural, engaging and easy-to-understand way.
The audience should feel that a knowledgeable tech reviewer is explaining the news to them personally.

==================================================
LANGUAGE STYLE
- Use 85% Hindi (written in Latin/English alphabet, e.g., "Google ne aaj...").
- Use 15% English ONLY for: Product names, Company names, Technical terms.
- Examples: Google, Gemini, ChatGPT, OpenAI, Microsoft, Apple, Android, iPhone, NVIDIA, AI, Machine Learning, Cloud, Software.

==================================================
PERSONALITY
- Sound: Friendly, Confident, Experienced, Trustworthy, Knowledgeable, Professional, Conversational, Helpful.
- AVOID: Do not sound like a News anchor, AI assistant, Textbook, Wikipedia article, Marketing advertisement, Robot.

==================================================
MANDATORY STRUCTURE
You must follow these 10 steps in exactly this order:
1. Greeting: Start the very first sentence with "Hello Friends"
2. News Summary: Immediately tell the viewer what happened. Example: "Aaj Google ne Gemini ke liye ek naya update launch kiya hai."
3. Company Introduction: Never assume the viewer knows the company. Example: "Google ke baare mein to aap sab jaante hi honge. Ye duniya ki sabse badi technology companies mein se ek hai." OR "Agar aapne is company ka naam pehli baar suna hai to bata dein ki ye company AI aur software products banati hai."
4. What Does The Company Do: Explain in simple language.
5. Transition: Use "Ab baat karte hain...", "Lekin yahan interesting baat ye hai...", "Ab sawal ye hai ki..."
6. Explain The Update: What is new? What changed?
7. Explain The Technology: Simple language. No jargon. Example: "Simple shabdon mein samjhein to..."
8. Explain User Impact: Why should viewers care? What changes for them?
9. Conclusion: Summarize the news briefly.
10. Subscribe: Only once, at the very end. "Yahi thi aaj ki technology update. Aisi aur technology news ke liye channel ko subscribe karna na bhoole."

==================================================
TRANSITION RULE
Every sentence must connect to the previous sentence.
Use words like: Ab, Lekin, Iske baad, Interesting baat ye hai, Simple shabdon mein, Iska matlab ye hua ki, Isi wajah se, Agar aap, Yahan dhyan dene wali baat.

==================================================
FORBIDDEN
Fact dumping, Wikipedia style, Random facts, Disconnected sentences, Repeating company names, Repeating subscribe message.

==================================================
SENTENCE STYLE
- Use very simple Hindi. Write like you are talking to a friend.
- Avoid technical jargon, long explanations, and complex sentences.
- Maximum sentence length: 15 words.
- If a sentence is confusing, rewrite it simpler.
- Never sound like a News anchor, AI assistant, or Wikipedia article.

==================================================
SPECIAL CHARACTER RULES
- NEVER use markdown, bullet points, hashtags, special characters, or URLs in the narration.
- Do not speak words like "Hashtag", "Asterisk", "Slash", "Bracket", "URL".

==================================================
SCENE SPLITTER RULES
- Every single sentence MUST be its own distinct scene.
- One sentence = One scene.
- For each scene, you must provide the narration, a short on-screen subtitle, and a highly detailed image prompt.

==================================================
IMAGE PROMPT RULES
- The image prompt MUST directly match the narration of that exact sentence.
- NEVER generate humans unless the news is specifically about a person. The image must explain the technology, not show a random human.
- Priority visuals: Official company branding, Product interfaces, Software dashboards, App screenshots, Technology diagrams, Product renders, Company logos, News-style graphics.
- If news mentions Google -> Google branding, Gemini UI, Google keynote.
- If news mentions OpenAI -> ChatGPT interface, OpenAI branding.
- If news mentions Microsoft -> Copilot interface, Microsoft branding.
- If news mentions Apple -> iPhone render, Apple keynote, iOS interface.
- If news mentions NVIDIA -> GPU render, AI datacenter graphics.
- FORBIDDEN IMAGES: woman portrait, man portrait, business person, microphone speaker, conference audience, random office worker, beautiful woman, professional headshot, cinematic portrait, Nature, Mountains, Travel, Romance, Random people, Generic AI wallpaper, Futuristic city, Unrelated technology art.
- Good Example: "Google Gemini branding on a sleek software dashboard interface, highly detailed, realistic, 16:9."

==================================================
OUTPUT FORMAT
You MUST output valid JSON ONLY, strictly conforming to this schema.
CRITICAL WARNING: Do NOT create multiple "scenes" arrays. There must be EXACTLY ONE "scenes" array containing all 10 scene objects.
{
  "title": "...",
  "description": "...",
  "tags": ["..."],
  "hashtags": ["..."],
  "pinned_comment": "...",
  "scenes": [
    {
      "scene_number": 1,
      "narration": "...",
      "subtitle": "...",
      "image_prompt": "..."
    },
    {
      "scene_number": 2,
      "narration": "...",
      "subtitle": "...",
      "image_prompt": "..."
    }
  ]
}
"""


def clean_json_string(raw_response: str) -> str:
    """Extract JSON from markdown code blocks if present."""
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_response, re.DOTALL)
    if match:
        return match.group(1)
    
    start = raw_response.find('{')
    end = raw_response.rfind('}')
    if start != -1 and end != -1:
        return raw_response[start:end+1]
        
    return raw_response

def _verify_script(client: Client, config: Config, script_text: str) -> bool:
    """Ask LLM to verify if the script answers the 5 required questions."""
    system_prompt = (
        "You are a strict QA reviewer. Read the provided script and determine if a 15-year-old can clearly understand:\n"
        "1. Who is the company?\n"
        "2. What does the company do?\n"
        "3. What happened?\n"
        "4. Why is it important?\n"
        "5. How does it affect users?\n\n"
        "If ALL 5 questions are clearly answered in simple language, reply with EXACTLY 'PASS'.\n"
        "If ANY answer is missing or confusing, reply with EXACTLY 'FAIL'."
    )
    try:
        response = client.chat(
            model=config.ollama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Script to review:\n\n{script_text}"}
            ],
            options={"temperature": 0.1}
        )
        return "PASS" in response['message']['content'].upper()
    except Exception as e:
        logger.warning(f"Verification call failed: {e}. Assuming PASS to avoid blocking.")
        return True


def _humanize_narration(client: Client, config: Config, text: str, prev_text: str = None) -> str:
    """Rewrite a single narration line to sound extremely natural and conversational, using context."""
    system_prompt = (
        "You are an expert Indian tech reviewer. The user will give you a script line to rewrite. "
        "Rewrite it to be EXTREMELY simple, as if explaining to a 15-year-old friend. "
        "Use 85% Hindi and 15% English. Maximum 15 words. "
        "Do NOT change the core meaning. Do NOT add hashtags, URLs, or markdown. "
        "The script must feel like one continuous conversation. Never jump from one fact to another abruptly. "
        "If a previous sentence is provided, ensure your rewritten sentence connects LOGICALLY and smoothly to it. "
        "Use transition words if appropriate (e.g., 'Ab', 'Lekin', 'Isi wajah se'). "
        "If the text contains a company introduction, keep the conversational tone like 'Dosto, ... ke baare mein aap jaante honge'. "
        "If the text ends with the subscription message, keep it exactly like that. "
        "Return ONLY the spoken text, nothing else."
    )
    
    user_msg = ""
    if prev_text:
        user_msg += f"PREVIOUS SENTENCE (for context): {prev_text}\n\n"
    user_msg += f"Rewrite THIS sentence to sound conversational and flow naturally:\n\n{text}"

    try:
        response = client.chat(
            model=config.ollama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            options={"temperature": 0.6}
        )
        return response['message']['content'].strip()
    except Exception as e:
        logger.warning(f"Failed to humanize narration: {e}")
        return text

def generate_script_v2(
    story: NewsStory,
    config: Config,
    date_str: str,
) -> ScriptDataV2:
    """Generate the V2 scene-by-scene script using Ollama."""
    
    output_path = config.scripts_dir / f"{date_str}_v2.json"
    
    if output_path.exists():
        logger.info(f"Found cached V2 script at {output_path}")
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ScriptDataV2(**data)
        except Exception as e:
            logger.warning(f"Failed to parse cached script: {e}")
            
    logger.info(f"Generating V2 Script using Ollama ({config.ollama_model})...")
    client = Client(host=config.ollama_base_url)
    
    user_prompt = f"""Write a professional Hindi tech news script for the following story:
Title: {story.title}
Source: {story.source}
Summary: {story.summary}

Remember: One sentence = One scene. Output ONLY valid JSON."""

    max_retries = 3
    for attempt in range(max_retries):
        logger.info(f"Ollama generation attempt {attempt + 1}/{max_retries}")
        response = client.chat(
            model=config.ollama_model,
            messages=[
                {"role": "system", "content": MASTER_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            format=ScriptDataV2.model_json_schema(),
            options={"temperature": 0.7, "num_predict": 4096}
        )
        
        raw_text = response['message']['content']
        json_str = clean_json_string(raw_text)
        
        try:
            parsed_data = json.loads(json_str)
            script_obj = ScriptDataV2(**parsed_data)
            
            # Combine narration for verification
            full_narration = " ".join([scene.narration for scene in script_obj.scenes])
            
            logger.info("Running script QA verification...")
            if not _verify_script(client, config, full_narration):
                logger.warning(f"Script validation FAILED on attempt {attempt + 1}. Retrying...")
                if attempt == max_retries - 1:
                    logger.error("Script validation failed on final attempt. Proceeding anyway but quality may be low.")
                else:
                    continue
            else:
                logger.info("Script validation PASSED.")
            
            # Second pass: Humanize narration
            logger.info("Performing humanization pass on script scenes...")
            prev_narration = None
            for scene in script_obj.scenes:
                humanized = _humanize_narration(client, config, scene.narration, prev_text=prev_narration)
                if humanized:
                    scene.narration = humanized
                    prev_narration = humanized
                else:
                    prev_narration = scene.narration
                    
            # Save cache
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(script_obj.model_dump(), f, indent=2, ensure_ascii=False)
                
            return script_obj
            
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON returned by LLM (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to parse LLM JSON response after {max_retries} attempts.\nRaw Response:\n{raw_text}")
                raise RuntimeError("LLM did not return valid JSON for the script.")
        except Exception as e:
            logger.warning(f"Unexpected error parsing LLM response on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to parse LLM JSON response after {max_retries} attempts.\nRaw Response:\n{raw_text}")
                raise RuntimeError("LLM did not return valid JSON for the script.")
            else:
                continue
