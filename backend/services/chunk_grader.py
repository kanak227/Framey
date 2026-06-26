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

# Initialize the clients lazily to prevent crash-on-import
_client = None

def get_groq_client():
    global _client
    if _client is None:
        _client = Groq()
    return _client

def get_gemini_client():
    from google import genai
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

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
    Grades a single text block using Gemini or Groq API with exponential backoff retries.
    Returns the graded block if the score is >= 6.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    use_gemini = bool(gemini_key)
    
    # Proactive rate-limit spacing to avoid hitting free-tier limits (5 RPM for Gemini 2.5-flash Free Tier)
    if use_gemini:
        gemini_sleep = float(os.getenv("GEMINI_RATE_LIMIT_SLEEP", "12.0"))
        if gemini_sleep > 0:
            time.sleep(gemini_sleep)
    else:
        time.sleep(3.0)
        
    print(f"Grading block {block['start']}s to {block['end']}s using {'Gemini' if use_gemini else 'Groq'}...", flush=True)
    
    max_retries = 5
    base_delay = 8.0
    
    for attempt in range(max_retries):
        try:
            if use_gemini:
                from google import genai
                from google.genai import types
                client = get_gemini_client()
                if not client:
                    raise ValueError("Failed to initialize Gemini client")
                
                model_name = os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-flash")
                response = client.models.generate_content(
                    model=model_name,
                    contents=f"Grade this transcript block:\n\n{block['text']}",
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json"
                    )
                )
                result_text = response.text
            else:
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
                # Check for rate-limiting 429 resource exhaustion
                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                    import re
                    match = re.search(r"retry in (\d+\.?\d*)s", err_msg)
                    if match:
                        sleep_time = float(match.group(1)) + 2.0  # add 2s safety margin
                        print(f"Rate limit hit. Sleeping for {sleep_time:.2f}s as requested by Gemini API...", file=sys.stderr)
                        time.sleep(sleep_time)
                        continue
                
                sleep_time = (base_delay if not use_gemini else 2.0) * (2 ** attempt)
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
        
    # Grade blocks sequentially for Gemini (due to 5 RPM limit) or in parallel for Groq
    use_gemini = bool(os.getenv("GEMINI_API_KEY"))
    max_workers = 1 if use_gemini else 2
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(grade_block, blocks))
        
    # Filter out blocks scoring below 6 (or failed gradings)
    surviving_blocks = [r for r in results if r is not None]
    
    # Sort by start time just to be clean
    surviving_blocks.sort(key=lambda x: x["start"])
    
    return surviving_blocks
