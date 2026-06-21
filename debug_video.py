import os
from pathlib import Path
from src.config import load_config
from src.audio_aligner import align_audio, split_into_scenes
from src.subtitle_generator import generate_dynamic_subtitles
from src.video_generator import generate_video

def main():
    config = load_config()
    date_str = "2026-06-20_v1"
    
    # Paths
    audio_path = config.audio_dir / f"{date_str}.wav"
    script_path = config.scripts_dir / "2026-06-20_v1_crew.json"
    
    with open(script_path, "r", encoding="utf-8") as f:
        import json
        script_text = json.load(f)["script"]
        
    print(f"Aligning audio...")
    timestamps = align_audio(str(audio_path), script_text)
    
    print(f"Splitting into scenes...")
    scenes = split_into_scenes(timestamps)
    
    print(f"Constructing image segments for 5 images...")
    image_segments = []
    for i in range(5):
        if i >= len(scenes):
            break
        scene = scenes[i]
        path = config.project_root / "assets" / "scenes" / date_str / f"scene_{i+1:03d}.png"
        image_segments.append({
            "start": scene["start"],
            "end": scene["end"],
            "path": str(path)
        })
        print(f"Segment {i}: {path} ({scene['start']} to {scene['end']})")
        
    print(f"Generating Subtitles...")
    subtitle_path = generate_dynamic_subtitles(timestamps, config, date_str)
    
    print(f"Generating Video...")
    final_video = generate_video(image_segments, str(audio_path), subtitle_path, config, date_str)
    print(f"FINAL VIDEO GENERATED AT: {final_video}")

if __name__ == "__main__":
    main()
