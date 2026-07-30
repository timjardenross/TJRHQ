#!/usr/bin/env python3
"""Decision-to-Mission Conversion for USS-TJR-MSN-0010 D3.

Converts a strategic decision record into a structured mission candidate
and stores it in logs/missions/ — separate from decision records.

Every mission candidate includes:
    - Mission title and ID
    - Recommended action (from Commander)
    - Decision summary
    - Risks (from specialist and challenge review)
    - Success criteria
    - Suggested lead and supporting specialists (D5)
    - Status: Draft → Ready → Assigned → In Progress → Completed

Usage:
    from mission_candidate import create_mission_candidate, load_mission_candidates
    candidate = create_mission_candidate(decision_record)
    if candidate:
        print(candidate["mission_candidate_id"])

CLI:
    python3 tools/supabase/mission_candidate.py --decision-id DEC-...
    python3 tools/supabase/mission_candidate.py --list
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from specialist_assignment import assign_specialists


ROOT = Path(__file__).resolve().parents[2]
MISSION_DIR = ROOT / "logs/missions"

MISSION_STATUSES = (
    "Draft",          # Just generated — not yet reviewed
    "Ready",          # Captain approved — ready for assignment
    "Assigned",       # Specialist assigned and briefed
    "In Progress",    # Active implementation
    "Completed",      # Implementation done
    "Deferred",       # Explicitly deferred
    "Rejected",       # Captain rejected the mission
)


def create_mission_candidate(
    decision_record: dict[str, Any],
) -> dict[str, Any] | None:
    """Convert a strategic decision record into a mission candidate.

    Returns None if the decision is not strategic.
    Stores the candidate in logs/missions/ and returns the record.
    """
    if decision_record.get("decision_mode") != "strategic":
        return None

    MISSION_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S-%f")
    mission_candidate_id = f"MIS-{timestamp}-{uuid.uuid4().hex[:6]}"

    assignment = assign_specialists(decision_record)

    action = (
        decision_record.get("recommended_action")
        or decision_record.get("final_recommendation")
        or "See decision record."
    )
    if action.lower().startswith("recommended action:"):
        action = action[len("recommended action:"):].strip()

    title = _generate_title(decision_record, action)
    risks = _extract_risks(decision_record)
    success_criteria = _generate_success_criteria(decision_record, action)
    decision_summary = _generate_summary(decision_record)

    candidate: dict[str, Any] = {
        "mission_candidate_id": mission_candidate_id,
        "decision_id": decision_record.get("decision_id"),
        "collaboration_id": decision_record.get("collaboration_id"),
        "created_at": now.isoformat(),
        "status": "Draft",
        # Mission content
        "title": title,
        "recommended_action": action,
        "decision_summary": decision_summary,
        "risks": risks,
        "success_criteria": success_criteria,
        # Specialist ownership (D5)
        **assignment.as_dict(),
        # Decision context carried forward
        "question": decision_record.get("question"),
        "decision_mode": decision_record.get("decision_mode"),
        "current_bottleneck": decision_record.get("current_bottleneck"),
        "opportunity_cost": decision_record.get("opportunity_cost"),
        "time_to_value": decision_record.get("time_to_value"),
        "reversibility": decision_record.get("reversibility"),
        "strategic_alignment": decision_record.get("strategic_alignment"),
        "options": decision_record.get("options", []),
        # Captain fields
        "captain_notes": None,
        "assigned_specialist": None,
        "github_issue_url": None,   # set when a GitHub issue is created
    }

    path = MISSION_DIR / f"{timestamp}-mission.json"
    path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    return candidate


def load_mission_candidates(status: str | None = None) -> list[dict[str, Any]]:
    """Load all mission candidates, optionally filtered by status."""
    if not MISSION_DIR.exists():
        return []
    records = []
    for path in sorted(MISSION_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if status is None or record.get("status") == status:
                records.append(record)
        except Exception:  # noqa: BLE001
            continue
    return records


def update_mission_status(
    mission_candidate_id: str,
    status: str,
    assigned_specialist: str | None = None,
    captain_notes: str | None = None,
    github_issue_url: str | None = None,
) -> Path | None:
    """Update the status and optional fields of a mission candidate."""
    if status not in MISSION_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Must be one of: {MISSION_STATUSES}")
    path = _find_mission_path(mission_candidate_id)
    if path is None:
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    record["status"] = status
    if assigned_specialist is not None:
        record["assigned_specialist"] = assigned_specialist
    if captain_notes is not None:
        record["captain_notes"] = captain_notes
    if github_issue_url is not None:
        record["github_issue_url"] = github_issue_url
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def _find_mission_path(mission_candidate_id: str) -> Path | None:
    if not MISSION_DIR.exists():
        return None
    for path in MISSION_DIR.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("mission_candidate_id") == mission_candidate_id:
                return path
        except Exception:  # noqa: BLE001
            continue
    return None


# ---------------------------------------------------------------------------
# Content generation helpers
# ---------------------------------------------------------------------------

def _generate_title(record: dict[str, Any], action: str) -> str:
    """Produce a concise mission title from the action and question."""
    question = record.get("question", "")
    # Try to extract a subject from common strategic patterns
    lowered = question.lower()
    if "slack" in lowered:
        return "Implement Slack Runtime — USS TJR Crew Collaboration"
    if "voice core" in lowered:
        return "Implement Voice Core — USS TJR Conversational Runtime"
    if "notion" in lowered and "source of truth" in lowered:
        return "Clarify Notion Source-of-Truth Boundaries"
    if "notion" in lowered:
        return "Improve Notion Operational Visibility"
    if "msn-0009" in lowered or "decision intelligence" in lowered:
        return "Implement Commander Decision Intelligence Core"

    # Fallback: truncate the recommended action to a title
    title = action.split(".")[0].strip()
    if len(title) > 80:
        title = title[:77] + "..."
    return title


def _extract_risks(record: dict[str, Any]) -> list[str]:
    """Compile risks from specialist positions, reviewer, and decision frame."""
    risks: list[str] = []

    # From specialist positions
    positions = record.get("specialist_positions") or []
    for pos in positions:
        if pos.get("confidence") and int(pos["confidence"]) < 70:
            risks.append(
                f"Low confidence ({pos['confidence']}%) from {pos.get('specialist', 'specialist')} "
                f"— validate before execution."
            )

    # From opportunity cost
    opp = record.get("opportunity_cost")
    if opp:
        risks.append(f"Opportunity cost: {opp}")

    # From reversibility
    rev = record.get("reversibility")
    if rev:
        rev_lower = rev.lower()
        if "low" in rev_lower or "expensive" in rev_lower:
            risks.append(f"Low reversibility: {rev} — difficult to undo once committed.")

    # From reviewer position
    reviewer = record.get("reviewer_position")
    if reviewer and reviewer.get("escalation_required") == "True":
        risks.append(
            f"Escalation required per reviewer {reviewer.get('reviewer', 'reviewer')}: "
            f"{reviewer.get('recommendation_adjustment', 'see challenge review')}"
        )

    if not risks:
        risks.append("No specific risks identified from decision frame. Review specialist outputs before executing.")

    return risks


def _generate_success_criteria(record: dict[str, Any], action: str) -> list[str]:
    """Generate outcome-based success criteria from the decision frame."""
    criteria: list[str] = []
    ttv = record.get("time_to_value") or ""
    alignment = record.get("strategic_alignment") or ""
    options = record.get("options") or []

    # Primary criterion: chosen action is delivered
    criteria.append(f"Recommended action is implemented and validated: {action[:100]}.")

    # Time to value criterion
    if "short" in ttv.lower():
        criteria.append("Value is visible to Captain TJR within days, not weeks.")
    elif "medium" in ttv.lower():
        criteria.append("Value is visible and measurable within 2–4 weeks of implementation.")
    else:
        criteria.append("Time to value is defined and tracked against the forecast.")

    # Bottleneck criterion
    bottleneck = record.get("current_bottleneck")
    if bottleneck:
        criteria.append(f"The identified bottleneck is resolved: {bottleneck[:120]}.")

    # Opportunity cost is acknowledged
    if len(options) >= 2:
        criteria.append(
            f"The deferred option ({options[1].get('description', 'Option B')}) "
            f"is explicitly scheduled for future review."
        )

    # Strategic alignment
    if "high" in alignment.lower():
        criteria.append("Decision outcome demonstrably advances current USS TJR strategic objectives.")

    return criteria


def _generate_summary(record: dict[str, Any]) -> str:
    """Generate a one-paragraph decision summary."""
    question = record.get("question", "No question recorded.")
    bottleneck = record.get("current_bottleneck", "Not specified.")
    alignment = record.get("strategic_alignment", "Not assessed.")
    return (
        f"Commander TJR made a strategic decision in response to: '{question}'. "
        f"The identified bottleneck was: {bottleneck}. "
        f"Strategic alignment: {alignment}."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_candidates(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        print("No mission candidates found.")
        return
    print(f"\n{'='*60}")
    print(f"Mission Candidates — {len(candidates)} record(s)")
    print(f"{'='*60}")
    for c in candidates:
        print(f"\nMission ID  : {c.get('mission_candidate_id')}")
        print(f"Status      : {c.get('status')}")
        print(f"Title       : {c.get('title')}")
        print(f"Lead        : {c.get('lead_specialist')}")
        print(f"Supporting  : {', '.join(c.get('supporting_specialists', []))}")
        print(f"Action      : {c.get('recommended_action', '')[:100]}")
        print(f"Time-to-val : {c.get('time_to_value')}")
        print(f"Decision ID : {c.get('decision_id')}")
        print(f"{'-'*60}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission Candidate converter for USS TJR.")
    parser.add_argument("--decision-id", help="Generate a mission candidate from this decision ID")
    parser.add_argument("--list", action="store_true", help="List all mission candidates")
    parser.add_argument("--status", help="Filter list by status")
    args = parser.parse_args()

    if args.decision_id:
        from decision_register import _find_decision_path
        path = _find_decision_path(args.decision_id)
        if path is None:
            print(f"Decision {args.decision_id} not found.")
            raise SystemExit(1)
        record = json.loads(path.read_text(encoding="utf-8"))
        candidate = create_mission_candidate(record)
        if candidate:
            print(f"Mission candidate created: {candidate['mission_candidate_id']}")
            _print_candidates([candidate])
        else:
            print("Decision is not strategic. No mission candidate created.")
    elif args.list:
        candidates = load_mission_candidates(args.status)
        _print_candidates(candidates)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
