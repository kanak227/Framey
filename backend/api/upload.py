import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Header, BackgroundTasks
from pydantic import BaseModel
from workers.video_pipeline import process_video_task, update_job_status
from services.supabase_client import get_supabase_client, get_supabase_service_client

router = APIRouter()

async def get_current_user(authorization: str = Header(...)):
    """
    Validates the Bearer token with Supabase and returns the user object.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Must be Bearer <token>"
        )
    jwt_token = authorization.split(" ")[1]
    try:
        supabase = get_supabase_client()
        res = supabase.auth.get_user(jwt_token)
        return res.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

@router.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...), user = Depends(get_current_user)):
    # Validate extension
    filename = file.filename or ""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS)).upper()}"
        )
        
    # Generate unique job ID
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    
    # Locate/create temp directory
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    temp_dir = os.path.join(backend_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    temp_file_name = f"{job_id}{ext}"
    temp_file_path = os.path.join(temp_dir, temp_file_name)
    
    # Save the file with a chunked write to monitor and enforce file size limit
    total_size = 0
    try:
        with open(temp_file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB chunk
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size allowed is {MAX_FILE_SIZE // (1024 * 1024)}MB."
                    )
                buffer.write(chunk)
    except HTTPException:
        # Clean up partial upload on size limit exceed
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Failed to save video: {str(e)}")
        
    # Initialize the job status in Supabase
    try:
        supabase = get_supabase_service_client()
        supabase.table("jobs").insert({
            "id": job_id,
            "user_id": user.id,
            "status": "pending",
            "step": "Initializing pipeline...",
            "progress": 0,
            "clips": []
        }).execute()
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Failed to create job in database: {str(e)}")
    
    # Run the pipeline in a background task
    if os.getenv("USE_CELERY", "false").lower() == "true":
        process_video_task.delay(job_id, temp_file_path)
    else:
        background_tasks.add_task(process_video_task, job_id, temp_file_path)
    
    # Return immediately, don't wait for pipeline
    return {"job_id": job_id}


class UrlUploadRequest(BaseModel):
    url: str


@router.post("/upload-url")
async def upload_url(request: UrlUploadRequest, background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    url = request.url
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL format. Must start with http:// or https://"
        )
        
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    
    # Initialize the job status in Supabase
    try:
        supabase = get_supabase_service_client()
        supabase.table("jobs").insert({
            "id": job_id,
            "user_id": user.id,
            "status": "pending",
            "step": "Initializing download pipeline...",
            "progress": 0,
            "clips": []
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job in database: {str(e)}")
    
    # Pass the URL directly. process_video_task will download/process it in the background.
    if os.getenv("USE_CELERY", "false").lower() == "true":
        process_video_task.delay(job_id, url)
    else:
        background_tasks.add_task(process_video_task, job_id, url)
    
    return {"job_id": job_id}



