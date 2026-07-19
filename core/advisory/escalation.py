"""Escalation Model — USS-TJR-MSN-0096 WP2.

A four-level ladder for advisory notifications. Advisory notifications remain
INFORMATIONAL — no level grants authority, triggers approvals, or takes action.

    observation  — noticed; no action implied
    warning      — worth a look in the daily brief
    concern      — should be reviewed soon
    escalation   — surface to the Captain promptly (still advisory)

False positives are minimised by requiring a minimum evidence count before any
level above 'observation' is assigned.
"""

from __future__ import annotations

from dataclasses import dataclass

LEVELS = ("observation", "warning", "concern", "escalation")
_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}

# Minimum supporting evidence before escalating past observation.
_MIN_EVIDENCE = 2


@dataclass(frozen=True)
class EscalationLevel:
    level: str
    rank: int

    def at_least(self, other: str) -> bool:
        return self.rank >= _RANK.get(other, 0)


def classify(severity: str, *, frequency: int = 1, confident: bool = True) -> EscalationLevel:
    """Map a severity + evidence count to an escalation level.

    severity: "info" | "watch" | "concern" (from signals), or a free label.
    frequency: how many times the condition was observed (evidence strength).
    confident: False forces a downgrade (uncertain → lower the cry-wolf risk).
    """
    base = {
        "info": "observation",
        "watch": "warning",
        "concern": "concern",
        "critical": "escalation",
    }.get((severity or "").lower(), "observation")

    # Frequency can promote a concern to an escalation.
    if base == "concern" and frequency >= 3:
        base = "escalation"

    # Cry-wolf guard: too little evidence caps the level at observation.
    if frequency < _MIN_EVIDENCE and base != "observation":
        base = "observation"

    if not confident and base != "observation":
        base = LEVELS[max(0, _RANK[base] - 1)]

    return EscalationLevel(level=base, rank=_RANK[base])


def rank(level: str) -> int:
    return _RANK.get(level, 0)
