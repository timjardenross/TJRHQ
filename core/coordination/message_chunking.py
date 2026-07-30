"""Split long messages so they survive chat-platform character limits.

Telegram caps a message at 4096 chars; Slack at ~40000 but blocks/sections are
smaller. A long engineering plan or patch must be sent as several messages
rather than truncated. This splits text boundary-aware:

    paragraph (blank line)  →  line  →  hard char cut (last resort)

and it never splits inside a fenced code block — each chunk re-opens/closes the
fence so code stays valid in every part. Pure, dependency-free, reusable by any
Telegram/Slack front-end.
"""

from __future__ import annotations

# Conservative defaults: Telegram hard limit is 4096; leave headroom for the
# part header and a possibly-reopened code fence.
TELEGRAM_LIMIT = 4096
DEFAULT_LIMIT = 3800


def _split_oversized_line(line: str, limit: int) -> list[str]:
    """Hard-split a single line longer than the limit (last resort)."""
    return [line[i:i + limit] for i in range(0, len(line), limit)]


def chunk_message(text: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    """Split `text` into chunks each <= `limit` chars, on safe boundaries.

    Returns [] for empty text, [text] when it already fits. Splits on blank-line
    paragraph breaks first, then single newlines, then (only if a single line is
    itself too long) a hard character cut. Fenced code blocks (```) are kept
    valid: a chunk that ends inside a fence closes it, and the next chunk reopens
    it with the same info string.
    """
    if text is None or not text.strip():
        return []
    text = text.strip("\n")
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for raw_line in text.split("\n"):
        if len(raw_line) <= limit:
            if not current:
                current = raw_line
            elif len(current) + 1 + len(raw_line) <= limit:
                current += "\n" + raw_line
            else:
                flush()
                current = raw_line
        else:
            # a single line longer than the limit → hard-split it; the last piece
            # carries on as the running chunk so following lines can pack onto it.
            flush()
            pieces = _split_oversized_line(raw_line, limit)
            chunks.extend(pieces[:-1])
            current = pieces[-1]
    flush()

    return _balance_code_fences(chunks)


def _balance_code_fences(chunks: list[str]) -> list[str]:
    """Keep ``` fences valid across chunk boundaries.

    If a chunk has an odd number of fences (ends inside a code block), close it,
    and reopen the block at the start of the next chunk using the same language.
    """
    out: list[str] = []
    carry_lang: str | None = None
    for chunk in chunks:
        body = chunk
        if carry_lang is not None:
            body = f"```{carry_lang}\n" + body
            carry_lang = None
        # Count fences in this (possibly reopened) chunk.
        fences = [ln for ln in body.split("\n") if ln.lstrip().startswith("```")]
        if len(fences) % 2 == 1:
            # ends inside a code block — capture the language from the opening fence
            opener = fences[-1].strip()
            carry_lang = opener[3:].strip()  # text after ``` (may be "")
            body = body + "\n```"
        out.append(body)
    return out


def chunk_with_headers(text: str, limit: int = DEFAULT_LIMIT,
                       header: str = "({i}/{n})") -> list[str]:
    """Like chunk_message, but prefix multi-part output with `(i/n)` headers.

    Single-chunk output is returned unprefixed. The header length is accounted
    for so prefixed chunks still fit under `limit`.
    """
    # First pass to learn the part count, with headroom for the header.
    rough = chunk_message(text, limit=max(64, limit - 16))
    n = len(rough)
    if n <= 1:
        return rough
    return [f"{header.format(i=i + 1, n=n)}\n{c}" for i, c in enumerate(rough)]


__all__ = ["chunk_message", "chunk_with_headers", "TELEGRAM_LIMIT", "DEFAULT_LIMIT"]
