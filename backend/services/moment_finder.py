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
    "You are an expert video content editor. Your job is to find the exact start and end timestamps of the "
    "single best 15-50 second moment inside a given transcript block that can be cut into a standalone short-form video (TikTok/Reel).\n\n"
    "Crucial Guidelines:\n"
    "1. The moment must be standalone, containing a complete thought with a hook and a clear resolution/tip.\n"
    "2. The moment MUST start and end at natural sentence boundaries. NEVER start or end mid-sentence or mid-word.\n"
    "3. Look at the exact timestamps of the words provided. Identify the first word of the starting sentence and "
    "   the last word of the ending sentence. Use their exact start and end timestamps respectively.\n"
    "4. The duration (end - start) must be between 15 and 50 seconds.\n\n"
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
    Finds the best moment in a single block using Gemini or Groq API with exponential backoff retries.
    Validates and adjusts the timestamps returned by the API.
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
        
    print(f"Finding moment in block {block['start']}s to {block['end']}s using {'Gemini' if use_gemini else 'Groq'}...", flush=True)
    
    max_retries = 5
    base_delay = 8.0
    
    for attempt in range(max_retries):
        try:
            # Prepare a highly compact string of words with timestamps to save tokens
            # Format: word(start,end)
            words_context = " ".join([
                f"{w['word']}({round(w['start'], 1)},{round(w['end'], 1)})"
                for w in block.get("words", [])
            ])
            
            user_message = (
                f"Transcript Block with Word Timestamps formatted as word(start,end):\n"
                f"{words_context}\n\n"
                f"Identify the best standalone 30-90 second moment inside this block."
            )
            
            if use_gemini:
                from google import genai
                from google.genai import types
                client = get_gemini_client()
                if not client:
                    raise ValueError("Failed to initialize Gemini client")
                
                model_name = os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-flash")
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_message,
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
                        {"role": "user", "content": user_message}
                    ],
                    model=model_name,
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
            print(f"Error finding moment in block {block['start']}-{block['end']} (Attempt {attempt+1}/{max_retries}): {e}", file=sys.stderr)
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
        
    # Process blocks sequentially for Gemini (due to 5 RPM limit) or in parallel for Groq
    use_gemini = bool(os.getenv("GEMINI_API_KEY"))
    max_workers = 1 if use_gemini else 2
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(find_moment_in_block, graded_blocks))
        
    # Filter out any failed results
    moments = [m for m in results if m is not None]
    
    # Sort chronologically by start timestamp
    moments.sort(key=lambda x: x["start"])
    
    return moments

SYSTEM_PROMPT_SINGLE_CALL = (
    "You are an expert video content editor and viral video strategist.\n"
    "Your job is to analyze the transcript of a long-form video and select the 1 to 5 best standalone moments "
    "that can be cut into viral short-form videos (like TikToks, Reels, or YouTube Shorts).\n\n"
    "Each moment must meet these strict criteria:\n"
    "1. Be between 15 and 50 seconds in duration.\n"
    "2. Have a strong hook (first 5 seconds of the clip must capture attention).\n"
    "3. Contain a complete, self-contained thought, value bomb, or funny/surprising moment.\n"
    "4. Have a clear resolution or logical ending.\n\n"
    "You MUST respond with a JSON object containing a list under the key 'clips'. Each clip must have:\n"
    "- 'start': The start timestamp in seconds (decimal, e.g., 45.2)\n"
    "- 'end': The end timestamp in seconds (decimal, e.g., 105.8)\n"
    "- 'reason': A brief reason explaining why this moment is highly engaging.\n\n"
    "Crucial: Ensure the start and end seconds align exactly with the transcript timestamps. Only return valid JSON."
)

def format_transcript_with_seconds(words: list[dict], interval: float = 15.0) -> str:
    """
    Groups words into segments of roughly `interval` seconds, prefixed with start/end seconds.
    Example:
    [0.0 -> 12.3] Hello everyone, today we are going to learn about the secret.
    [12.3 -> 25.0] To building high conversion landing pages.
    """
    if not words:
        return ""
        
    segments = []
    current_segment = []
    segment_start = words[0]["start"]
    
    for w in words:
        current_segment.append(w["word"])
        duration = w["end"] - segment_start
        if duration >= interval or w["word"].endswith((".", "?", "!")):
            segment_end = w["end"]
            segments.append(f"[{segment_start:.1f} -> {segment_end:.1f}] {' '.join(current_segment)}")
            current_segment = []
            segment_start = w["end"]
            
    if current_segment:
        segment_end = words[-1]["end"]
        segments.append(f"[{segment_start:.1f} -> {segment_end:.1f}] {' '.join(current_segment)}")
        
    return "\n".join(segments)

def find_moments_single_call(words: list[dict]) -> list[dict]:
    """
    Finds viral moments in the transcript using a single Gemini API call.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("GEMINI_API_KEY not set. Cannot use single-call analyzer.", flush=True)
        return []
        
    print("Running Single-Call Gemini Analyzer...", flush=True)
    
    # 1. Format the transcript
    transcript = format_transcript_with_seconds(words)
    
    # 2. Call Gemini
    from google import genai
    from google.genai import types
    client = get_gemini_client()
    if not client:
        raise ValueError("Failed to initialize Gemini client")
        
    model_name = os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-flash")
    
    user_prompt = (
        f"Here is the transcript of the video with start and end times in seconds:\n\n"
        f"{transcript}\n\n"
        f"Please analyze the transcript and select the best 1 to 5 standalone moments for short-form clips."
    )
    
    max_retries = 3
    base_delay = 5.0
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT_SINGLE_CALL,
                    response_mime_type="application/json"
                )
            )
            result = parse_json_response(response.text)
            clips = result.get("clips", [])
            print(f"Single-Call Analyzer successfully found {len(clips)} clips!", flush=True)
            return clips
        except Exception as e:
            print(f"Error in single-call analyzer (Attempt {attempt+1}/{max_retries}): {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                # Check for rate-limiting 429
                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                    import re
                    match = re.search(r"retry in (\d+\.?\d*)s", err_msg)
                    if match:
                        sleep_time = float(match.group(1)) + 2.0
                        print(f"Rate limit hit in single-call. Sleeping for {sleep_time:.2f}s...", file=sys.stderr)
                        time.sleep(sleep_time)
                        continue
                
                time.sleep(base_delay * (attempt + 1))
                
    print("Single-Call Analyzer failed. Returning empty list to fall back to multi-call pipeline.", file=sys.stderr)
    return []
