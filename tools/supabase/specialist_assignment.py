#!/usr/bin/env python3
"""Specialist Assignment Framework for USS-TJR-MSN-0010 D5.

Maps mission types (derived from decision_mode and question signals) to a
lead specialist and supporting specialists drawn from the USS TJR crew.

This module is used by mission_candidate.py to populate the ownership
recommendation in every mission package.

Usage:
    from specialist_assignment import assign_specialists, MissionAssignment
    assignment = assign_specialists(decision_record)
    print(assignment.lead)           # "Chief Engineer"
    print(assignment.supporting)     # ["Coder Agent", "QA & Test Officer"]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Crew roster (derived from registry/Crew-Manifest.md)
# ---------------------------------------------------------------------------

CREW = {
    "Chief of Staff",
    "Chief Engineer",
    "Coder Agent",
    "Knowledge Officer",
    "QA & Test Officer",
    "Medical Officer",
    "Research Officer",       # future crew — may not yet be active
    "UX Design Officer",
    "Operations Officer",     # future crew
}

# ---------------------------------------------------------------------------
# Mission type → specialist mapping
# ---------------------------------------------------------------------------

# Keyed by (decision_mode, domain_signal). First match wins.
# domain_signal is a substring checked against the question (lowercased).
_DOMAIN_ASSIGNMENTS: list[tuple[str | None, str, str, list[str]]] = [
    # (decision_mode, question_signal, lead, supporting)

    # Governance always goes to Chief of Staff
    ("governance",     "",                  "Chief of Staff",   ["Chief Engineer"]),

    # Architecture / infrastructure
    ("architectural",  "",                  "Chief Engineer",   ["Coder Agent", "Knowledge Officer"]),

    # Strategic — broken down by domain signals
    ("strategic",      "slack",             "Chief Engineer",   ["Chief of Staff", "Coder Agent"]),
    ("strategic",      "voice core",        "Chief Engineer",   ["Chief of Staff"]),
    ("strategic",      "notion",            "Knowledge Officer",["Chief of Staff", "UX Design Officer"]),
    ("strategic",      "knowledge",         "Knowledge Officer",["Chief of Staff"]),
    ("strategic",      "ux",                "UX Design Officer",["Chief Engineer"]),
    ("strategic",      "experience",        "UX Design Officer",["Chief Engineer"]),
    ("strategic",      "mission",           "Chief of Staff",   ["Chief Engineer"]),
    ("strategic",      "roadmap",           "Chief of Staff",   ["Chief Engineer"]),
    ("strategic",      "automation",        "Coder Agent",      ["Chief Engineer", "QA & Test Officer"]),
    ("strategic",      "testing",           "QA & Test Officer",["Coder Agent"]),
    ("strategic",      "research",          "Research Officer", ["Knowledge Officer"]),
    ("strategic",      "",                  "Chief of Staff",   ["Chief Engineer"]),  # fallback

    # Operational — execution-focused
    ("operational",    "architecture",      "Chief Engineer",   ["Coder Agent"]),
    ("operational",    "implement",         "Coder Agent",      ["Chief Engineer", "QA & Test Officer"]),
    ("operational",    "deploy",            "Coder Agent",      ["Chief Engineer"]),
    ("operational",    "test",              "QA & Test Officer",["Coder Agent"]),
    ("operational",    "knowledge",         "Knowledge Officer",["Chief of Staff"]),
    ("operational",    "notion",            "Knowledge Officer",["UX Design Officer"]),
    ("operational",    "",                  "Chief Engineer",   ["Coder Agent"]),     # fallback
]


@dataclass(frozen=True)
class MissionAssignment:
    lead: str
    supporting: list[str]
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "lead_specialist": self.lead,
            "supporting_specialists": self.supporting,
            "assignment_rationale": self.rationale,
        }


def assign_specialists(
    decision_record: dict[str, Any],
) -> MissionAssignment:
    """Recommend a lead specialist and supporting crew for a decision-derived mission.

    Uses decision_mode + question signals to find the best match.
    Falls back to Chief of Staff + Chief Engineer if nothing matches.
    """
    mode = (decision_record.get("decision_mode") or "strategic").lower()
    question = (decision_record.get("question") or "").lower()

    for rule_mode, signal, lead, supporting in _DOMAIN_ASSIGNMENTS:
        if rule_mode is not None and rule_mode != mode:
            continue
        if signal and signal not in question:
            continue
        rationale = _rationale(mode, signal, lead)
        # Filter supporting to crew members that exist; keep order
        active_supporting = [s for s in supporting if s in CREW]
        return MissionAssignment(lead=lead, supporting=active_supporting, rationale=rationale)

    # Hard fallback
    return MissionAssignment(
        lead="Chief of Staff",
        supporting=["Chief Engineer"],
        rationale="No specific domain signal detected. Default ownership assigned to Chief of Staff.",
    )


def _rationale(mode: str, signal: str, lead: str) -> str:
    if mode == "governance":
        return f"Governance decisions are owned by {lead} with authority over assignment and approval."
    if mode == "architectural":
        return f"Architectural decisions are led by {lead} who owns system design and component placement."
    if signal:
        return f"Domain signal '{signal}' detected in question. {lead} owns this domain."
    return f"{lead} is the default lead for {mode} decisions without a specific domain signal."
