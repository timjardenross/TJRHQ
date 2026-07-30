#!/usr/bin/env python3
"""Decision Register for USS-TJR-MSN-0009B / MSN-0010.

Writes a separate JSON record to logs/decisions/ for every strategic
decision made by Commander TJR. Non-strategic runs are not logged here.

The register is a durable record that Captain TJR can review over time
to track which strategic choices were made, what was sacrificed, and
whether the decision held up.

MSN-0010 D2/D6 extensions:
    - Status field: Proposed → Accepted/Rejected → In Progress → Completed → Reviewed
    - update_decision_outcome(): update status and captain review fields in-place
    - Query helpers: get_open_decisions(), get_decisions_awaiting_review(),
                     get_decisions_by_mode(), get_decisions_by_date_range()

Usage (called automatically from collaborative_specialist_runtime.py):
    from decision_register import write_decision_record
    record_path = write_decision_record(collaboration_id, question, decision_context, log_payload)

CLI viewer:
    python3 tools/supabase/decision_register.py
    python3 tools/supabase/decision_register.py --status open
    python3 tools/supabase/decision_register.py --awaiting-review
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[2]
DECISION_DIR = ROOT / "logs/decisions"

# ---------------------------------------------------------------------------
# Decision lifecycle statuses (D2/D6)
# ---------------------------------------------------------------------------

DECISION_STATUSES = (
    "Proposed",      # Written by Commander — awaiting Captain review
    "Accepted",      # Captain accepted the recommendation
    "Rejected",      # Captain rejected the recommendation
    "In Progress",   # Mission underway from this decision
    "Completed",     # Implementation done
    "Reviewed",      # Outcome reviewed by Captain
    "Deferred",      # Explicitly deferred — revisit later
)

# Outcome values for captain_decision_held
OUTCOME_VALUES = ("success", "partial_success", "failure", "deferred")

# Fields carried forward from the collaboration log payload
_PAYLOAD_FIELDS = (
    "mission_id",
    "synthesis_model",
    "synthesis_provider",
    "challenge_mode",
    "reviewer_selected",
    "latency_ms",
    "source_count",
    "source_paths",
    "final_recommendation",
    "specialists_selected",
)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_decision_record(
    collaboration_id: str,
    question: str,
    decision_context: dict[str, Any],
    log_payload: dict[str, Any],
) -> Path | None:
    """Write a decision register record for a strategic decision.

    Returns the Path of the written record, or None if decision_mode is
    not 'strategic' (non-strategic decisions are not registered here).
    """
    if decision_context.get("decision_mode") != "strategic":
        return None

    DECISION_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S-%f")
    decision_id = f"DEC-{timestamp}-{uuid.uuid4().hex[:6]}"

    record: dict[str, Any] = {
        "decision_id": decision_id,
        "collaboration_id": collaboration_id,
        "timestamp": now.isoformat(),
        "question": question,
        # Lifecycle status (D2)
        "status": "Proposed",
        # Decision frame
        "decision_mode": decision_context.get("decision_mode"),
        "current_bottleneck": decision_context.get("current_bottleneck"),
        "options": decision_context.get("options", []),
        "opportunity_cost": decision_context.get("opportunity_cost"),
        "time_to_value": decision_context.get("time_to_value"),
        "reversibility": decision_context.get("reversibility"),
        "strategic_alignment": decision_context.get("strategic_alignment"),
        "required_decision": decision_context.get("required_decision"),
        # Specialist positions at time of decision
        "specialist_positions": decision_context.get("specialist_positions", []),
        "reviewer_position": decision_context.get("reviewer_position"),
        # Commander output
        "recommended_action": log_payload.get("recommended_action"),
        "final_recommendation": log_payload.get("final_recommendation"),
        # Context from collaboration log
        **{field: log_payload.get(field) for field in _PAYLOAD_FIELDS},
        # Captain review fields
        "captain_outcome_review": None,   # How did this decision play out?
        "captain_decision_held": None,    # success / partial_success / failure / deferred
        "captain_review_date": None,
        "captain_notes": None,
        # Linked mission (set when a mission candidate is generated — D3)
        "linked_mission_id": None,
    }

    path = DECISION_DIR / f"{timestamp}-decision.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Update (D6 — lifecycle tracking)
# ---------------------------------------------------------------------------

def update_decision_outcome(
    decision_id: str,
    status: str,
    captain_decision_held: str | None = None,
    captain_outcome_review: str | None = None,
    captain_notes: str | None = None,
    linked_mission_id: str | None = None,
) -> Path | None:
    """Update the lifecycle status and captain review fields of an existing record.

    Finds the record by decision_id (scans DECISION_DIR), updates it in-place,
    and writes it back. Returns the path or None if not found.

    Args:
        decision_id:           The DEC-... identifier.
        status:                One of DECISION_STATUSES.
        captain_decision_held: "success" / "partial_success" / "failure" / "deferred"
        captain_outcome_review: Free-text outcome description.
        captain_notes:          Any notes from Captain TJR.
        linked_mission_id:      Mission ID if a mission was created from this decision.
    """
    if status not in DECISION_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Must be one of: {DECISION_STATUSES}")

    path = _find_decision_path(decision_id)
    if path is None:
        return None

    record = json.loads(path.read_text(encoding="utf-8"))
    record["status"] = status
    if captain_decision_held is not None:
        record["captain_decision_held"] = captain_decision_held
    if captain_outcome_review is not None:
        record["captain_outcome_review"] = captain_outcome_review
    if captain_notes is not None:
        record["captain_notes"] = captain_notes
    if linked_mission_id is not None:
        record["linked_mission_id"] = linked_mission_id
    if status in ("Reviewed", "Completed") and not record.get("captain_review_date"):
        record["captain_review_date"] = datetime.now(timezone.utc).isoformat()

    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def _find_decision_path(decision_id: str) -> Path | None:
    """Scan DECISION_DIR for a record with the given decision_id."""
    if not DECISION_DIR.exists():
        return None
    for path in DECISION_DIR.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("decision_id") == decision_id:
                return path
        except Exception:  # noqa: BLE001
            continue
    return None


# ---------------------------------------------------------------------------
# Load (base)
# ---------------------------------------------------------------------------

def load_decisions(decision_mode: str | None = None) -> list[dict[str, Any]]:
    """Load all decision register records, optionally filtered by mode."""
    if not DECISION_DIR.exists():
        return []
    records = []
    for path in sorted(DECISION_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            # Back-fill status for records written before D2 was added
            if "status" not in record:
                record["status"] = "Proposed"
            if decision_mode is None or record.get("decision_mode") == decision_mode:
                records.append(record)
        except Exception:  # noqa: BLE001
            continue
    return records


# ---------------------------------------------------------------------------
# Query helpers (D2)
# ---------------------------------------------------------------------------

def get_open_decisions() -> list[dict[str, Any]]:
    """Return decisions that are Proposed or Accepted but not yet Completed/Reviewed."""
    return [
        r for r in load_decisions()
        if r.get("status") in ("Proposed", "Accepted", "In Progress")
    ]


def get_decisions_awaiting_review() -> list[dict[str, Any]]:
    """Return decisions that are Completed but not yet Reviewed."""
    return [
        r for r in load_decisions()
        if r.get("status") == "Completed" and not r.get("captain_review_date")
    ]


def get_decisions_by_mode(mode: str) -> list[dict[str, Any]]:
    """Return all decisions with the given decision_mode."""
    return load_decisions(decision_mode=mode)


def get_decisions_by_date_range(
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """Return decisions within an ISO-format date range (YYYY-MM-DD, inclusive).

    Args:
        start_date: e.g. "2026-06-01"
        end_date:   e.g. "2026-06-30"
    """
    records = load_decisions()
    result = []
    for record in records:
        ts = (record.get("timestamp") or "")[:10]
        if start_date <= ts <= end_date:
            result.append(record)
    return result


# ---------------------------------------------------------------------------
# Summary display
# ---------------------------------------------------------------------------

def print_decision_summary(records: list[dict[str, Any]]) -> None:
    """Print a human-readable summary of decision register records."""
    if not records:
        print("No decision records found.")
        return
    print(f"\n{'='*60}")
    print(f"Decision Register — {len(records)} record(s)")
    print(f"{'='*60}")
    for record in records:
        status = record.get("status", "Proposed")
        print(f"\nDecision ID : {record.get('decision_id')}")
        print(f"Status      : {status}")
        print(f"Timestamp   : {record.get('timestamp', '')[:19]}")
        print(f"Question    : {record.get('question')}")
        print(f"Bottleneck  : {record.get('current_bottleneck')}")
        rec = record.get("recommended_action") or record.get("final_recommendation") or ""
        if rec.lower().startswith("recommended action:"):
            rec = rec[len("recommended action:"):].strip()
        print(f"Recommended : {rec}")
        print(f"Opportunity : {record.get('opportunity_cost')}")
        print(f"Reversible  : {record.get('reversibility')}")
        held = record.get("captain_decision_held")
        if held is not None:
            print(f"Outcome     : {held}")
        else:
            print("Captain review: pending")
        if record.get("linked_mission_id"):
            print(f"Mission     : {record['linked_mission_id']}")
        print(f"{'-'*60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI viewer for the Decision Register."""
    import argparse

    parser = argparse.ArgumentParser(description="Decision Register viewer for USS TJR.")
    parser.add_argument("--mode", default="strategic", help="Filter by decision mode (default: strategic)")
    parser.add_argument("--all", action="store_true", help="Show all modes")
    parser.add_argument("--status", choices=["open", "awaiting-review"], help="Filter by lifecycle state")
    parser.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    args = parser.parse_args()

    if args.status == "open":
        records = get_open_decisions()
    elif args.status == "awaiting-review":
        records = get_decisions_awaiting_review()
    elif args.from_date and args.to_date:
        records = get_decisions_by_date_range(args.from_date, args.to_date)
    else:
        mode_filter = None if args.all else args.mode
        records = load_decisions(mode_filter)

    print_decision_summary(records)


if __name__ == "__main__":
    main()
