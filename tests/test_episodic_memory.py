"""Unit tests for core/platform/episodic_memory.py — episodic memory v1.

All Supabase and HTTP calls are mocked so these run fully offline.
Tests cover: embed_text, store_memory, recall_similar (vector + keyword fallback),
and increment_reuse.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure repo root is on the path so the module resolves its internal imports.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.platform.episodic_memory import (
    embed_text,
    increment_reuse,
    recall_similar,
    store_memory,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_embed_response(vector: list[float]) -> MagicMock:
    """Build a urllib response mock that returns an embed JSON body."""
    body = json.dumps({"embeddings": [vector]}).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


_SAMPLE_VECTOR = [0.1] * 768


# ── embed_text ────────────────────────────────────────────────────────────────

class TestEmbedText:
    def test_returns_first_vector_on_success(self):
        with patch("urllib.request.urlopen", return_value=_fake_embed_response(_SAMPLE_VECTOR)):
            result = embed_text("hello world")
        assert result == _SAMPLE_VECTOR

    def test_returns_none_on_url_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            result = embed_text("hello world")
        assert result is None

    def test_returns_none_on_empty_text(self):
        result = embed_text("")
        assert result is None

    def test_returns_none_on_whitespace_text(self):
        result = embed_text("   ")
        assert result is None

    def test_returns_none_when_no_embeddings_field(self):
        body = json.dumps({"success": False}).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp):
            result = embed_text("hello")
        assert result is None

    def test_posts_to_model_router_with_correct_payload(self):
        captured_requests = []

        def fake_urlopen(req, timeout=None):
            captured_requests.append(req)
            return _fake_embed_response(_SAMPLE_VECTOR)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            embed_text("test query")

        assert len(captured_requests) == 1
        req = captured_requests[0]
        payload = json.loads(req.data.decode())
        assert payload["model"] == "nomic-embed-text"
        assert payload["input"] == "test query"
        assert "localhost:8891" in req.full_url

    def test_returns_none_on_unexpected_exception(self):
        with patch("urllib.request.urlopen", side_effect=RuntimeError("unexpected")):
            result = embed_text("test")
        assert result is None


# ── store_memory ──────────────────────────────────────────────────────────────

class TestStoreMemory:
    def _make_raw_client(self, inserted_id: str = "uuid-abc") -> MagicMock:
        raw = MagicMock()
        insert_execute = MagicMock()
        insert_execute.data = [{"id": inserted_id}]
        raw.table.return_value.insert.return_value.execute.return_value = insert_execute

        update_execute = MagicMock()
        raw.table.return_value.update.return_value.eq.return_value.execute.return_value = update_execute
        return raw

    def test_returns_row_id_on_success(self):
        raw = self._make_raw_client("new-uuid")
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=_SAMPLE_VECTOR),
        ):
            result = store_memory(
                question="what is risk?",
                findings="risk is present",
                recommendation="act now",
                confidence=0.9,
                tags=["risk"],
                query_hash="abc123",
            )
        assert result == "new-uuid"

    def test_attaches_embedding_to_row(self):
        raw = self._make_raw_client("embed-uuid")
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=_SAMPLE_VECTOR),
        ):
            store_memory("q", "findings", "rec", 0.8, [], "hash1")

        # Verify update was called with the embedding vector
        update_calls = raw.table.return_value.update.call_args_list
        assert any(
            "embedding" in (args[0] if args else kwargs)
            for args, kwargs in update_calls
        ), "update() should have been called with embedding"

    def test_returns_row_id_even_when_embed_unavailable(self):
        """Row must be stored even when the Model Router is down."""
        raw = self._make_raw_client("no-embed-uuid")
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=None),
        ):
            result = store_memory("q", "f", "r", 0.5, [], "hash2")
        assert result == "no-embed-uuid"

    def test_returns_none_when_supabase_unavailable(self):
        with patch("core.platform.episodic_memory._supabase_raw", return_value=None):
            result = store_memory("q", "f", "r", 0.5, [], "hash3")
        assert result is None

    def test_returns_none_when_insert_returns_no_rows(self):
        raw = MagicMock()
        insert_execute = MagicMock()
        insert_execute.data = []
        raw.table.return_value.insert.return_value.execute.return_value = insert_execute
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=_SAMPLE_VECTOR),
        ):
            result = store_memory("q", "f", "r", 0.5, [], "hash4")
        assert result is None

    def test_embedding_text_combines_question_and_findings_prefix(self):
        raw = self._make_raw_client("combo-uuid")
        captured_texts = []

        def fake_embed(text):
            captured_texts.append(text)
            return _SAMPLE_VECTOR

        long_findings = "x" * 1000  # longer than 500 char limit
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", side_effect=fake_embed),
        ):
            store_memory("my question", long_findings, "rec", 0.7, [], "hash5")

        assert len(captured_texts) == 1
        embed_input = captured_texts[0]
        assert embed_input.startswith("my question ")
        assert len(embed_input) <= len("my question ") + 500


# ── recall_similar ────────────────────────────────────────────────────────────

class TestRecallSimilar:
    def test_returns_rpc_results_on_vector_success(self):
        rpc_rows = [
            {"id": "r1", "original_question": "risk?", "similarity": 0.9},
        ]
        raw = MagicMock()
        raw.rpc.return_value.execute.return_value.data = rpc_rows
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=_SAMPLE_VECTOR),
        ):
            result = recall_similar("risk analysis")
        assert result == rpc_rows
        raw.rpc.assert_called_once_with(
            "match_research_memories",
            {"query_embedding": _SAMPLE_VECTOR, "match_threshold": 0.75, "match_count": 10},
        )

    def test_falls_back_to_keyword_when_embed_unavailable(self):
        keyword_rows = [{"id": "k1", "original_question": "risk?"}]
        raw = MagicMock()
        keyword_chain = (
            raw.table.return_value.select.return_value
            .ilike.return_value
            .eq.return_value
            .order.return_value
            .limit.return_value
        )
        keyword_chain.execute.return_value.data = keyword_rows
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=None),
        ):
            result = recall_similar("risk")
        assert len(result) == 1
        assert result[0]["id"] == "k1"
        # Sentinel similarity is added by the fallback path
        assert "similarity" in result[0]
        assert result[0]["similarity"] == 0.0
        # rpc() was NOT called
        raw.rpc.assert_not_called()

    def test_falls_back_to_keyword_when_rpc_raises(self):
        keyword_rows = [{"id": "k2", "original_question": "outage?"}]
        raw = MagicMock()
        raw.rpc.return_value.execute.side_effect = RuntimeError("rpc exploded")
        keyword_chain = (
            raw.table.return_value.select.return_value
            .ilike.return_value
            .eq.return_value
            .order.return_value
            .limit.return_value
        )
        keyword_chain.execute.return_value.data = keyword_rows
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=_SAMPLE_VECTOR),
        ):
            result = recall_similar("outage")
        assert result[0]["id"] == "k2"

    def test_returns_empty_on_supabase_unavailable(self):
        with patch("core.platform.episodic_memory._supabase_raw", return_value=None):
            result = recall_similar("anything")
        assert result == []

    def test_returns_empty_on_empty_query(self):
        result = recall_similar("")
        assert result == []

    def test_respects_threshold_and_limit_parameters(self):
        raw = MagicMock()
        raw.rpc.return_value.execute.return_value.data = []
        with (
            patch("core.platform.episodic_memory._supabase_raw", return_value=raw),
            patch("core.platform.episodic_memory.embed_text", return_value=_SAMPLE_VECTOR),
        ):
            recall_similar("query", threshold=0.85, limit=3)
        raw.rpc.assert_called_once_with(
            "match_research_memories",
            {"query_embedding": _SAMPLE_VECTOR, "match_threshold": 0.85, "match_count": 3},
        )


# ── increment_reuse ───────────────────────────────────────────────────────────

class TestIncrementReuse:
    def test_increments_reuse_count(self):
        raw = MagicMock()
        raw.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"reuse_count": 3}
        ]
        with patch("core.platform.episodic_memory._supabase_raw", return_value=raw):
            increment_reuse("some-uuid")
        raw.table.return_value.update.assert_called_once_with({"reuse_count": 4})

    def test_no_op_when_supabase_unavailable(self):
        with patch("core.platform.episodic_memory._supabase_raw", return_value=None):
            # Must not raise
            increment_reuse("some-uuid")

    def test_no_op_on_empty_memory_id(self):
        raw = MagicMock()
        with patch("core.platform.episodic_memory._supabase_raw", return_value=raw):
            increment_reuse("")
        raw.table.assert_not_called()

    def test_no_op_when_row_not_found(self):
        raw = MagicMock()
        raw.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        with patch("core.platform.episodic_memory._supabase_raw", return_value=raw):
            # Must not raise
            increment_reuse("missing-uuid")
        raw.table.return_value.update.assert_not_called()

    def test_non_blocking_on_exception(self):
        raw = MagicMock()
        raw.table.side_effect = RuntimeError("db down")
        with patch("core.platform.episodic_memory._supabase_raw", return_value=raw):
            # Must not raise — increment_reuse is always best-effort
            increment_reuse("any-uuid")
