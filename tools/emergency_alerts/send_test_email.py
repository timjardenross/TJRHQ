"""Send sample alert emails (made-up data) to an address you name.

Builds each email type with the real code path (subjects, header block, plain-text
part, sites list) from fixed fictional alerts, and sends them through the same
Resend settings the ingestion service uses (RESEND_API_KEY, RESEND_FROM). Every
message is labelled TEST in the subject and the first line. Nothing is read from
or written to the database.

Run it wherever the Resend settings are present (the ingestion host):

    python tools/emergency_alerts/send_test_email.py --to you@example.com
    python tools/emergency_alerts/send_test_email.py --to you@example.com --only EW,BOM-HIGH
    python tools/emergency_alerts/send_test_email.py --to team@example.com --cc you@example.com   # the real arrangement
    python tools/emergency_alerts/send_test_email.py --to you@example.com --dry-run   # print only

--to is required: it never falls back to the configured recipient, so a test can
not reach the live team mailbox by accident. --cc copies a second address, which
mirrors the planned live setup (team mailbox as To, the Captain on CC) and tests
both addresses with one message.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "core" / "platform"))

import alert_email
import bom_areas

import intelligence.emergency_alerts as ea
from core.notifications import resend_email

_BANNER = "<p><strong>TEST MESSAGE - made-up data. This is not a real alert.</strong></p>"


def _site(**o):
    base = {"id": "s1", "name": "Katoomba Branch", "site_type": "Branch", "suburb": "Katoomba", "state": "NSW", "postcode": "2780",
            "priority": "Tier 1", "latitude": None, "longitude": None, "geocode_quality": "none", "address": "1 Main St"}
    return {**base, **o}


def build_samples() -> list[tuple[str, str, str]]:
    """(notice tag, subject, html) for every email type, from fictional alerts."""
    sites = [_site(), _site(id="s2", name="Springwood Branch", suburb="Springwood", postcode="2777", priority="Tier 2")]
    base = {"id": "test-0001", "jurisdiction": "NSW", "alert_type": "bushfire", "location": "Katoomba, Blue Mountains",
            "description": "A fire is burning out of control near Katoomba. Leave now if the way is clear.",
            "canonical_url": "https://example.invalid/official-warning", "issued_at": "2026-11-02T14:05:00+11:00", "latitude": None, "longitude": None}
    out: list[tuple[str, str]] = []

    def capture(**kw):
        out.append((kw["subject"], kw["html"]))
        return True

    vic_sites = [_site(id="v1", name="Bendigo", suburb="Bendigo", state="VIC", postcode="3550"),
                 _site(id="v2", name="Horsham", suburb="Horsham", state="VIC", postcode="3400"),
                 _site(id="v3", name="Mildura", suburb="Mildura", state="VIC", postcode="3500", priority="Tier 3")]
    bom = {"id": "test-0002", "headline": "Severe Thunderstorm Warning for parts of Mallee, Northern Country and Wimmera Forecast Districts.",
           "jurisdiction": "VIC", "alert_type": "storm", "issued_at": None, "location": None, "latitude": None, "longitude": None,
           "raw_text": "x\nhttps://example.invalid/bom", "description": "TOP PRIORITY FOR IMMEDIATE BROADCAST\n\nSevere Thunderstorm Warning\n\nIssued at 2:38 pm Monday, 2 November 2026.\n\nSevere thunderstorms are likely to produce heavy rainfall and damaging winds."}
    matched = bom_areas.AreaResult("matched", ["Mallee", "Northern Country", "Wimmera"], vic_sites, 0)
    now = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
    followup = {**base, "id": "test-0003", "source_key": "nsw_rfs", "is_active": True, "severity": "emergency_warning",
                "headline": "Bushfire Emergency Warning - Katoomba", "emergency_email_tier": "watch_and_act",
                "emergency_email_hash": "x", "emergency_email_last_at": "2026-11-02T01:00:00+00:00", "emergency_email_lifted_at": None}
    ended = {**followup, "id": "test-0004", "is_active": False, "severity": "watch_and_act", "headline": "Bushfire Watch and Act - Springwood"}

    common = [patch.object(ea, "send_email", side_effect=capture), patch.object(ea, "_supabase_request"),
              patch.object(ea.alert_silences, "list_active_silences", return_value=[])]
    for p in common:
        p.start()
    try:
        with patch.object(ea.site_matching, "list_active_sites", return_value=sites):
            with patch.object(ea, "supabase_get", return_value=[{**base, "severity": "emergency_warning", "headline": "Bushfire Emergency Warning - Katoomba"}]):
                ea._send_emergency_warning_emails("nsw_rfs")
            with patch.object(ea, "supabase_get", return_value=[{**base, "id": "test-0005", "severity": "watch_and_act", "headline": "Bushfire Watch and Act - Springwood"}]):
                ea._send_watch_and_act_emails("nsw_rfs")
            with patch.object(ea, "supabase_get", return_value=[followup, ended]):
                ea._send_follow_up_emails(now)
        with patch.object(ea.site_matching, "list_active_sites", return_value=vic_sites), \
             patch.object(ea.bom_areas, "match_alert", return_value=matched), patch.object(ea, "supabase_get", return_value=[bom]):
            ea._send_bom_attention_emails("bom_vic")
    finally:
        for p in common:
            p.stop()
    digest_html = ('<pre style="font-family:monospace;white-space:pre-wrap">Notice: DIGEST\nActive-Alerts: 31</pre>'
                   "<p>Sample daily overview: two flood warnings remain in force in south-west Queensland; nothing above Advice elsewhere.</p>")
    out.append(("[DIGEST] Emergency Alert Hub - daily overview (31 active)", digest_html))
    return [(s.split("]")[0].lstrip("["), s, h) for s, h in out]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", required=True, help="recipient for the test messages (required)")
    ap.add_argument("--cc", help="optional second recipient, copied on every test message")
    ap.add_argument("--only", help="comma-separated notice tags, e.g. EW,BOM-HIGH")
    ap.add_argument("--dry-run", action="store_true", help="print subjects, send nothing")
    args = ap.parse_args()
    wanted = {t.strip().upper() for t in args.only.split(",")} if args.only else None
    sent = failed = 0
    for tag, subject, html in build_samples():
        if wanted and tag.upper() not in wanted:
            continue
        body = _BANNER + html
        subject = f"[TEST] {subject}"
        if args.dry_run:
            print(subject + (f"   (To: {args.to}, Cc: {args.cc})" if args.cc else f"   (To: {args.to})"))
            continue
        if resend_email.send_email(to=args.to, subject=subject, html=body, text=alert_email.html_to_text(body), cc=args.cc):
            sent += 1
            print(f"sent: {subject}")
        else:
            failed += 1
            print(f"FAILED: {subject} -> {resend_email.last_failure}")
    if not args.dry_run:
        print(f"{sent} sent, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
