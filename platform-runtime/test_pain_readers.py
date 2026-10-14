"""Phase 2 step 1: pain readers label new data, label old numeric as history,
and never present a missing value as zero / 'no pain'."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence.captains_brief import _format_capacity_block  # noqa: E402
from platform_runtime.commands.health_appointment_prep import _generate_prep_brief  # noqa: E402

APPT = {"event_date": "2026-10-20", "title": "Review"}


def _brief(summary):
    return _generate_prep_brief(APPT, summary, [], [])


def _block(**cap):
    return "\n".join(_format_capacity_block({"has_checked_in": True, "latest_capacity_state": "green", **cap}))


def test_captains_brief_labels_new_pain_state():
    assert "Pain vs usual: Higher than usual" in _block(latest_pain_state="elevated")


def test_captains_brief_labels_old_numeric_as_history():
    text = _block(latest_pain_score=6)
    assert "older 0-10 record" in text and "6/10" in text


def test_captains_brief_shows_nothing_when_pain_missing():
    text = _block()
    assert "Pain" not in text and "0/10" not in text


def test_prep_brief_uses_baseline_wording_for_check_ins():
    text = _brief({"days_logged": 5, "pain_state_counts": {"baseline": 3, "elevated": 1}})
    assert "Pain compared with your usual baseline: 3 around usual, 1 higher than usual" in text


def test_prep_brief_labels_numeric_as_older_records():
    text = _brief({"days_logged": 5, "avg_pain": 6.5, "max_pain": 8, "pain_state_counts": {}})
    assert "Pain (older 0-10 records): average 6.5/10" in text


def test_prep_brief_missing_pain_is_not_reported_as_zero():
    text = _brief({"days_logged": 5, "pain_state_counts": {}})
    assert "Pain" not in text and "0/10" not in text
