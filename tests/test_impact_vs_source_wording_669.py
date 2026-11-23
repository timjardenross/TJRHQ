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


def sections(text):
    a = text.index(IMPACT_H)
    b = text.index(SOURCE_H)
    c = text.index("WARNINGS AND FORECASTS")
    return text[a:b], text[b:c]


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
