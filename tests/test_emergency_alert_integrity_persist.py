"""Per-source integrity rows (migration 0252): what each run's drop ledger saw, persisted
once per run, plus the digest section that reads them back. Offline: Supabase is mocked."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alert_summary as summary
import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters.base import (
    CanonicalAlert,
    DropLedger,
)

NEWEST = datetime(2026, 11, 6, 5, 0, tzinfo=timezone.utc)


def _ledger():
    lg = DropLedger()
    lg.seen(4)
    lg.observe(NEWEST)
    lg.exclude("smoke_alert", sample="Smoke Alert - Test Town")
    lg.exclude("smoke_alert", sample="Smoke Alert - Other Town")
    lg.invalid("no_title")
    lg.counts["unmapped_product_hazardous_surf_warning"] = 1
    return lg


def _alert():
    return CanonicalAlert(source_key="wa_dfes", jurisdiction="WA", headline="Fire", event_key="e1", alert_type="bushfire", severity="advice")


def test_integrity_row_splits_the_ledger_by_namespace():
    row = ea._integrity_row("wa_dfes", "ok", _ledger(), 1, ["STALE: x"])
    assert row["source_key"] == "wa_dfes" and row["status"] == "ok"
    assert row["items_seen"] == 4 and row["accepted"] == 1
    assert row["excluded"] == {"smoke_alert": 2}
    assert row["invalid"] == {"no_title": 1}
    assert row["unmapped"] == {"product_hazardous_surf_warning": 1}
    assert row["samples"]["excluded_smoke_alert"] == ["Smoke Alert - Test Town", "Smoke Alert - Other Town"]
    assert row["newest_item_at"] == NEWEST.isoformat()
    assert row["warnings"] == ["STALE: x"]


def test_integrity_row_is_none_without_a_ledger():
    assert ea._integrity_row("x", "ok", None, 0, []) is None


def test_upsert_failure_never_raises():
    with patch.object(ea, "_supabase_request", side_effect=RuntimeError("relation does not exist")):
        ea._upsert_integrity([{"source_key": "a"}])  # must not raise: migration 0252 may not be applied yet


def test_upsert_is_one_merge_duplicates_request():
    with patch.object(ea, "_supabase_request") as req:
        ea._upsert_integrity([{"source_key": "a"}, {"source_key": "b"}])
        ea._upsert_integrity([])
    assert req.call_count == 1
    assert req.call_args.args[:2] == ("POST", "emergency_alert_source_integrity?on_conflict=source_key")
    assert "merge-duplicates" in req.call_args.kwargs["extra_headers"]["Prefer"]


def _adapters(ledger):
    adapter = SimpleNamespace(fetch_with_ledger=lambda: ([_alert()], ledger))
    return {"wa_dfes": (adapter, "emergency_alert_wa_dfes")}


def test_standalone_run_source_writes_its_row_directly():
    with patch.object(ea, "_ADAPTERS", _adapters(_ledger())), patch.object(ea, "_upsert_batch"), \
         patch.object(ea, "_expire_stale", return_value=0), patch.object(ea, "_record_heartbeat"), \
         patch.object(ea, "_upsert_integrity") as up:
        result = ea.run_source("wa_dfes")
    up.assert_called_once()
    assert up.call_args.args[0][0]["source_key"] == "wa_dfes"
    assert "_integrity" not in result


def test_batched_run_source_defers_the_row_to_run_all():
    beats: list[dict] = []
    with patch.object(ea, "_ADAPTERS", _adapters(_ledger())), patch.object(ea, "_upsert_batch"), \
         patch.object(ea, "_expire_stale", return_value=0), patch.object(ea, "_record_heartbeat"), \
         patch.object(ea, "_upsert_integrity") as up:
        result = ea.run_source("wa_dfes", heartbeats=beats)
    up.assert_not_called()
    assert result["_integrity"]["source_key"] == "wa_dfes"


def test_run_all_writes_every_row_in_one_call_and_strips_the_private_key():
    adapters = {k: v for k, v in _adapters(_ledger()).items()}
    adapters["nsw_rfs"] = (SimpleNamespace(fetch_with_ledger=lambda: ([_alert()], _ledger())), "emergency_alert_nsw_rfs")
    with patch.object(ea, "_ADAPTERS", adapters), patch.object(ea, "_upsert_batch"), \
         patch.object(ea, "_expire_stale", return_value=0), patch.object(ea, "record_heartbeats"), \
         patch.object(ea, "_send_follow_up_emails", return_value={}), \
         patch.object(ea, "_upsert_integrity") as up:
        results = ea.run_all()
    up.assert_called_once()
    assert sorted(r["source_key"] for r in up.call_args.args[0]) == ["nsw_rfs", "wa_dfes"]
    assert all("_integrity" not in r for r in results.values() if isinstance(r, dict))


# ---- digest section ----

def _row(**kw):
    base = {"source_key": "wa_dfes", "status": "ok", "items_seen": 4, "accepted": 1, "excluded": {}, "invalid": {}, "unmapped": {}, "samples": {}, "warnings": []}
    base.update(kw)
    return base


def _section(rows):
    with patch.object(summary, "supabase_get", return_value=rows):
        return summary._dropped_section()


def test_digest_section_shows_what_is_dropped_with_examples():
    html = _section([_row(excluded={"smoke_alert": 2}, samples={"excluded_smoke_alert": ["Smoke Alert - Test Town", "b", "c"]})])
    assert "wa_dfes" in html and "smoke_alert 2" in html and "Smoke Alert - Test Town" in html
    assert "“c”" not in html  # capped at 2 examples per reason


def test_digest_section_is_empty_when_nothing_is_noteworthy():
    assert _section([_row()]) == ""
    assert _section([]) == ""


def test_digest_section_surfaces_warnings_failures_and_unmapped_products():
    html = _section([_row(status="failed", warnings=["STALE: newest item 80h old (expected under 72h)"], unmapped={"product_x": 3})])
    assert "FAILED" in html and "STALE: newest item 80h old" in html and "product_x 3" in html


def test_digest_section_escapes_feed_text():
    html = _section([_row(excluded={"r": 1}, samples={"excluded_r": ["<script>x</script>"]})])
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_digest_section_swallows_read_errors():
    with patch.object(summary, "supabase_get", side_effect=RuntimeError("no table")):
        assert summary._dropped_section() == ""
