import sys
import os
import time
import threading

# Ensure backend dir is in PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from workers.video_pipeline import process_video, job_statuses

def main():
    video_path = "sample.mp4" if os.path.exists("sample.mp4") else "temp/sample.mp4"
    if not os.path.exists(video_path):
        print(f"Error: sample.mp4 not found at {video_path}")
        sys.exit(1)
        
    job_id = "test_run_e2e"
    print(f"Starting Video Pipeline on {video_path}")
    print(f"Job ID: {job_id}\n")
    
    # Run the orchestrator in a background thread to print status in real-time
    t = threading.Thread(target=process_video, args=(job_id, video_path))
    t.start()
    
    last_step = None
    last_progress = None
    
    while t.is_alive():
        status = job_statuses.get(job_id)
        if status:
            step = status.get("step")
            progress = status.get("progress")
            if step != last_step or progress != last_progress:
                print(f"[{progress}%] {step}")
                last_step = step
                last_progress = progress
        time.sleep(1)
        
    t.join()
    
    final_status = job_statuses.get(job_id)
    print("\n--- Execution Finished ---")
    print(f"Final Status: {final_status['status'].upper()}")
    
    if final_status["status"] == "done":
        print("\nGenerated Clips:")
        for clip in final_status["clips"]:
            print(f"\n  - Path: {clip['path']}")
            print(f"    Time: {clip['start']}s -> {clip['end']}s (Duration: {clip['duration']}s)")
            print(f"    Reason: {clip['reason']}")
    elif final_status["status"] == "failed":
        print(f"\nError: {final_status.get('error')}")

if __name__ == "__main__":
    main()
