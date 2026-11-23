"""#669 audit 3 — one organisation under two names is one publisher; an aggregator re-post of an outlet's story is not corroboration."""
from datetime import datetime, timezone

from intelligence import brief_evidence as be
from intelligence import weekly_evidence as we

NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)


def _ev(i, title, source, summary="", hours=3):
    return {"id": f"ev-{i}", "title": title, "summary": summary, "source": source, "geography": "AU",
            "collected_at": f"2026-11-22T{21 - hours // 2:02d}:{10 + i:02d}:00+00:00", "url": f"https://example.org/{i}"}


T1 = "Live: Power still out after SA transmission line downed"
T2 = "Transmission towers crushed, knocking out power to 20,000 in South Australia"
SUM = "20,000 customers without power after transmission towers were crushed in a storm in South Australia."


def test_alias_names_resolve_to_one_family():
    assert we.publisher_family("Google News - Telstra", T2 + " - Australian Broadcasting Corporation") == we.publisher_family("ABC News", T1)
    assert we.publisher_family("ABC News Business", "x") == we.publisher_family("ABC News", "x")
    assert we.publisher_family("Guardian Australia", "x") == we.publisher_family("Google News - x", "t - The Guardian")


def test_unrelated_publishers_stay_distinct():
    assert we.publisher_family("ABC News", "x") != we.publisher_family("Guardian Australia", "x")
    assert we.publisher_family("Google News - x", "t - Some Other Paper") == "some other paper"


def test_aggregator_repost_of_same_outlet_is_not_corroboration():
    events = [_ev(1, T1, "ABC News", SUM), _ev(2, T2 + " - Australian Broadcasting Corporation", "Google News - Telstra", SUM)]
    es = be.build_evidence(events, now=NOW, window_hours=72)
    grouped = [i for i in es.incidents if len(i.reports) >= 2]
    assert grouped, "the two reports should form one incident"
    assert all(i.evidence_status != "corroborated" for i in grouped)


def test_genuinely_independent_publisher_still_corroborates():
    events = [_ev(1, T1, "ABC News", SUM), _ev(2, T2 + " - InDaily", "Google News - Telstra", SUM),
              _ev(3, "Transmission towers crushed, 20,000 without power in South Australia", "ITnews", SUM)]
    es = be.build_evidence(events, now=NOW, window_hours=72)
    assert any(i.evidence_status == "corroborated" for i in es.incidents)
