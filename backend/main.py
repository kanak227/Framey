import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the backend directory is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.upload import router as upload_router
from api.jobs import router as jobs_router

app = FastAPI(
    title="Framey Video-to-Shorts API",
    description="API for transforming raw footage into styled, captioned, and cut short-form videos.",
    version="1.0.0"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production to match React frontend URL if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
