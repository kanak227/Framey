import os
import sys
import json
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
    "You are an expert video content editor. Your job is to find the exact start and end timestamps of the "
    "single best 30-90 second moment inside a given transcript block that can be cut into a standalone short-form video (TikTok/Reel).\n\n"
    "Crucial Guidelines:\n"
    "1. The moment must be standalone, containing a complete thought with a hook and a clear resolution/tip.\n"
    "2. The moment MUST start and end at natural sentence boundaries. NEVER start or end mid-sentence or mid-word.\n"
    "3. Look at the exact timestamps of the words provided. Identify the first word of the starting sentence and "
    "   the last word of the ending sentence. Use their exact start and end timestamps respectively.\n"
    "4. The duration (end - start) must be between 30 and 90 seconds.\n\n"
    "Response Format:\n"
    "You must respond ONLY with a raw JSON object. Do not include markdown blocks, backticks, or any conversational text. "
    "The JSON object must follow this exact schema:\n"
    "{\n"
    '  "start": <float, exact start timestamp of the starting word of the clip>,\n'
    '  "end": <float, exact end timestamp of the ending word of the clip>,\n'
    '  "reason": "<a short explanation of why this specific moment was selected>"\n'
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

def find_moment_in_block(block: dict) -> dict | None:
    """
    Finds the best moment in a single block using Groq API and validates the timestamps.
    """
    try:
        client = get_groq_client()
        
        # Prepare the list of words with timestamps as context
        words_context = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for w in block.get("words", [])
        ]
        
        user_message = (
            f"Transcript Block (from {block['start']}s to {block['end']}s):\n"
            f"\"{block['text']}\"\n\n"
            f"Word Timestamps:\n"
            f"{json.dumps(words_context, indent=2)}\n\n"
            f"Identify the best standalone 30-90 second moment inside this block."
        )
        
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        
        result_text = chat_completion.choices[0].message.content
        result = parse_json_response(result_text)
        
        start = float(result.get("start", block["start"]))
        end = float(result.get("end", block["end"]))
        reason = result.get("reason", "")
        
        # Validation/Correction step to prevent downstream FFmpeg errors
        if start < block["start"]:
            start = block["start"]
            
        if end > block["end"]:
            end = block["end"]
            
        if (end - start) > 90.0:
            end = start + 90.0
            
        return {
            "start": start,
            "end": end,
            "reason": reason
        }
    except Exception as e:
        print(f"Error finding moment in block {block['start']}-{block['end']}: {e}", file=sys.stderr)
    return None

def find_moments(graded_blocks: list[dict]) -> list[dict]:
    """
    Processes surviving blocks in parallel to find the exact cut timestamps.
    
    Args:
        graded_blocks (list[dict]): List of graded blocks containing text, start, end, and words.
        
    Returns:
        list[dict]: List of refined clip boundaries ready for FFmpeg.
    """
    if not graded_blocks:
        return []
        
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(find_moment_in_block, graded_blocks))
        
    # Filter out any failed results
    moments = [m for m in results if m is not None]
    
    # Sort chronologically by start timestamp
    moments.sort(key=lambda x: x["start"])
    
    return moments
