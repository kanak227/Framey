import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor
from groq import Groq
from dotenv import load_dotenv

# Resolve the path to the root .env file
services_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(services_dir)
project_root = os.path.dirname(backend_dir)
env_path = os.path.join(project_root, ".env")

load_dotenv(dotenv_path=env_path)

# Initialize the Groq client lazily to prevent crash-on-import
_client = None

def get_groq_client():
    global _client
    if _client is None:
        _client = Groq()
    return _client

SYSTEM_PROMPT = (
    "You are an expert video content editor. Your job is to grade a block of transcript text on a scale from 1 to 10 "
    "based on its potential to be cut into a successful short-form video (like a TikTok, Reel, or Short).\n\n"
    "Evaluation Criteria:\n"
    "- Score high (6-10) if the text:\n"
    "  1. Contains a complete thought that makes sense standalone.\n"
    "  2. Has something punchy, useful, surprising, or emotional.\n"
    "  3. Has a clear moment that can fit within a 30-90 seconds duration.\n"
    "- Score low (1-5) if the text is boring, incomplete, context-dependent, or consists of filler conversation.\n\n"
    "Response Format:\n"
    "You must respond ONLY with a raw JSON object. Do not include markdown blocks, backticks, or any conversational text. "
    "The JSON object must follow this exact schema:\n"
    "{\n"
    '  "score": <integer between 1 and 10>,\n'
    '  "reason": "<a short 3-6 word explanation of why this score was given>"\n'
    "}"
)

def parse_json_response(response_text: str) -> dict:
    """
    Parses the JSON response from Groq, cleaning any markdown formatting if present.
    """
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)

def grade_block(block: dict) -> dict | None:
    """
    Grades a single text block using Groq API with exponential backoff retries.
    Returns the graded block if the score is >= 6.
    """
    max_retries = 3
    base_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            client = get_groq_client()
            model_name = os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant")
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Grade this transcript block:\n\n{block['text']}"}
                ],
                model=model_name,
                response_format={"type": "json_object"}
            )
            result_text = chat_completion.choices[0].message.content
            result = parse_json_response(result_text)
            
            score = int(result.get("score", 0))
            reason = result.get("reason", "")
            
            if score >= 6:
                return {
                    "start": block["start"],
                    "end": block["end"],
                    "score": score,
                    "text": block["text"],
                    "reason": reason,
                    "words": block["words"]
                }
            return None
        except Exception as e:
            print(f"Error grading block {block['start']}-{block['end']} (Attempt {attempt+1}/{max_retries}): {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                sleep_time = base_delay * (2 ** attempt)
                print(f"Retrying in {sleep_time:.2f} seconds...", file=sys.stderr)
                time.sleep(sleep_time)
    return None

def grade_chunks(words: list[dict]) -> list[dict]:
    """
    Groups words into 2-minute blocks, grades each block using Groq,
    and returns blocks with a score >= 6.
    
    Args:
        words (list[dict]): List of dictionaries with 'word', 'start', and 'end'.
        
    Returns:
        list[dict]: List of high-scoring blocks.
    """
    if not words:
        return []
        
    # Group words into 2-minute (120 seconds) blocks
    block_duration = 120
    max_time = max(w["end"] for w in words)
    
    blocks = []
    for start_time in range(0, int(max_time) + 1, block_duration):
        end_time = start_time + block_duration
        block_words = [w for w in words if start_time <= w["start"] < end_time]
        
        if not block_words:
            continue
            
        text = " ".join(w["word"] for w in block_words)
        blocks.append({
            "start": start_time,
            "end": end_time,
            "text": text,
            "words": block_words
        })
        
    # Grade blocks in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(grade_block, blocks))
        
    # Filter out blocks scoring below 6 (or failed gradings)
    surviving_blocks = [r for r in results if r is not None]
    
    # Sort by start time just to be clean
    surviving_blocks.sort(key=lambda x: x["start"])
    
    return surviving_blocks
