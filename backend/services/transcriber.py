import os
from concurrent.futures import ThreadPoolExecutor
from faster_whisper import WhisperModel

# Initialize and load the model once globally outside the function.
# We set cpu_threads=2 to avoid oversubscribing the CPU when running 4 parallel workers.
model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=2)

def transcribe_chunk(chunk_dict: dict) -> dict:
    """
    Helper function to transcribe a single chunk.
    """
    path = chunk_dict["path"]
    offset = chunk_dict["offset"]
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"Chunk file not found at: {path}")
        
    # Transcribe with word_timestamps=True to get word-level timing
    segments, info = model.transcribe(path, word_timestamps=True)
    
    words_list = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                words_list.append({
                    "word": w.word.strip(),
                    "start": w.start,
                    "end": w.end
                })
                
    return {
        "path": path,
        "offset": offset,
        "words": words_list
    }

def transcribe_chunks(chunks: list[dict]) -> list[dict]:
    """
    Transcribes multiple chunks in parallel using ThreadPoolExecutor.
    
    Args:
        chunks (list[dict]): List of dictionaries with 'path' and 'offset'.
        
    Returns:
        list[dict]: List of transcribed chunks with their word-level timestamps.
    """
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(transcribe_chunk, chunks))
    return results
