import os
import sys
import json
import redis

# Ensure the backend directory is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workers.celery_app import celery_app
from services.audio_extractor import extract_audio
from services.transcriber import transcribe_audio
from services.chunk_grader import grade_chunks
from services.moment_finder import find_moments
from services.clip_cutter import cut_clips

# Redis client configuration
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(redis_url)

# Backward compatibility status store for local run_pipeline.py script
job_statuses = {}

def update_job_status(job_id: str, status: str, step: str, progress: int, clips: list = None, error: str = None):
    """
    Updates the job status in Redis with a 24-hour expiration.
    """
    status_data = {
        "status": status,
        "step": step,
        "progress": progress,
        "clips": clips or []
    }
    if error is not None:
        status_data["error"] = error
        
    # Update local in-memory store for local script compatibility
    job_statuses[job_id] = status_data
        
    try:
        redis_client.setex(f"job:{job_id}", 86400, json.dumps(status_data))
    except Exception as e:
        print(f"Failed to update job status in Redis: {e}", file=sys.stderr)

def process_video(job_id: str, video_path: str) -> list[dict]:
    """
    Synchronous compatibility wrapper for run_pipeline.py
    """
    return process_video_task(job_id, video_path)

@celery_app.task(name="workers.video_pipeline.process_video_task")
def process_video_task(job_id: str, video_path: str) -> list[dict]:
    """
    Orchestrates the entire 7-step pipeline from raw video to cut clips.
    Updates Redis at each step.
    
    Args:
        job_id (str): The unique identifier for this job.
        video_path (str): Path to the original video file.
        
    Returns:
        list[dict]: List of output clips metadata.
    """
    try:
        # Step 1: Audio Extraction
        update_job_status(job_id, "processing", "Extracting audio...", 15)
        audio_path = extract_audio(video_path)
        
        # Step 2: Transcription
        update_job_status(job_id, "processing", "Transcribing...", 50)
        words = transcribe_audio(audio_path)
        
        # Step 3 & 4: Chunk Grading and Moment Finding
        update_job_status(job_id, "processing", "Finding best moments...", 80)
        graded_blocks = grade_chunks(words)
        moments = find_moments(graded_blocks)
        
        # Step 5: Clip Cutter (includes cleanup of intermediate files)
        update_job_status(job_id, "processing", "Cutting clips...", 90)
        clips = cut_clips(
            video_path=video_path,
            moments=moments,
            job_id=job_id,
            temp_audio_path=audio_path,
            temp_chunks=None
        )
        
        # Complete!
        update_job_status(job_id, "done", "Complete", 100, clips=clips)
        return clips
        
    except Exception as e:
        update_job_status(job_id, "failed", "Failed", 100, error=str(e))
        print(f"Error processing job {job_id}: {e}", file=sys.stderr)
        raise e
    finally:
        # Cleanup original video if it is a temporary upload
        if video_path and os.path.exists(video_path):
            filename = os.path.basename(video_path)
            if filename.startswith("job_"):
                try:
                    os.remove(video_path)
                    print(f"Cleaned up original uploaded video file: {video_path}")
                except Exception as cleanup_err:
                    print(f"Failed to delete original video {video_path}: {cleanup_err}", file=sys.stderr)


