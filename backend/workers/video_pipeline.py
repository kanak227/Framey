import os
import sys
import json
import redis
import subprocess

# Ensure the backend directory is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workers.celery_app import celery_app
from services.audio_extractor import extract_audio
from services.transcriber import transcribe_audio
from services.chunk_grader import grade_chunks
from services.moment_finder import find_moments, find_moments_single_call
from services.clip_cutter import cut_clips
from services.supabase_client import get_supabase_service_client

# Redis client configuration
_redis_client = None
def get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _redis_client = redis.from_url(redis_url)
    return _redis_client

# Backward compatibility status store for local run_pipeline.py script
job_statuses = {}

def update_job_status(job_id: str, status: str, step: str, progress: int, clips: list = None, error: str = None):
    """
    Updates the job status in Supabase.
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
        supabase = get_supabase_service_client()
        update_payload = {
            "status": status,
            "step": step,
            "progress": progress,
            "clips": clips or []
        }
        if error is not None:
            update_payload["error"] = error
            
        supabase.table("jobs").update(update_payload).eq("id", job_id).execute()
    except Exception as e:
        print(f"Failed to update job status in Supabase: {e}", file=sys.stderr)

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
        # Check if video_path is a URL and download it first
        if video_path.startswith("http://") or video_path.startswith("https://"):
            update_job_status(job_id, "processing", "Downloading video from URL...", 5)
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            temp_dir = os.path.join(backend_dir, "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            downloaded_file = os.path.join(temp_dir, f"{job_id}.mp4")
            
            is_direct_url = any(ext in video_path.lower() for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm"]) or "supabase.co" in video_path or "supabase.in" in video_path
            
            if is_direct_url:
                print(f"Downloading direct link: {video_path}")
                import urllib.request
                urllib.request.urlretrieve(video_path, downloaded_file)
            else:
                cmd = [
                    "yt-dlp",
                    "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "--merge-output-format", "mp4",
                    "-o", downloaded_file,
                    video_path
                ]
                
                print(f"Running download command: {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    print(f"yt-dlp standard download failed: {res.stderr}")
                    # Fallback to simple best format
                    cmd_fallback = [
                        "yt-dlp",
                        "-f", "best",
                        "-o", downloaded_file,
                        video_path
                    ]
                    print(f"Running fallback download command: {' '.join(cmd_fallback)}")
                    res_fallback = subprocess.run(cmd_fallback, capture_output=True, text=True)
                    if res_fallback.returncode != 0:
                        raise Exception(f"Failed to download video from URL: {res_fallback.stderr or res.stderr}")
            
            if not os.path.exists(downloaded_file):
                matching_files = [f for f in os.listdir(temp_dir) if f.startswith(job_id)]
                if matching_files:
                    downloaded_file = os.path.join(temp_dir, matching_files[0])
                else:
                    raise Exception("Video downloaded but output file could not be found.")
            
            video_path = downloaded_file

        # Step 1: Audio Extraction
        update_job_status(job_id, "processing", "Extracting audio...", 15)
        audio_path = extract_audio(video_path)
        
        # Step 2: Transcription
        update_job_status(job_id, "processing", "Transcribing...", 50)
        words = transcribe_audio(audio_path)
        
        # Step 3 & 4: Chunk Grading and Moment Finding
        update_job_status(job_id, "processing", "Finding best moments...", 80)
        
        # Try single-call Gemini analyzer first if configured
        moments = []
        if os.getenv("GEMINI_API_KEY"):
            try:
                moments = find_moments_single_call(words)
            except Exception as e:
                print(f"Single-Call Gemini Analyzer failed, falling back to multi-call pipeline: {e}", file=sys.stderr)
                
        # Fallback to original block-by-block pipeline if single-call returned no moments
        if not moments:
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
        
        # Upload clips to Supabase Storage
        update_job_status(job_id, "processing", "Uploading clips to cloud...", 95)
        supabase = get_supabase_service_client()
        
        uploaded_clips = []
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        for clip in clips:
            local_rel_path = clip["path"]
            local_abs_path = os.path.join(backend_dir, local_rel_path)
            
            if os.path.exists(local_abs_path):
                filename = os.path.basename(local_abs_path)
                storage_path = f"{job_id}/{filename}"
                
                # Upload file to public bucket 'clips'
                try:
                    with open(local_abs_path, "rb") as f:
                        supabase.storage.from_("clips").upload(
                            path=storage_path,
                            file=f,
                            file_options={"content-type": "video/mp4"}
                        )
                    # Get public URL
                    public_url = supabase.storage.from_("clips").get_public_url(storage_path)
                    clip["path"] = public_url
                except Exception as upload_err:
                    print(f"Failed to upload clip {filename} to Supabase: {upload_err}", file=sys.stderr)
                
                uploaded_clips.append(clip)
            else:
                uploaded_clips.append(clip)
                
        # Clean up local output folder
        import shutil
        job_dir = os.path.join(backend_dir, "temp", job_id)
        if os.path.exists(job_dir):
            try:
                shutil.rmtree(job_dir)
                print(f"Cleaned up local clips directory: {job_dir}")
            except Exception as e:
                print(f"Failed to delete local clips directory: {e}", file=sys.stderr)
                
        # Complete!
        update_job_status(job_id, "done", "Complete", 100, clips=uploaded_clips)
        return uploaded_clips
        
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


