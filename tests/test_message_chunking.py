#!/usr/bin/env python3
"""Tests for message chunking (Telegram/Slack character-limit handling).

Pure; no network. Runnable under pytest or directly:
`python3 tests/test_message_chunking.py` from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.message_chunking import (
    DEFAULT_LIMIT,
    chunk_message,
    chunk_with_headers,
)


def test_empty_and_short_text():
    assert chunk_message("") == []
    assert chunk_message("   \n  ") == []
    assert chunk_message("hello") == ["hello"]


def test_short_text_is_single_chunk():
    txt = "line one\nline two\nline three"
    assert chunk_message(txt, limit=100) == [txt]


def test_every_chunk_is_within_limit():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    chunks = chunk_message(text, limit=300)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_splits_on_line_boundaries_not_mid_word_when_possible():
    text = "\n".join(["alpha", "bravo", "charlie", "delta", "echo"])
    chunks = chunk_message(text, limit=12)   # forces multiple chunks
    # no word was broken — every original word appears intact somewhere
    joined = "\n".join(chunks)
    for w in ("alpha", "bravo", "charlie", "delta", "echo"):
        assert w in joined
    assert all(len(c) <= 12 for c in chunks)


def test_oversized_single_line_is_hard_split():
    text = "z" * 1000     # one line, no boundaries
    chunks = chunk_message(text, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == text          # nothing lost


def test_code_fence_kept_valid_across_chunks():
    code = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(80)) + "\n```"
    chunks = chunk_message(code, limit=200)
    assert len(chunks) > 1
    for c in chunks:
        # every chunk has balanced fences (even count of ``` lines)
        fences = [ln for ln in c.split("\n") if ln.lstrip().startswith("```")]
        assert len(fences) % 2 == 0, f"unbalanced fence in chunk: {c[:40]!r}"


def test_chunk_with_headers_numbers_multipart_only():
    short = chunk_with_headers("tiny", limit=100)
    assert short == ["tiny"]                # single part → no header
    big = chunk_with_headers("\n".join("y" * 50 for _ in range(50)), limit=200)
    assert len(big) > 1
    assert big[0].startswith("(1/")
    assert big[-1].startswith(f"({len(big)}/{len(big)})")


def test_default_limit_under_telegram_cap():
    assert DEFAULT_LIMIT < 4096


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
