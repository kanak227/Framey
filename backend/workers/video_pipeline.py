import os
import sys

# Ensure the backend directory is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.audio_extractor import extract_audio
from services.chunker import split_audio
from services.transcriber import transcribe_chunks
from services.transcript_merger import merge_transcripts
from services.chunk_grader import grade_chunks
from services.moment_finder import find_moments
from services.clip_cutter import cut_clips

# Global in-memory dictionary to store job statuses
job_statuses = {}

def process_video(job_id: str, video_path: str) -> list[dict]:
    """
    Orchestrates the entire 7-step pipeline from raw video to cut clips.
    Updates the global job_statuses dict at each step.
    
    Args:
        job_id (str): The unique identifier for this job.
        video_path (str): Path to the original video file.
        
    Returns:
        list[dict]: List of output clips metadata.
    """
    try:
        # Step 1: Audio Extraction
        job_statuses[job_id] = {
            "status": "processing",
            "step": "Extracting audio...",
            "progress": 10,
            "clips": []
        }
        audio_path = extract_audio(video_path)
        
        # Step 2: Audio Chunking
        job_statuses[job_id] = {
            "status": "processing",
            "step": "Splitting into chunks...",
            "progress": 25,
            "clips": []
        }
        chunks = split_audio(audio_path)
        
        # Step 3: Transcription
        job_statuses[job_id] = {
            "status": "processing",
            "step": "Transcribing...",
            "progress": 45,
            "clips": []
        }
        transcribed_chunks = transcribe_chunks(chunks)
        
        # Step 4: Transcript Merger
        job_statuses[job_id] = {
            "status": "processing",
            "step": "Merging transcript...",
            "progress": 60,
            "clips": []
        }
        merged_words = merge_transcripts(transcribed_chunks)
        
        # Step 5 & 6: Chunk Grading and Moment Finding
        job_statuses[job_id] = {
            "status": "processing",
            "step": "Finding best moments...",
            "progress": 80,
            "clips": []
        }
        graded_blocks = grade_chunks(merged_words)
        moments = find_moments(graded_blocks)
        
        # Step 7: Clip Cutter (includes cleanup of intermediate files)
        job_statuses[job_id] = {
            "status": "processing",
            "step": "Cutting clips...",
            "progress": 90,
            "clips": []
        }
        clips = cut_clips(
            video_path=video_path,
            moments=moments,
            job_id=job_id,
            temp_audio_path=audio_path,
            temp_chunks=chunks
        )
        
        # Complete!
        job_statuses[job_id] = {
            "status": "done",
            "step": "Complete",
            "progress": 100,
            "clips": clips
        }
        return clips
        
    except Exception as e:
        job_statuses[job_id] = {
            "status": "failed",
            "step": "Failed",
            "progress": 100,
            "error": str(e),
            "clips": []
        }
        print(f"Error processing job {job_id}: {e}", file=sys.stderr)
        raise e
