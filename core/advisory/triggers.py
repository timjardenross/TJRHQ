"""Advisory Triggers — USS-TJR-MSN-0096 WP1.

Decides when advisors should *speak unprompted* by reading existing signals:

    * health deterioration   * mission delay / open loops
    * confidence decline     * repeated blockers
    * dependency risks       * capacity overload

Each trigger is INFORMATIONAL and carries an escalation level (escalation.py).
Reuse-only: signals.py, patterns.py, calibration.py. No new memory, no action.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import signals as _signals
from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_patterns = _import_sibling("patterns")
_escalation = _import_sibling("escalation")


@dataclass
class Trigger:
    trigger_type: str
    level: str                   # observation | warning | concern | escalation
    message: str
    source: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_triggers() -> list[Trigger]:
    """Return all active advisory triggers, strongest first."""
    triggers: list[Trigger] = []
    sigs = _signals.emerging_signals()
    pats = _patterns.detect_patterns()

    # confidence decline
    for s in sigs:
        if s.name == "advisory_confidence" and s.direction == "worsening":
            lvl = _escalation.classify("concern", frequency=2)
            triggers.append(Trigger("confidence_decline", lvl.level,
                                    "Advisory confidence is declining.", "signals", s.evidence))
        if s.name == "recommendation_success" and s.direction == "worsening":
            lvl = _escalation.classify("concern", frequency=2)
            triggers.append(Trigger("outcome_decline", lvl.level,
                                    "Recommendation success rate is declining.", "signals"))
        if s.name == "escalation_risk" and s.direction == "increasing":
            lvl = _escalation.classify("concern", frequency=3)
            triggers.append(Trigger("dependency_risk", lvl.level,
                                    "Decision-escalation frequency is rising.", "signals", s.evidence))

    # repeated blockers
    blockers = [p for p in pats if p.pattern_type == "recurring_risk"]
    for p in blockers[:3]:
        lvl = _escalation.classify("concern" if p.signal == "caution" else "watch", frequency=p.frequency)
        triggers.append(Trigger("repeated_blocker", lvl.level, p.description, "patterns", p.evidence))

    # mission delay / open loops
    for p in pats:
        if p.pattern_type == "open_loops":
            lvl = _escalation.classify("watch", frequency=p.frequency)
            triggers.append(Trigger("mission_delay", lvl.level,
                                    p.description, "patterns", p.evidence))

    # capacity overload — many open loops at once
    open_loops = next((p for p in pats if p.pattern_type == "open_loops"), None)
    if open_loops and open_loops.frequency >= 6:
        lvl = _escalation.classify("concern", frequency=open_loops.frequency)
        triggers.append(Trigger("capacity_overload", lvl.level,
                                f"{open_loops.frequency} open advisory loops — possible overload.",
                                "patterns"))

    # health deterioration — wired; fires when health series exist (Supabase).
    for s in sigs:
        if s.name.startswith("health") and s.direction in ("worsening", "increasing"):
            lvl = _escalation.classify("critical", frequency=3)
            triggers.append(Trigger("health_deterioration", lvl.level, s.detail, "signals"))

    triggers.sort(key=lambda t: _escalation.rank(t.level), reverse=True)
    return triggers


def to_markdown(triggers: list[Trigger] | None = None) -> str:
    triggers = evaluate_triggers() if triggers is None else triggers
    if not triggers:
        return "No advisory triggers active — nothing warrants the Captain's attention right now."
    icon = {"escalation": "🔴", "concern": "🟠", "warning": "🟡", "observation": "⚪"}
    L = ["# Advisory Triggers", ""]
    for t in triggers:
        L.append(f"- {icon.get(t.level, '•')} **{t.trigger_type}** ({t.level}): {t.message}")
    L.append("\n_Informational only — Captain decides. No action taken._")
    return "\n".join(L)
