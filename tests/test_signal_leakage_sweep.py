"""Briefs/Captain's Brief consolidation — broader signal-leakage sweep.

`tests/test_signal_leakage_fix.py` locked in the root-cause fix (PR #275/
#277) for the first five confirmed instances of raw signal text (a headline,
an exception message, a bare state transition) being written to
`core_events.recommended_action` instead of `core_events.description`. This
file locks in five more call sites found during the follow-up sweep of the
rest of the Briefs/Captain's Brief pipeline, all the same shape:

  - tools/supabase/ingest_knowledge.py — a document's own relative path
  - tools/supabase/docling_ingest.py — same, docling extraction path
  - platform_runtime/commands/mission_lifecycle.py — a bare mission status
  - platform_runtime/human_systems_scheduler.py — a push notification's
    category label (message.title)
  - telegram_bots/recovery_officer/engagement_dispatcher.py — an internal
    dispatch code (e.g. "escalation_l3", "reminder_morning", "none")

Each of these previously wrote observational content into
`recommended_action` (reserved for a genuine reasoned proposal per
core/platform/event_bus.py's own docstring) instead of `description`, with
no other field to carry the actual content — the same root cause as the
first five leaks.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_ingest_knowledge_uses_description_not_recommended_action(monkeypatch, tmp_path):
    from tools.supabase._local_import_supabase import import_sibling

    ingest_knowledge = import_sibling("ingest_knowledge")

    calls = []
    monkeypatch.setattr(
        "core.platform.event_bus.publish_event",
        lambda *a, **k: calls.append(k) or "evt-fake",
    )

    src = tmp_path / "some-doc.md"
    src.write_text("# Title\n\nBody content.", encoding="utf-8")
    monkeypatch.setattr(ingest_knowledge, "iter_files", lambda paths: [src])
    monkeypatch.setattr(ingest_knowledge, "ROOT", tmp_path)
    monkeypatch.setattr(ingest_knowledge, "_docling_extract", None)

    class _FakeClient:
        def upsert(self, table, rows, conflict_col):
            if table == "specialists":
                return [{"role": r["role"], "id": f"spec-{i}"} for i, r in enumerate(rows)]
            if table == "knowledge_documents":
                return [{"id": "doc-1", **rows[0]}]
            return rows

        def delete(self, table, filters):
            pass

        def insert(self, table, rows):
            return rows

    monkeypatch.setattr(ingest_knowledge, "SupabaseClient", lambda: _FakeClient())

    ingest_knowledge.ingest([str(tmp_path)], dry_run=False)

    assert len(calls) == 1
    assert calls[0].get("description") == "some-doc.md"
    assert calls[0].get("recommended_action") is None


def test_docling_ingest_uses_description_not_recommended_action(monkeypatch):
    from tools.supabase._local_import_supabase import import_sibling

    docling_ingest = import_sibling("docling_ingest")

    calls = []
    monkeypatch.setattr(
        "core.platform.event_bus.publish_event",
        lambda *a, **k: calls.append(k) or "evt-fake",
    )
    monkeypatch.setattr(
        docling_ingest,
        "extract_document",
        lambda path: {"text": "extracted body", "tables": [], "metadata": {}},
    )
    monkeypatch.setattr(docling_ingest, "source_path_for", lambda path: "docs/some-report.pdf")

    class _FakeClient:
        def upsert(self, table, rows, conflict_col):
            return [{"id": "doc-2", **rows[0]}]

        def delete(self, table, filters):
            pass

        def insert(self, table, rows):
            return rows

    docling_ingest.process_one(_FakeClient(), Path("docs/some-report.pdf"), dry_run=False)

    assert len(calls) == 1
    assert calls[0].get("description") == "docs/some-report.pdf"
    assert calls[0].get("recommended_action") is None


def test_mission_status_change_uses_description_not_recommended_action(monkeypatch):
    from platform_runtime.commands import mission_lifecycle as ml
    from tools.supabase.client import CommanderSupabaseClient

    monkeypatch.setattr(CommanderSupabaseClient, "is_enabled", lambda self: True)
    monkeypatch.setattr(CommanderSupabaseClient, "_patch", lambda self, query, payload, timeout=10: {"ok": True})
    monkeypatch.setattr(
        "core.platform.heartbeat.record_heartbeat", lambda *a, **k: None,
    )

    calls = []
    monkeypatch.setattr(
        "core.platform.event_bus.publish_event",
        lambda *a, **k: calls.append(k) or "evt-fake",
    )

    ok, _event_id = ml._supabase_update_mission_status("USS-TJR-0100", "Blocked")

    assert ok is True
    assert len(calls) == 1
    assert calls[0].get("description") == "Mission USS-TJR-0100 status changed to Blocked"
    assert calls[0].get("recommended_action") is None


def test_human_systems_push_uses_description_not_recommended_action(monkeypatch):
    from platform_runtime import human_systems_scheduler as hss
    from platform_runtime.lib.human_systems.push import PushMessage

    calls = []
    monkeypatch.setattr(
        "core.platform.event_bus.publish_event",
        lambda *a, **k: calls.append(k) or "evt-fake",
    )

    message = PushMessage(
        kind="degradation",
        output_class="risk_signal",
        title="Capacity Degradation Alert",
        body="Your recovery confidence has dropped sharply this week.",
        severity="warning",
    )
    hss._publish_core_event("degradation", message, {"delivered": True, "dry_run": False})

    assert len(calls) == 1
    assert calls[0].get("description") == "Capacity Degradation Alert"
    assert calls[0].get("recommended_action") is None


def test_recovery_dispatch_uses_description_not_recommended_action(monkeypatch):
    from telegram_bots.recovery_officer import engagement_dispatcher as ed

    calls = []
    monkeypatch.setattr(
        "core.platform.event_bus.publish_event",
        lambda *a, **k: calls.append(k) or "evt-fake",
    )

    ed._emit_and_return({"action": "escalation_l3", "confidence": 40})

    assert len(calls) == 1
    assert calls[0].get("description") == "escalation_l3"
    assert calls[0].get("recommended_action") is None
