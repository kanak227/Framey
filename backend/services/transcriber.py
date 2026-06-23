import os
import sys
import subprocess
from groq import Groq
from dotenv import load_dotenv

# Resolve the path to the root .env file and load it
services_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(services_dir)
project_root = os.path.dirname(backend_dir)
env_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=env_path)

# Initialize Groq client lazily
_client = None
def get_groq_client():
    global _client
    if _client is None:
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set. Please check your .env file.")
        _client = Groq(api_key=groq_api_key)
    return _client

def transcribe_audio(audio_path: str) -> list[dict]:
    """
    Transcribes the entire audio file using the Groq Whisper API.
    If the file size exceeds 25MB, it is compressed to a 32kbps mono MP3 first.
    
    Args:
        audio_path (str): Path to the input audio file.
        
    Returns:
        list[dict]: List of dictionaries containing 'word', 'start', and 'end'.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Input audio file not found at: {audio_path}")
        
    client = get_groq_client()
    
    # Check if the file size exceeds the 25MB limit of Groq Whisper API
    file_size = os.path.getsize(audio_path)
    temp_compressed_path = None
    upload_path = audio_path
    
    if file_size > 25 * 1024 * 1024:
        print(f"Audio file is {file_size / (1024*1024):.2f}MB, which exceeds Groq's 25MB limit.")
        print("Compressing audio to 32kbps mono MP3 for API upload...")
        
        # Generate temporary compressed filename in the same directory
        dir_name = os.path.dirname(audio_path)
        base_name = os.path.basename(audio_path)
        name, _ = os.path.splitext(base_name)
        temp_compressed_path = os.path.join(dir_name, f"{name}_compressed.mp3")
        
        # Compress using ffmpeg: 32k bitrate, 1 channel (mono)
        compress_cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-codec:a", "libmp3lame", "-b:a", "32k", "-ac", "1",
            temp_compressed_path
        ]
        
        try:
            subprocess.run(compress_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            upload_path = temp_compressed_path
            print(f"Compressed file size: {os.path.getsize(upload_path) / (1024*1024):.2f}MB")
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg compression failed: {e}", file=sys.stderr)
            # Proceed with original file and hope for the best if compression fails
            upload_path = audio_path

    print("Sending request to Groq Whisper API...")
    try:
        with open(upload_path, "rb") as file_obj:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(upload_path), file_obj.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
            
        words_list = []
        if hasattr(transcription, 'words') and transcription.words:
            for w in transcription.words:
                if isinstance(w, dict):
                    word_text = w.get("word", "").strip()
                    start = w.get("start")
                    end = w.get("end")
                else:
                    word_text = getattr(w, "word", "").strip()
                    start = getattr(w, "start", None)
                    end = getattr(w, "end", None)
                words_list.append({
                    "word": word_text,
                    "start": start,
                    "end": end
                })
        return words_list
        
    finally:
        # Clean up temporary compressed file
        if temp_compressed_path and os.path.exists(temp_compressed_path):
            try:
                os.remove(temp_compressed_path)
                print(f"Cleaned up temporary compressed file: {temp_compressed_path}")
            except Exception as e:
                print(f"Failed to delete temp compressed file: {e}", file=sys.stderr)
