"""
Teacher Module for AI Daily News Agent.

Allows the user to teach the AI agent new guidelines and rules
using either text or multilingual voice commands. 
The LLM converts the user's feedback into a structured rule, 
which is saved into memory.json.

Usage:
    python teacher.py --text "Always end the video by saying 'Jai Hind'"
    python teacher.py --voice
"""

import argparse
import sys
import ollama

from src.memory import add_rule
from src.config import load_config
from src.logger import get_logger, setup_logging

logger = get_logger("teacher")

def _translate_to_rule(raw_feedback: str, config) -> str:
    """Uses the LLM to translate raw multilingual feedback into a clear rule."""
    logger.info("Translating feedback into a rule using Llama 3...")
    prompt = (
        "You are an AI assistant that manages the memory rules for an AI YouTube News Agent.\n"
        "The user will provide feedback or a command in any language (English, Hindi, etc.).\n"
        "Your job is to translate and summarize their feedback into a SINGLE, clear, imperative rule in English.\n\n"
        f"USER FEEDBACK: {raw_feedback}\n\n"
        "OUTPUT FORMAT: Return ONLY the English rule. Do not wrap it in quotes. No extra commentary."
    )
    
    client = ollama.Client(host=config.ollama_base_url)
    response = client.chat(
        model=config.ollama_model,
        messages=[{"role": "system", "content": prompt}]
    )
    
    rule = response["message"]["content"].strip().strip('"').strip("'")
    return rule

def process_text(text: str, config, category: str = "script"):
    logger.info("Processing text feedback: %s (category=%s)", text, category)
    rule = _translate_to_rule(text, config)
    add_rule(rule, category=category)
    print(f"\n[+] Successfully learned new '{category}' rule: {rule}")

def process_voice(config, category: str = "script"):
    try:
        import speech_recognition as sr
        import sounddevice as sd
        import soundfile as sf
        import tempfile
    except ImportError:
        logger.error("Missing audio libraries. Run: pip install SpeechRecognition sounddevice soundfile")
        sys.exit(1)
        
    fs = 44100  # Sample rate
    seconds = 5  # Duration of recording
    
    print("\n🎤 Listening... (Speak your feedback now in any language)")
    print(f"Recording for {seconds} seconds...")
    
    try:
        myrecording = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
        sd.wait()  # Wait until recording is finished
    except Exception as e:
        print(f"❌ Microphone error: {e}")
        return

    print("⏳ Processing audio...")
    
    # Save as temp WAV file for speech_recognition
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
        sf.write(tmpfile.name, myrecording, fs)
        tmp_path = tmpfile.name
        
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(tmp_path) as source:
            audio = recognizer.record(source)
        
        # Using Google Web Speech API (supports many languages automatically)
        transcript = recognizer.recognize_google(audio)
        print(f"🎙️ You said: {transcript}")
        
        rule = _translate_to_rule(transcript, config)
        add_rule(rule, category=category)
        print(f"\n[+] Successfully learned new '{category}' rule: {rule}")
        
    except sr.UnknownValueError:
        print("❌ Could not understand the audio.")
    except sr.RequestError as e:
        print(f"❌ Could not request results from Google Speech Recognition service; {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        import os
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def main():
    parser = argparse.ArgumentParser(description="Teach the AI Agent new rules via text or voice.")
    parser.add_argument("--text", type=str, help="Text feedback to teach the agent.")
    parser.add_argument("--voice", action="store_true", help="Use microphone to record voice feedback.")
    parser.add_argument(
        "--category",
        type=str,
        default="script",
        choices=["script", "visual", "voice", "general"],
        help=(
            "Which part of the pipeline this rule should steer. "
            "'script' (default) reaches the CrewAI script-writing agents. "
            "'visual' reaches the ComfyUI Director AI prompt in image_generator.py. "
            "'voice' and 'general' are reserved for future consumers."
        ),
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(config.logs_dir, "teacher")

    if args.text:
        process_text(args.text, config, category=args.category)
    elif args.voice:
        process_voice(config, category=args.category)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
