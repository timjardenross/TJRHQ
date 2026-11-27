"""27 November 2026: stories left out for relevance came back through the list of morning items not otherwise covered."""
from datetime import datetime, timedelta, timezone

import pytest

from intelligence import eod_assessment as ea

EVENING = datetime(2026, 11, 27, 7, 0, tzinfo=timezone.utc)
MORNING = EVENING - timedelta(hours=11)
EXCLUDED = ["Teacher's licence suspended amid police investigation", "Cricket captain speaks about sandpapergate ban"]
KEPT = "Hospital outage under police investigation after nurse allegations"


def event(i, title):
    when = (MORNING - timedelta(hours=3)).isoformat()
    return {"id": f"{i}0000000-0000-4000-8000-000000000000", "title": title, "summary": title, "source": "ABC News", "geography": "AU",
            "published_at": when, "collected_at": when, "url": f"https://example{i}.com.au/story"}


def legacy_morning(events):
    """The earlier morning format listed these stories; the evening compares against whatever was actually delivered."""
    views, _ = ea._views(events, MORNING)
    lines = ["MONITORING"] + [f"- [WATCH] {v.headline} — status current status unknown; confidence reported [{v.incident_id}; "
                              f"1 report(s); evidence: ABC News #{v.report_ids[0][:8]}]" for v in views]
    return {"brief_text": "\n".join(lines), "generated_at": MORNING.isoformat()}


@pytest.mark.parametrize("title", EXCLUDED)
def test_excluded_story_does_not_return_through_carryover(title):
    events = [event(1, title)]
    row = legacy_morning(events)
    assert title in row["brief_text"]
    out = "\n".join(x for _, body in ea.assess(events, row, now=EVENING) for x in body)
    assert title not in out and "not otherwise covered" not in out


def test_an_ordinary_unmatched_morning_item_is_still_carried():
    events = [event(2, "Bank payments outage investigation continues")]
    row = legacy_morning(events)
    out = "\n".join(x for _, body in ea.assess([], row, now=EVENING) for x in body)
    assert "Not treated as resolved" in out and "Bank payments outage" in out
