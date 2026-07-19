"""Opportunity Detection — USS-TJR-MSN-0096 WP3.

Advisors surface opportunities, not only risks:

    * stalled work            (open loops worth restarting)
    * emerging themes          (improving trajectories / reinforced lessons)
    * reusable solutions       (high-success lessons to apply again)
    * strategic opportunities  (topics with strong historical success)

Reuse-only: patterns.py, signals.py, learning.py. Informational.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import patterns as _patterns
import signals as _signals
import learning as _learning


@dataclass
class Opportunity:
    opportunity_type: str
    message: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_opportunities() -> list[Opportunity]:
    out: list[Opportunity] = []
    pats = _patterns.detect_patterns()
    sigs = _signals.emerging_signals()

    # stalled work — open loops are an opportunity to close and learn
    for p in pats:
        if p.pattern_type == "open_loops":
            out.append(Opportunity(
                "stalled_work",
                f"{p.frequency} advisory loop(s) are open — closing them improves learning signal.",
                p.evidence,
            ))

    # emerging themes — improving trajectories
    for s in sigs:
        if s.direction == "improving":
            out.append(Opportunity(
                "emerging_theme",
                f"{s.name} is improving — momentum worth reinforcing.",
                s.evidence,
            ))

    # reusable solutions — lessons that correlate with good outcomes
    reinforcement = _learning.lesson_reinforcement()
    reusable = [(lid, d) for lid, d in reinforcement.items() if d.get("signal") == "reinforce"]
    reusable.sort(key=lambda x: x[1].get("success_rate", 0), reverse=True)
    for lid, d in reusable[:3]:
        out.append(Opportunity(
            "reusable_solution",
            f"Lesson {lid} has a strong track record "
            f"({int(d.get('success_rate', 0)*100)}% across {d.get('appearances')} uses) — reapply it.",
            [lid],
        ))

    # strong advisor outcomes are a strategic opportunity to lean on
    strong = [p for p in pats if p.pattern_type == "advisor_outcome" and p.signal == "reinforce"]
    for p in strong[:2]:
        out.append(Opportunity("strategic_opportunity", p.description, p.evidence))

    return out


def to_markdown(opps: list[Opportunity] | None = None) -> str:
    opps = detect_opportunities() if opps is None else opps
    if not opps:
        return "No opportunities surfaced yet (insufficient history)."
    L = ["# Opportunities", ""]
    for o in opps:
        L.append(f"- 💡 **{o.opportunity_type}**: {o.message}")
    return "\n".join(L)
