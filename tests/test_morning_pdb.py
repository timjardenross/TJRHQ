"""Morning product (BRIEF_MORNING_PDB_V1). Synthetic events; no network, no send, no model."""
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

MORNING = datetime(2026, 11, 25, 20, 0, tzinfo=timezone.utc)     # 07:00 Melbourne
EVENING = MORNING + timedelta(hours=11)


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for flag in (ea.MORNING_FLAG, ea.FLAG, "BRIEF_THEMES_V1", "BRIEF_THEMES_V1_MORNING", "INTEL_PRODUCTS_IN_BRIEF", "BRIEF_COVERAGE_V1", "BRIEF_COVERAGE_V1_MORNING", "COVERAGE_CRITICALITY_SHADOW_V1"):
        monkeypatch.delenv(flag, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


def event(n, title, at, source="ABC News", geography="AU"):
    return {"id": f"{n:08x}-0000-4000-8000-000000000000", "title": title, "summary": "", "source": source, "geography": geography,
            "collected_at": at.isoformat(), "published_at": at.isoformat(), "url": f"https://example.org/{n}"}


OUTAGE = event(1, "Telstra outage leaves thousands of customers without mobile service in Victoria", MORNING - timedelta(hours=2))


def text_of(sections):
    return "\n".join(x for heading, body in sections for x in (heading, *body))


def test_eight_sections_in_order_then_supporting_detail():
    headings = [h for h, _ in ea.assess_morning([OUTAGE], None, now=MORNING)]
    assert [h.split(".")[0] for h in headings[:8]] == [str(n) for n in range(1, 9)]
    assert headings[8].startswith("SUPPORTING DETAIL") and len(headings) == 9


def test_judgements_stated_unavailable_and_no_change_claimed_without_a_previous_brief():
    sections = dict(ea.assess_morning([OUTAGE], None, now=MORNING))
    assert "NOT AVAILABLE" in "\n".join(sections["2. KEY INTELLIGENCE JUDGEMENTS"])
    changes = "\n".join(sections["6. MATERIAL CHANGES AND EMERGING PATTERNS"])
    assert "Change cannot be assessed" in changes and "NEW:" not in changes


def test_quiet_collection_is_not_an_all_clear():
    text = text_of(ea.assess_morning([event(3, "Council opens new library", MORNING - timedelta(hours=1))], None, now=MORNING))
    assert "not an all-clear" in text and "Material items: 0 Australian, 0 international" in text


def test_evening_assessment_reads_this_morning_product():
    text = text_of(ea.assess_morning([OUTAGE], None, now=MORNING))
    record = ea.parse_morning({"brief_text": text, "generated_at": MORNING.isoformat()})
    assert record.entries and "00000001" in record.report_ids
    inc, (headline, _state) = next(iter(record.entries.items()))
    assert inc in record.incident_ids and "Telstra" in headline
    evening = ea.assess([OUTAGE, event(4, "Weather stays mild", EVENING - timedelta(hours=1))],
                        {"brief_text": text, "generated_at": MORNING.isoformat()}, now=EVENING)
    assert "NEW: Telstra" not in text_of(evening)


def test_second_day_reports_change_against_the_previous_brief():
    previous = {"brief_text": text_of(ea.assess_morning([OUTAGE], None, now=MORNING)), "generated_at": MORNING.isoformat()}
    later = MORNING + timedelta(days=1)
    new = event(2, "Westpac payments outage leaves customers unable to pay", later - timedelta(hours=2), "iTnews")
    changes = "\n".join(dict(ea.assess_morning([OUTAGE, new], previous, now=later))["6. MATERIAL CHANGES AND EMERGING PATTERNS"])
    assert "NEW: Westpac" in changes and "NEW: Telstra" not in changes


def _stub_brief(monkeypatch, events):
    monkeypatch.setattr(cb, "_get_capacity_today", lambda: {"has_checked_in": True, "latest_capacity_state": "amber", "checkin_label": "private-marker"})
    monkeypatch.setattr(cb, "_get_infra_verification", lambda: None)
    monkeypatch.setattr(cb, "_get_recent_signals", lambda **kw: [])
    monkeypatch.setattr(cb, "_get_latest_ori_brief", lambda: None)
    monkeypatch.setattr(cb, "_get_previous_morning_record", lambda: None)
    monkeypatch.setattr(cb, "_get_previous_evening_record", lambda: None)
    monkeypatch.setattr(cb, "_morning_gap", lambda: __import__("intelligence.brief_reliability", fromlist=["x"]).get_gap(lambda *a: [], "2026-11-26"))
    monkeypatch.setattr(be, "load_events", lambda sb_get, **kw: events)


def test_flag_on_has_no_model_narrative_and_capacity_stays_out_of_the_email(monkeypatch):
    monkeypatch.setenv(ea.MORNING_FLAG, "1")
    now = datetime.now(timezone.utc)
    _stub_brief(monkeypatch, [event(5, "Telstra <NRP> outage leaves customers without service", now - timedelta(hours=1))])
    monkeypatch.setattr(cb, "build_daily_digest", lambda **kw: (_ for _ in ()).throw(AssertionError("model narrative requested")))
    text = cb.generate_morning_brief()
    assert "1. EXECUTIVE BOTTOM LINE" in text and "&lt;NRP&gt;" in text and "<NRP>" not in text and "PLATFORM, TODAY" not in text
    assert text.index("private-marker") > text.index("SUPPORTING DETAIL")
    emailed = cb._strip_personal_blocks(text)
    assert "private-marker" not in emailed and "SUPPORTING DETAIL" in emailed


def test_flag_off_keeps_the_previous_format(monkeypatch):
    _stub_brief(monkeypatch, [OUTAGE])
    monkeypatch.setattr(cb, "build_daily_digest", None)
    text = cb.generate_morning_brief()
    assert "MORNING BRIEF" in text and "EXECUTIVE BOTTOM LINE" not in text and "could not be produced" not in text


@pytest.mark.parametrize("failure", ["no evidence", "error"])
def test_failure_falls_back_and_says_so(monkeypatch, failure):
    monkeypatch.setenv(ea.MORNING_FLAG, "1")
    _stub_brief(monkeypatch, [] if failure == "no evidence" else [OUTAGE])
    monkeypatch.setattr(cb, "build_daily_digest", None)
    if failure == "error":
        monkeypatch.setattr(ea, "assess_morning", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    text = cb.generate_morning_brief()
    assert "could not be produced" in text and "This is not an all-clear" in text and "private-marker" in text


@pytest.mark.parametrize("headline", ["Springfield teacher's licence suspended amid police investigation",
                                      "Veteran coach's spray shut down ball tampering row after Sandpapergate"])
def test_individual_conduct_and_sport_without_a_service_are_left_out(headline):
    text = text_of(ea.assess_morning([event(6, headline, MORNING - timedelta(hours=1))], None, now=MORNING))
    assert headline[-30:] not in text and "Material items: 0 Australian" in text


def test_service_reporting_that_mentions_a_worker_is_kept():
    kept = event(7, "Telstra outage: worker investigation after thousands of customers lose mobile service", MORNING - timedelta(hours=1))
    assert "Telstra outage" in text_of(ea.assess_morning([kept], None, now=MORNING))


def test_criticality_is_omitted_for_a_stale_or_absent_coverage_record(monkeypatch):
    monkeypatch.setenv("COVERAGE_CRITICALITY_SHADOW_V1", "1")
    for latest in (None, {"coverage": {"failed": 1}, "generated_at": "2020-01-01T00:00:00+00:00"}):
        monkeypatch.setattr(cb, "_get_latest_ori_brief", lambda latest=latest: latest)
        assert cb._criticality_lines() == []


def test_rail_disruption_does_not_claim_water_and_is_not_called_ongoing():
    rail = event(8, "NSW trains to be disrupted from Friday after rail union vote", MORNING - timedelta(hours=2))
    text = text_of(ea.assess_morning([rail], None, now=MORNING))
    assert "water" not in text and "(announced, not started; 1 reports;" in text and "(ongoing" not in text
    assert ea.parse_morning({"brief_text": text, "generated_at": MORNING.isoformat()}).entries
    assert ea._sector_words("transport_water", "Boil water alert after pipe burst")[0] == "water"


def test_restored_item_is_not_described_as_continuing():
    restored = event(9, "Telstra restores mobile service in Victoria after outage", MORNING - timedelta(hours=2))
    previous = {"brief_text": text_of(ea.assess_morning([restored], None, now=MORNING)), "generated_at": MORNING.isoformat()}
    evening = text_of(ea.assess([restored, event(10, "Weather stays mild", EVENING - timedelta(hours=1))], previous, now=EVENING))
    assert "Continuing, no new reporting since 07:00, restored" not in evening
    if "Telstra restores" in evening:
        assert "Restored earlier, no new reporting" in evening


@pytest.mark.parametrize("pair", [("ASIC sues major insurer over complaints handling and claims delays",
                                   "ASIC sues AIG Australia over 534 missed complaint deadlines"),
                                  ("APRA finalises new governance rules to start in 2028",
                                   "APRA keeps 12-year board tenure cap despite pushback"),
                                  ("APRA finalises new governance rules", "APRA sets 12-year director limit for 2028")])
def test_one_regulatory_development_per_actor_and_subject(pair):
    events = [event(20 + n, t, MORNING - timedelta(hours=2), "Google News: regulators") for n, t in enumerate(pair)]
    assert len(ea.policy_items(events, MORNING - timedelta(days=1))) == 1


def test_different_regulatory_subjects_stay_separate():
    events = [event(30, "APRA finalises new governance rules", MORNING - timedelta(hours=2)),
              event(31, "APRA retains lending buffer", MORNING - timedelta(hours=1))]
    assert len(ea.policy_items(events, MORNING - timedelta(days=1))) == 2


def test_confirmed_overseas_vulnerability_is_a_leading_indicator_without_an_australian_link():
    cisa = event(11, "CISA Adds Three Known Exploited Vulnerabilities to Catalog", MORNING - timedelta(hours=2), "CISA Alerts", "")
    body = "\n".join(dict(ea.assess_morning([cisa], None, now=MORNING))["5. INTERNATIONAL LEADING INDICATORS"])
    assert "CISA Adds Three" in body and "no direct Australian dependency established" in body


def test_existing_product_findings_are_retained_and_branding_is_tjrhq(monkeypatch):
    monkeypatch.setenv(ea.MORNING_FLAG, "1")
    _stub_brief(monkeypatch, [event(12, "Telstra outage leaves customers without service", datetime.now(timezone.utc) - timedelta(hours=1))])
    monkeypatch.setattr(cb, "_retained_product_lines", lambda: ["INTELLIGENCE PRODUCTS", "- Recurring provider: <retained finding>"])
    text = cb.generate_morning_brief()
    assert "&lt;retained finding&gt;" in text and "TJRHQ" in text
    assert "Starship" not in text and "Stardate" not in text


FORECAST_TITLE = "Severe heatwave and extreme bushfire danger forecast across Victoria and South Australia this weekend"
FORECAST = event(7, FORECAST_TITLE, MORNING + timedelta(hours=6))


def _evening_row(events):
    sections = ea.assess(events, None, now=EVENING)
    return {"brief_text": text_of(sections), "generated_at": EVENING.isoformat()}


def _next_morning(events, evening_row):
    previous = {"brief_text": text_of(ea.assess_morning([OUTAGE], None, now=MORNING)), "generated_at": MORNING.isoformat()}
    return dict(ea.assess_morning(events, previous, now=MORNING + timedelta(days=1), evening_row=evening_row))


def test_forecast_only_bottom_line_does_not_contradict_the_material_count():
    bluf = "\n".join(dict(ea.assess_morning([FORECAST], None, now=MORNING + timedelta(days=1)))["1. EXECUTIVE BOTTOM LINE"])
    assert "Material items: 1 Australian" in bluf
    assert "No Australian development met the materiality bar" not in bluf
    assert "forecast, not an incident" in bluf and "not an all-clear" in bluf


def test_item_already_in_the_evening_brief_is_not_new_next_morning():
    events = [OUTAGE, FORECAST]
    row = _evening_row(events)
    assert "inc-" in row["brief_text"]
    without = "\n".join(_next_morning(events, None)["6. MATERIAL CHANGES AND EMERGING PATTERNS"])
    assert "NEW: Severe heatwave" in without                     # the defect: only the previous morning is compared
    sections = _next_morning(events, row)
    assert "NEW: Severe heatwave" not in "\n".join(sections["6. MATERIAL CHANGES AND EMERGING PATTERNS"])
    assert "no new reporting since the previous brief" in "\n".join(sections["3. NATIONAL AND SYSTEMIC RESILIENCE"])


def test_reporting_after_the_evening_brief_is_an_update_not_new():
    row = _evening_row([OUTAGE, FORECAST])
    later = event(8, FORECAST_TITLE, EVENING + timedelta(hours=3), source="The Age")
    sections = _next_morning([OUTAGE, FORECAST, later], row)
    assert "NEW: Severe heatwave" not in "\n".join(sections["6. MATERIAL CHANGES AND EMERGING PATTERNS"])
    assert f"{ea.UPDATED}; FORECAST" in "\n".join(sections["3. NATIONAL AND SYSTEMIC RESILIENCE"])


def test_item_absent_from_the_evening_brief_stays_new_and_an_older_evening_is_ignored():
    events = [OUTAGE, FORECAST]
    for row in (_evening_row([OUTAGE]), dict(_evening_row(events), generated_at=(MORNING - timedelta(hours=13)).isoformat())):
        assert "NEW: Severe heatwave" in "\n".join(_next_morning(events, row)["6. MATERIAL CHANGES AND EMERGING PATTERNS"])
