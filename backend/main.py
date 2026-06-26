import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the backend directory is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.upload import router as upload_router
from api.jobs import router as jobs_router
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Framey Video-to-Shorts API",
    description="API for transforming raw footage into styled, captioned, and cut short-form videos.",
    version="1.0.0"
)

# Configure CORS middleware
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount temp directory to serve generated video clips
# Note: uses /app/temp inside Docker, falls back to local relative path if running bare
temp_dir = "/app/temp" if os.path.exists("/app/temp") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
os.makedirs(temp_dir, exist_ok=True)
app.mount("/temp", StaticFiles(directory=temp_dir), name="temp")

# Register routers
app.include_router(upload_router, tags=["Upload"])
app.include_router(jobs_router, tags=["Jobs"])

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Framey Video-to-Shorts API",
        "docs_url": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("ENV", "development").lower() != "production"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
