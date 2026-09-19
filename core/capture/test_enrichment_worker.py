"""Tests for core/capture/enrichment_worker.py — MSN-XXXX-D."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import enrichment_worker as ew

# ── _call_llm response parsing ────────────────────────────────────────────────

def _mock_ollama(content: str):
    """Patch urllib.request.urlopen to return a mock Ollama response."""
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

    def test_actionable_fields_parsed(self):
        suggestion_json = json.dumps({
            "classification": "reference",
            "importance": "medium",
            "suggested_route": "note",
            "confidence": 0.7,
            "actionable": "yes",
            "actionable_confidence": 0.85,
            "reasoning": "A concrete errand.",
        })
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("buy dog food")
        assert result["actionable"] == "yes"
        assert result["actionable_confidence"] == 0.85

    def test_missing_actionable_defaults_to_ambiguous_zero_confidence(self):
        """Safe failure mode: absence must never imply 'yes' — matches this
        worker's existing default-to-unclassified pattern for a missing/bad
        classification."""
        suggestion_json = json.dumps({
            "classification": "personal",
            "importance": "low",
            "suggested_route": "note",
            "confidence": 0.6,
            "reasoning": "no actionable field at all",
        })
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("felt tired today")
        assert result["actionable"] == "ambiguous"
        assert result["actionable_confidence"] == 0.0

    def test_invalid_actionable_value_falls_back_to_ambiguous(self):
        suggestion_json = json.dumps({
            "classification": "personal",
            "importance": "low",
            "suggested_route": "note",
            "confidence": 0.6,
            "actionable": "definitely",  # invalid
            "actionable_confidence": 0.9,
            "reasoning": "test",
        })
        with _mock_ollama(suggestion_json):
            result = ew._call_llm("some text")
        assert result["actionable"] == "ambiguous"

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

    def test_duplicate_match_skips_llm_and_flags_item(self):
        fake_match = ew.dedup.DuplicateMatch(duplicate_of_id="dup-source-id", similarity=0.91, matched_text="earlier capture")
        captured_patch_calls = []

        def fake_patch(table, match, update):
            captured_patch_calls.append(update)

        with patch.object(ew.dedup, "find_duplicate", return_value=fake_match), \
             patch("urllib.request.urlopen") as mock_urlopen, \
             patch.object(ew, "_sb_patch", side_effect=fake_patch):
            result = ew.enrich_item(self._item(), dedup_index=object())

        assert result is True
        mock_urlopen.assert_not_called()  # no LLM call once a duplicate is found
        update = captured_patch_calls[-1]
        assert update["duplicate_of_id"] == "dup-source-id"
        assert update["duplicate_similarity"] == 0.91
        assert "duplicate_checked_at" in update
        assert update["ai_enrichment_status"] == "enriched"

    def test_duplicate_match_dry_run_writes_nothing(self, capsys):
        fake_match = ew.dedup.DuplicateMatch(duplicate_of_id="dup-source-id", similarity=0.91, matched_text="earlier capture")
        with patch.object(ew.dedup, "find_duplicate", return_value=fake_match), \
             patch.object(ew, "_sb_patch") as mock_patch:
            result = ew.enrich_item(self._item(), dry_run=True, dedup_index=object())
        assert result is True
        mock_patch.assert_not_called()
        assert "dedup DRY RUN" in capsys.readouterr().out

    def test_no_dedup_index_behaves_as_before(self):
        """Passing no dedup_index (the default) must never call find_duplicate
        with anything that touches semhash — behaviour identical to before
        this feature existed."""
        suggestion_json = json.dumps({
            "classification": "reference", "importance": "low",
            "suggested_route": "note", "confidence": 0.6, "reasoning": "test",
        })
        with _mock_ollama(suggestion_json), patch.object(ew, "_sb_patch"):
            result = ew.enrich_item(self._item())
        assert result is True

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


class TestActionableRouting:
    """Mission 3: captured_items -> personal_tasks bridge."""

    def _item(self, **kwargs) -> dict:
        base = {
            "id":                    "00000000-0000-0000-0000-000000000002",
            "title":                 "Buy dog food",
            "raw_text":              "I need to buy dog food",
            "summary":               None,
            "ai_enrichment_status":  "not_enriched",
        }
        base.update(kwargs)
        return base

    def test_actionable_yes_above_threshold_routes_to_personal_task(self):
        suggestion_json = json.dumps({
            "classification": "reference", "importance": "medium",
            "suggested_route": "note", "confidence": 0.7,
            "actionable": "yes", "actionable_confidence": 0.9,
            "reasoning": "A concrete errand.",
        })
        with _mock_ollama(suggestion_json), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_route_to_personal_task", return_value=True) as mock_route, \
             patch.object(ew, "_auto_route_personal") as mock_log, \
             patch.object(ew, "_promote_to_intelligence_note") as mock_promote:
            result = ew.enrich_item(self._item())
        assert result is True
        mock_route.assert_called_once()
        mock_log.assert_not_called()
        mock_promote.assert_not_called()

    def test_actionable_ambiguous_falls_through_to_classification_routing(self):
        suggestion_json = json.dumps({
            "classification": "mission", "importance": "high",
            "suggested_route": "missions_inbox", "confidence": 0.9,
            "actionable": "ambiguous", "actionable_confidence": 0.3,
            "reasoning": "test",
        })
        with _mock_ollama(suggestion_json), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_route_to_personal_task") as mock_route, \
             patch.object(ew, "_promote_to_intelligence_note", return_value=True) as mock_promote:
            result = ew.enrich_item(self._item())
        assert result is True
        mock_route.assert_not_called()
        mock_promote.assert_called_once()

    def test_actionable_yes_below_confidence_threshold_does_not_route(self):
        suggestion_json = json.dumps({
            "classification": "reference", "importance": "low",
            "suggested_route": "note", "confidence": 0.6,
            "actionable": "yes", "actionable_confidence": 0.4,  # below 0.6 bar
            "reasoning": "test",
        })
        with _mock_ollama(suggestion_json), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_route_to_personal_task") as mock_route:
            ew.enrich_item(self._item())
        mock_route.assert_not_called()

    def test_unclassified_never_routes_even_if_actionable(self):
        """Hard invariant must win regardless of actionability."""
        suggestion_json = json.dumps({
            "classification": "unclassified", "importance": "medium",
            "suggested_route": "none", "confidence": 0.3,
            "actionable": "yes", "actionable_confidence": 0.95,
            "reasoning": "test",
        })
        with _mock_ollama(suggestion_json), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_route_to_personal_task") as mock_route:
            ew.enrich_item(self._item())
        mock_route.assert_not_called()

    def test_route_to_personal_task_idempotent_on_unique_violation(self):
        """A retried enrichment pass must not create a second task — the
        unique-violation on insert is treated as 'already routed', not an
        error, and the existing task's id is used to complete the link."""
        conflict_body = b'{"code":"23505","message":"duplicate key value violates unique constraint \\"personal_tasks_source_capture_uniq\\""}'

        class _FakeHTTPError(ew.urllib.error.HTTPError):
            def __init__(self):
                super().__init__("url", 409, "Conflict", {}, None)
            def read(self):
                return conflict_body

        item = self._item()
        suggestion = {"actionable": "yes", "actionable_confidence": 0.9, "importance": "medium"}
        patch_calls = []

        with patch.object(ew, "_sb_insert", side_effect=_FakeHTTPError()), \
             patch.object(ew, "_sb_get_one", return_value={"id": "existing-task-id"}), \
             patch.object(ew, "_sb_patch", side_effect=lambda t, m, u: patch_calls.append(u)), \
             patch.object(ew, "_send_telegram_confirmation"):
            result = ew._route_to_personal_task(item, suggestion)

        assert result is True
        assert patch_calls[-1]["routed_to_id"] == "existing-task-id"
        assert patch_calls[-1]["routed_to_table"] == "personal_tasks"

    def test_idempotent_retry_does_not_resend_confirmation(self):
        """A reprocessed item must not send a second Telegram confirmation
        — only the original pass that actually created the task does."""
        conflict_body = b'{"code":"23505","message":"duplicate key value violates unique constraint \\"personal_tasks_source_capture_uniq\\""}'

        class _FakeHTTPError(ew.urllib.error.HTTPError):
            def __init__(self):
                super().__init__("url", 409, "Conflict", {}, None)
            def read(self):
                return conflict_body

        item = self._item()
        suggestion = {"actionable": "yes", "actionable_confidence": 0.9, "importance": "medium"}

        with patch.object(ew, "_sb_insert", side_effect=_FakeHTTPError()), \
             patch.object(ew, "_sb_get_one", return_value={"id": "existing-task-id"}), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_send_telegram_confirmation") as mock_confirm:
            result = ew._route_to_personal_task(item, suggestion)

        assert result is True
        mock_confirm.assert_not_called()

    def test_fresh_route_sends_exactly_one_confirmation(self):
        item = self._item()
        suggestion = {"actionable": "yes", "actionable_confidence": 0.9, "importance": "medium"}

        with patch.object(ew, "_sb_insert", return_value={"id": "new-task-id"}), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_send_telegram_confirmation") as mock_confirm:
            result = ew._route_to_personal_task(item, suggestion)

        assert result is True
        mock_confirm.assert_called_once()

    def test_parsed_due_date_hint_honoured_on_task_creation(self):
        """Preserves temporal intent extracted by the Telegram NL-capture
        path (telegram-bots/xo/app.py) across the captured_items ->
        personal_tasks bridge."""
        item = self._item(summary=json.dumps({"parsed_due_date": "2026-09-26", "parse_source": "telegram_nl_capture"}))
        suggestion = {"actionable": "yes", "actionable_confidence": 0.9, "importance": "medium"}
        insert_calls = []

        def fake_insert(table, record):
            insert_calls.append(record)
            return {"id": "new-task-id"}

        with patch.object(ew, "_sb_insert", side_effect=fake_insert), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_send_telegram_confirmation"):
            ew._route_to_personal_task(item, suggestion)

        assert insert_calls[0]["due_date"] == "2026-09-26"

    def test_no_due_date_hint_creates_task_with_none_due_date(self):
        item = self._item()  # summary=None
        suggestion = {"actionable": "yes", "actionable_confidence": 0.9, "importance": "medium"}
        insert_calls = []

        def fake_insert(table, record):
            insert_calls.append(record)
            return {"id": "new-task-id"}

        with patch.object(ew, "_sb_insert", side_effect=fake_insert), \
             patch.object(ew, "_sb_patch"), \
             patch.object(ew, "_send_telegram_confirmation"):
            ew._route_to_personal_task(item, suggestion)

        assert insert_calls[0]["due_date"] is None


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
             patch.object(ew.dedup, "build_recent_index", return_value=None), \
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
             patch.object(ew.dedup, "build_recent_index", return_value=None), \
             patch("urllib.request.urlopen", side_effect=Exception("connection refused")), \
             patch.object(ew, "_sb_patch"), \
             patch("time.sleep"):
            result = ew.run_batch(limit=10)
        assert result["errors"] == 1
        assert result["ok"] == 0

    def test_builds_dedup_index_once_and_passes_to_every_item(self):
        items = [
            {"id": f"id-{i:04d}", "title": f"Item {i}", "raw_text": f"text {i}", "summary": None, "ai_enrichment_status": "not_enriched"}
            for i in range(3)
        ]
        sentinel_index = object()
        seen_indexes = []

        def fake_enrich_item(item, dry_run=False, dedup_index=None):
            seen_indexes.append(dedup_index)
            return True

        with patch.object(ew, "_sb_get", return_value=items), \
             patch.object(ew.dedup, "build_recent_index", return_value=sentinel_index) as build_mock, \
             patch.object(ew, "enrich_item", side_effect=fake_enrich_item), \
             patch("time.sleep"):
            ew.run_batch(limit=10)

        build_mock.assert_called_once()
        assert seen_indexes == [sentinel_index, sentinel_index, sentinel_index]


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
