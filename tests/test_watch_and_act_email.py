"""Watch and Act emails: every active, unsilenced one is emailed once; no site matching."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import intelligence.emergency_alerts as ea

ROW = {"id": "w1", "headline": "Bushfire Watch and Act - Katoomba", "jurisdiction": "NSW", "alert_type": "bushfire", "severity": "watch_and_act",
       "location": "Katoomba, NSW", "description": "Prepare to leave", "canonical_url": "https://x", "issued_at": None, "latitude": None, "longitude": None}


def _run(silences=None, send_ok=True):
    with patch.object(ea, "supabase_get", return_value=[ROW]), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=silences or []), \
         patch.object(ea, "_supabase_request") as req, \
         patch.object(ea, "send_email", return_value=send_ok) as send:
        n = ea._send_watch_and_act_emails("nsw_rfs")
    return n, send, req


def test_every_watch_and_act_is_emailed_with_tag_header_and_no_site_content():
    n, send, req = _run()
    kw = send.call_args.kwargs
    assert n == 1 and kw["subject"] == "[WA] NSW - Bushfire Watch and Act - Katoomba"
    assert "Notice: WA" in kw["html"] and "Alert-ID: w1" in kw["html"] and "Source: nsw_rfs" in kw["html"]
    assert "Sites" not in kw["html"] and "sites" not in kw["html"] and "Tier1" not in kw["html"]
    assert "emergency_email_sent_at" in req.call_args_list[0].kwargs["body"]


def test_carries_a_plain_text_part_without_markup():
    _n, send, _req = _run()
    kw = send.call_args.kwargs
    assert kw["text"].startswith("Alert-ID: w1") and "<" not in kw["text"] and "Prepare to leave" in kw["text"]


def test_a_silence_suppresses_watch_and_act_but_never_marks_it_sent():
    sil = {"id": "s", "reason": "t", "match_jurisdiction": "NSW", "match_alert_type": None, "match_severity": None,
           "match_source_key": None, "starts_at": "2000-01-01T00:00:00+00:00", "ends_at": "2999-01-01T00:00:00+00:00"}
    n, send, req = _run(silences=[sil])
    assert n == 0 and not send.called and not req.called


def test_failed_send_is_recorded_and_retried():
    n, _send, req = _run(send_ok=False)
    assert n == 0 and any("emergency_email_failed_at" in (c.kwargs.get("body") or {}) for c in req.call_args_list)


def test_cc_is_passed_only_when_configured():
    with patch.object(ea, "_EMERGENCY_EMAIL_CC", "tim.jarden-ross@anz.com"), patch.object(ea, "send_email", return_value=True) as send:
        ea._deliver("s", "h")
    assert send.call_args.kwargs["cc"] == "tim.jarden-ross@anz.com"
    with patch.object(ea, "_EMERGENCY_EMAIL_CC", None), patch.object(ea, "send_email", return_value=True) as send:
        ea._deliver("s", "h")
    assert "cc" not in send.call_args.kwargs


def test_the_body_link_is_labelled_honestly_for_a_list_page_and_offers_the_record():
    row = {**ROW, "canonical_url": "https://incidents.rfs.nsw.gov.au/api/v1/incidents/9"}
    with patch.object(ea, "supabase_get", return_value=[row]), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
         patch.object(ea, "_supabase_request"), patch.object(ea, "send_email", return_value=True) as send:
        ea._send_watch_and_act_emails("nsw_rfs")
    html = send.call_args.kwargs["html"]
    assert "current incidents list - find this alert on it" in html and "Data record for this alert" in html
    assert 'href="https://www.rfs.nsw.gov.au/fire-information/fires-near-me"' in html
