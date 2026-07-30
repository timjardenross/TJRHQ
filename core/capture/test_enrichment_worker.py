"""Tests for core/capture/enrichment_worker.py — MSN-XXXX-D."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import enrichment_worker as ew


# ── _call_llm response parsing ────────────────────────────────────────────────

def _mock_ollama(content: str):
    """Patch urllib.request.urlopen to return a mock Ollama response."""
    import io
    resp_body = json.dumps({"message": {"content": content}}).encode()

    class _FakeResp:
        def read(self): return resp_body
        def __enter__(self): return self
        def __exit__(self, *a): pass

    return patch("urllib.request.urlopen", return_value=_FakeResp())


class TestCallLLM:
    def test_valid_response_parsed(self):
        suggestion_json = json.dumps({
            "classification": "mission",
            "importance": "high",
            "suggested_route": "missions_inbox",
            "confidence": 0.9,
            "reasoning": "Clear build request.",
        })
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("Build a new monitoring dashboard")
        assert result["classification"] == "mission"
        assert result["importance"] == "high"
        assert result["confidence"] == 0.9

    def test_invalid_classification_falls_back_to_unclassified(self):
        suggestion_json = json.dumps({
            "classification": "banana",  # invalid
            "importance": "high",
            "suggested_route": "none",
            "confidence": 0.5,
            "reasoning": "test",
        })
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("some text")
        assert result["classification"] == "unclassified"

    def test_invalid_importance_falls_back_to_medium(self):
        suggestion_json = json.dumps({
            "classification": "reference",
            "importance": "extreme",  # invalid
            "suggested_route": "none",
            "confidence": 0.7,
            "reasoning": "test",
        })
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("some text")
        assert result["importance"] == "medium"

    def test_confidence_clamped(self):
        suggestion_json = json.dumps({
            "classification": "research",
            "importance": "low",
            "suggested_route": "research_inbox",
            "confidence": 1.5,  # > 1.0
            "reasoning": "test",
        })
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("idea about quantum computing")
        assert result["confidence"] <= 1.0

    def test_markdown_fenced_json_stripped(self):
        suggestion_json = "```json\n" + json.dumps({
            "classification": "decision",
            "importance": "high",
            "suggested_route": "decision_queue",
            "confidence": 0.8,
            "reasoning": "Needs Captain choice.",
        }) + "\n```"
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("Should we go with option A or B?")
        assert result["classification"] == "decision"


# ── enrich_item ───────────────────────────────────────────────────────────────

class TestEnrichItem:
    def _item(self, **kwargs) -> dict:
        base = {
            "id":                    "00000000-0000-0000-0000-000000000001",
            "title":                 "Call the physio tomorrow",
            "raw_text":              "I need to call the physio tomorrow and book an appointment",
            "summary":               None,
            "ai_enrichment_status":  "not_enriched",
        }
        base.update(kwargs)
        return base

    def test_dry_run_does_not_call_supabase(self, capsys):
        suggestion_json = json.dumps({
            "classification": "reference",
            "importance": "medium",
            "suggested_route": "note",
            "confidence": 0.75,
            "reasoning": "A reminder task.",
        })
        with _mock_ollama(suggestion_json), \
             patch.object(ew, "_sb_patch") as mock_patch:
            result = ew.enrich_item(self._item(), dry_run=True)
        assert result is True
        mock_patch.assert_not_called()

    def test_empty_text_returns_false(self):
        item = self._item(raw_text="", title="")
        result = ew.enrich_item(item, dry_run=True)
        assert result is False

    def test_llm_failure_sets_failed_status(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")), \
             patch.object(ew, "_sb_patch") as mock_patch:
            result = ew.enrich_item(self._item())
        assert result is False
        # second call sets failed status
        calls = [str(c) for c in mock_patch.call_args_list]
        assert any("failed" in c for c in calls)

    def test_successful_enrichment_writes_summary(self):
        suggestion_json = json.dumps({
            "classification": "mission",
            "importance": "high",
            "suggested_route": "missions_inbox",
            "confidence": 0.88,
            "reasoning": "Build request.",
        })
        captured_patch_calls = []

        def fake_patch(table, match, update):
            captured_patch_calls.append((table, match, update))

        with _mock_ollama(suggestion_json), patch.object(ew, "_sb_patch", side_effect=fake_patch):
            result = ew.enrich_item(self._item())

        assert result is True
        final_patch = captured_patch_calls[-1][2]
        assert final_patch["ai_enrichment_status"] == "enriched"
        summary = json.loads(final_patch["summary"])
        assert summary["suggested_classification"] == "mission"
        assert summary["ai_confidence"] == 0.88
        assert "enriched_at" in summary
        assert "enrichment_model" in summary

    def test_does_not_auto_route(self):
        """Enrichment must never update processing_status or classification on the item."""
        suggestion_json = json.dumps({
            "classification": "mission",
            "importance": "high",
            "suggested_route": "missions_inbox",
            "confidence": 0.9,
            "reasoning": "test",
        })
        captured_patches = []

        def fake_patch(table, match, update):
            captured_patches.append(update)

        with _mock_ollama(suggestion_json), patch.object(ew, "_sb_patch", side_effect=fake_patch):
            ew.enrich_item(self._item())

        for patch_update in captured_patches:
            assert "processing_status" not in patch_update, \
                "Enrichment must not change processing_status"
            assert "classification" not in patch_update, \
                "Enrichment must not auto-set classification — suggestions only"
            assert "routed_to_table" not in patch_update, \
                "Enrichment must not auto-route"


# ── run_batch ─────────────────────────────────────────────────────────────────

class TestRunBatch:
    def test_empty_queue_returns_zero(self):
        with patch.object(ew, "_sb_get", return_value=[]):
            result = ew.run_batch(limit=10)
        assert result == {"processed": 0, "ok": 0, "errors": 0}

    def test_processes_all_returned_items(self):
        items = [
            {"id": f"id-{i:04d}", "title": f"Item {i}", "raw_text": f"text {i}", "summary": None, "ai_enrichment_status": "not_enriched"}
            for i in range(3)
        ]
        suggestion_json = json.dumps({
            "classification": "reference", "importance": "low",
            "suggested_route": "note", "confidence": 0.6, "reasoning": "test",
        })
        with patch.object(ew, "_sb_get", return_value=items), \
             _mock_ollama(suggestion_json), \
             patch.object(ew, "_sb_patch"), \
             patch("time.sleep"):
            result = ew.run_batch(limit=10)
        assert result["processed"] == 3
        assert result["ok"] == 3
        assert result["errors"] == 0

    def test_item_error_counted_not_fatal(self):
        items = [
            {"id": "id-0001", "title": "Test", "raw_text": "test", "summary": None, "ai_enrichment_status": "not_enriched"},
        ]
        with patch.object(ew, "_sb_get", return_value=items), \
             patch("urllib.request.urlopen", side_effect=Exception("connection refused")), \
             patch.object(ew, "_sb_patch"), \
             patch("time.sleep"):
            result = ew.run_batch(limit=10)
        assert result["errors"] == 1
        assert result["ok"] == 0


# ── _safe_parse_summary ────────────────────────────────────────────────────────

class TestSafeParseSummary:
    def test_none_returns_empty_dict(self):
        assert ew._safe_parse_summary(None) == {}

    def test_dict_passthrough(self):
        d = {"a": 1}
        assert ew._safe_parse_summary(d) == {"a": 1}

    def test_json_string_parsed(self):
        assert ew._safe_parse_summary('{"x": 2}') == {"x": 2}

    def test_invalid_json_returns_empty(self):
        assert ew._safe_parse_summary("not json {") == {}


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
