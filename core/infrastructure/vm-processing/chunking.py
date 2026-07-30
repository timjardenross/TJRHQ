"""Text chunking for embedding generation (USS-TJR-MSN-0205C).

Deliberately separate from core/coordination/message_chunking.py, which
splits text to fit Telegram's 4096-char message limit (display concern, no
overlap). Embedding chunks need bounded size for a different reason
(retrieval granularity) and benefit from overlap so a fact split across a
chunk boundary is still findable from either chunk.
"""

from __future__ import annotations


def chunk_text(text: str, max_chars: int = 1200, overlap_chars: int = 150) -> list:
    """Split text into overlapping chunks, breaking on paragraph/sentence/word
    boundaries where possible rather than mid-word. Returns [] for blank text."""
    text = text.strip()
    if not text:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be >= 0")

    if len(text) <= max_chars:
        return [text]

    # overlap_chars only matters once we actually need to slide a window,
    # so it's validated here rather than up front — short text with a
    # small max_chars shouldn't have to satisfy a constraint on a
    # parameter that never comes into play.
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be < max_chars")

    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + max_chars, text_len)
        if end < text_len:
            end = _find_break_point(text, start, end)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(end - overlap_chars, start + 1)  # always make forward progress
    return chunks


def _find_break_point(text: str, start: int, hard_end: int) -> int:
    """Look backward from hard_end for a paragraph, then sentence, then word
    boundary, within a reasonable search window. Falls back to hard_end."""
    window_start = max(start, hard_end - 200)
    window = text[window_start:hard_end]

    for sep in ("\n\n", ". ", "\n", " "):
        idx = window.rfind(sep)
        if idx != -1:
            return window_start + idx + len(sep)
    return hard_end
