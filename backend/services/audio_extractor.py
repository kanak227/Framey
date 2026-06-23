import os
import subprocess
import uuid

def extract_audio(video_path: str) -> str:
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Input video file not found at: {video_path}")
        
    services_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(services_dir)
    temp_dir = os.path.join(backend_dir, "temp")
    
    os.makedirs(temp_dir, exist_ok=True)
    
    video_filename = os.path.basename(video_path)
    base_name, _ = os.path.splitext(video_filename)
    unique_id = uuid.uuid4().hex[:8]
    output_filename = f"{base_name}_{unique_id}.mp3"
    output_path = os.path.join(temp_dir, output_filename)
    
    # Run FFmpeg command to extract audio:
    # ffmpeg -y -i video.mp4 -q:a 0 -map a output.mp3
    # Note: -y is included to auto-overwrite files and prevent interactive blocking.
    command = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-q:a", "0",
        "-map", "a",
        output_path
    ]
    
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg extraction failed.\nStdout: {e.stdout}\nStderr: {e.stderr}"
        raise RuntimeError(error_msg) from e
        
    return os.path.abspath(output_path)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 audio_extractor.py <path_to_video>")
        sys.exit(1)
        
    video = sys.argv[1]
    print(f"Extracting audio from: {video}")
    try:
        out_path = extract_audio(video)
        print(f"✓ Success! Audio extracted to: {out_path}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

