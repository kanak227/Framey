# Framey: AI-Powered Video-to-Shorts Pipeline

Framey is an enterprise-ready, AI-powered video editing pipeline designed to turn raw, long-form video footage into viral-ready, standalone short clips (such as TikToks, YouTube Shorts, or Instagram Reels) — automatically graded, cut, and timed in minutes.

---

## 🏛️ System Architecture

Framey operates on a distributed, asynchronous queue system utilizing **FastAPI**, **Celery**, and **Redis**. High-intensity workloads (like transcription and video rendering) run in the background, keeping the user interface completely non-blocking and responsive.

Detailed documentation on structural topology, database keys, and queue patterns can be found in the [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) document.

```mermaid
graph TD
    A[Input Video] -->|Step 1: audio_extractor.py| B[Master Audio MP3]
    B -->|Step 2: chunker.py| C[30s Audio Chunks]
    C -->|Step 3: transcriber.py| D[Chunk Transcripts + Word Timestamps]
    D -->|Step 4: transcript_merger.py| E[Merged Master Transcript]
    E -->|Step 5: chunk_grader.py| F[2-Min Block Grading via Groq]
    F -->|Step 6: moment_finder.py| G[Refined Clip Timestamps 30-90s via Groq]
    G -->|Step 7: clip_cutter.py| H[Final MP4 Clips + Clean Temp Files]
```

---

## ✨ Features & Optimizations

*   **Precise Cutting (Glitch-Free)**: Re-encodes output video streams (`-c:v libx264 -c:a aac`) to guarantee clips cut exactly on sentence/word boundaries. No black frames, frozen screens, or sound desynchronization.
*   **Upload Guards**: Validates incoming file formats (`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`) and caps file sizes at `500MB` via chunked stream monitoring.
*   **Automated Storage Reclamation**: Sweeps away all intermediate files (split chunks, raw audio) and deletes the original uploaded file upon job completion or failure, maintaining a minimal storage footprint.
*   **Groq API Rate-Limit Protection**: Wraps grader and moment extraction in retry loops with exponential backoff to handle HTTP `429` (Rate-Limit Exceeded) responses gracefully.
*   **Whisper GPU Acceleration**: Dynamically detects and leverages CUDA GPUs if present for transcription speedups (falling back to optimized CPU quantization if unavailable).

---

## 📁 Directory Structure

```text
Framey/
├── docs/
│   └── ARCHITECTURE.md         # Full system architecture guide
├── backend/
│   ├── run_pipeline.py         # End-to-end orchestration runner for tests
│   ├── test_pipeline.py        # Test script to run transcription pipeline only
│   ├── main.py                 # FastAPI web application entry point
│   ├── api/
│   │   ├── upload.py           # POST /upload with size limits and format checks
│   │   └── jobs.py             # GET /status/{job_id} endpoint
│   ├── services/
│   │   ├── audio_extractor.py  # Step 1: Extracts audio track via FFmpeg
│   │   ├── chunker.py          # Step 2: Splits audio into 30s segments
│   │   ├── transcriber.py      # Step 3: Local Whisper transcription with GPU fallback
│   │   ├── transcript_merger.py# Step 4: Recombines and offsets timestamps
│   │   ├── chunk_grader.py     # Step 5: Groq evaluation with backoff
│   │   ├── moment_finder.py    # Step 6: Groq sentence alignment with backoff
│   │   └── clip_cutter.py      # Step 7: Re-encodes H.264 clips & cleans up temp directories
│   ├── workers/
│   │   ├── celery_app.py       # Celery configuration
│   │   └── video_pipeline.py   # Main pipeline orchestrator/Celery task
│   └── temp/                   # Auto-generated workspace for cuts and segments
├── frontend/                   # Client workspace placeholder
├── storage/                    # Output directory for video storage
├── docker-compose.yml          # Container configuration (FastAPI, Redis, Celery Worker)
├── .env                        # Environment configurations (Groq API keys)
└── README.md                   # Core Documentation
```

---

## 🛠️ Setup & Installation

### Option 1: Docker Compose (Recommended)
Make sure you have [Docker](https://www.docker.com/) and Docker Compose installed.

1. Create a `.env` file in the root directory:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   ```
2. Build and start the services:
   ```bash
   docker-compose up --build
   ```
This launches:
*   **Redis** on port `6379`
*   **FastAPI backend** on port `8000`
*   **Celery worker** (listens to tasks)

### Option 2: Local Installation (Manual)
1.  **Install FFmpeg**:
    ```bash
    # Ubuntu / Debian
    sudo apt update && sudo apt install -y ffmpeg
    # macOS
    brew install ffmpeg
    ```
2.  **Setup Virtual Environment**:
    ```bash
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Run Locally**:
    *   Start Redis locally or through Docker: `docker run -d -p 6379:6379 redis:alpine`
    *   Start FastAPI server: `python3 main.py`
    *   Start Celery worker: `celery -A workers.celery_app worker --loglevel=info`

---

## 💻 API Endpoints

### 1. Upload Video
*   **Endpoint**: `POST /upload`
*   **Content-Type**: `multipart/form-data`
*   **Body**: `file` (Video binary)
*   **Response**:
    ```json
    {
      "job_id": "job_e9b441ca"
    }
    ```

### 2. Get Job Status (Polling)
*   **Endpoint**: `GET /status/{job_id}`
*   **Response (Processing)**:
    ```json
    {
      "status": "processing",
      "step": "Transcribing...",
      "progress": 45,
      "clips": []
    }
    ```
*   **Response (Done)**:
    ```json
    {
      "status": "done",
      "step": "Complete",
      "progress": 100,
      "clips": [
        {
          "path": "temp/job_e9b441ca/clip_1.mp4",
          "start": 12.34,
          "end": 67.89,
          "duration": 55.55,
          "reason": "A highly punchy hook summarizing the core tip."
        }
      ]
    }
    ```

### 3. Get Job Status (Real-time Stream)
*   **Endpoint**: `GET /status/stream/{job_id}`
*   **Protocol**: HTTP Server-Sent Events (SSE)
*   **Data Format**: `text/event-stream` (Yields status data prefixed with `data: ` whenever it updates, closing the stream automatically when the job finishes).


---

## 💡 Key Design Highlights

> [!TIP]
> **Parallel Processing:** Chunk transcription utilizes `ThreadPoolExecutor` to speed up CPU-bound Whisper transcriptions, using 4 parallel workers.
> **Cost & Speed Optimized:** Video cutting uses H.264 and AAC re-encoding which ensures that cut clips play back smoothly and without glitches on modern platforms.