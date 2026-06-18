import os
import uuid
from pydub import AudioSegment

def split_audio(audio_path: str) -> list[dict]:
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Input audio file not found at: {audio_path}")
        
    services_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(services_dir)
    temp_dir = os.path.join(backend_dir, "temp")
    
    # Create a unique subfolder within temp to avoid filename collisions
    session_id = uuid.uuid4().hex[:8]
    chunk_dir = os.path.join(temp_dir, f"chunks_{session_id}")
    os.makedirs(chunk_dir, exist_ok=True)
    
    # Load the full audio file using Pydub
    audio = AudioSegment.from_file(audio_path)
    
    chunk_length_ms = 30 * 1000  # 30 seconds
    chunk_results = []
    
    # Loop through the audio in 30-second windows
    for i, start_ms in enumerate(range(0, len(audio), chunk_length_ms)):
        chunk = audio[start_ms:start_ms + chunk_length_ms]
        chunk_filename = f"chunk_{i}.mp3"
        chunk_path = os.path.join(chunk_dir, chunk_filename)
        
        # Save each window as a separate .mp3 file
        chunk.export(chunk_path, format="mp3")
        chunk_results.append({
            "path": os.path.abspath(chunk_path),
            "offset": start_ms // 1000
        })
        
    return chunk_results
