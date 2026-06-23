# Video-to-Shorts Pipeline Backend

This directory contains the backend services and orchestration logic for the AI-powered video-to-shorts conversion feature. The pipeline takes a raw video file, processes it, scores the narrative structure using LLMs, and extracts standalone short clips.

---

## ⚙️ How It Works (The 7-Step Pipeline)

The core feature is executed sequentially across 7 stages:

```mermaid
graph TD
    A[Input Video] -->|Step 1: audio_extractor| B[audio_extractor.py]
    B -->|Step 2: chunker| C[chunker.py]
    C -->|Step 3: transcriber| D[transcriber.py]
    D -->|Step 4: transcript_merger| E[transcript_merger.py]
    E -->|Step 5: chunk_grader| F[chunk_grader.py]
    F -->|Step 6: moment_finder| G[moment_finder.py]
    G -->|Step 7: clip_cutter| H[clip_cutter.py]
```

### Stage Details

1. **Audio Extraction (`services/audio_extractor.py`)**
   * Uses `ffmpeg` to extract the master audio channel from the source video as an MP3.
   
2. **Audio Chunking (`services/chunker.py`)**
   * Uses `pydub` to slice the master audio into 30-second sub-chunks. This enables parallel processing and prevents transcription timeouts.

3. **Parallel Transcription (`services/transcriber.py`)**
   * Uses `faster-whisper` (running locally on CPU using `int8` quantization) with 4 thread-pool workers to transcribe chunks in parallel. It retrieves exact word-level timestamps.

4. **Transcript Merger (`services/transcript_merger.py`)**
   * Combines word transcripts from all chunks, adjusting timestamps according to chunk offsets and sorting them chronologically.

5. **Transcript Grading (`services/chunk_grader.py`)**
   * Segments the merged transcript into 2-minute blocks and prompts the Groq API (`llama-3.3-70b-versatile`) to evaluate them. Blocks scoring $\ge 6$ on a scale of 1-10 (relevance, punchiness, hook presence) are selected for clip generation.

6. **Moment Finder (`services/moment_finder.py`)**
   * Identifies the exact starting and ending word-level timestamps (between 30 and 90 seconds) for the most standalone segment within each high-scoring block. It aligns boundaries precisely with natural sentence structures.

7. **Clip Cutter & Cleanup (`services/clip_cutter.py`)**
   * Cuts the video at exact boundaries using H.264/AAC re-encoding (`-c:v libx264 -c:a aac`) to guarantee glitch-free, frame-perfect starting and ending boundaries.
   * Cleans up all intermediate audio, chunk folders, and the original raw uploaded video from the temp directory once completed or failed.

---

## 🛠️ Getting Started

### 1. Requirements
* **System**: `ffmpeg`
* **Python**: `python >= 3.10`

### 2. Install Dependencies
Ensure you are in the `backend/` directory, activate your virtual environment, and run:
```bash
pip install pydub faster-whisper groq python-dotenv
```

### 3. Environment Variables
Ensure a `.env` file exists at the root of the workspace containing:
```env
GROQ_API_KEY=your_groq_api_key
```

---

## 💻 Running the Pipeline

### End-to-End Orchestrator
To execute the complete 7-step pipeline:
```bash
python3 run_pipeline.py
```
This imports `process_video` from `workers/video_pipeline.py` and logs the pipeline's progress in real-time, outputting final video files in `temp/<job_id>`.

### Testing Transcription Pipeline Only
To test steps 1 through 4 (Audio extraction $\rightarrow$ Transcription merger) without querying the LLM or cutting video files:
```bash
python3 test_pipeline.py <path_to_sample_video>
```
