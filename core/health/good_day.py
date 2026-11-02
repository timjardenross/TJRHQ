"""Provisional "good day" rule (agreed 2026-11-02, revised 2026-11-03).

A day is a likely good day when it stayed the same or improved and the whole-day compensation was
moderate or lower. A missing answer is unknown and is never counted against the day. The Captain's
own "Was today a good day?" answer, when given, always wins over the rule.

Borrowed capacity ("capacity_debt") is deliberately NOT part of the rule for now (Captain's call,
2026-11-03): it is still asked and stored, and still feeds the burnout trend and the day plan, but a
"maybe" or "yes" does not make a day not-good here.

Pure functions: nothing is stored, so recalibrating needs no migration.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

_COMP_OK = ("low", "moderate")


def provisional_good_day(evening: dict[str, Any] | None) -> bool | None:
    """True / False for a likely good / not-good day, or None when there's nothing to judge.

    ``evening`` is a capacity_checkins row with checkin_type='evening'.
    """
    if not evening:
        return None

    own = evening.get("good_day")
    if own == "yes":
        return True
    if own == "no":
        return False
    # "kind_of" and a missing answer fall through to the rule.

    checks: list[bool] = []
    if evening.get("day_trajectory") is not None:
        checks.append(evening["day_trajectory"] in ("same", "improved"))
    if evening.get("day_compensation_load") is not None:
        checks.append(evening["day_compensation_load"] in _COMP_OK)

    if not checks:
        return None
    return all(checks)


def summarize_good_days(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count good days over a window of capacity_checkins rows.

    Uses the latest evening row for each calendar date. ``judged`` is the number of days with a
    verdict, ``good`` how many of them were good, and ``longest_run`` the longest stretch of
    consecutive calendar days that were all good. A day with no evening answer, or no verdict, is
    unknown and ends a run (nothing is assumed about it).
    """
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("checkin_type") != "evening" or not row.get("log_date"):
            continue
        day = str(row["log_date"])[:10]
        prev = latest.get(day)
        if prev is None or str(row.get("captured_at") or "") >= str(prev.get("captured_at") or ""):
            latest[day] = row

    verdicts = {day: provisional_good_day(row) for day, row in latest.items()}
    judged_days = sorted(d for d, v in verdicts.items() if v is not None)
    good_days = [d for d in judged_days if verdicts[d]]

    longest = run = 0
    prev_day: date | None = None
    for d in good_days:
        cur = date.fromisoformat(d)
        run = run + 1 if prev_day is not None and cur - prev_day == timedelta(days=1) else 1
        longest = max(longest, run)
        prev_day = cur

    return {"judged": len(judged_days), "good": len(good_days), "longest_run": longest}
