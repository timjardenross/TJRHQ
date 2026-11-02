"""[UPDATE] and [LIFTED] follow-up emails for alerts already emailed."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import alert_email

import intelligence.emergency_alerts as ea

NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)


def _row(**o):
    base = {"id": "a1", "source_key": "nsw_rfs", "headline": "Bushfire - Katoomba", "jurisdiction": "NSW", "alert_type": "bushfire",
            "severity": "watch_and_act", "location": "Katoomba", "description": "Prepare to leave", "canonical_url": "https://x",
            "issued_at": None, "is_active": True, "emergency_email_tier": "watch_and_act", "emergency_email_hash": None,
            "emergency_email_last_at": (NOW - timedelta(hours=1)).isoformat(), "emergency_email_lifted_at": None}
    base.update(o)
    if base["emergency_email_hash"] is None and base["emergency_email_tier"]:
        base["emergency_email_hash"] = alert_email.content_hash(base)
    return base


def _run(rows, silences=None, send_ok=True):
    with patch.object(ea, "supabase_get", return_value=rows), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=silences or []), \
         patch.object(ea.site_matching, "list_active_sites", return_value=[]), \
         patch.object(ea, "_supabase_request") as req, \
         patch.object(ea, "send_email", return_value=send_ok) as send:
        out = ea._send_follow_up_emails(NOW)
    return out, send, req


def test_no_change_no_email():
    out, send, req = _run([_row()])
    assert out == {"updates": 0, "lifted": 0} and not send.called and not req.called


def test_alert_emailed_before_the_migration_is_baselined_silently():
    _out, send, req = _run([_row(emergency_email_tier=None, emergency_email_hash=None)])
    assert not send.called and "emergency_email_tier" in req.call_args.kwargs["body"]


def test_escalation_to_emergency_warning_emails_an_update_even_though_already_emailed():
    out, send, req = _run([_row(severity="emergency_warning")])
    kw = send.call_args.kwargs
    assert out["updates"] == 1 and kw["subject"].startswith("[UPDATE] NSW - ")
    assert "Escalated from Watch and Act to Emergency Warning" in kw["html"]
    assert "emergency_email_tier" in req.call_args.kwargs["body"]


def test_wording_change_is_throttled_to_one_every_30_minutes():
    changed = _row(description="Leave now")
    changed["emergency_email_hash"] = alert_email.content_hash(_row())
    recent = {**changed, "emergency_email_last_at": (NOW - timedelta(minutes=10)).isoformat()}
    assert _run([recent])[0]["updates"] == 0
    assert _run([changed])[0]["updates"] == 1


def test_ended_alert_gets_one_lifted_notice_that_is_not_an_all_clear():
    out, send, req = _run([_row(is_active=False)])
    kw = send.call_args.kwargs
    assert out["lifted"] == 1 and kw["subject"].startswith("[LIFTED] NSW - ")
    assert "not an all-clear" in kw["html"]
    assert "emergency_email_lifted_at" in req.call_args.kwargs["body"]
    assert _run([_row(is_active=False, emergency_email_lifted_at=NOW.isoformat())])[0]["lifted"] == 0


def test_old_ended_alert_from_before_the_migration_is_closed_silently():
    out, send, req = _run([_row(is_active=False, emergency_email_tier=None)])
    assert out["lifted"] == 0 and not send.called and "emergency_email_lifted_at" in req.call_args.kwargs["body"]


def test_a_silence_suppresses_a_watch_and_act_update_but_not_an_emergency_warning_update():
    sil = {"id": "s", "reason": "t", "match_jurisdiction": "NSW", "match_alert_type": None, "match_severity": None,
           "match_source_key": None, "starts_at": "2000-01-01T00:00:00+00:00", "ends_at": "2999-01-01T00:00:00+00:00"}
    changed = _row(description="Leave now")
    changed["emergency_email_hash"] = alert_email.content_hash(_row())
    assert _run([changed], silences=[sil])[0]["updates"] == 0
    assert _run([_row(severity="emergency_warning")], silences=[sil])[0]["updates"] == 1


def test_failed_send_is_not_recorded_so_it_retries():
    out, _send, req = _run([_row(is_active=False)], send_ok=False)
    assert out["lifted"] == 0 and not req.called


def test_read_failure_never_raises():
    with patch.object(ea, "supabase_get", side_effect=RuntimeError("column does not exist")):
        assert ea._send_follow_up_emails(NOW) == {"updates": 0, "lifted": 0}
