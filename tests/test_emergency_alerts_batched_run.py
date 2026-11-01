"""run_all() batches stale-alert expiry and heartbeats across sources, and
only queries for unsent emergency warnings when a source's feed has an
active one (was ~4 Supabase requests per source per 15-min tick)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters.base import CanonicalAlert


def _adapter(alerts=None, error=None):
    def fetch():
        if error:
            raise error
        return alerts or []
    return SimpleNamespace(fetch=fetch)


def _alert(source_key, severity="advice", closed=False):
    return CanonicalAlert(source_key=source_key, jurisdiction="NSW", headline="h", event_key=f"{source_key}-1",
                          severity=severity, closed=closed)


ADAPTERS = {
    "quiet": (_adapter([_alert("quiet")]), "emergency_alert_quiet"),
    "broken": (_adapter(error=RuntimeError("feed down")), "emergency_alert_broken"),
    "warning": (_adapter([_alert("warning", severity="emergency_warning")]), "emergency_alert_warning"),
}


def _run_all(stale_rows):
    with patch.object(ea, "_ADAPTERS", ADAPTERS), \
         patch.object(ea, "_upsert_batch") as upsert, \
         patch.object(ea, "supabase_get", return_value=stale_rows) as get, \
         patch.object(ea, "_supabase_request") as request, \
         patch.object(ea, "_send_emergency_warning_emails", return_value=1) as emails, \
         patch.object(ea, "_record_heartbeat") as single_heartbeat, \
         patch.object(ea, "record_heartbeats") as batch_heartbeats:
        results = ea.run_all()
    return SimpleNamespace(results=results, upsert=upsert, get=get, request=request, emails=emails,
                           single_heartbeat=single_heartbeat, batch_heartbeats=batch_heartbeats)


def test_one_expiry_read_one_patch_one_heartbeat_post():
    run = _run_all([{"id": "a1", "source_key": "quiet"}, {"id": "a2", "source_key": "quiet"}])

    assert run.upsert.call_count == 2
    run.get.assert_called_once()
    assert "source_key=in.(quiet,warning)" in run.get.call_args.args[0]
    run.request.assert_called_once()
    assert run.request.call_args.args[1] == "alerts?id=in.(a1,a2)"
    run.single_heartbeat.assert_not_called()
    run.batch_heartbeats.assert_called_once()

    beats = {hb["domain_key"]: hb for hb in run.batch_heartbeats.call_args.args[0]}
    assert beats["emergency_alert_quiet"]["detail"] == "1 alert(s), 0 unknown severity, 2 expired"
    assert beats["emergency_alert_broken"]["status"] == "failed"
    assert beats["emergency_alert_warning"]["detail"].endswith("0 expired, 1 emergency email(s) sent")
    assert all("_counts" not in hb for hb in beats.values())
    assert run.results["quiet"]["expired"] == 2
    assert "pending_expiry" not in run.results["quiet"]


def test_emails_only_checked_for_sources_with_an_active_warning():
    run = _run_all([])
    run.emails.assert_called_once_with("warning")


def test_closed_warning_does_not_trigger_email_check():
    adapters = {"warning": (_adapter([_alert("warning", severity="emergency_warning", closed=True)]), "emergency_alert_warning")}
    with patch.object(ea, "_ADAPTERS", adapters), \
         patch.object(ea, "_upsert_batch"), \
         patch.object(ea, "supabase_get", return_value=[]), \
         patch.object(ea, "_send_emergency_warning_emails") as emails, \
         patch.object(ea, "record_heartbeats"):
        ea.run_all()
    emails.assert_not_called()


def test_standalone_run_source_still_expires_and_heartbeats_itself():
    with patch.object(ea, "_ADAPTERS", ADAPTERS), \
         patch.object(ea, "_upsert_batch"), \
         patch.object(ea, "_expire_stale", return_value=3) as expire, \
         patch.object(ea, "_record_heartbeat") as single_heartbeat:
        result = ea.run_source("quiet")
    expire.assert_called_once()
    assert result["expired"] == 3
    assert single_heartbeat.call_args.kwargs["detail"] == "1 alert(s), 0 unknown severity, 3 expired"
