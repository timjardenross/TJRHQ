"""Confidence vs materiality (Captain's rule): a HIGH-materiality incident with WEAK evidence is a PROMINENT verification priority
('URGENT TO VERIFY'), not buried in the ordinary verification buckets. High materiality + strong evidence escalates as before; low
materiality + weak evidence stays low priority. Stricter corroboration (aggregators never corroborate) must not hide an emerging incident."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_evidence as be

NOW = datetime(2026, 11, 23, 0, 0, tzinfo=timezone.utc)
HEADING = "URGENT TO VERIFY (potentially severe, not yet corroborated)"
T1 = "Eyre Peninsula blackout: 20,000 customers without power after transmission towers crushed"
T2 = "Eyre Peninsula blackout leaves 20,000 customers without power as storm crushed transmission towers, crews assess damage"
OUTLOOK = "Microsoft Outlook outage leaves millions of Australian customers unable to access email - ABC News"


def ev(i, title, source, hours_ago=2, geo="AU"):
    t = NOW - timedelta(hours=hours_ago)
    return {"id": i, "title": title, "source": source, "geography": geo, "collected_at": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "url": f"https://example.test/{i}"}


def _one(events):
    es = be.build_evidence(events, now=NOW)
    assert len(es.incidents) == 1
    return es, es.incidents[0]


def _urgent_section(lines):
    if HEADING not in lines:
        return []
    out = []
    for line in lines[lines.index(HEADING) + 1:]:
        if not line.startswith("- "):
            break
        out.append(line)
    return out


GN_ONLY = [ev("g1", T1 + " - ABC News", "Google News - Power", 3), ev("g2", T2 + " - The Guardian", "Google News - Energy", 2)]


def test_a_google_news_only_au_blackout_is_urgent_to_verify():
    es, i = _one(GN_ONLY)
    assert i.priority == "VERIFY" and i.materiality == "high"
    assert i.urgent_verify is True
    assert i.evidence_status == "unverified" and i.independent_publishers == 0      # aggregators never corroborate
    lines = be.morning_view(es)
    body = _urgent_section(lines)
    assert len(body) == 1 and "Eyre Peninsula blackout" in body[0]
    assert "seen only via aggregator" in body[0]
    assert "next:" in body[0] and f"[{i.incident_id};" in body[0]
    # not repeated in the ordinary verification buckets or the forward watch
    assert sum(line.count(i.incident_id) for line in lines) == 1


def test_b_same_blackout_from_abc_and_guardian_direct_escalates_not_urgent():
    es, i = _one([ev("a1", T1, "ABC News", 3), ev("a2", T2, "Guardian Australia", 2)])
    assert i.priority == "ESCALATE" and i.evidence_status == "corroborated" and not i.urgent_verify
    assert HEADING not in be.morning_view(es)


def test_c_low_materiality_google_news_only_is_reference_and_not_shown():
    es, i = _one([ev("l1", "Council reviews streetlight maintenance schedule - Local Paper", "Google News - Local")])
    assert i.priority == "REFERENCE" and not i.urgent_verify
    assert HEADING not in be.morning_view(es)


def test_d_single_credible_and_primary_reports_unchanged():
    _, single = _one([ev("s1", T1, "ABC News")])
    assert single.priority == "ESCALATE" and single.provisional and not single.urgent_verify
    es, prim = _one([ev("p1", T1, "AEMO Market Notices")])
    assert prim.priority == "ESCALATE" and prim.evidence_status == "officially_confirmed" and not prim.urgent_verify
    assert HEADING not in be.morning_view(es)


def test_e_high_materiality_international_story_stays_behind_the_au_gate():
    es, i = _one([ev("i1", "Blackout leaves 2 million customers without power across Texas after grid failure - CNN", "Google News - Power", geo="")])
    assert i.materiality == "high" and i.priority == "REFERENCE" and not i.urgent_verify
    assert HEADING not in be.morning_view(es)


def test_f_global_platform_outage_with_stated_au_exposure_via_google_news_is_urgent():
    es, i = _one([ev("m1", OUTLOOK, "Google News - Cloud", geo="")])
    assert i.priority == "VERIFY" and i.urgent_verify
    assert any("Microsoft Outlook outage" in line for line in _urgent_section(be.morning_view(es)))


def test_f2_platform_outage_with_only_a_plausible_dependency_is_not_urgent():
    # no Australian impact stated: the dependency cap keeps it an ordinary verification item
    es, i = _one([ev("m2", "Microsoft Outlook outage leaves millions of customers unable to access email - CNN", "Google News - Cloud", geo="")])
    assert not i.urgent_verify
    assert HEADING not in be.morning_view(es)


def test_g_item_older_than_24h_never_in_urgent_section():
    old = [ev("o1", T1 + " - ABC News", "Google News - Power", 30), ev("o2", T2 + " - The Guardian", "Google News - Energy", 29)]
    es, i = _one(old)
    assert i.urgent_verify is False            # not urgent: its newest report is older than the 24-hour recency
    assert HEADING not in be.morning_view(es)


def test_h_section_absent_when_empty_and_placed_before_what_matters_today():
    es, _ = _one([ev("a1", T1, "ABC News", 3), ev("a2", T2, "Guardian Australia", 2)])
    lines = be.morning_view(es)
    assert HEADING not in lines and not any("urgent to verify" in line.lower() for line in lines)
    es2 = be.build_evidence(GN_ONLY + [ev("c1", "Coles Group investigating a cyber incident", "ABC News", 5)], now=NOW)
    lines2 = be.morning_view(es2)
    sit = max(n for n, line in enumerate(lines2) if line.startswith("Operational situation"))
    assert sit < lines2.index(HEADING) < lines2.index("What matters today — OFFICIALLY CONFIRMED or CORROBORATED incidents")


def test_i_hedged_high_materiality_report_is_still_verify_not_urgent():
    _, i = _one([ev("h1", "Eyre Peninsula blackout: 20,000 customers reportedly without power after transmission towers crushed", "ABC News")])
    assert i.priority == "VERIFY" and not i.urgent_verify


def test_medium_materiality_weak_evidence_stays_ordinary_verify():
    _, i = _one([ev("w1", "Telstra mobile outage hits some customers in Adelaide - Local Paper", "Google News - Telco")])
    assert i.materiality != "high" and not i.urgent_verify


def test_j_weekly_view_still_renders_and_lists_urgent_item_for_monitoring():
    es = be.build_evidence(GN_ONLY + [ev("a1", "Coles Group investigating a cyber incident", "ABC News", 5)], now=NOW)
    text = "\n".join(be.weekly_view(es))
    assert "EVIDENCE-BASED WEEK" in text and "MONITOR: Eyre Peninsula blackout" in text


# ── recency: urgent is about NOW (found in integrated regression on real history) ───────────────────────────────────────────────
def test_urgent_flag_requires_a_recent_newest_report():
    gn = lambda h: [ev("a", "Eyre Peninsula blackout leaves 20,000 customers without power - ABC News & Headlines", "Google News - Telstra", h)]
    assert _one(gn(3))[1].urgent_verify is True
    assert _one(gn(23))[1].urgent_verify is True
    assert _one(gn(25))[1].urgent_verify is False        # beyond the 24h recency the morning view uses
    assert _one(gn(9 * 24))[1].urgent_verify is False    # a 9-day-old story must not be flagged urgent


def test_a_stale_urgent_item_is_not_promoted_in_the_weekly_view():
    stale = [ev("s1", T1 + " - ABC News", "Google News - Power", 9 * 24)]
    mid = [ev("r1", "Optus outage hits customers across Sydney, services patchy - ABC News", "Google News - Telstra", 5 * 24)]
    es = be.build_evidence(stale + mid, now=NOW, window_hours=240)
    assert not any(i.urgent_verify for i in es.incidents)         # the 9-day-old blackout is not flagged, so it cannot head the list
    assert be.weekly_view(es, None)                               # and the weekly view still renders
