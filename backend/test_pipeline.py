import sys
import os

# Ensure the backend directory is in the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.audio_extractor import extract_audio
from services.chunker import split_audio
from services.transcriber import transcribe_chunks
from services.transcript_merger import merge_transcripts

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_pipeline.py <sample_video_path>")
        sys.exit(1)
        
    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(f"Error: Sample video file not found at '{video_path}'")
        sys.exit(1)
        
    print(f"Starting E2E transcription pipeline for video: {video_path}")
    
    # 1. Extract audio
    print("\n--- Step 1: Extracting Audio ---")
    audio_path = extract_audio(video_path)
    print(f"Extracted audio path: {audio_path}")
    
    # 2. Split audio into chunks
    print("\n--- Step 2: Chunking Audio ---")
    chunks = split_audio(audio_path)
    print(f"Generated {len(chunks)} chunks:")
    for chunk in chunks:
        print(f"  Path: {chunk['path']} | Offset: {chunk['offset']}s")
        
    # 3. Transcribe chunks
    print("\n--- Step 3: Transcribing Chunks ---")
    transcribed_chunks = transcribe_chunks(chunks)
    print("Transcription complete.")
    
    # 4. Merge transcripts
    print("\n--- Step 4: Merging Transcripts ---")
    final_word_list = merge_transcripts(transcribed_chunks)
    
    # Print final word list
    print("\n--- Final Word List ---")
    for word_info in final_word_list:
        print(f"Word: {word_info['word']:<15} | Start: {word_info['start']:<6.2f}s | End: {word_info['end']:<6.2f}s")

if __name__ == "__main__":
    main()
