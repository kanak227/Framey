import os
import json
import redis
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter()

# Initialize Redis client
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(redis_url)

@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    # Lookup the job status in Redis
    try:
        data = redis_client.get(f"job:{job_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")
        
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return json.loads(data)

@router.get("/status/stream/{job_id}")
async def stream_job_status(job_id: str):
    """
    Streams job status updates as Server-Sent Events (SSE).
    """
    # Verify the job exists before starting the stream
    try:
        data = redis_client.get(f"job:{job_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")
        
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    async def status_generator():
        last_data = None
        while True:
            try:
                data = redis_client.get(f"job:{job_id}")
            except Exception as e:
                err_data = json.dumps({"status": "error", "error": f"Database connection error: {str(e)}"})
                yield f"data: {err_data}\n\n"
                break
                
            if not data:
                err_data = json.dumps({"status": "error", "error": "Job not found"})
                yield f"data: {err_data}\n\n"
                break
                
            decoded_data = data.decode("utf-8")
            if decoded_data != last_data:
                yield f"data: {decoded_data}\n\n"
                last_data = decoded_data
                
            try:
                parsed_data = json.loads(decoded_data)
                status = parsed_data.get("status")
                if status in ("done", "failed"):
                    break
            except Exception:
                break
                
            await asyncio.sleep(1.0)

    return StreamingResponse(status_generator(), media_type="text/event-stream")


