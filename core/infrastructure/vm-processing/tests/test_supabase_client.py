from supabase_client import _strip_null_bytes


def test_strips_null_byte_from_string():
    assert _strip_null_bytes("abc\x00def") == "abcdef"


def test_leaves_clean_string_unchanged():
    assert _strip_null_bytes("clean text") == "clean text"


def test_recurses_into_nested_dicts_and_lists():
    value = {
        "extracted_text": "some\x00text",
        "metadata": {"note": "ni\x00ce"},
        "processing_log": [{"event": "failed", "detail": "bad\x00byte"}],
    }
    cleaned = _strip_null_bytes(value)
    assert cleaned["extracted_text"] == "sometext"
    assert cleaned["metadata"]["note"] == "nice"
    assert cleaned["processing_log"][0]["detail"] == "badbyte"


def test_non_string_values_pass_through():
    assert _strip_null_bytes(42) == 42
    assert _strip_null_bytes(None) is None
    assert _strip_null_bytes([1, 2.5, None]) == [1, 2.5, None]
