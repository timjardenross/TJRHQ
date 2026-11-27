"""27 November 2026 production defect: a suspended NSW rail strike shown beside the disruption it had replaced. Public headlines."""
from datetime import datetime, timedelta, timezone

import pytest

from intelligence import eod_assessment as ea

EVENING = datetime(2026, 11, 27, 7, 0, tzinfo=timezone.utc)          # 18:00 Melbourne
MORNING = EVENING - timedelta(hours=11)
ABC = "https://www.abc.net.au/news/2026-11-"
SUSPENDED = "NSW train strike suspended after Fair Work Commission hearing"
PLANNED_A = "NSW regional and interstate trains could be offline for a week from Friday"
PLANNED_B = "Train services to be disrupted after Fair Work Commission delays decision"
SUSPENDED_SLUG = ABC + "26/nsw-passenger-trains-strike-suspended-after-fair-work-hearing/107428948"


def event(i, title, when, url, summary=""):
    return {"id": f"{i}0000000-0000-4000-8000-000000000000", "title": title, "summary": summary, "source": "ABC News", "geography": "AU",
            "published_at": when.isoformat(), "collected_at": when.isoformat(), "url": url}


A = event(1, PLANNED_A, datetime(2026, 11, 25, 7, 47, tzinfo=timezone.utc), ABC + "25/train-disruptions-nsw-strike-planned/107425948")
B = event(2, PLANNED_B, datetime(2026, 11, 26, 8, 17, tzinfo=timezone.utc),
          ABC + "26/nsw-passenger-trains-disrupted-fair-work-delays-decision/107428948",
          "Many NSW regional and interstate passenger train services are to be cancelled or replaced by coaches after the ruling on "
          "industrial action is delayed.")
S = event(9, SUSPENDED, EVENING - timedelta(hours=4), SUSPENDED_SLUG,
          "The Fair Work Commission has suspended industrial action on the NSW rail network; passenger train services are to resume.")


def text(sections):
    return "\n".join(x for h, body in sections for x in (h, *body))


def morning_row(events):
    return {"brief_text": text(ea.assess_morning(events, None, now=MORNING)), "generated_at": MORNING.isoformat()}


def assert_reconciled(out):
    assert "action suspended" in out or "reported suspended or called off" in out
    assert "announced, not started" not in out and "Announced disruption" not in out and "announced and not yet started" not in out
    assert "actual service disruption" not in out
    for line in out.splitlines():                          # earlier notices appear only when labelled as replaced
        if PLANNED_A in line or PLANNED_B in line:
            assert "Replaces earlier notice" in line, line


def test_evening_after_the_morning_carried_the_disruption():
    sections = dict(ea.assess([A, B, S], morning_row([A, B]), now=EVENING))
    out = text(sections.items())
    assert_reconciled(out)
    bottom = "\n".join(sections["1. EXECUTIVE BOTTOM LINE"])
    assert f"Most decision-relevant: {SUSPENDED}" in bottom and "confirm with the operator" in bottom.lower()
    watch = sections["7. OVERNIGHT WATCH"]
    assert [w for w in watch if "train" in w.lower()] == [w for w in watch if w.startswith("- Resumption:")]
    assert "escalating" not in bottom and "not otherwise covered" not in bottom


@pytest.mark.parametrize("events", [[A, B, S], [A, S], [S, B, A]])
def test_morning_shows_one_current_story(events):
    assert_reconciled(text(ea.assess_morning(events, None, now=EVENING)))


def test_article_rewritten_in_place_with_a_stale_title():
    rewritten = {**B, "url": SUSPENDED_SLUG}
    out = text(ea.assess_morning([A, rewritten], None, now=EVENING))
    assert_reconciled(out)
    assert "- Industrial action behind an announced disruption reported suspended (action suspended;" in out


def test_next_brief_reads_the_new_status():
    row = {"brief_text": text(ea.assess_morning([A, B, S], None, now=EVENING)), "generated_at": EVENING.isoformat()}
    assert [state for _, state in ea.parse_morning(row).entries.values()] == ["action suspended"]


@pytest.mark.parametrize("title", [
    "NSW train strike could be suspended after Fair Work Commission hearing",
    "ARTC asks commission to have NSW train strike suspended",
    "NSW trains suspended as strike begins",
    "Victoria train strike suspended after Fair Work Commission hearing",
])
def test_hedged_different_or_unrelated_reports_replace_nothing(title):
    other = {**S, "title": title, "summary": title, "url": ABC + "27/story/107430000"}
    out = text(ea.assess_morning([B, other], None, now=EVENING))
    assert PLANNED_B in out and "announced, not started" in out and "Replaces earlier notice" not in out


def test_a_later_announcement_is_not_closed_by_an_older_suspension():
    later = event(3, "NSW regional trains could be offline from Monday under a new rail strike", EVENING - timedelta(hours=1),
                  ABC + "27/new-strike-nsw/107431000")
    out = text(ea.assess_morning([S, later], None, now=EVENING))
    assert "announced, not started" in out and "Replaces earlier notice" not in out
