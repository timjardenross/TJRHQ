"""Tests for core/capture/dedup.py — cross-item semantic duplicate
detection for the Capture Workbench.

build_recent_index/find_duplicate are tested against a fake index object
(duck-typed to SemHash's real DeduplicationResult shape, verified against
its own dataclass source — see health_signal_synthesis.py's sibling test
suite for the same approach) rather than the real semhash package, so
these tests don't depend on Hugging Face Hub being reachable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dedup


def _item(item_id: str, text: str | None = "some capture text") -> dict:
    return {"id": item_id, "raw_text": text}


def _fake_index(filtered):
    """A duck-typed stand-in for a real SemHash instance — only
    .deduplicate() is ever called on it by find_duplicate()."""
    return SimpleNamespace(deduplicate=lambda records, threshold: SimpleNamespace(filtered=filtered))


def _duplicate_record(record, exact=False, duplicates=None):
    return SimpleNamespace(record=record, exact=exact, duplicates=duplicates or [])


# ── find_duplicate ────────────────────────────────────────────────────────────

def test_find_duplicate_none_when_no_index():
    assert dedup.find_duplicate(None, _item("a")) is None


def test_find_duplicate_none_when_no_text():
    index = _fake_index(filtered=[])
    assert dedup.find_duplicate(index, _item("a", text=None)) is None


def test_find_duplicate_none_when_nothing_filtered():
    index = _fake_index(filtered=[])
    assert dedup.find_duplicate(index, _item("a")) is None


def test_find_duplicate_returns_match():
    existing = {"id": "existing-1", "text": "buy milk on the way home"}
    index = _fake_index(filtered=[
        _duplicate_record(_item("new-1"), duplicates=[(existing, 0.93)]),
    ])
    match = dedup.find_duplicate(index, _item("new-1"))
    assert match is not None
    assert match.duplicate_of_id == "existing-1"
    assert match.similarity == 0.93
    assert match.matched_text == "buy milk on the way home"


def test_find_duplicate_skips_self_match():
    """The recent window isn't filtered by id, so an item can appear in
    its own comparison set — never report a self-match as a duplicate."""
    self_record = {"id": "new-1", "text": "same text"}
    real_dup = {"id": "existing-1", "text": "same text elsewhere"}
    index = _fake_index(filtered=[
        _duplicate_record(_item("new-1"), duplicates=[(self_record, 1.0), (real_dup, 0.9)]),
    ])
    match = dedup.find_duplicate(index, _item("new-1"))
    assert match is not None
    assert match.duplicate_of_id == "existing-1"


def test_find_duplicate_none_when_only_self_match():
    self_record = {"id": "new-1", "text": "same text"}
    index = _fake_index(filtered=[
        _duplicate_record(_item("new-1"), duplicates=[(self_record, 1.0)]),
    ])
    assert dedup.find_duplicate(index, _item("new-1")) is None


def test_find_duplicate_none_when_filtered_entry_has_no_duplicates():
    index = _fake_index(filtered=[_duplicate_record(_item("new-1"), duplicates=[])])
    assert dedup.find_duplicate(index, _item("new-1")) is None


def test_find_duplicate_handles_index_exception_gracefully():
    index = SimpleNamespace(deduplicate=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert dedup.find_duplicate(index, _item("a")) is None


# ── build_recent_index ────────────────────────────────────────────────────────

def test_build_recent_index_none_when_no_usable_records():
    assert dedup.build_recent_index([]) is None
    assert dedup.build_recent_index([_item("a", text=None), _item("b", text="")]) is None


def test_build_recent_index_calls_semhash_with_expected_records():
    pytest.importorskip("semhash")
    items = [_item("a", "first note"), _item("b", "second note")]
    with patch("semhash.SemHash.from_records") as from_records_mock:
        dedup.build_recent_index(items)
    from_records_mock.assert_called_once()
    _, kwargs = from_records_mock.call_args
    assert kwargs["records"] == [{"id": "a", "text": "first note"}, {"id": "b", "text": "second note"}]
    assert kwargs["columns"] == ["text"]


def test_build_recent_index_skips_items_with_no_text():
    pytest.importorskip("semhash")
    items = [_item("a", "has text"), _item("b", text=None), _item("c", text="")]
    with patch("semhash.SemHash.from_records") as from_records_mock:
        dedup.build_recent_index(items)
    _, kwargs = from_records_mock.call_args
    assert [r["id"] for r in kwargs["records"]] == ["a"]


def test_build_recent_index_falls_back_to_title_when_no_raw_text():
    pytest.importorskip("semhash")
    items = [{"id": "a", "raw_text": None, "title": "title only"}]
    with patch("semhash.SemHash.from_records") as from_records_mock:
        dedup.build_recent_index(items)
    _, kwargs = from_records_mock.call_args
    assert kwargs["records"] == [{"id": "a", "text": "title only"}]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
