"""'blackout period' (a financial/regulatory restriction) is not a power blackout (24 Nov preview defect)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import event_detection as ed


def _ev(i, title, source="ABC News"):
    return {"id": i, "title": title, "summary": "", "source": source, "geography": "AU",
            "collected_at": "2026-11-23T23:18:00+00:00", "published_at": "2026-11-23T23:00:00+00:00", "url": f"https://x/{i}"}


def test_blackout_period_headline_is_not_an_outage_candidate():
    c = ed.detect_candidate(_ev("a", "Top Fed official probed over whether she breached ‘blackout period’"))
    assert "outage" not in c.types


def test_a_real_blackout_headline_is_unchanged():
    c = ed.detect_candidate(_ev("b", "Eyre Peninsula blackout leaves thousands without power"))
    assert "outage" in c.types


def test_the_idiom_does_not_join_a_real_blackout_incident():
    evs = [_ev("a", "Top Fed official probed over whether she breached ‘blackout period’", "Financial Times"),
           _ev("b", "Eyre Peninsula blackout leaves thousands without power"),
           _ev("c", "SA Power Networks restores power after Eyre Peninsula blackout")]
    decisions = ed.run(evs)
    joined = [d for d in decisions if any("blackout period" in (m.title or "") for m in d.group.members)]
    assert joined == [] or all(len(d.group.members) == 1 for d in joined)


def test_other_idioms_are_neutralised():
    for t in ("Media blackout imposed on the inquiry", "Trading blackout begins ahead of results", "Quiet period: earnings blackout dates announced"):
        assert "outage" not in ed.detect_candidate(_ev("x", t)).types
