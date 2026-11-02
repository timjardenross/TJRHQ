"""Send sample alert emails (made-up data) to an address you name.

Builds each email type with the real code path (subjects, header block, plain-text
part) from fixed fictional alerts, and sends them through the same
Resend settings the ingestion service uses (RESEND_API_KEY, RESEND_FROM). Every
message is labelled TEST in the subject and the first line. Nothing is read from
or written to the database.

Run it wherever the Resend settings are present (the ingestion host):

    python tools/emergency_alerts/send_test_email.py --to you@example.com
    python tools/emergency_alerts/send_test_email.py --to you@example.com --only EW,BOM-HIGH
    python tools/emergency_alerts/send_test_email.py --to team@example.com --cc you@example.com   # the real arrangement
    python tools/emergency_alerts/send_test_email.py --to team@example.com --scenario no-impact   # alerts that touch none of our sites
    python tools/emergency_alerts/send_test_email.py --to team@example.com --scenario impact      # alerts that do
    python tools/emergency_alerts/send_test_email.py --to you@example.com --dry-run   # print only

Scenarios (for testing whatever reads the mailbox downstream): `no-impact` and `impact`
each send two alerts (an Emergency Warning and a BOM high-attention warning) built from
fixed fictional text. The emails do NOT say which scenario they belong to; the expected
answer (EXPECTED below, checked against the site register on 2 Nov 2026) is printed by
the script instead, so the reader's own site matching can be checked against it.

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

import intelligence.emergency_alerts as ea
from core.notifications import resend_email

_BANNER = "<p><strong>TEST MESSAGE - made-up data. This is not a real alert.</strong></p>"


def build_samples() -> list[tuple[str, str, str]]:
    """(notice tag, subject, html) for every email type, from fictional alerts."""
    base = {"id": "test-0001", "jurisdiction": "NSW", "alert_type": "bushfire", "location": "Katoomba, Blue Mountains",
            "description": "A fire is burning out of control near Katoomba. Leave now if the way is clear.",
            "canonical_url": "https://example.invalid/official-warning", "issued_at": "2026-11-02T14:05:00+11:00", "latitude": None, "longitude": None}
    out: list[tuple[str, str]] = []

    def capture(**kw):
        out.append((kw["subject"], kw["html"]))
        return True

    bom = {"id": "test-0002", "headline": "Severe Thunderstorm Warning for parts of Mallee, Northern Country and Wimmera Forecast Districts.",
           "jurisdiction": "VIC", "alert_type": "storm", "issued_at": None, "location": None, "latitude": None, "longitude": None,
           "raw_text": "x\nhttps://example.invalid/bom", "description": "TOP PRIORITY FOR IMMEDIATE BROADCAST\n\nSevere Thunderstorm Warning\n\nIssued at 2:38 pm Monday, 2 November 2026.\n\nSevere thunderstorms are likely to produce heavy rainfall and damaging winds."}
    now = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
    followup = {**base, "id": "test-0003", "source_key": "nsw_rfs", "is_active": True, "severity": "emergency_warning",
                "headline": "Bushfire Emergency Warning - Katoomba", "emergency_email_tier": "watch_and_act",
                "emergency_email_hash": "x", "emergency_email_last_at": "2026-11-02T01:00:00+00:00", "emergency_email_lifted_at": None}
    ended = {**followup, "id": "test-0004", "is_active": False, "severity": "watch_and_act", "headline": "Bushfire Watch and Act - Springwood"}

    with patch.object(ea, "send_email", side_effect=capture), patch.object(ea, "_supabase_request"), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[]):
        with patch.object(ea, "supabase_get", return_value=[{**base, "severity": "emergency_warning", "headline": "Bushfire Emergency Warning - Katoomba"}]):
            ea._send_emergency_warning_emails("nsw_rfs")
        with patch.object(ea, "supabase_get", return_value=[{**base, "id": "test-0005", "severity": "watch_and_act", "headline": "Bushfire Watch and Act - Springwood"}]):
            ea._send_watch_and_act_emails("nsw_rfs")
        with patch.object(ea, "supabase_get", return_value=[followup, ended]):
            ea._send_follow_up_emails(now)
        with patch.object(ea, "supabase_get", return_value=[bom]):
            ea._send_bom_attention_emails("bom_vic")
    digest_html = ('<pre style="font-family:monospace;white-space:pre-wrap">Notice: DIGEST\nActive-Alerts: 31</pre>'
                   "<p>Sample daily overview: two flood warnings remain in force in south-west Queensland; nothing above Advice elsewhere.</p>")
    out.append(("[DIGEST] Emergency Alert Hub - daily overview (31 active)", digest_html))
    return [(s.split("]")[0].lstrip("["), s, h) for s, h in out]


# Expected site impact, as of the 2 Nov 2026 register (494 sites). Not placed in the emails.
EXPECTED = {
    "no-impact": [
        "EW  WA  Gibson Desert (remote): nearest site is Kalgoorlie, about 800 km away -> NO site impacted",
        "BOM QLD Moderate Flood Warning for the Barcoo River: no site is inside any Barcoo catchment -> NO site impacted",
    ],
    "impact": [
        "EW  TAS Hobart: Hobart (Tier 1) ~2 km, Closed for Refurbishment - Hobart (Tier 3) ~2 km, Rosny Park Specialist Hub (Tier 2) ~5 km, Glenorchy and Kingston (Tier 3) within 10 km -> SITES impacted",
        (
            "BOM VIC Severe Thunderstorm, parts of Mallee, Northern Country and Wimmera Forecast Districts: 14 sites inside "
            "(Tier 1: Bendigo, Echuca, Horsham, Mildura, Shepparton, Swan Hill; Tier 3: the same towns plus Kerang and Yarrawonga) -> SITES impacted"
        ),
    ],
}


def build_scenarios(which: str) -> list[tuple[str, str, str]]:
    """Two alerts per scenario from fixed fictional text, through the real email code.
    `which` is no-impact, impact or all."""
    now_text = "Issued at 2:38 pm Monday, 2 November 2026."
    ew = lambda i, juris, headline, loc, desc: {
        "id": i, "jurisdiction": juris, "alert_type": "bushfire", "severity": "emergency_warning", "headline": headline, "location": loc,
        "description": desc, "canonical_url": "https://example.invalid/official-warning", "issued_at": "2026-11-02T14:05:00+11:00",
        "latitude": None, "longitude": None}
    bom = lambda i, juris, headline, atype, body: {
        "id": i, "jurisdiction": juris, "headline": headline, "alert_type": atype, "issued_at": None, "location": None, "latitude": None,
        "longitude": None, "raw_text": "x\nhttps://example.invalid/bom",
        "description": f"TOP PRIORITY FOR IMMEDIATE BROADCAST\n\n{headline}\n\n{now_text}\n\n{body}"}
    scenarios = {
        "no-impact": (
            ew("test-s1-ew", "WA", "Bushfire Emergency Warning - Gibson Desert Reserve", "Gibson Desert, Western Australia (remote, near Warburton)",
               "A fast-moving fire is burning in remote desert country. There are no towns in its path. Avoid travel in the area."),
            bom("test-s1-bom", "QLD", "Moderate Flood Warning for the Barcoo River", "flood",
                "Moderate flooding is occurring along the Barcoo River in south-west Queensland. River heights are expected to remain high."),
        ),
        "impact": (
            ew("test-s2-ew", "TAS", "Bushfire Emergency Warning - Hobart", "Hobart and surrounds, Tasmania",
               "A fire is burning out of control on the edge of Hobart. Conditions are changing rapidly. Leave now if the way is clear."),
            bom("test-s2-bom", "VIC", "Severe Thunderstorm Warning for parts of Mallee, Northern Country and Wimmera Forecast Districts.", "storm",
                "Severe thunderstorms are likely to produce heavy rainfall, damaging winds and large hailstones. Locations which may be affected include Horsham, Bendigo and Swan Hill."),
        ),
    }
    picks = scenarios if which == "all" else {which: scenarios[which]}
    out: list[tuple[str, str]] = []

    def capture(**kw):
        out.append((kw["subject"], kw["html"]))
        return True

    with patch.object(ea, "send_email", side_effect=capture), patch.object(ea, "_supabase_request"), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[]):
        for ew_row, bom_row in picks.values():
            with patch.object(ea, "supabase_get", return_value=[ew_row]):
                ea._send_emergency_warning_emails("test_source")
            with patch.object(ea, "supabase_get", return_value=[bom_row]):
                ea._send_bom_attention_emails("bom_test")
    return [(s.split("]")[0].lstrip("["), s, h) for s, h in out]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", required=True, help="recipient for the test messages (required)")
    ap.add_argument("--cc", help="optional second recipient, copied on every test message")
    ap.add_argument("--scenario", choices=["no-impact", "impact", "all"], help="send the two-alert scenario(s) instead of the standard set")
    ap.add_argument("--only", help="comma-separated notice tags, e.g. EW,BOM-HIGH")
    ap.add_argument("--dry-run", action="store_true", help="print subjects, send nothing")
    args = ap.parse_args()
    wanted = {t.strip().upper() for t in args.only.split(",")} if args.only else None
    sent = failed = 0
    samples = build_scenarios(args.scenario) if args.scenario else build_samples()
    for tag, subject, html in samples:
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
    if args.scenario:
        print("\nExpected site impact (the emails do not say):")
        for name in (["no-impact", "impact"] if args.scenario == "all" else [args.scenario]):
            for line in EXPECTED[name]:
                print(f"  [{name}] {line}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
