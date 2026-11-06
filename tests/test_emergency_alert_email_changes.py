"""Email alert changes: CAP + local-time header fields, per-tag recipients, opt-in Advice emails, LIFTED duration, and
[FEED] down / reminder / recovered emails. Offline: Supabase and the mailer are mocked."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import alert_email

import intelligence.emergency_alerts as ea

NOW = datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)


def _keys(block: str) -> dict[str, str]:
    body = re.sub(r"<pre[^>]*>|</pre>", "", block)
    return dict(line.split(": ", 1) for line in body.split("\n") if ": " in line)


# ---- helpers in alert_email ----

def test_local_time_uses_the_jurisdictions_zone_and_daylight_saving():
    assert alert_email.local_time("2026-11-06T09:00:00+00:00", "NSW") == "2026-11-06 20:00 AEDT"
    assert alert_email.local_time("2026-07-06T09:00:00+00:00", "NSW") == "2026-07-06 19:00 AEST"
    assert alert_email.local_time("2026-11-06T09:00:00Z", "WA") == "2026-11-06 17:00 AWST"
    assert alert_email.local_time(NOW, "QLD") == "2026-11-06 16:00 AEST"


@pytest.mark.parametrize("value,jurisdiction", [(None, "NSW"), ("", "NSW"), ("2026-11-06T09:00:00", "NSW"), ("4:55 pm Saturday", "NSW"), ("2026-11-06T09:00:00+00:00", "XX"), ("2026-11-06T09:00:00+00:00", None)])
def test_local_time_is_none_when_it_cannot_be_trusted(value, jurisdiction):
    assert alert_email.local_time(value, jurisdiction) is None


@pytest.mark.parametrize("minutes,text", [(0, "under 1m"), (45, "45m"), (200, "3h 20m"), (120, "2h"), (1500, "1d 1h"), (1440, "1d")])
def test_format_duration(minutes, text):
    assert alert_email.format_duration(timedelta(minutes=minutes)) == text


def test_advice_rules_parse_and_match():
    rules = alert_email.parse_advice_rules(" nsw:Flood, *:bushfire ,QLD:* , junk, :x, y: ")
    assert rules == [("NSW", "flood"), ("*", "bushfire"), ("QLD", "*")]
    assert alert_email.advice_matches(rules, "NSW", "flood") and alert_email.advice_matches(rules, "vic", "bushfire") and alert_email.advice_matches(rules, "QLD", "storm")
    assert not alert_email.advice_matches(rules, "NSW", "storm") and not alert_email.advice_matches(rules, "SA", "flood")
    assert alert_email.parse_advice_rules(None) == [] and alert_email.parse_advice_rules("") == []
    assert not alert_email.advice_matches([], "NSW", "flood")


def test_header_carries_cap_and_local_times_after_the_original_keys():
    row = {"id": "a1", "severity": "advice", "jurisdiction": "NSW", "headline": "h", "source_key": "nsw_rfs", "issued_at": "2026-11-06T05:08:00+00:00",
           "cap_event": "Fire Weather", "cap_urgency": "Unknown", "cap_certainty": "Observed", "cap_severity": "Severe"}
    keys = _keys(alert_email.fields_block(alert_email.ADVICE, row))
    assert list(keys)[:10] == ["Alert-ID", "Notice", "Tier", "Jurisdiction", "Headline", "Location", "Issued", "Official-Link", "Source", "Sent-At"]
    assert keys["Notice"] == "ADVICE" and keys["Tier"] == "Advice"
    assert (keys["CAP-Event"], keys["CAP-Urgency"], keys["CAP-Certainty"], keys["CAP-Severity"]) == ("Fire Weather", "Unknown", "Observed", "Severe")
    assert keys["Issued-Local"] == "2026-11-06 16:08 AEDT" and keys["Sent-At-Local"].endswith(("AEDT", "AEST"))


def test_header_omits_cap_and_issued_local_when_there_is_nothing_to_show():
    keys = _keys(alert_email.fields_block(alert_email.EW, {"id": "a1", "severity": "emergency_warning", "jurisdiction": "NSW", "headline": "h", "source_key": "nsw_rfs"}))
    assert not any(k.startswith("CAP-") for k in keys) and "Issued-Local" not in keys and "Sent-At-Local" in keys


def test_feed_block_has_its_own_keys():
    keys = _keys(alert_email.feed_block({"source_key": "nsw_rfs", "jurisdiction": "NSW", "problem": "failed", "since": "2026-11-06T05:00:00+00:00"}, {"Failed-Runs": 3}))
    assert list(keys)[:4] == ["Notice", "Source", "Jurisdiction", "Problem"] and keys["Notice"] == "FEED" and keys["Failed-Runs"] == "3"
    assert keys["Since-Local"] == "2026-11-06 16:00 AEDT" and "Tier" not in keys


# ---- recipients ----

def test_recipients_default_then_per_tag_override(monkeypatch):
    monkeypatch.setattr(ea, "_EMERGENCY_EMAIL_TO", "team@example.invalid")
    monkeypatch.setattr(ea, "_EMERGENCY_EMAIL_CC", None)
    for name in ("EMERGENCY_ALERT_EMAIL_TO_EW", "EMERGENCY_ALERT_EMAIL_CC_EW", "EMERGENCY_ALERT_EMAIL_TO_BOM_HIGH"):
        monkeypatch.delenv(name, raising=False)
    assert ea._recipients("EW") == ("team@example.invalid", None) and ea._recipients(None) == ("team@example.invalid", None)
    monkeypatch.setenv("EMERGENCY_ALERT_EMAIL_TO_EW", "ew@example.invalid")
    monkeypatch.setenv("EMERGENCY_ALERT_EMAIL_CC_EW", "boss@example.invalid")
    monkeypatch.setenv("EMERGENCY_ALERT_EMAIL_TO_BOM_HIGH", "bom@example.invalid")
    assert ea._recipients("EW") == ("ew@example.invalid", "boss@example.invalid")
    assert ea._recipients("BOM-HIGH") == ("bom@example.invalid", None)
    assert ea._recipients("WA") == ("team@example.invalid", None)  # other tags unchanged


def test_deliver_sends_to_the_tag_specific_recipient(monkeypatch):
    monkeypatch.setenv("EMERGENCY_ALERT_EMAIL_TO_EW", "ew@example.invalid")
    with patch.object(ea, "send_email", return_value=True) as send:
        assert ea._deliver("s", "<p>x</p>", alert_email.EW)
    assert send.call_args.kwargs["to"] == "ew@example.invalid"


# ---- Advice emails ----

def _advice_row(**o):
    base = {"id": "adv1", "headline": "Flood Advice - Creek", "jurisdiction": "NSW", "alert_type": "flood", "severity": "advice",
            "location": "Creek", "description": "Watch the creek", "canonical_url": "https://x", "issued_at": None}
    base.update(o)
    return base


def _send_advice(rows, rules, silences=None, send_ok=True):
    with patch.object(ea, "supabase_get", return_value=rows), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=silences or []), \
         patch.object(ea, "_supabase_request") as req, \
         patch.object(ea, "send_email", return_value=send_ok) as send:
        n = ea._send_advice_emails("nsw_rfs", rules)
    return n, send, req


def test_advice_email_is_sent_only_for_matching_rules_and_marks_the_alert():
    n, send, req = _send_advice([_advice_row(), _advice_row(id="adv2", alert_type="storm")], [("NSW", "flood")])
    assert n == 1 and send.call_count == 1
    assert send.call_args.kwargs["subject"].startswith("[ADVICE] NSW - ") and "Notice: ADVICE" in send.call_args.kwargs["html"]
    assert any("emergency_email_sent_at" in (c.kwargs.get("body") or {}) for c in req.call_args_list)


def test_advice_can_be_silenced():
    silence = {"id": "s1", "reason": "planned burn", "match_jurisdiction": "NSW", "match_alert_type": "flood", "match_severity": None, "match_source_key": None}
    with patch.object(ea.alert_silences, "check_silence", return_value=silence):
        n, send, _ = _send_advice([_advice_row()], [("*", "*")], silences=[silence])
    assert n == 0 and not send.called


def test_failed_advice_send_records_the_failure_and_retries_later():
    n, _send, req = _send_advice([_advice_row()], [("*", "*")], send_ok=False)
    assert n == 0
    bodies = [c.kwargs.get("body") or {} for c in req.call_args_list]
    assert all("emergency_email_sent_at" not in b for b in bodies) and any("emergency_email_failed_at" in b for b in bodies)


def test_advice_rules_default_to_off(monkeypatch):
    monkeypatch.delenv("EMERGENCY_ALERT_ADVICE_EMAIL", raising=False)
    assert ea._advice_rules() == []
    monkeypatch.setenv("EMERGENCY_ALERT_ADVICE_EMAIL", "NSW:flood")
    assert ea._advice_rules() == [("NSW", "flood")]


# ---- follow-ups: Advice is exempt, LIFTED shows how long ----

def _follow_row(**o):
    base = {"id": "a1", "source_key": "nsw_rfs", "headline": "Bushfire - Katoomba", "jurisdiction": "NSW", "alert_type": "bushfire", "severity": "watch_and_act",
            "location": "Katoomba", "description": "Prepare", "canonical_url": "https://x", "issued_at": None, "is_active": True,
            "first_seen_at": (NOW - timedelta(hours=4)).isoformat(), "last_seen_at": (NOW - timedelta(minutes=40)).isoformat(),
            "emergency_email_tier": "watch_and_act", "emergency_email_hash": None, "emergency_email_last_at": (NOW - timedelta(hours=1)).isoformat(), "emergency_email_lifted_at": None}
    base.update(o)
    if base["emergency_email_hash"] is None and base["emergency_email_tier"]:
        base["emergency_email_hash"] = alert_email.content_hash(base)
    return base


def _follow(rows):
    with patch.object(ea, "supabase_get", return_value=rows), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
         patch.object(ea, "_supabase_request") as req, \
         patch.object(ea, "send_email", return_value=True) as send:
        out = ea._send_follow_up_emails(NOW)
    return out, send, req


def test_lifted_email_says_how_long_the_source_listed_the_alert():
    out, send, _ = _follow([_follow_row(is_active=False)])
    kw = send.call_args.kwargs
    assert out["lifted"] == 1 and "Listed-For: 3h 20m" in kw["html"] and "listed it for 3h 20m" in kw["html"]


def test_lifted_email_still_sends_when_the_times_are_missing():
    out, send, _ = _follow([_follow_row(is_active=False, first_seen_at=None)])
    assert out["lifted"] == 1 and "Listed-For" not in send.call_args.kwargs["html"]


def test_advice_alerts_get_no_wording_update_and_no_lifted_just_a_silent_close():
    changed = _follow_row(severity="advice", emergency_email_tier="advice", description="Different words now")
    changed["emergency_email_hash"] = alert_email.content_hash(_follow_row(severity="advice", emergency_email_tier="advice"))
    out, send, _ = _follow([changed])
    assert out == {"updates": 0, "lifted": 0} and not send.called
    out, send, req = _follow([_follow_row(severity="advice", emergency_email_tier="advice", is_active=False)])
    assert out == {"updates": 0, "lifted": 0} and not send.called
    assert "emergency_email_lifted_at" in req.call_args.kwargs["body"]


def test_an_advice_that_escalates_still_emails_an_update():
    out, send, _ = _follow([_follow_row(severity="watch_and_act", emergency_email_tier="advice")])
    assert out["updates"] == 1 and "Escalated from Advice to Watch and Act" in send.call_args.kwargs["html"]


# ---- [FEED] emails ----

def _feed(results, states=None, integrity=None, send_ok=True, now=NOW, table_missing=False):
    def get(path):
        if table_missing:
            raise RuntimeError("relation does not exist")
        return states or []

    with patch.object(ea, "supabase_get", side_effect=get), \
         patch.object(ea, "_supabase_request") as req, \
         patch.object(ea, "send_email", return_value=send_ok) as send:
        out = ea._send_feed_emails(results, integrity or {}, now=now)
    return out, send, req


def _state(**o):
    base = {"source_key": "nsw_rfs", "problem": "failed", "consecutive": 2, "since": (NOW - timedelta(minutes=30)).isoformat(), "emailed_at": None, "detail": "HTTP 503"}
    base.update(o)
    return base


def _written(req):
    return {row["source_key"]: row for row in req.call_args.kwargs["body"]}


def test_a_failed_source_is_emailed_on_the_third_failed_run_not_before():
    out, send, req = _feed({"nsw_rfs": {"error": "HTTP 503", "count": 0}})
    assert out["down"] == 0 and not send.called and _written(req)["nsw_rfs"]["consecutive"] == 1
    out, send, req = _feed({"nsw_rfs": {"error": "HTTP 503", "count": 0}}, states=[_state(consecutive=1)])
    assert out["down"] == 0 and not send.called
    out, send, req = _feed({"nsw_rfs": {"error": "HTTP 503", "count": 0}}, states=[_state()])
    kw = send.call_args.kwargs
    assert out["down"] == 1 and kw["subject"].startswith("[FEED] NSW - nsw_rfs is not reporting (3 failed runs in a row)")
    assert "Notice: FEED" in kw["html"] and "HTTP 503" in kw["html"] and "NOT reassuring" in kw["html"]
    assert _written(req)["nsw_rfs"]["emailed_at"] == NOW.isoformat() and _written(req)["nsw_rfs"]["consecutive"] == 3


def test_a_stale_feed_is_emailed_straight_away():
    out, send, req = _feed({"nsw_rfs": {"count": 4}}, integrity={"nsw_rfs": {"warnings": ["STALE: newest item 80h old (expected under 72h)"]}})
    assert out["down"] == 1 and "its feed has gone quiet" in send.call_args.kwargs["subject"]
    assert _written(req)["nsw_rfs"]["problem"] == "stale"


def test_no_repeat_email_until_the_reminder_interval():
    emailed = (NOW - timedelta(hours=2)).isoformat()
    out, send, _ = _feed({"nsw_rfs": {"error": "x", "count": 0}}, states=[_state(consecutive=9, emailed_at=emailed)])
    assert out == {"down": 0, "reminders": 0, "recovered": 0} and not send.called
    later = (NOW - timedelta(hours=13)).isoformat()
    out, send, _ = _feed({"nsw_rfs": {"error": "x", "count": 0}}, states=[_state(consecutive=9, emailed_at=later)])
    assert out["reminders"] == 1 and "still not reporting" in send.call_args.kwargs["subject"]


def test_recovery_is_emailed_once_and_the_state_cleared():
    out, send, req = _feed({"nsw_rfs": {"count": 4}}, states=[_state(consecutive=5, emailed_at=NOW.isoformat(), since=(NOW - timedelta(hours=2)).isoformat())])
    kw = send.call_args.kwargs
    assert out["recovered"] == 1 and kw["subject"] == "[FEED] NSW - nsw_rfs is reporting again" and "down for about 2h" in kw["html"]
    row = _written(req)["nsw_rfs"]
    assert row["problem"] is None and row["consecutive"] == 0 and row["emailed_at"] is None


def test_a_blip_that_never_reached_the_threshold_recovers_silently():
    out, send, req = _feed({"nsw_rfs": {"count": 4}}, states=[_state(consecutive=1)])
    assert out["recovered"] == 0 and not send.called and _written(req)["nsw_rfs"]["problem"] is None


def test_failed_recovery_email_keeps_the_state_so_it_retries():
    out, _send, req = _feed({"nsw_rfs": {"count": 4}}, states=[_state(emailed_at=NOW.isoformat())], send_ok=False)
    assert out["recovered"] == 0 and not req.called


def test_failed_down_email_is_not_recorded_as_sent():
    out, _send, req = _feed({"nsw_rfs": {"error": "x", "count": 0}}, states=[_state()], send_ok=False)
    assert out["down"] == 0 and _written(req)["nsw_rfs"]["emailed_at"] is None


def test_healthy_and_skipped_sources_write_and_send_nothing():
    out, send, req = _feed({"nsw_rfs": {"count": 4}, "nt_securent": {"count": 0, "skipped": True}})
    assert out == {"down": 0, "reminders": 0, "recovered": 0} and not send.called and not req.called


def test_without_the_state_table_nothing_is_sent(caplog):
    out, send, req = _feed({"nsw_rfs": {"error": "x", "count": 0}}, states=[_state()], table_missing=True)
    assert out == {"down": 0, "reminders": 0, "recovered": 0} and not send.called and not req.called
    assert "migration 0254" in caplog.text


def test_state_write_failure_is_swallowed():
    with patch.object(ea, "supabase_get", return_value=[]), patch.object(ea, "_supabase_request", side_effect=RuntimeError("down")), \
         patch.object(ea, "send_email", return_value=True):
        out = ea._send_feed_emails({"nsw_rfs": {"error": "x", "count": 0}}, {}, now=NOW)  # must not raise
    assert out["down"] == 0


def test_run_all_hands_results_and_integrity_rows_to_the_feed_pass():
    from types import SimpleNamespace

    from intelligence.ingestion.emergency_alert_adapters.base import (
        CanonicalAlert,
        DropLedger,
    )

    lg = DropLedger()
    lg.seen(1)
    alert = CanonicalAlert(source_key="s1", jurisdiction="NSW", headline="h", event_key="e1", alert_type="bushfire", severity="advice")
    adapters = {"s1": (SimpleNamespace(fetch_with_ledger=lambda: ([alert], lg)), "emergency_alert_s1"),
                "s2": (SimpleNamespace(fetch=lambda: (_ for _ in ()).throw(RuntimeError("down"))), "emergency_alert_s2")}
    with patch.object(ea, "_ADAPTERS", adapters), patch.object(ea, "_upsert_batch"), patch.object(ea, "_expire_stale_many", return_value={}), \
         patch.object(ea, "record_heartbeats"), patch.object(ea, "_upsert_integrity"), patch.object(ea, "_send_follow_up_emails", return_value={}), \
         patch.object(ea, "_send_feed_emails", return_value={"down": 0}) as feed:
        results = ea.run_all()
    feed.assert_called_once()
    seen_results, seen_integrity = feed.call_args.args
    assert "error" in seen_results["s2"] and "_integrity" not in seen_results["s1"] and set(seen_integrity) == {"s1"}
    assert results["_feed_alerts"] == {"down": 0}
