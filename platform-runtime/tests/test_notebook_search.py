"""Tests for notebook_search.py (EXEC-010C WP6)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BOT_DIR = REPO_ROOT / "slack-bot"
for p in (str(REPO_ROOT), str(BOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.notebook.notebook_search import (
    SearchHit,
    SearchResults,
    _excerpt,
    _score,
    _tokenise,
    format_search_results,
    search,
)


# ── Unit: tokenise / score / excerpt ──────────────────────────────────────────

def test_tokenise_splits_on_whitespace_and_punctuation():
    tokens = _tokenise("operational resilience dashboard")
    assert "operational" in tokens
    assert "resilience" in tokens
    assert "dashboard" in tokens


def test_tokenise_filters_short_tokens():
    tokens = _tokenise("a to do it")
    assert not any(len(t) <= 2 for t in tokens)


def test_score_returns_zero_for_no_match():
    assert _score("unrelated text", ["xyzzy", "quux"]) == 0.0


def test_score_returns_nonzero_for_match():
    assert _score("architecture design pattern", ["architecture", "design"]) > 0.0


def test_score_capped_at_one():
    text = "architecture " * 50
    s = _score(text, ["architecture"])
    assert s <= 1.0


def test_excerpt_returns_text_around_first_match():
    text = "This is some content about architecture and design decisions."
    ex = _excerpt(text, ["architecture"])
    assert "architecture" in ex.lower()


def test_excerpt_handles_empty_text():
    assert _excerpt("", ["foo"]) == ""


# ── search — empty query ───────────────────────────────────────────────────────

def test_search_empty_query_returns_empty_results():
    sb = MagicMock()
    results = search("", sb)
    assert results.empty
    assert results.query == ""


def test_search_whitespace_query_returns_empty():
    sb = MagicMock()
    results = search("   ", sb)
    assert results.empty


# ── search — supabase failure ──────────────────────────────────────────────────

def test_search_supabase_error_degrades_gracefully():
    sb = MagicMock()
    sb.table.side_effect = Exception("Connection error")
    results = search("architecture", sb)
    assert isinstance(results, SearchResults)
    assert results.empty


# ── search — hit ranking ───────────────────────────────────────────────────────

def _make_sb_with_notes(rows_per_table: dict[str, list[dict]]) -> MagicMock:
    """Build a Supabase mock that returns the given rows for each table name.

    _search_table builds chains like:
      .table(t).select(cols).not_.in_(col, vals).limit(n).execute()  [with status_filter]
      .table(t).select(cols).limit(n).execute()                       [without status_filter]
      .table(t).select(cols).like(col, pat).limit(n).execute()        [command_memory]

    not_ is an attribute (not called), so chain is: .not_.in_().limit().execute()
    """
    sb = MagicMock()

    def _table_side_effect(table_name):
        m = MagicMock()
        rows = rows_per_table.get(table_name, [])
        chain = MagicMock()
        chain.execute.return_value.data = rows
        # with status_filter: .select().not_.in_().limit().execute()
        m.select.return_value.not_.in_.return_value.limit.return_value = chain
        # without status_filter: .select().limit().execute()
        m.select.return_value.limit.return_value = chain
        # command_memory path: .select().like().limit().execute()
        m.select.return_value.like.return_value.limit.return_value = chain
        return m

    sb.table.side_effect = _table_side_effect
    return sb


def test_search_returns_hits_from_intelligence_notes():
    sb = _make_sb_with_notes({
        "intelligence_notes": [
            {"id": "n1", "title": "Architecture review", "raw_content": "architecture design discussion", "triage_summary": "", "status": "CAPTURED"},
        ]
    })
    results = search("architecture", sb)
    hit_sources = [h.source_type for h in results.hits]
    assert "intelligence_notes" in hit_sources


def test_search_results_sorted_by_relevance_descending():
    sb = _make_sb_with_notes({
        "intelligence_notes": [
            {"id": "n1", "title": "Architecture", "raw_content": "architecture design architecture pattern architecture", "triage_summary": "", "status": "CAPTURED"},
            {"id": "n2", "title": "Other", "raw_content": "architecture", "triage_summary": "", "status": "CAPTURED"},
        ]
    })
    results = search("architecture", sb)
    if len(results.hits) >= 2:
        assert results.hits[0].relevance >= results.hits[1].relevance


def test_search_respects_limit():
    many_notes = [
        {"id": f"n{i}", "title": f"Note {i}", "raw_content": "architecture design", "triage_summary": "", "status": "CAPTURED"}
        for i in range(30)
    ]
    sb = _make_sb_with_notes({"intelligence_notes": many_notes})
    results = search("architecture", sb, limit=5)
    assert len(results.hits) <= 5


# ── format_search_results ──────────────────────────────────────────────────────

def test_format_empty_results():
    results = SearchResults(query="test")
    out = format_search_results(results)
    assert "No results" in out
    assert "test" in out


def test_format_results_includes_title():
    results = SearchResults(
        query="architecture",
        hits=[SearchHit(source_type="intelligence_notes", record_id="n1", title="Architecture Review", excerpt="...", relevance=0.9)],
        sources_searched=["intelligence_notes"],
    )
    out = format_search_results(results)
    assert "Architecture Review" in out
    assert "Notebook" in out
