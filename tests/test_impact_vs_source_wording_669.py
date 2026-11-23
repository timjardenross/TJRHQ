"""#669 (morning-quality concern 3): uncertain operational IMPACT is worded differently from uncertain SOURCE credibility.

Written to FAIL on the pre-fix behaviour: both were lumped under 'REQUIRES VERIFICATION (unverified, hedged or weakly
evidenced; not treated as fact)' with an 'unverified' tag, so a mainstream report of an investigation (credible source, impact
not yet shown) read as if the source itself were doubtful.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intelligence import brief_evidence as be

NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)
IMPACT_H = "IMPACT NOT YET ESTABLISHED"
SOURCE_H = "SOURCE NOT YET VERIFIED"


def ev(i, title, source, age=3, geo="AU"):
    return {"id": i, "title": title, "source": source, "geography": geo, "summary": "",
            "collected_at": (NOW - timedelta(hours=age)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def view(events, **override):
    es = be.build_evidence(events, now=NOW, window_hours=72)
    for i in es.incidents:
        for k, v in override.items():
            setattr(i, k, v)
    return es, "\n".join(be.morning_view(es))


RETRO_H = "RETROSPECTIVE REPORTS"


def sections(text):
    a = text.index(IMPACT_H)
    r = text.index(RETRO_H)
    b = text.index(SOURCE_H)
    c = text.index("WARNINGS AND FORECASTS")
    return text[a:r], text[b:c]


def retro_section(text):
    return text[text.index(RETRO_H):text.index(SOURCE_H)]


COLES = "Coles Group investigating a cyber incident"


def test_a_credible_source_with_impact_not_yet_shown_is_worded_as_an_impact_question():
    _, text = view([ev("a", COLES, "ABC News")])
    impact, source = sections(text)
    assert "Coles Group" in impact and "Coles Group" not in source
    assert "IMPACT NOT YET ESTABLISHED]" in impact                  # in the tag
    assert "SOURCE UNVERIFIED" not in impact                         # pre-fix: tagged 'unverified' under REQUIRES VERIFICATION


def test_an_unverified_source_is_worded_as_a_source_question():
    _, text = view([ev("a", COLES, "ABC News")], evidence_status="unverified")
    impact, source = sections(text)
    assert "Coles Group" in source and "Coles Group" not in impact
    assert "SOURCE UNVERIFIED" in source and "IMPACT NOT YET ESTABLISHED" not in source.split("Coles Group")[1].split("\n")[0].split("]")[0]


def test_a_hedged_report_is_a_source_question():
    _, text = view([ev("a", "Coles Group likely hit by cyber incident, sources say", "ABC News")])
    _impact, source = sections(text)
    assert "Coles Group" in source and "SOURCE UNVERIFIED" in source


def test_a_stated_impact_from_a_credible_source_carries_neither_warning():
    es = be.build_evidence([ev("a", "Power outage hits 20,000 customers in SA", "ABC News")], now=NOW, window_hours=72)
    tag = be._tag(es.incidents[0])
    assert "IMPACT NOT YET ESTABLISHED" not in tag and "SOURCE UNVERIFIED" not in tag


def test_headings_always_appear_and_empty_sections_say_none():
    _, text = view([ev("a", "Power outage hits 20,000 customers in SA", "ABC News")])
    impact, source = sections(text)
    assert "- None." in impact and "- None." in source


def test_the_old_blended_heading_is_gone():
    _, text = view([ev("a", COLES, "ABC News")])
    assert "REQUIRES VERIFICATION" not in text


def test_forward_watch_verify_lines_cover_both_kinds():
    _, text = view([ev("a", COLES, "ABC News")])
    assert "- Verify: Coles Group" in text.split("Forward watch")[1]


def test_retrospective_reports_keep_their_own_label_and_are_not_called_impact_questions():
    es = be.build_evidence([ev("a", 'APRA calls Microsoft outage a "near miss" for financial system', "Insurance Business", 3)], now=NOW, window_hours=72)
    tag = be._tag(es.incidents[0])
    assert "retrospective report" in tag and "IMPACT NOT YET ESTABLISHED" not in tag


# ── Codex review of #678 ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_credible_retrospective_report_has_its_own_section_not_the_impact_section():
    """Codex P2: 'Post-mortem of the Optus outage released' (ABC News, retrospective) appeared under 'effect on service not yet shown'."""
    _, text = view([ev("a", "Post-mortem of the Optus outage released", "ABC News", 3)])
    impact, source = sections(text)
    retro = retro_section(text)
    assert "Optus" in retro and "Optus" not in impact and "Optus" not in source          # pre-fix: under the impact section
    assert "retrospective report" in retro


def test_retrospective_reports_stay_visible_not_filtered_out():
    es, text = view([ev("a", "Post-mortem of the Optus outage released", "ABC News", 3)])
    assert any(i.impact_status == "retrospective" for i in es.incidents)
    assert text.count("Optus") >= 1


def test_an_unverified_retrospective_report_is_a_source_question():
    _, text = view([ev("a", "Post-mortem of the Optus outage released", "ABC News", 3)], evidence_status="unverified")
    _impact, source = sections(text)
    assert "Optus" in source and "retrospective report" in source


def test_every_section_heading_is_present_and_empty_ones_say_none():
    _, text = view([ev("a", "Power outage hits 20,000 customers in SA", "ABC News")])
    for h in (IMPACT_H, RETRO_H, SOURCE_H):
        assert h in text
    assert retro_section(text).strip().endswith("- None.")


# ── Operational situation versus emerging exposure ──────────────────────────────────────────────────────────

CISA = "CISA Adds One Known Exploited Vulnerability to Catalog"


def test_the_brief_states_the_operational_situation_and_separates_emerging_exposure():
    _, text = view([ev("a", CISA, "CISA Alerts")])
    assert "Operational situation: no confirmed, corroborated or single-source reported current disruption" in text
    assert "emerging exposures are listed separately" in text and "no operational consequence is inferred" in text
    assert "EMERGING EXPOSURE" in text
    exposure = text[text.index("EMERGING EXPOSURE"):text.index("Operational implications")]
    assert CISA in exposure
    assert CISA not in sections(text)[0]                       # a vulnerability advisory is not an unestablished service impact


def test_the_situation_line_counts_real_disruptions_and_does_not_invent_any():
    _, text = view([ev("a", "Telstra mobile outage leaves customers across Australia without service", "ABC News"),
                    ev("b", "Telstra mobile outage leaves thousands unable to call, company confirms", "Telstra Exchange")])
    assert "Operational situation: 1 confirmed or corroborated" in text or "Operational situation: 0 confirmed or corroborated and 1" in text
    _, quiet = view([ev("a", CISA, "CISA Alerts")])
    assert "Operational implications (only what the cited reports state)\n- No operational implication" in quiet


def test_a_quiet_day_with_no_exposure_has_no_exposure_sentence():
    _, text = view([ev("a", "Some unrelated sports story", "ABC News", age=2)])
    assert "Operational situation: no confirmed" in text and "emerging exposures are listed" not in text


# ── Forward Watch needs a credible current reason ───────────────────────────────────────────────────────────

AGG = "Google News - Critical Infrastructure/Energy Cyberattack AU"
MS13 = "Microsoft's Friday 13th outage continues with fraud and employee risk warnings - Insurance Business"


def forward(text):
    return text[text.index("Forward watch"):text.index("WORTH KNOWING")] if "WORTH KNOWING" in text else text[text.index("Forward watch"):]


def test_a_stale_aggregator_only_report_stays_visible_but_is_not_carried_into_forward_watch():
    _, text = view([ev("a", MS13, AGG, age=5.4)])
    assert MS13 in text[text.index(SOURCE_H):text.index("WARNINGS AND FORECASTS")]      # still shown, labelled source-not-verified
    assert "Microsoft's Friday 13th" not in forward(text)                                # but not a 24-72h watch item


def test_an_aggregator_only_item_stated_as_ongoing_is_not_a_forward_watch_ongoing():
    _, text = view([ev("a", "Telstra outage continues across Australia, thousands still without service - Some Outlet", AGG, age=2)])
    assert "- Ongoing:" not in forward(text)


def test_a_credible_report_still_reaches_forward_watch():
    _, text = view([ev("a", "Telstra mobile outage continues across Australia, thousands still without service", "ABC News", age=2)])
    assert "- Ongoing: Telstra mobile outage continues" in forward(text)


def test_aggregator_plus_mainstream_is_credible():
    _, text = view([ev("a", "Telstra mobile outage continues across Australia, thousands still without service - ABC News", AGG, age=2),
                    ev("b", "Telstra mobile outage continues across Australia, thousands still without service", "ABC News", age=1)])
    assert "- Ongoing:" in forward(text)


# ── External release review of #678 ─────────────────────────────────────────────────────────────────────────────
TEL = [ev("a", "Telstra mobile outage leaves customers across Australia without service", "ABC News"),
       ev("b", "Telstra mobile outage leaves thousands unable to call, company confirms", "Telstra Exchange")]


def test_an_incident_with_unknown_current_status_is_not_counted_as_a_current_disruption():
    es, text = view(TEL, restoration_status="unknown")
    for i in es.incidents:
        i.record["restoration_status"] = "unknown"
    text = "\n".join(be.morning_view(es))
    line = next(l for l in text.splitlines() if l.startswith("Operational situation:"))
    assert "0 confirmed" not in line and "1 confirmed" not in line
    assert "current status unknown — not counted as current disruptions" in line


def test_an_incident_with_known_current_status_is_still_counted():
    es = be.build_evidence(TEL, now=NOW, window_hours=72)
    for i in es.incidents:
        i.record["restoration_status"] = "ongoing"
    line = next(l for l in "\n".join(be.morning_view(es)).splitlines() if l.startswith("Operational situation:"))
    assert "confirmed or corroborated" in line and "status unknown" not in line


def test_a_low_quality_blog_is_a_source_question_not_an_impact_question():
    _, text = view([ev("a", COLES, "Random Cyber Blog")])
    impact, source = sections(text)
    assert "Coles Group" in source and "Coles Group" not in impact


def test_forward_watch_verify_lines_carry_the_citation():
    _, text = view([ev("a", COLES, "ABC News")])
    verify = next(l for l in text.split("Forward watch")[1].splitlines() if l.startswith("- Verify:"))
    assert "[" in verify and "report(s)" in verify


def test_editorial_relevance_only_is_tagged_and_not_counted_or_listed_as_matters_today():
    es = be.build_evidence([ev("a", "Power outage hits 20,000 customers in SA", "ABC News")], now=NOW, window_hours=72)
    es.incidents[0].reasons.append("Australian-audience outlet only")
    assert "editorial relevance only (Australian operational impact not established)" in be._tag(es.incidents[0])
    text = "\n".join(be.morning_view(es))
    line = next(l for l in text.splitlines() if l.startswith("Operational situation:"))
    assert "no confirmed" in line
    matters = text[text.index("What matters today"):text.index(IMPACT_H)]
    assert "20,000" not in matters
    assert "20,000" in text[text.index(SOURCE_H):text.index("WARNINGS AND FORECASTS")]


LONDON = "Power outage leaves 20,000 customers in London without electricity"


def test_london_outage_from_an_australian_outlet_is_editorial_only_without_injected_reasons():
    es = be.build_evidence([ev("a", LONDON, "ABC News", geo="GB")], now=NOW, window_hours=72)
    inc = es.incidents[0]
    # With #677 merged the relevance gate may demote this incident to REFERENCE (hidden altogether); on this branch alone it stays
    # actionable and carries the tag. Either way it is never counted as a current disruption.
    assert inc.priority == "REFERENCE" or "editorial relevance only" in be._tag(inc)
    text = "\n".join(be.morning_view(es))
    line = next(l for l in text.splitlines() if l.startswith("Operational situation:"))
    assert "no confirmed" in line
    assert "20,000" not in text[text.index("What matters today"):text.index(IMPACT_H)]


def test_an_au_geography_incident_is_not_editorial_only():
    es = be.build_evidence([ev("a", LONDON, "ABC News", geo="AU")], now=NOW, window_hours=72)
    assert "editorial relevance only" not in be._tag(es.incidents[0])


def test_a_gb_incident_naming_an_australian_operator_is_not_editorial_only():
    es = be.build_evidence([ev("a", "Telstra outage leaves 20,000 customers without service", "ABC News", geo="GB")],
                           now=NOW, window_hours=72)
    assert "editorial relevance only" not in be._tag(es.incidents[0])


def test_no_recent_incidents_is_insufficient_coverage_not_all_quiet():
    _, lines = None, be.morning_view(be.build_evidence([], now=NOW, window_hours=72))
    assert lines[0].startswith("⚠️ EVIDENCE COVERAGE INSUFFICIENT")
    sit = next(l for l in lines if l.startswith("Operational situation:"))
    assert "insufficient" in sit and "no confirmed" not in sit


def test_recent_incidents_have_no_coverage_marker():
    _, text = view([ev("a", COLES, "ABC News")])
    assert "EVIDENCE COVERAGE INSUFFICIENT" not in text


def test_general_news_at_reference_priority_is_not_published_as_editorial_relevance():
    """Integration finding: the derived editorial-only rule must not surface never-actionable REFERENCE news (election results, court
    cases) in the source-quality section or Forward Watch."""
    es = be.build_evidence([ev("a", "Democrats clinch their largest House majority since 1992", "ABC News", geo="GLOBAL")], now=NOW, window_hours=72)
    inc = es.incidents[0]
    assert inc.priority == "REFERENCE"
    assert "editorial relevance only" not in be._tag(inc)
    text = "\n".join(be.morning_view(es))
    assert "Democrats clinch" not in text


# ── relevance routing is outlet-independent and defers to #677's verdict when present ──────────────────────────────────

import pytest

from intelligence import event_detection as _ed

HAS_677 = hasattr(_ed, "australian_relevance")
LONDON_STATED = "Power outage leaves 20,000 customers in London without electricity"
AWS = "Global outage on AWS leaves millions of users offline"


def _classify(title, source, geo="GB"):
    es = be.build_evidence([ev("a", title, source, geo=geo)], now=NOW, window_hours=72)
    inc = es.incidents[0]
    text = "\n".join(be.morning_view(es))
    sit = next(l for l in text.splitlines() if l.startswith("Operational situation:"))
    fw = text[text.index("Forward watch"):]
    return inc, be._editorial_only(inc), be._tag(inc), sit, fw, inc.priority


@pytest.mark.parametrize("title", [LONDON_STATED, AWS])
def test_same_foreign_incident_is_classified_identically_whichever_outlet_reports_it(title):
    a = _classify(title, "ABC News")
    b = _classify(title, "BBC News")
    assert a[1] == b[1]                                   # editorial classification
    assert a[2] == b[2]                                   # tag
    assert a[3] == b[3]                                   # disruption count line
    assert a[4].replace("ABC News", "X") == b[4].replace("BBC News", "X")   # Forward Watch treatment
    assert a[5] == b[5]


def test_a_foreign_incident_with_no_au_link_is_editorial_only_for_any_outlet_without_upstream_verdict():
    for outlet in ("ABC News", "BBC News", "Reuters"):
        es = be.build_evidence([ev("a", LONDON_STATED, outlet, geo="GB")], now=NOW, window_hours=72)
        inc = es.incidents[0]
        if be._upstream_verdict(inc) is None and inc.priority != "REFERENCE":
            assert be._editorial_only(inc), outlet


def test_a_plausible_dependency_keeps_its_caveat_and_is_not_editorial_only():
    inc, editorial, tag, *_ = _classify(AWS, "BBC News")
    if inc.priority == "REFERENCE":
        pytest.skip("hidden as reference")
    assert not editorial
    assert "plausible dependency; Australian impact not established" in tag


@pytest.mark.skipif(not HAS_677, reason="needs #677 relevance gate")
def test_upstream_reasons_drive_the_classification_when_present():
    es = be.build_evidence([ev("a", AWS, "BBC News", geo="GB")], now=NOW, window_hours=72)
    inc = es.incidents[0]
    assert be._upstream_verdict(inc) == "plausible"
    inc.reasons = ["Australian-audience outlet only: editorial relevance, Australian operational impact not established (capped at WATCH)"]
    assert be._editorial_only(inc)


def test_upstream_verdict_is_read_from_reasons():
    es = be.build_evidence([ev("a", AWS, "BBC News", geo="GB")], now=NOW, window_hours=72)
    inc = es.incidents[0]
    inc.priority = "VERIFY"
    inc.reasons = ["Australian relevance: plausible dependency on AWS (Australian impact not established)"]
    assert not be._editorial_only(inc) and "plausible dependency; Australian impact not established" in be._tag(inc)
    inc.reasons = ["Australian relevance: australian geography"]
    assert not be._editorial_only(inc) and "plausible dependency" not in be._tag(inc)
    inc.reasons = ["no demonstrated Australian relevance or dependency: kept as reference"]
    assert not be._editorial_only(inc)
    inc.reasons = ["Australian-audience outlet only: editorial relevance"]
    assert be._editorial_only(inc)
