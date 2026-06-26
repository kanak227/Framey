import os
import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services.supabase_client import get_supabase_service_client

router = APIRouter()

@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Lookup the job status in Supabase.
    """
    try:
        supabase = get_supabase_service_client()
        res = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job_data = res.data[0]
        # Return format consistent with frontend expectations
        return {
            "status": job_data["status"],
            "step": job_data["step"],
            "progress": job_data["progress"],
            "clips": job_data["clips"],
            "error": job_data.get("error")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")

@router.get("/status/stream/{job_id}")
async def stream_job_status(job_id: str):
    """
    Streams job status updates as Server-Sent Events (SSE) by querying Supabase.
    """
    try:
        supabase = get_supabase_service_client()
        res = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Job not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

    async def status_generator():
        last_data_str = None
        while True:
            try:
                res = supabase.table("jobs").select("*").eq("id", job_id).execute()
                if not res.data:
                    err_data = json.dumps({"status": "error", "error": "Job not found"})
                    yield f"data: {err_data}\n\n"
                    break
                
                job_data = res.data[0]
                formatted_data = {
                    "status": job_data["status"],
                    "step": job_data["step"],
                    "progress": job_data["progress"],
                    "clips": job_data["clips"],
                    "error": job_data.get("error")
                }
                
                data_str = json.dumps(formatted_data)
                if data_str != last_data_str:
                    yield f"data: {data_str}\n\n"
                    last_data_str = data_str
                    
                if job_data["status"] in ("done", "failed"):
                    break
            except Exception as e:
                err_data = json.dumps({"status": "error", "error": f"Database query error: {str(e)}"})
                yield f"data: {err_data}\n\n"
                break
                
            await asyncio.sleep(1.5)

    return StreamingResponse(status_generator(), media_type="text/event-stream")
