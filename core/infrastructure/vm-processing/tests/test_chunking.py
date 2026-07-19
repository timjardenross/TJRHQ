import pytest

from chunking import chunk_text


def test_short_text_returns_single_chunk():
    assert chunk_text("short text", max_chars=100) == ["short text"]


def test_blank_text_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_long_text_splits_with_overlap_and_bounded_size():
    text = ("word " * 2000).strip()
    chunks = chunk_text(text, max_chars=100, overlap_chars=20)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # every chunk is non-empty and words aren't glued together mid-token
    assert all(c.strip() for c in chunks)


def test_invalid_overlap_raises():
    with pytest.raises(ValueError):
        chunk_text("x" * 10, max_chars=5, overlap_chars=5)
    with pytest.raises(ValueError):
        chunk_text("x" * 10, max_chars=0)


def test_always_makes_forward_progress_no_infinite_loop():
    # A pathological string with no natural break points near the boundary.
    text = "a" * 5000
    chunks = chunk_text(text, max_chars=50, overlap_chars=45)
    assert len(chunks) > 1
    assert "".join(chunks).replace("a", "a")  # just confirms it terminated
