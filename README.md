# AI Daily News YouTube Agent

A fully autonomous, multi-channel AI agent that automatically generates and uploads daily news videos and YouTube Shorts. 

This project fetches the latest trending news, writes a professional Hindi script, generates a high-quality voiceover, creates stunning AI visuals via ComfyUI, stitches them into a dynamic video using FFmpeg, and automatically uploads the final result to YouTube—completely hands-free.

## 🚀 Features

- **Multi-Channel Support:** Run completely separate pipelines with isolated caching, distinct topics, and different configuration files (e.g., Tech News channel vs. Explainer channel).
- **YouTube Shorts:** Fully supports vertical (9:16) video generation with highly condensed, fast-paced scripts tailored for the 60-second limit.
- **Automated AI Visuals:** Integrates with local ComfyUI to automatically generate dynamic scenes. Features auto-recovery, programmatic text overlays, and fallback web-scraping if ComfyUI fails.
- **Smart Script Writing:** Uses LLMs to craft engaging scripts. Enforces rules like spelling out years in words (so TTS reads them naturally instead of character-by-character) and isolating the core story.
- **Automated Voiceover (TTS):** Integrated with both `edge-tts` and Sarvam TTS for hyper-realistic Hindi and Hinglish voiceovers.
- **Resilient YouTube Uploader:** Automatically refreshes OAuth tokens and includes robust retry logic for network drops (`WinError 10054`) using resumable uploads.
- **Zero-Touch Automation:** Includes a Windows startup script (`RunAINews.bat`) that triggers the pipelines sequentially on system boot, waiting for network connectivity before starting.

## 📂 Project Structure

```
ai_news_agent/
│
├── channels/                 # Multi-channel configurations and OAuth tokens
│   ├── channel_2/
│   │   ├── config.json       # Channel-specific overrides (privacy, topic, etc.)
│   │   └── youtube_token.json
│
├── src/                      # Core pipeline modules
│   ├── config.py             # Global and channel configuration loading
│   ├── image_generator_v2.py # ComfyUI integration and text overlay logic
│   ├── news_collector.py     # RSS fetching and Google News scraping
│   ├── script_writer_v2.py   # LLM prompt engineering and script JSON formatting
│   ├── video_generator_v2.py # FFmpeg dynamic zoom-pan and subtitle burning
│   ├── voice_generator_v2.py # Text-To-Speech generation
│   ├── youtube_uploader.py   # Resumable YouTube API uploads
│   └── quality_reviewer_v2.py# Automated validation before rendering
│
├── main.py                   # Master orchestrator script
├── requirements.txt          # Python dependencies
└── README.md
```

## 🛠️ Prerequisites

1. **Python 3.10+**
2. **FFmpeg** (Must be added to system PATH)
3. **ComfyUI** (Configured locally with `juggernautXL_ragnarok.safetensors` or your preferred checkpoint)
4. **Google Cloud Console Project** (YouTube Data API v3 enabled with OAuth Client ID)

## 🏃‍♂️ Usage

**Run the default channel (Landscape Video):**
```bash
python main.py
```

**Run a specific channel as a YouTube Short:**
```bash
python main.py --channel tech_news --portrait
```

**Run all channels sequentially (Background Automation):**
You can use the provided script to sequentially run multiple pipelines without overlapping cache issues.
```bash
python scratch/run_all.py
```

## 🧠 Automated Startup
The project can be configured to run automatically on Windows Logon via a `.bat` file placed in the user's `Startup` folder, ensuring daily videos are created simply by turning on the PC.
