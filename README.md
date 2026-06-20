# 🤖 AI Daily News YouTube Agent

A fully automated, **100% free**, local AI system that runs daily on Windows 11 to:

1. 📰 **Collect** trending tech news from Google News RSS
2. ✍️ **Write** professional YouTube scripts using Ollama (llama3:8b)
3. 🔊 **Generate** natural-sounding narration with edge-tts
4. 🖼️ **Create** branded image slides with Pillow
5. 🎬 **Assemble** 1920×1080 MP4 videos with FFmpeg (transitions + subtitles)
6. 📤 **Upload** to YouTube automatically via Data API v3
7. ⏰ **Schedule** daily runs at 7:00 AM via Windows Task Scheduler

---

## 📋 Requirements

| Component        | Details                                      |
|-----------------|----------------------------------------------|
| **OS**          | Windows 11                                   |
| **GPU**         | NVIDIA RTX 3050 6GB (or any CUDA GPU)        |
| **RAM**         | 24GB recommended                             |
| **Python**      | 3.10 or later                                |
| **FFmpeg**      | Latest version                               |
| **Ollama**      | Latest version with `llama3:8b` model        |
| **Internet**    | Required (news, TTS, YouTube upload)         |

---

## 🚀 Quick Start

### 1. Clone or Download the Project

```bash
cd C:\Users\YourName\Projects
# Place the ai_news_agent folder here
```

### 2. Run Setup

Double-click `setup.bat` or run from terminal:

```bash
setup.bat
```

This will:
- ✅ Create a Python virtual environment
- ✅ Install all dependencies
- ✅ Create project directories
- ✅ Check for FFmpeg and Ollama
- ✅ Pull the llama3:8b model
- ✅ Create `.env` from template

### 3. Run the Agent

```bash
# Activate virtual environment
venv\Scripts\activate

# Run without YouTube upload (test first!)
python main.py --skip-upload

# Run the full pipeline with upload
python main.py
```

---

## 🔧 Installation Details

### FFmpeg Installation

Choose one method:

**Method 1 — winget (Recommended)**
```powershell
winget install Gyan.FFmpeg
```

**Method 2 — Manual Download**
1. Download from [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/)
2. Download the "ffmpeg-release-essentials.zip"
3. Extract to `C:\ffmpeg`
4. Add `C:\ffmpeg\bin` to your system PATH:
   - Open Start → "Environment Variables"
   - Under System Variables, find `Path`
   - Click Edit → New → `C:\ffmpeg\bin`
   - Click OK
5. Verify: `ffmpeg -version`

**Method 3 — Chocolatey**
```powershell
choco install ffmpeg
```

### Ollama Installation

1. Download from [ollama.com/download/windows](https://ollama.com/download/windows)
2. Run the installer
3. Pull the model:
```bash
ollama pull llama3:8b
```
4. Verify Ollama is running:
```bash
ollama list
```

> **Note:** Ollama runs as a background service. The `llama3:8b` model requires ~4.7GB VRAM. If you have memory issues, use the quantized version: `ollama pull llama3:8b-q4_0`

### YouTube API Setup

1. **Create a Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Click "Select a project" → "New Project"
   - Name it "AI Daily News Agent"
   - Click "Create"

2. **Enable YouTube Data API v3**
   - Go to "APIs & Services" → "Library"
   - Search "YouTube Data API v3"
   - Click "Enable"

3. **Configure OAuth Consent Screen**
   - Go to "APIs & Services" → "OAuth consent screen"
   - Select "External" → Click "Create"
   - Fill in App name: "AI Daily News Agent"
   - Add your email as User support email and Developer contact
   - Click "Save and Continue" through all steps
   - Under "Test users" → Add your Google email

4. **Create OAuth Credentials**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Application type: "Desktop app"
   - Name: "AI Daily News Agent"
   - Click "Create"
   - Click "Download JSON"
   - Save the file as `config/client_secrets.json` in your project

5. **First Run Authorization**
   - The first time you run with YouTube upload, a browser window will open
   - Sign in with your Google account
   - Click "Continue" (even if it says "unverified")
   - Click "Continue" again to grant permissions
   - The token will be saved to `config/youtube_token.json` for future runs

> **Important:** Keep `config/client_secrets.json` and `config/youtube_token.json` private. Never commit them to git.

---

## ⚙️ Configuration

All settings are in the `.env` file. Copy from template if not done:

```bash
copy .env.example .env
```

### Key Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `llama3:8b` | Ollama model for script generation |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `TTS_VOICE` | `en-US-GuyNeural` | Edge TTS voice |
| `TTS_RATE` | `+0%` | Speech rate adjustment |
| `YOUTUBE_PRIVACY` | `private` | Upload visibility (private/unlisted/public) |
| `YOUTUBE_CATEGORY` | `28` | Category (28 = Science & Technology) |
| `CHANNEL_NAME` | `AI Daily News` | Branding on video slides |
| `FFMPEG_PATH` | `ffmpeg` | Path to FFmpeg binary |

### Available TTS Voices

| Voice | Description |
|-------|-------------|
| `en-US-GuyNeural` | American English, Male (default) |
| `en-US-JennyNeural` | American English, Female |
| `en-US-AriaNeural` | American English, Female (news style) |
| `en-GB-RyanNeural` | British English, Male |
| `en-GB-SoniaNeural` | British English, Female |
| `en-AU-WilliamNeural` | Australian English, Male |

---

## 📁 Project Structure

```
ai_news_agent/
├── src/                          # Source code modules
│   ├── __init__.py               # Package initializer
│   ├── config.py                 # Configuration management
│   ├── logger.py                 # Logging setup (file + console)
│   ├── news_collector.py         # Google News RSS scraper
│   ├── script_writer.py          # Ollama LLM script generator
│   ├── voice_generator.py        # edge-tts voice synthesizer
│   ├── subtitle_generator.py     # SRT → ASS subtitle converter
│   ├── image_generator.py        # Pillow slide creator
│   ├── video_generator.py        # FFmpeg video assembler
│   ├── youtube_uploader.py       # YouTube Data API uploader
│   └── scheduler.py              # Windows Task Scheduler manager
├── news/                         # Collected news JSON files
├── scripts/                      # Generated script JSON files
├── audio/                        # TTS audio files (MP3 + SRT)
├── images/                       # Generated slide images
├── videos/                       # Final MP4 videos + ASS subtitles
├── logs/                         # Daily log files
├── config/                       # OAuth credentials (gitignored)
├── main.py                       # Entry point / pipeline orchestrator
├── requirements.txt              # Python dependencies
├── setup.bat                     # Automated setup script
├── .env.example                  # Environment variable template
└── README.md                     # This file
```

---

## 🖥️ CLI Commands

```bash
# Full pipeline (collect → script → voice → slides → video → upload)
python main.py

# Skip YouTube upload (for testing)
python main.py --skip-upload

# Re-run for a specific date
python main.py --date 2026-06-01

# Set up daily 7:00 AM schedule
python main.py --schedule

# Check if schedule exists
python main.py --check-schedule

# Remove the schedule
python main.py --unschedule
```

---

## ⏰ Daily Scheduling

Set up automatic daily runs at 7:00 AM:

```bash
python main.py --schedule
```

This creates a Windows Task Scheduler task named `AI_Daily_News_Agent`. To verify:

1. Open Task Scheduler (search "Task Scheduler" in Start)
2. Look for `AI_Daily_News_Agent` in the task list
3. Check the "Triggers" tab confirms "Daily at 7:00 AM"

To remove:
```bash
python main.py --unschedule
```

> **Note:** Scheduling may require administrator privileges. Right-click your terminal and "Run as administrator" if needed.

---

## 📊 Pipeline Flow

```
┌─────────────────┐
│  Google News RSS │
│  (3 feeds)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  News Collector  │ → news/YYYY-MM-DD.json
│  (Top 5 stories)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Script Writer   │ → scripts/YYYY-MM-DD.json
│  (Ollama LLM)   │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────┐
│ Voice  │ │   Image    │
│ (TTS)  │ │ Generator  │
│        │ │ (7 slides) │
└───┬────┘ └─────┬──────┘
    │             │
    ▼             │
┌────────┐        │
│Subtitle│        │
│  (ASS) │        │
└───┬────┘        │
    │             │
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │   FFmpeg     │ → videos/YYYY-MM-DD.mp4
    │ (2-pass)    │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │  YouTube     │
    │  Uploader    │
    └─────────────┘
```

---

## 🔍 Troubleshooting

### "Ollama connection refused"
- Make sure Ollama is running: `ollama serve`
- Check the base URL in `.env` matches `http://localhost:11434`

### "FFmpeg not found"
- Install FFmpeg (see installation section)
- Make sure `ffmpeg` is on your PATH: `ffmpeg -version`

### "No news stories collected"
- Check your internet connection
- Google News RSS feeds may be temporarily unavailable
- Try running again in a few minutes

### "YouTube upload failed"
- Ensure `config/client_secrets.json` exists
- Delete `config/youtube_token.json` and re-authorize
- Check your YouTube API quota at [Google Cloud Console](https://console.cloud.google.com/)

### "Out of VRAM"
- Use a smaller model: set `OLLAMA_MODEL=llama3:8b-q4_0` in `.env`
- Close other GPU-intensive applications

### Video has no audio
- Check that `audio/YYYY-MM-DD.mp3` was generated
- Ensure edge-tts has internet access
- Try a different TTS voice in `.env`

---

## 📄 License

This project is open source and free to use. All tools and APIs used are free:

| Tool | License / Cost |
|------|---------------|
| Python | PSF License (Free) |
| Ollama + llama3 | MIT + Meta License (Free) |
| edge-tts | MIT (Free) |
| Pillow | HPND (Free) |
| FFmpeg | LGPL/GPL (Free) |
| YouTube Data API | Free (10,000 quota/day) |
| feedparser | BSD (Free) |

---

## 🤝 Contributing

Feel free to fork and improve! Some ideas:
- Add more news sources (Reddit, Hacker News, TechCrunch RSS)
- Add background music to videos
- Implement A/B testing for video titles
- Add analytics tracking for upload performance
- Support multiple languages
- Add thumbnail generation for YouTube
