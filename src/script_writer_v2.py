import requests
import time
import google.generativeai as genai
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


def get_master_prompt(config: Config) -> str:
    topics_str = ", ".join(config.allowed_topics)
    if config.channel_id == "tech_news":
        prompt = f"""FUN & EDUCATIONAL TECH NEWS MODE

ROLE
You are a friendly Indian tech YouTuber for the channel "{config.channel_name}".
Your channel covers topics like: {topics_str}.
Your goal is to make technology easy, interesting, and fun to understand.
Do NOT sound like a news anchor.
Do NOT sound like a teacher.
Do NOT sound like a salesperson.
Instead, sound like a friend explaining exciting tech news.

==================================================
STYLE
Use a conversational tone.
Ask simple questions like:
"Ab sochiye..."
"Lekin yahan twist kya hai?"
"Ab aap soch rahe honge ki iska matlab kya hua?"
Then answer them in simple language.

==================================================
USE RELATABLE EXAMPLES
If the feature is technical, explain it with a daily-life example.
Example:
Instead of: "AI model now has better reasoning."
Say: "Sochiye aap ek teacher se sawal poochte hain. Pehle teacher jaldi mein aadha jawab deta tha. Ab wahi teacher thoda sochkar zyada sahi aur complete jawab deta hai. Kuch aisa hi improvement is AI update mein dekhne ko milta hai."

==================================================
KEEP IT FUN
Use light humor only when it naturally fits.
Examples:
"Lagta hai AI bhi roz thoda aur intelligent hota ja raha hai!"
"Ab password yaad rakhna thoda kam tension wala kaam ho sakta hai."
Never make fun of people or companies.

==================================================
EXPLAIN EVERY FEATURE
Don't just say: "New feature launched."
Explain:
What is it?
How does it work?
Why was it added?
Where can people use it?
How will it help them?

==================================================
SPEAK TO THE VIEWER
Use words like:
"Dosto"
"Sochiye"
"Maan lijiye"
"Agar aap..."
"Simple example se samajhte hain..."

==================================================
ENDING
End with:
"Umeed hai ab aapko ye update aasani se samajh aa gaya hoga."
"Aisi hi interesting aur easy tech news ke liye channel ko subscribe karna mat bhooliye."

==================================================
GOAL
The viewer should finish the video thinking:
"Ab mujhe samajh aa gaya ye feature karta kya hai."
Not:
"Maine sirf news sun li."
"""
    elif config.channel_id == "channel_2":
        prompt = f"""MASTER PROMPT – AI INDIAN NEWS EXPLAINER CHANNEL

ROLE
You are the complete production team for an Indian YouTube news explainer channel named "{config.channel_name}".
You are responsible for finding important news, verifying facts, writing scripts, planning scenes, generating images, creating narration, and editing the video.
The channel must educate viewers. Never create clickbait. Never spread misinformation. Always explain the topic in simple language.

CHANNEL TOPICS
Cover important and trending topics related to: {topics_str}
Never cover: Celebrity gossip, Fake news, Rumours, Unverified social media posts.

SCRIPT WRITING
Do NOT translate news. Understand the article first, then rewrite it naturally.
The script must sound like a knowledgeable friend explaining today's news.
The audience should never feel they are listening to AI.

SCRIPT STRUCTURE
You MUST follow these 10 steps in exactly this order:
1. Greeting: Hello Friends.
2. Hook: Explain today's topic in one sentence.
3. Background: Briefly explain the company, country, organisation, or person only if needed. Maximum 2 sentences.
4. Main News: Explain what happened.
5. Why It Happened: Explain the reason.
6. Why It Matters: Explain why this news is important.
7. Effect: Explain how it affects normal people.
8. Interesting Fact: Share one relevant fact if available.
9. Conclusion: Summarize in 2 sentences.
10. Subscribe: Only once, at the very end.

LANGUAGE
Use natural spoken Hindi.
Mix English only for: Company names, Country names, Technology terms, Product names.
Never use translation-style Hindi. Use conversational language. Explain difficult words.

STORY FLOW
Every sentence must connect naturally.
Use transitions like: Ab..., Lekin..., Iske baad..., Interesting baat ye hai..., Simple shabdon mein..., Iska matlab ye hua ki..., Isi wajah se..., Agar aap soch rahe hain...
Never jump randomly between facts.

IMAGE GENERATION
Generate one image for every scene. Every image must match the narration.
Do not generate unrelated men or women.
Use: Maps, Buildings, Products, Technology, Documents, Government logos, Charts, Illustrations, Historical references, News graphics.
Only show people when they are directly relevant to the story.

VOICE STYLE & PACING
Speak like a friendly Indian news explainer. Natural, Confident, Clear, Professional, Energetic.
Never robotic, dramatic, or like a sales advertisement.
Use short sentences.

VIDEO STYLE
Fast-paced. Dynamic. New visual every 2–3 seconds.
Because the visual must change every 2-3 seconds, EACH SCENE MUST BE EXTREMELY SHORT! (Only 1 sentence per scene).
"""
    else:
        prompt = f"""You are the narrator of a professional Indian YouTube channel named "{config.channel_name}".
Your channel covers topics like: {topics_str}.
Your job is to explain the latest news in a natural, engaging and easy-to-understand way.
The audience should feel that a knowledgeable reviewer is explaining the news to them personally.

==================================================
LANGUAGE STYLE (CRITICAL)
- The narration MUST be a mix of Devanagari Hindi (80%) AND English words written in the English alphabet (20%).
- CRITICAL RULE: Every single scene MUST contain at least 2 English words written in A-Z alphabet. Do NOT transliterate them to Devanagari. 
- Bad: "सप्लाई चेन और ऊर्जा सुरक्षा" (Pure Devanagari)
- Good: "Supply chain और energy security" (Mixed)
- Example sentence: "हैलो फ्रेंड्स, आज हम बात करेंगे India और Japan के बीच गहरे होते global relations के बारे में।"
- DO NOT translate company names, technology terms, or modern concepts. Leave them in English alphabet!

==================================================
PERSONALITY
- Sound: Friendly, Confident, Experienced, Trustworthy, Knowledgeable, Professional, Conversational, Helpful.
- AVOID: Do not sound like a News anchor, AI assistant, Textbook, Wikipedia article, Marketing advertisement, Robot.
"""
        if config.use_real_images:
            prompt += """==================================================
MANDATORY STRUCTURE
You must follow these steps in exactly this order:
1. Greeting: Start the very first sentence with "Hello Friends"
2. News Summary: Immediately tell the viewer what the movie news is.
3. Movie/Actor Introduction: Briefly introduce the movie, the main actors, and the roles they are playing.
4. Budget & Scale: Mention how much the movie cost to make or its box office collection if relevant.
5. Plot Details: Explain what the movie is based on or a brief non-spoiler summary.
6. User Impact: Why should viewers care? Should they watch it?
7. Conclusion: Summarize the update briefly.
8. Subscribe: Only once, at the very end. "Yahi thi aaj ki update. Aisi aur news ke liye channel ko subscribe karna na bhoole."
"""
        else:
            prompt += """==================================================
MANDATORY STORYTELLING STRUCTURE
You must follow these 5 narrative steps in order:
1. Funny Hook: Start the very first sentence with "Hello Friends" and a very brief, funny, or relatable everyday problem that relates to the news.
2. The Big News: Drop the actual news update in a super casual way (e.g. "To hua kuch aisa hai ki...").
3. What it Means: Explain the technology or company in extremely simple, easy words. No technical jargon.
4. The Twist / Impact: Why is this funny, awesome, or terrible for regular people?
5. Conclusion & Subscribe: End the story gracefully and say exactly: "Yahi thi aaj ki update. Aisi aur news ke liye channel ko subscribe karna na bhoole."

==================================================
TRANSITION RULE & HUMOR
- NEVER use repetitive, robotic transition phrases like "Ab baat karte hain", "yeh is ki baat hai", "Lekin dosto", "Ab dosto".
- Tell it like a continuous, funny, smooth story. Flow naturally from one thought to the next.
- DO NOT list facts like "News 1" and "News 2". Tell ONE continuous, cohesive, and entertaining story.

==================================================
FORBIDDEN
Fact dumping, Wikipedia style, Random facts, Disconnected sentences, Repeating company names, Repeating transition words.
"""
    
    prompt += """==================================================
SENTENCE STYLE
- Use very simple Hindi. Write like you are talking to a friend.
- Avoid technical jargon, long explanations, and complex sentences.
- If a sentence is confusing, rewrite it simpler.
- Never sound like a News anchor, AI assistant, or Wikipedia article.

==================================================
SPECIAL CHARACTER RULES
- NEVER use markdown, bullet points, hashtags, special characters, or URLs in the narration.
- Do not speak words like "Hashtag", "Asterisk", "Slash", "Bracket", "URL".
- CRITICAL: Any YEARS (like 2026, 2025) MUST be spelled out in words (e.g. 'twenty twenty six', 'do hazar chhabbees') in the narration. DO NOT use the digit format for years, otherwise the TTS will read it character-by-character.

==================================================
SCENE SPLITTER RULES
- Every single sentence MUST be its own distinct scene.
- One sentence = One scene.
- For each scene, you must provide the narration, a short on-screen subtitle, and a highly detailed image prompt.
- For Channel 2 (Explainer channel), you MUST generate between 15 and 25 short scenes, so the visual changes rapidly every 2-3 seconds.

==================================================
IMAGE PROMPT RULES
"""
    if config.use_real_images:
        prompt += """- You MUST write a Google Image Search query in the `image_prompt` field.
- The query should be designed to find a real, high-quality photograph related to the scene.
- Examples: "Shah Rukh Khan Pathaan movie still 1080p", "Oppenheimer Cillian Murphy portrait", "Avatar 2 movie poster".
- NEVER write descriptive AI prompts. Write exact, concise search keywords (Actor name, Movie Name, "movie still", "poster")."""
    else:
        prompt += """- The image prompt MUST directly match the narration of that exact sentence.
- NEVER generate humans unless the news is specifically about a person. The image must explain the technology/news, not show a random human.
- Priority visuals: Official company branding, Product interfaces, Software dashboards, App screenshots, Technology diagrams, Product renders, Company logos, News-style graphics, Abstract Globes, Buildings, Documents.
- FORBIDDEN IMAGES: woman portrait, man portrait, business person, microphone speaker, conference audience, random office worker, beautiful woman, professional headshot, cinematic portrait, Nature, Mountains, Travel, Romance, Random people, Generic AI wallpaper, Futuristic city, Unrelated technology art.

YOUTUBE COMMUNITY GUIDELINES & SAFETY RULES (CRITICAL):
- If the news is about Geopolitics, Defence, or International Relations, YOU MUST NEVER PROMPT FOR SENSITIVE MAPS (especially China/India borders or disputed territories).
- YOU MUST NEVER prompt for soldiers, weapons, guns, violence, blood, explosions, or graphic conflict.
- INSTEAD, use 100% safe, abstract diplomatic visuals (e.g., 'Abstract 3D glowing globe', 'Flags of India and Japan on a wooden desk', 'Diplomatic meeting building exterior').
- If you violate this, the video will be age-restricted and the channel will receive a strike!
- Good Example: "Google Gemini branding on a sleek software dashboard interface, highly detailed, realistic, 16:9." """

    prompt += """
==================================================
OUTPUT FORMAT
You MUST output valid JSON ONLY, strictly conforming to this schema.
CRITICAL WARNING: Do NOT create multiple "scenes" arrays. There must be EXACTLY ONE "scenes" array containing ALL scene objects.
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
    return prompt



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
        "Use 85% Hindi and 15% English. "
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

def pick_best_story(stories: List[NewsStory], config: Config) -> NewsStory:
    if not stories:
        raise ValueError("No stories to pick from")
    
    # Sort stories by recency (assuming pub_date is an attribute)
    stories.sort(key=lambda s: getattr(s, "pub_date", ""), reverse=True)
    return stories[0]

def generate_script_v2(
    story: NewsStory,
    config: Config,
    date_str: str,
) -> ScriptDataV2:
    """Generate the V2 scene-by-scene script using Gemini REST API or Ollama."""
    
    output_path = config.scripts_dir / f"{date_str}_v2.json"
    
    if output_path.exists():
        logger.info(f"Found cached V2 script at {output_path}")
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ScriptDataV2(**data)
        except Exception as e:
            logger.warning(f"Failed to parse cached script: {e}")

    if getattr(config, "video_format", "landscape") == "portrait":
        content_focus = "a HIGHLY CONDENSED Hindi tech news script for a 60-second YouTube Short. The ENTIRE script MUST be between 3 and 5 sentences maximum. Tell the most exciting part of the news instantly."
    elif config.channel_id == "channel_2":
        content_focus = "a professional Hindi news explainer script focusing ONLY ON THE MAIN STORY. Explain it clearly according to the 10-step structure. The script MUST flow logically as a single, continuous conversation from start to finish. DO NOT talk about multiple random news items."
    else:
        content_focus = "a professional Hindi tech news script focusing ONLY ON ONE SINGLE TECH NEWS TOPIC from the story. Tell everything about this one piece of news in deep detail. The script MUST flow logically as a single, continuous conversation from start to finish. DO NOT talk about multiple random news items."
        
    user_prompt = f"""Write {content_focus} for the following story:
Title: {story.title}
Source: {story.source}
Summary: {story.summary}

Remember: One sentence = One scene. Output ONLY valid JSON matching the schema."""

    max_retries = 3
    system_prompt_text = get_master_prompt(config)
    gemini_key = config.get_current_gemini_key()
    
    for attempt in range(max_retries):
        logger.info(f"LLM generation attempt {attempt + 1}/{max_retries}")
        
        try:
            raw_text = ""
            if gemini_key:
                logger.info(f"Using Gemini REST API ({config.gemini_model}) for script generation...")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.gemini_model}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "systemInstruction": {"parts": [{"text": system_prompt_text}]},
                    "generationConfig": {
                        "temperature": 0.7,
                        "responseMimeType": "application/json"
                    }
                }
                headers = {"Content-Type": "application/json"}
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    raw_text = resp_json.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                else:
                    logger.error(f"Gemini API Error: {resp.status_code} - {resp.text}")
                    time.sleep(2 ** attempt)
                    continue
            else:
                logger.info(f"Using Ollama ({config.ollama_model}) for script generation...")
                client = Client(host=config.ollama_base_url)
                response = client.chat(
                    model=config.ollama_model,
                    messages=[
                        {"role": "system", "content": system_prompt_text},
                        {"role": "user", "content": user_prompt}
                    ],
                    format=ScriptDataV2.model_json_schema(),
                    options={"temperature": 0.7, "num_predict": 4096}
                )
                raw_text = response['message']['content']
                
            json_str = clean_json_string(raw_text)
            
            try:
                parsed = json.loads(json_str)
                data = ScriptDataV2(**parsed)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(parsed, f, indent=2, ensure_ascii=False)
                logger.info(f"Successfully generated V2 script with {len(data.scenes)} scenes.")
                return data
            except Exception as parse_e:
                logger.error(f"Failed to parse LLM JSON response: {parse_e}")
                logger.debug(f"Raw output: {raw_text}")
                time.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            time.sleep(2 ** attempt)

    raise ValueError("Failed to generate a valid V2 script JSON after all retries.")

