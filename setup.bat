@echo off
REM ================================================================
REM  AI Daily News YouTube Agent — Setup Script
REM  This script sets up the complete development environment.
REM ================================================================

echo.
echo ============================================================
echo   AI Daily News YouTube Agent — Setup
echo ============================================================
echo.

REM ----------------------------------------------------------------
REM 1. Check Python installation
REM ----------------------------------------------------------------
echo [1/6] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not on PATH.
    echo         Download from: https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
python --version
echo [OK] Python found.
echo.

REM ----------------------------------------------------------------
REM 2. Create virtual environment
REM ----------------------------------------------------------------
echo [2/6] Creating virtual environment...
if exist "venv" (
    echo [INFO] Virtual environment already exists. Skipping creation.
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)
echo.

REM ----------------------------------------------------------------
REM 3. Activate venv and install dependencies
REM ----------------------------------------------------------------
echo [3/6] Installing Python dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.
echo.

REM ----------------------------------------------------------------
REM 4. Create output directories
REM ----------------------------------------------------------------
echo [4/6] Creating project directories...
if not exist "news" mkdir news
if not exist "scripts" mkdir scripts
if not exist "audio" mkdir audio
if not exist "images" mkdir images
if not exist "videos" mkdir videos
if not exist "logs" mkdir logs
if not exist "config" mkdir config
echo [OK] Directories created.
echo.

REM ----------------------------------------------------------------
REM 5. Check FFmpeg
REM ----------------------------------------------------------------
echo [5/6] Checking FFmpeg installation...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg is NOT installed or not on PATH.
    echo.
    echo   To install FFmpeg, choose one of these methods:
    echo.
    echo   Method 1 — winget (recommended):
    echo     winget install Gyan.FFmpeg
    echo.
    echo   Method 2 — Manual:
    echo     1. Download from https://www.gyan.dev/ffmpeg/builds/
    echo     2. Extract to C:\ffmpeg
    echo     3. Add C:\ffmpeg\bin to your system PATH
    echo.
    echo   Method 3 — Chocolatey:
    echo     choco install ffmpeg
    echo.
) else (
    echo [OK] FFmpeg found.
)
echo.

REM ----------------------------------------------------------------
REM 6. Check Ollama
REM ----------------------------------------------------------------
echo [6/6] Checking Ollama installation...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Ollama is NOT installed.
    echo.
    echo   To install Ollama:
    echo     1. Download from https://ollama.com/download/windows
    echo     2. Run the installer
    echo     3. After install, pull the model:
    echo        ollama pull llama3:8b
    echo.
) else (
    echo [OK] Ollama found.
    echo.
    echo Pulling llama3:8b model (this may take a while on first run)...
    ollama pull llama3:8b
    echo [OK] Model ready.
)
echo.

REM ----------------------------------------------------------------
REM Create .env from template if it doesn't exist
REM ----------------------------------------------------------------
if not exist ".env" (
    echo Creating .env from template...
    copy .env.example .env >nul
    echo [OK] Created .env file — edit it to customize settings.
) else (
    echo [INFO] .env file already exists. Skipping.
)
echo.

REM ----------------------------------------------------------------
REM Done
REM ----------------------------------------------------------------
echo ============================================================
echo   Setup Complete!
echo ============================================================
echo.
echo   Next steps:
echo.
echo   1. Edit .env to customize settings (optional)
echo.
echo   2. Set up YouTube API credentials:
echo      a. Go to https://console.cloud.google.com/
echo      b. Create a new project
echo      c. Enable "YouTube Data API v3"
echo      d. Create OAuth 2.0 credentials (Desktop app)
echo      e. Download client_secrets.json to config\ folder
echo.
echo   3. Run the agent:
echo      venv\Scripts\activate
echo      python main.py --skip-upload
echo.
echo   4. Schedule daily runs (optional):
echo      python main.py --schedule
echo.
echo ============================================================
pause
