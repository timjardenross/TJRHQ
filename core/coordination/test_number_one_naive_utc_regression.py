"""Mission 1 (USS-TJR-MSN-1) fix: number-one-exporter.service was silently
failing every cycle ("Failed to export brief: can't subtract offset-naive
and offset-aware datetimes" -- confirmed live in its journal, daily_brief.json
stayed 6 days stale while its 7 sibling exports kept succeeding).

Root cause: NumberOne.current_time was tz-aware (datetime.now(timezone.utc))
while Mission.created_at/last_updated default to naive (datetime.utcnow),
and _parse_iso_datetime()'s two return paths disagreed with each other too
(naive when a string parses, aware on its None/error fallback) -- so any
real mission with a valid `updated_at`/`last_updated` ISO string produced a
naive Mission.last_updated that couldn't be subtracted from the aware
current_time in get_daily_brief()'s / follow-up detection's `(self.
current_time - mission.last_updated).days` age computations.

pytest-only regression (existing core/coordination/test_number_one.py is a
manual `python3 test_number_one.py` script whose create_test_mission()
fixture builds last_updated as a live tz-aware datetime object directly,
never exercising the from_registry()/_parse_iso_datetime() string-parsing
path that actually broke in production)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # number_one.py's own package dir, matches its sibling test's import style

from number_one import CoordinationConfig, Mission, NumberOne


def _registry_mission(mission_id: str, updated_at_iso: str, **overrides) -> dict:
    """Shape matches what Mission.from_registry() actually receives from the
    live Mission Registry/Command Memory JSON -- an ISO 8601 string, not a
    datetime object."""
    row = {
        "mission_id": mission_id,
        "title": f"Mission {mission_id}",
        "status": "Active",
        "priority": "P1",
        "updated_at": updated_at_iso,
        "created_at": updated_at_iso,
    }
    row.update(overrides)
    return row


class TestNaiveUtcRegression:
    def test_from_registry_produces_naive_datetimes(self):
        mission = Mission.from_registry(_registry_mission("MSN-0001", "2026-09-13T00:00:00Z"))
        assert mission.last_updated.tzinfo is None
        assert mission.created_at.tzinfo is None

    def test_from_registry_missing_updated_at_also_naive(self):
        row = _registry_mission("MSN-0002", "2026-09-13T00:00:00Z")
        del row["updated_at"]
        del row["created_at"]
        mission = Mission.from_registry(row)
        assert mission.last_updated.tzinfo is None

    def test_get_daily_brief_does_not_raise_with_real_iso_timestamps(self):
        """The exact production crash: a mission with a real, valid,
        several-days-old ISO updated_at -- must not raise TypeError."""
        engine = NumberOne(CoordinationConfig())
        missions = [_registry_mission("MSN-0003", "2026-09-13T00:00:00Z")]
        brief = engine.get_daily_brief(missions)  # would raise pre-fix
        assert brief.total_missions == 1

    def test_get_daily_brief_handles_mixed_present_and_missing_timestamps(self):
        """Mixed batch -- one mission with a real string, one relying on
        the None/error fallback -- both fallback paths must agree with
        current_time's naive-ness too."""
        engine = NumberOne(CoordinationConfig())
        row_with_ts = _registry_mission("MSN-0004", "2026-09-01T00:00:00Z")
        row_without_ts = _registry_mission("MSN-0005", "2026-09-13T00:00:00Z")
        del row_without_ts["updated_at"]
        del row_without_ts["created_at"]
        brief = engine.get_daily_brief([row_with_ts, row_without_ts])  # would raise pre-fix
        assert brief.total_missions == 2

    def test_current_time_is_naive(self):
        engine = NumberOne(CoordinationConfig())
        assert engine.current_time.tzinfo is None
