"""Provisional "good day" rule (agreed 2026-11-02).

A day is a likely good day when it stayed the same or improved, no capacity was borrowed from
tomorrow, and the whole-day compensation was moderate or lower. A missing answer is unknown and
is never counted against the day. The Captain's own "Was today a good day?" answer, when given,
always wins over the rule. Pure function: nothing is stored, so recalibrating needs no migration.
"""

from __future__ import annotations

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
    if evening.get("capacity_debt") is not None:
        checks.append(evening["capacity_debt"] == "no")
    if evening.get("day_compensation_load") is not None:
        checks.append(evening["day_compensation_load"] in _COMP_OK)

    if not checks:
        return None
    return all(checks)
