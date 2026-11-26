"""End-of-day assessment (BRIEF_EOD_ASSESSMENT_V1). Synthetic events; no network, no send, no model."""
from __future__ import annotations

import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence import brief_evidence as be
from intelligence import captains_brief as cb
from intelligence import eod_assessment as ea

NOW = datetime(2026, 11, 26, 7, 0, tzinfo=timezone.utc)          # 18:00 Melbourne
MORNING = datetime(2026, 11, 25, 20, 0, tzinfo=timezone.utc)     # 07:00 Melbourne


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for flag in (ea.FLAG, "BRIEF_COVERAGE_V1", "BRIEF_COVERAGE_V1_MORNING"):
        monkeypatch.delenv(flag, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


def event(n, title, at, source="ABC News", geography="AU", summary=""):
    return {"id": f"{n:08x}-0000-4000-8000-000000000000", "title": title, "summary": summary, "source": source, "geography": geography,
            "collected_at": at.isoformat(), "published_at": at.isoformat(), "url": f"https://example.org/{n}"}


OUTAGE = event(1, "Telstra outage leaves thousands of customers without mobile service in Victoria", MORNING - timedelta(hours=2))
RESTORED = event(2, "Telstra restores mobile service in Victoria after outage", NOW - timedelta(hours=2), "iTnews")


def morning_row(text, caveat=None):
    return {"brief_text": text, "generated_at": MORNING.isoformat(), "collection_caveat": caveat}


def section(sections, number):
    return "\n".join(next(body for heading, body in sections if heading.startswith(f"{number}. ")))


def whole(sections):
    return "\n".join(x for _, body in sections for x in body)


def carried(state="ongoing"):
    inc = ea.build_items([OUTAGE], None, MORNING)[0].view.incident_id
    return inc, morning_row(f"- {OUTAGE['title']} ({state}; 1 reports; {inc})\n    NEW 25 Nov 18:00Z: x [00000001]")


def test_all_nine_sections_in_order():
    sections = ea.assess([OUTAGE], None, now=NOW)
    assert [h.split(".")[0] for h, _ in sections] == [str(n) for n in range(1, 10)]


def test_no_morning_record_claims_no_change():
    sections = ea.assess([OUTAGE, RESTORED], None, now=NOW)
    assert "CANNOT BE ASSESSED" in section(sections, 1)
    assert "Not assessed" in section(sections, 2)
    for label in ("[NEW]", "[RESOLVED]", "[ESCALATING]", "[DETERIORATING]", "NO MATERIAL CHANGE"):
        assert label not in whole(sections)


def test_restoration_since_morning_is_resolved():
    _, row = carried()
    sections = ea.assess([OUTAGE, RESTORED], row, now=NOW)
    assert "RESOLVED" in section(sections, 2)
    assert "service reported restored" in whole(sections)


def test_item_first_collected_after_the_morning_brief_is_new():
    late = event(3, "Westpac payments outage stops card transactions across New South Wales", NOW - timedelta(hours=1))
    _, row = carried()
    sections = ea.assess([OUTAGE, late], row, now=NOW)
    assert "NEW: Westpac payments outage" in section(sections, 2)
    assert "NEW: Telstra" not in section(sections, 2)


def test_known_before_07_but_not_carried_is_not_called_new():
    sections = ea.assess([OUTAGE, event(4, "Weather stays mild", NOW - timedelta(hours=1))], morning_row("nothing relevant"), now=NOW)
    assert "NEW: Telstra" not in section(sections, 2)


def test_no_material_change_is_stated_only_when_something_was_collected():
    _, row = carried()
    quiet = ea.assess([OUTAGE, event(4, "Council opens new library", NOW - timedelta(hours=1))], row, now=NOW)
    assert "NO MATERIAL CHANGE" in section(quiet, 1)
    assert "Continuing, no new reporting since 07:00" in section(quiet, 4)
    silent = ea.assess([OUTAGE], row, now=NOW)
    assert "CANNOT BE ASSESSED" in section(silent, 1) and "NO MATERIAL CHANGE" not in whole(silent)


def test_unmatched_open_morning_item_is_carried_forward_not_resolved():
    row = morning_row("- Water supply failure in Hobart (ongoing; 3 reports; inc-0123456789)")
    sections = ea.assess([event(4, "Council opens new library", NOW - timedelta(hours=1))], row, now=NOW)
    assert "CARRIED FORWARD" in section(sections, 6) and "Not treated as resolved" in section(sections, 6)


def test_untiered_morning_lines_are_carried_forward_too():
    row = morning_row("- [ESCALATE · reported] Water supply failure in Hobart — impact stated in headline, ongoing; "
                      "moderate confidence [inc-0123456789; 1 report(s); evidence: ABC News #aaaaaaaa]")
    sections = ea.assess([event(4, "Council opens new library", NOW - timedelta(hours=1))], row, now=NOW)
    assert "CARRIED FORWARD" in section(sections, 6)


def test_improving_needs_an_established_worse_state():
    view = ea.build_items([OUTAGE], None, NOW)[0].view
    assert ea._lifecycle(view, "partially_restored", True, True, (view, "unknown"), None) != ea.IMPROVING
    assert ea._lifecycle(view, "partially_restored", True, True, (view, "ongoing"), None) == ea.IMPROVING


def test_regulatory_story_reported_before_the_morning_brief_is_not_new():
    _, row = carried()
    events = [OUTAGE, event(13, "APRA finalises new governance rules for banks", MORNING - timedelta(hours=3)),
              event(14, "APRA finalises governance overhaul for banks", NOW - timedelta(hours=1), "iTnews")]
    sections = ea.assess(events, row, now=NOW)
    assert "NEW regulatory" not in section(sections, 2)
    assert "predates the morning brief" in section(sections, 4)


def test_distinct_decisions_by_one_regulator_are_not_merged():
    at = NOW - timedelta(hours=1)
    events = [event(15, "ASIC sues insurer over claims delays", at), event(16, "ASIC sues insurer over data breach", at)]
    assert len(ea.policy_items(events, MORNING)) == 2


def test_regulatory_decision_proposal_and_commentary_are_separated():
    at = NOW - timedelta(hours=1)
    events = [event(5, "ASIC sues major insurer over claims delays", at),
              event(6, "ASIC sues major insurer over claims handling failures - Insurance Business", at, "Google News: regulators"),
              event(7, "APRA proposes changes to liquidity reporting", at),
              event(8, "ACMA warns telcos on scam messages", at),
              event(9, "Vendor adds CPS 230 support as APRA increases scrutiny", at)]
    items = ea.policy_items(events, MORNING)
    kinds = {p.actor: p.kind for p in items}
    assert len(items) == 3                                   # same story merged; vendor marketing excluded
    assert kinds["ASIC"].startswith("DECISION") and kinds["APRA"].startswith("PROPOSAL") and kinds["ACMA"].startswith("COMMENTARY")
    _, row = carried()
    assert "1 regulatory decision" in section(ea.assess([OUTAGE, *events], row, now=NOW), 1)


def test_outlook_and_patch_notices_are_not_disruptions():
    at = NOW - timedelta(hours=1)
    items = ea.build_items([event(10, "Victoria faces increased bushfire risk this summer", at),
                            event(11, "Vendor patches critical flaws that let attackers take over CMS sites", at, "iTnews")], None, NOW)
    assert not any(i.is_disruption or i.unresolved for i in items)


def test_source_reference_and_coverage_limits_are_retained():
    sections = ea.assess([OUTAGE], None, now=NOW, caveat="collection lagged", limitations=ea.source_limitations())
    assert "#00000001" in whole(sections)
    gaps = section(sections, 9)
    assert "collection lagged" in gaps and "Telstra coverage" in gaps and "rule-based" in gaps


def test_assessment_has_no_model_or_capacity_dependency():
    source = Path(ea.__file__).read_text(encoding="utf-8")
    for forbidden in ("judgements", "capacity_checkins", "llm", "model_router", "urllib.request", "requests"):
        assert f"import {forbidden}" not in source and f"from intelligence.{forbidden}" not in source
    assert "capacity" not in ea.assess.__code__.co_varnames


def _stub_brief(monkeypatch, events):
    monkeypatch.setattr(cb, "_get_capacity_today", lambda: {"has_checked_in": True, "latest_capacity_state": "amber", "checkin_label": "private-marker"})
    monkeypatch.setattr(cb, "_get_infra_verification", lambda: None)
    monkeypatch.setattr(cb, "_get_recent_signals", lambda **kw: [])
    monkeypatch.setattr(cb, "_get_todays_morning_brief_text", lambda: None)
    monkeypatch.setattr(cb, "_get_todays_morning_record", lambda: None)
    monkeypatch.setattr(cb, "_collection_coverage_caveat", lambda key: None)
    monkeypatch.setattr(be, "load_events", lambda sb_get, **kw: events)


def test_flag_off_keeps_the_legacy_summary(monkeypatch):
    _stub_brief(monkeypatch, [OUTAGE])
    text = cb.generate_eod_summary()
    assert "END-OF-DAY SUMMARY" in text and "ASSESSMENT" not in text and "could not be produced" not in text


def test_flag_on_renders_assessment_with_capacity_last_and_escaped(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv(ea.FLAG, "1")
    _stub_brief(monkeypatch, [event(12, "Telstra <NRP> outage leaves customers without service", now - timedelta(hours=1))])
    text = cb.generate_eod_summary()
    assert "END-OF-DAY ASSESSMENT" in text and "&lt;NRP&gt;" in text and "<NRP>" not in text
    assert text.index("private-marker") > text.index("10. PERSONAL CAPACITY") > text.index("9. GAPS")
    assert text.count("private-marker") == 1


@pytest.mark.parametrize("failure", ["no evidence", "error"])
def test_failure_falls_back_to_the_legacy_summary_and_says_so(monkeypatch, failure):
    monkeypatch.setenv(ea.FLAG, "1")
    _stub_brief(monkeypatch, [] if failure == "no evidence" else [OUTAGE])
    if failure == "error":
        monkeypatch.setattr(ea, "assess", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    text = cb.generate_eod_summary()
    assert "END-OF-DAY SUMMARY" in text and "could not be produced" in text
