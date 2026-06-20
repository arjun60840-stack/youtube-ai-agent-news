"""
Auto-Learner Module for AI Daily News Agent.

Connects to YouTube via the Data API, fetches recent video performance
(views, likes, comments), and uses Llama 3 to deduce what works best.
It then saves this new insight into memory.json.

Usage:
    python auto_learner.py
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import ollama
from src.config import load_config
from src.logger import get_logger, setup_logging
from src.memory import add_rule

logger = get_logger("auto_learner")

# We need the readonly scope to fetch video stats
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

def _get_authenticated_service(config):
    creds = None
    token_path = "youtube_learner_token.json"

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and creds.valid:
        return build("youtube", "v3", credentials=creds)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            logger.warning("Token refresh failed: %s", exc)
            creds = None

    if not creds:
        secrets_path = config.youtube_client_secrets
        if not os.path.isfile(secrets_path):
            logger.error(f"Client secrets not found at {secrets_path}. Cannot auth.")
            return None
            
        logger.info("Opening browser to authenticate YouTube Auto-Learner...")
        flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
        creds = flow.run_local_server(port=0)
        
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def fetch_recent_performance(youtube):
    """Fetches the 5 most recent videos and their statistics."""
    logger.info("Fetching channel data...")
    # Get the user's channel ID
    channels_response = youtube.channels().list(mine=True, part="contentDetails").execute()
    if not channels_response.get("items"):
        logger.error("No channel found for the authenticated user.")
        return []
        
    uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # Fetch recent videos from the uploads playlist
    playlist_response = youtube.playlistItems().list(
        playlistId=uploads_playlist_id,
        part="snippet",
        maxResults=5
    ).execute()
    
    video_ids = [item["snippet"]["resourceId"]["videoId"] for item in playlist_response.get("items", [])]
    if not video_ids:
        logger.info("No videos found on the channel.")
        return []

    # Fetch statistics for those videos
    stats_response = youtube.videos().list(
        id=",".join(video_ids),
        part="snippet,statistics"
    ).execute()

    videos_data = []
    for item in stats_response.get("items", []):
        videos_data.append({
            "title": item["snippet"]["title"],
            "views": int(item["statistics"].get("viewCount", 0)),
            "likes": int(item["statistics"].get("likeCount", 0)),
            "comments": int(item["statistics"].get("commentCount", 0))
        })
    
    return videos_data

def _deduce_rule_with_ai(videos_data, config) -> str:
    """Asks Llama 3 to find a pattern in the analytics and propose a rule."""
    logger.info("Analyzing performance data with Llama 3...")
    
    data_str = ""
    for v in videos_data:
        data_str += f"- '{v['title']}': {v['views']} views, {v['likes']} likes, {v['comments']} comments\n"
        
    prompt = (
        "You are an AI YouTube Strategist managing an automated news channel.\n"
        "Here are the analytics for our most recent videos:\n\n"
        f"{data_str}\n\n"
        "Analyze this data. What type of video title or topic performed the best?\n"
        "Based on the best performing video, write a SINGLE, concise imperative programming rule (under 15 words) "
        "that tells the scriptwriter LLM to focus on similar topics or styles in the future.\n"
        "OUTPUT FORMAT: Return ONLY the English rule. Do not wrap it in quotes. No extra commentary."
    )
    
    client = ollama.Client(host=config.ollama_base_url)
    response = client.chat(
        model=config.ollama_model,
        messages=[{"role": "system", "content": prompt}]
    )
    
    return response["message"]["content"].strip().strip('"').strip("'")

def run_auto_learner(config):
    youtube = _get_authenticated_service(config)
    if not youtube:
        return
        
    videos_data = fetch_recent_performance(youtube)
    if not videos_data:
        print("[-] Not enough data to learn from.")
        return
        
    print("\n📊 Recent Video Performance:")
    for v in videos_data:
        print(f"   {v['views']} views | {v['title']}")
        
    rule = _deduce_rule_with_ai(videos_data, config)
    
    print(f"\n🧠 AI Auto-Learner deduced a new rule:\n   -> {rule}")
    add_rule(rule)
    print("\n[+] Added to memory.json!")

def main():
    config = load_config()
    setup_logging(config.logs_dir, "auto_learner")
    run_auto_learner(config)

if __name__ == "__main__":
    main()
