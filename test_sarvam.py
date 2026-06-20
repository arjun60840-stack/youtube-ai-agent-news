import os
import base64
from sarvamai import SarvamAI

def main():
    api_key = "sk_8dgdkccd_vrVMxnP51EpJ5y4rVWtg6q38"
    client = SarvamAI(api_subscription_key=api_key)
    
    print("Sending request to Sarvam...")
    try:
        response = client.text_to_speech.convert(
            text="नमस्ते, आप कैसे हैं?",
            target_language_code="hi-IN",
            speaker="meera",
            model="bulbul:v3"
        )
        print("Success! Got audio array of length:", len(response.audios))
        if len(response.audios) > 0:
            audio_bytes = base64.b64decode(response.audios[0])
            print("Decoded audio bytes:", len(audio_bytes))
    except Exception as e:
        print("Error:", e)
    
if __name__ == "__main__":
    main()
