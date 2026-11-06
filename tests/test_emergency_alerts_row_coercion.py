"""Pre-upsert row validation: out-of-set alert_type/severity are coerced, never dropped."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters.base import CanonicalAlert


def _alert(n, **kw):
    return CanonicalAlert(source_key="x_src", jurisdiction="NSW", headline=f"SECRET-HEADLINE-{n}", event_key=f"e{n}", **kw)


def _run(alerts, caplog=None):
    adapter = SimpleNamespace(fetch=lambda: alerts)
    sent = []

    def fake_request(method, path, body=None, extra_headers=None, timeout=15):
        sent.append((method, path, body))

    with patch.dict(ea._ADAPTERS, {"x_src": (adapter, "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_supabase_request", side_effect=fake_request), \
         patch.object(ea, "_expire_stale", return_value=0), \
         patch.object(ea, "_record_heartbeat") as heartbeat:
        result = ea.run_source("x_src")
    return result, sent, heartbeat


def test_one_bad_row_does_not_stop_the_batch_and_is_never_dropped():
    alerts = [_alert(1, alert_type="bushfire", severity="advice"), _alert(2, alert_type="volcano", severity="critical"), _alert(3)]
    result, sent, _ = _run(alerts)
    upserts = [s for s in sent if s[1].startswith("alerts?on_conflict")]
    assert len(upserts) == 1
    rows = upserts[0][2]
    assert [r["event_key"] for r in rows] == ["e1", "e2", "e3"]
    assert rows[1]["alert_type"] == "other" and rows[1]["severity"] == "unknown"
    assert rows[0]["alert_type"] == "bushfire" and rows[0]["severity"] == "advice"
    assert result["count"] == 3
    json.dumps(rows)  # the body is still serialisable


def test_in_set_values_are_untouched():
    from alert_schema import ALLOWED_ALERT_TYPE, ALLOWED_SEVERITY
    alerts = [_alert(i, alert_type=t, severity=s) for i, (t, s) in enumerate(zip(sorted(ALLOWED_ALERT_TYPE), sorted(ALLOWED_SEVERITY) * 4))]
    rows = [{"alert_type": a.alert_type, "severity": a.severity} for a in alerts]
    assert ea._coerce_rows("x_src", rows) == (0, 0)
    assert rows == [{"alert_type": a.alert_type, "severity": a.severity} for a in alerts]


def test_counts_are_reported_in_heartbeat_detail():
    alerts = [_alert(1, alert_type="volcano"), _alert(2, alert_type="meteor", severity="critical"), _alert(3)]
    _, _, heartbeat = _run(alerts)
    detail = heartbeat.call_args.kwargs["detail"]
    assert heartbeat.call_args.kwargs["status"] == "ok"
    assert "| coerced 3 (alert_type 2, severity 1)" in detail


def test_clean_run_detail_has_no_coercion_text():
    _, _, heartbeat = _run([_alert(1, alert_type="flood", severity="advice")])
    assert "coerced" not in heartbeat.call_args.kwargs["detail"]


def test_warning_logs_source_and_bad_value_but_no_other_row_content(caplog):
    with caplog.at_level(logging.WARNING, logger="emergency-alerts"):
        _run([_alert(1, alert_type="volcano", severity="critical")])
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "x_src" in text and "volcano" in text and "critical" in text
    assert "SECRET-HEADLINE" not in text and "e1" not in text.replace("emergency", "")


def test_coerced_severity_counts_as_unknown_and_never_triggers_a_warning_email():
    alerts = [_alert(1, severity="EMERGENCY_WARNING")]  # wrong case = not in the set
    with patch.object(ea, "_send_emergency_warning_emails") as emails:
        result, _, _ = _run(alerts)
    emails.assert_not_called()
    assert result["unknown_severity"] == 1


def test_batched_run_all_carries_the_coercion_note_into_the_heartbeat():
    adapter = SimpleNamespace(fetch=lambda: [_alert(1, alert_type="volcano")])
    with patch.object(ea, "_ADAPTERS", {"x_src": (adapter, "emergency_alert_x")}), \
         patch.object(ea, "_upsert_batch"), \
         patch.object(ea, "supabase_get", return_value=[]), \
         patch.object(ea, "_supabase_request"), \
         patch.object(ea, "_send_follow_up_emails", return_value={"updates": 0, "lifted": 0}), \
         patch.object(ea, "record_heartbeats") as beats:
        ea.run_all()
    detail = beats.call_args.args[0][0]["detail"]
    assert "coerced 1 (alert_type 1, severity 0)" in detail
