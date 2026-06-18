def merge_transcripts(transcribed_chunks: list[dict]) -> list[dict]:
    """
    Merges transcribed chunks into a single, chronologically sorted word list,
    correcting the relative timestamps of each chunk with its starting offset.
    
    Args:
        transcribed_chunks (list[dict]): List of transcribed chunks. Each chunk contains:
            - 'path': str
            - 'offset': int/float (in seconds)
            - 'words': list[dict] where each word dict has 'word', 'start', and 'end'
            
    Returns:
        list[dict]: A flat list of all words with corrected timestamps, sorted by start time.
    """
    master_word_list = []
    
    for chunk in transcribed_chunks:
        offset = chunk.get("offset", 0)
        words = chunk.get("words", [])
        
        for w in words:
            corrected_word = {
                "word": w["word"],
                "start": w["start"] + offset,
                "end": w["end"] + offset
            }
            master_word_list.append(corrected_word)
            
    # Sort by 'start' time to handle out-of-order chunks from parallel execution
    master_word_list.sort(key=lambda x: x["start"])
    
    return master_word_list
