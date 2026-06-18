import os
import sys
import uuid
import shutil
import subprocess

def cut_clips(
    video_path: str,
    moments: list[dict],
    job_id: str = None,
    temp_audio_path: str = None,
    temp_chunks: list[dict] = None
) -> list[dict]:
    """
    Cuts the video into clips based on the specified timestamps using FFmpeg stream copy.
    Cleans up any specified intermediate temp files (audio / chunks) afterwards.
    
    Args:
        video_path (str): Path to the original video file.
        moments (list[dict]): List of moment definitions from Service 6.
        job_id (str, optional): Unique ID for the job. Generated if not provided.
        temp_audio_path (str, optional): Path to intermediate audio file to clean up.
        temp_chunks (list[dict], optional): List of chunk dicts to clean up.
        
    Returns:
        list[dict]: List of output clip paths and metadata.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Original video not found at: {video_path}")
        
    # Generate unique job ID if not provided
    if not job_id:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        
    # Setup job output directory inside backend/temp
    services_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(services_dir)
    temp_dir = os.path.join(backend_dir, "temp")
    job_dir = os.path.join(temp_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    output_clips = []
    
    for i, moment in enumerate(moments, 1):
        output_filename = f"clip_{i}.mp4"
        output_path = os.path.join(job_dir, output_filename)
        
        start = moment["start"]
        end = moment["end"]
        duration = round(end - start, 2)
        reason = moment.get("reason", "")
        
        # FFmpeg stream copy command
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", str(start),
            "-to", str(end),
            "-c", "copy",
            output_path
        ]
        
        print(f"Cutting clip {i} (duration {duration}s): {start}s -> {end}s...")
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            # Store the relative path in output for API consistency
            relative_path = os.path.join("temp", job_id, output_filename)
            output_clips.append({
                "path": relative_path,
                "start": start,
                "end": end,
                "duration": duration,
                "reason": reason
            })
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg failed for clip {i}: {e.stderr}", file=sys.stderr)
            raise e
            
    # Cleanup intermediate files to free up disk space
    print("\n--- Cleaning up intermediate files ---")
    if temp_audio_path and os.path.exists(temp_audio_path):
        try:
            os.remove(temp_audio_path)
            print(f"Removed temporary audio: {temp_audio_path}")
        except Exception as e:
            print(f"Failed to remove temp audio: {e}", file=sys.stderr)
            
    if temp_chunks:
        chunk_dirs = set()
        for chunk in temp_chunks:
            chunk_path = chunk.get("path")
            if chunk_path and os.path.exists(chunk_path):
                try:
                    os.remove(chunk_path)
                except Exception as e:
                    pass
                chunk_dirs.add(os.path.dirname(chunk_path))
                
        for chunk_dir in chunk_dirs:
            if os.path.exists(chunk_dir):
                try:
                    shutil.rmtree(chunk_dir)
                    print(f"Removed temporary chunk folder: {chunk_dir}")
                except Exception as e:
                    print(f"Failed to remove chunk folder {chunk_dir}: {e}", file=sys.stderr)
                    
    return output_clips
