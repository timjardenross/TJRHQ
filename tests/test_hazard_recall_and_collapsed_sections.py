"""Morning V1 follow-up (live brief of Tue 24 Nov 2026).

1. Hazard recall: a hazard warning stated only in the summary's first sentence ('The weather bureau is warning of severe storms west of
   Charleville') under a headline with no hazard term, and a 'quake' headline ('Top End shaken as major quake hits East Timor'), were missed
   because hazards were read from the headline only and 'quake' was not a hazard word.
2. Empty sections are collapsed into one 'Nothing to report in:' line instead of a heading and a 'None' each.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intelligence import brief_evidence as be
from intelligence import event_detection as ed

NOW = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)


def ev(i, title, summary="", source="ABC News", geo="AU", hours=5):
    t = (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": i, "title": title, "summary": summary, "source": source, "geography": geo, "collected_at": t, "published_at": t, "url": f"https://x/{i}"}


def decision(event):
    return ed.run([event], now=NOW)[0]


QLD = ("Storms to hit south-western Qld as heatwave lingers in far north",
       "The weather bureau is warning of severe storms west of Charleville, while the south-east could see storms returning later in the week.")
TIMOR = ("Top End shaken as major quake hits East Timor",
         "Northern Territory residents were rattled after a 6.8-magnitude earthquake struck north-east of Lospalos in East Timor on Saturday.")


# ── 1. hazard recall ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_storm_warning_stated_only_in_the_summary_is_a_hazard_warning():
    d = decision(ev("a", *QLD))
    assert "hazard" in d.group.members[0].types
    assert d.priority == "WATCH" and d.impact_status == "warning"            # a warning, never a stated outage


def test_quake_in_a_headline_is_a_hazard():
    d = decision(ev("a", TIMOR[0], ""))
    assert "hazard" in d.group.members[0].types and d.priority == "WATCH"


def test_the_summary_storm_warning_reaches_the_morning_view():
    es = be.build_evidence([ev("a", *QLD)], now=NOW, window_hours=72)
    text = "\n".join(be.morning_view(es))
    assert "Storms to hit south-western Qld" in text.split("WARNINGS AND FORECASTS")[1].split("\n\n")[0]
    assert "Operational situation: no confirmed" in text                       # still not counted as a disruption


def test_hazard_recall_controls_stay_quiet():
    peru = decision(ev("p", "Peru Rattled by 6.7-Magnitude Quake, With No Casualties Reported",
                       "Peru was shaken by a powerful earthquake late Friday that damaged some houses.", "Bloomberg", "GLOBAL"))
    assert peru.priority == "REFERENCE"                                          # foreign: the Australian-relevance gate still hides it
    colombia = decision(ev("c", "Colombia’s Economy Slowed More Than Expected in Third Quarter",
                           "Colombia’s economy grew less than expected in the third quarter as a devastating earthquake in the eastern part of the country hit output.",
                           "Bloomberg", "GLOBAL"))
    assert "hazard" not in colombia.group.members[0].types                       # a business story that mentions an earthquake
    insurers = decision(ev("i", "Insurers brace for claims", "Insurers expect payouts after last summer's bushfires."))
    assert "hazard" not in insurers.group.members[0].types
    plain = decision(ev("s", "Some unrelated sports story", "The storm of criticism over the coach continues."))
    assert "hazard" not in plain.group.members[0].types


def test_a_headline_hazard_is_unchanged():
    d = decision(ev("w", "Severe storm warning for south-west Queensland", "The weather bureau warns of damaging winds."))
    assert "hazard" in d.group.members[0].types and d.impact_status == "warning"


# ── 2. empty sections collapse ─────────────────────────────────────────────────────────────────────────────────
def test_a_quiet_day_collapses_every_empty_section_into_one_line():
    es = be.build_evidence([ev("a", "Some unrelated sports story")], now=NOW, window_hours=72)
    text = "\n".join(be.morning_view(es))
    assert "- None." not in text and "No active warning or forecast notice" not in text
    nothing = [l for l in text.splitlines() if l.startswith("Nothing to report in:")]
    assert len(nothing) == 1
    for name in ("reported by one source", "impact not yet established", "retrospective reports", "source not yet verified",
                 "warnings and forecasts", "emerging exposure", "operational implications", "forward watch"):
        assert name in nothing[0]
    assert "What matters today" in text and "None officially confirmed or corroborated" in text      # the primary answer stays explicit


def test_only_populated_sections_keep_their_heading():
    es = be.build_evidence([ev("a", *QLD)], now=NOW, window_hours=72)
    text = "\n".join(be.morning_view(es))
    nothing = next(l for l in text.splitlines() if l.startswith("Nothing to report in:"))
    assert "warnings and forecasts" not in nothing and "forward watch" not in nothing
    assert "warnings and forecasts" not in nothing and "WARNINGS AND FORECASTS" in text
