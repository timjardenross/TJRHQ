"""Watch and Act emails: only when one of our sites matches; never mark sent otherwise."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import intelligence.emergency_alerts as ea

ROW = {"id": "w1", "headline": "Bushfire Watch and Act - Katoomba", "jurisdiction": "NSW", "alert_type": "bushfire", "severity": "watch_and_act",
       "location": "Katoomba, NSW", "description": "d", "canonical_url": "https://x", "issued_at": None, "latitude": None, "longitude": None}
SITE = {"id": "s1", "name": "Katoomba Branch", "suburb": "Katoomba", "state": "NSW", "postcode": "2780", "priority": "Tier 1",
        "latitude": None, "longitude": None, "geocode_quality": "none", "site_type": "Branch", "address": "1 Main St"}


def _run(sites, silences=None, send_ok=True):
    with patch.object(ea, "supabase_get", return_value=[ROW]), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=silences or []), \
         patch.object(ea.site_matching, "list_active_sites", return_value=sites), \
         patch.object(ea, "_supabase_request") as req, \
         patch.object(ea, "send_email", return_value=send_ok) as send:
        n = ea._send_watch_and_act_emails("nsw_rfs")
    return n, send, req


def test_emails_when_a_site_matches_with_tag_and_fields():
    n, send, req = _run([SITE])
    kw = send.call_args.kwargs
    assert n == 1 and kw["subject"] == "[WA] NSW - Bushfire Watch and Act - Katoomba [1 site possibly affected, 1 Tier 1: Katoomba Branch]"
    assert "Notice: WA" in kw["html"] and "Alert-ID: w1" in kw["html"]
    assert "emergency_email_sent_at" in req.call_args_list[0].kwargs["body"]


def test_no_site_match_means_no_email_and_not_marked_sent():
    n, send, req = _run([{**SITE, "suburb": "Dubbo", "postcode": "2830"}])
    assert n == 0 and not send.called and not req.called


def test_a_silence_suppresses_watch_and_act_but_never_marks_it_sent():
    sil = {"id": "s", "reason": "t", "match_jurisdiction": "NSW", "match_alert_type": None, "match_severity": None,
           "match_source_key": None, "starts_at": "2000-01-01T00:00:00+00:00", "ends_at": "2999-01-01T00:00:00+00:00"}
    n, send, req = _run([SITE], silences=[sil])
    assert n == 0 and not send.called and not req.called


def test_failed_send_is_recorded_and_retried():
    n, _send, req = _run([SITE], send_ok=False)
    assert n == 0 and any("emergency_email_failed_at" in (c.kwargs.get("body") or {}) for c in req.call_args_list)


def test_cc_is_passed_only_when_configured():
    with patch.object(ea, "_EMERGENCY_EMAIL_CC", "captain@example.com"), patch.object(ea, "send_email", return_value=True) as send:
        ea._deliver("s", "h")
    assert send.call_args.kwargs["cc"] == "captain@example.com"
    with patch.object(ea, "_EMERGENCY_EMAIL_CC", None), patch.object(ea, "send_email", return_value=True) as send:
        ea._deliver("s", "h")
    assert "cc" not in send.call_args.kwargs


def test_every_alert_email_carries_a_plain_text_part_and_no_repeated_headline_block():
    n, send, _req = _run([SITE])
    kw = send.call_args.kwargs
    assert n == 1 and kw["text"] and "<" not in kw["text"] and "Notice: WA" in kw["text"]
    # the header block already carries headline / jurisdiction / location: not repeated underneath
    assert "<strong>Bushfire Watch and Act - Katoomba</strong>" not in kw["html"] and "Jurisdiction: NSW<br>" not in kw["html"]


def test_the_sites_banner_comes_first_in_the_body_and_the_plain_text():
    n, send, _req = _run([SITE])
    kw = send.call_args.kwargs
    assert n == 1 and kw["html"].startswith('<div style="border-left:6px solid #A23A34')
    assert kw["text"].startswith("1 of our sites possibly affected - 1 Tier 1")
    assert "Tier 1: Katoomba Branch" in kw["text"].split("Alert-ID")[0]
