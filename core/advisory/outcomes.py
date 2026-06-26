"""Advisory Outcome Tracking — USS-TJR-MSN-0093 WP3.

Closes the advisory loop by recording, for every piece of advice:

    advice given → recommendation issued → decision taken → outcome achieved
    → success/failure → confidence level → user feedback

Storage (file-based, matching the existing knowledge/mission-outcomes.jsonl
house pattern so the same tooling/conventions apply, and so it works offline):

    logs/advisory/<advisory_id>.json      — full snapshot of the advice given
    knowledge/advisory-outcomes.jsonl     — append-only outcome events

This module never raises to its callers — recording advice must never break an
advisory response. It grants no authority and triggers no action; it only
records what happened so the system can learn (WP4/WP5/WP7).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_REPO_ROOT = _HERE.parents[1]

# Storage root is overridable (ADVISORY_DATA_ROOT) so tests/sandboxes never
# pollute the committed repo. Default is the repo's logs/ + knowledge/ dirs.
def _data_root() -> Path:
    override = os.environ.get("ADVISORY_DATA_ROOT")
    return Path(override) if override else _REPO_ROOT


def _advisory_log_dir() -> Path:
    return _data_root() / "logs" / "advisory"


def _outcomes_file() -> Path:
    return _data_root() / "knowledge" / "advisory-outcomes.jsonl"


_VALID_OUTCOMES = {"success", "failure", "partial", "unknown"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"ADV-{stamp}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Recording advice
# ---------------------------------------------------------------------------

def record_advisory(response: Any, *, action: str = "advice") -> str:
    """Persist a snapshot of advice given. Returns the advisory_id (or "").

    Accepts an AdvisoryResponse or a plain dict (its to_dict() form). Safe to
    call on every request — swallows all errors.
    """
    try:
        data = response.to_dict() if hasattr(response, "to_dict") else dict(response)
    except Exception:  # noqa: BLE001
        return ""

    advisory_id = _new_id()
    conf = data.get("confidence") or {}
    record = {
        "advisory_id": advisory_id,
        "recorded_at": _now(),
        "action": action,
        "question": data.get("question", ""),
        "recommendation": data.get("recommendation", ""),
        "decision_mode": data.get("decision_mode", ""),
        "confidence_value": conf.get("value"),
        "confidence_band": conf.get("band"),
        "reviewer": data.get("reviewer"),
        "escalation_required": data.get("escalation_required", False),
        "degraded": data.get("degraded", False),
        "officers": [
            {"officer": o.get("officer"), "confidence": o.get("confidence"), "stance": o.get("stance")}
            for o in data.get("officer_perspectives", [])
        ],
        "lesson_ids": [l.get("lesson_id") for l in data.get("related_lessons", [])],
        "evidence_count": len(data.get("historical_evidence", [])),
        "related_decision_ids": [d.get("decision_id") for d in data.get("related_decisions", [])],
        # Outcome fields — populated later via record_outcome()
        "decision_taken": None,
        "outcome": None,
        "success": None,
        "feedback": None,
        "outcome_recorded_at": None,
    }

    try:
        _advisory_log_dir().mkdir(parents=True, exist_ok=True)
        path = _advisory_log_dir() / f"{advisory_id}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return ""
    return advisory_id


# ---------------------------------------------------------------------------
# Recording outcomes
# ---------------------------------------------------------------------------

def record_outcome(
    advisory_id: str,
    *,
    outcome: str,
    decision_taken: str = "",
    feedback: str = "",
) -> dict[str, Any]:
    """Record the outcome of previously-given advice.

    outcome: one of success | failure | partial | unknown.
    Returns {"ok": bool, "message": str, "advisory_id": str}.
    """
    outcome = (outcome or "").lower().strip()
    if outcome not in _VALID_OUTCOMES:
        return {"ok": False, "message": f"outcome must be one of {sorted(_VALID_OUTCOMES)}",
                "advisory_id": advisory_id}

    advisory_id = (advisory_id or "").strip()
    if advisory_id.lower() == "last":
        advisory_id = latest_advisory_id() or ""
    if not advisory_id:
        return {"ok": False, "message": "no advisory_id provided (and no recent advice found)",
                "advisory_id": ""}

    record = get_record(advisory_id)
    if record is None:
        return {"ok": False, "message": f"advisory record {advisory_id} not found",
                "advisory_id": advisory_id}

    # Update the snapshot record.
    record["decision_taken"] = decision_taken or record.get("decision_taken")
    record["outcome"] = outcome
    record["success"] = {"success": True, "failure": False}.get(outcome)  # partial/unknown → None
    record["feedback"] = feedback or record.get("feedback")
    record["outcome_recorded_at"] = _now()
    try:
        (_advisory_log_dir() / f"{advisory_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        return {"ok": False, "message": "failed to update advisory record", "advisory_id": advisory_id}

    # Append an outcome event to the append-only ledger (the learning signal).
    event = {
        "advisory_id": advisory_id,
        "recorded_at": _now(),
        "question": record.get("question", ""),
        "outcome": outcome,
        "success": record["success"],
        "decision_taken": decision_taken,
        "feedback": feedback,
        "confidence_value": record.get("confidence_value"),
        "confidence_band": record.get("confidence_band"),
        "officers": [o.get("officer") for o in record.get("officers", [])],
        "reviewer": record.get("reviewer"),
        "escalation_required": record.get("escalation_required", False),
        "lesson_ids": record.get("lesson_ids", []),
        "decision_mode": record.get("decision_mode", ""),
    }
    try:
        _outcomes_file().parent.mkdir(parents=True, exist_ok=True)
        with _outcomes_file().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        return {"ok": False, "message": "failed to append outcome event", "advisory_id": advisory_id}

    return {"ok": True, "message": f"outcome '{outcome}' recorded for {advisory_id}",
            "advisory_id": advisory_id}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def get_record(advisory_id: str) -> Optional[dict[str, Any]]:
    path = _advisory_log_dir() / f"{advisory_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_records() -> list[dict[str, Any]]:
    """All advisory snapshots (advice given), newest first."""
    if not _advisory_log_dir().exists():
        return []
    records = []
    for path in _advisory_log_dir().glob("ADV-*.json"):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    records.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)
    return records


def load_outcomes() -> list[dict[str, Any]]:
    """All recorded outcome events from the append-only ledger."""
    if not _outcomes_file().exists():
        return []
    out = []
    try:
        for line in _outcomes_file().read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def latest_advisory_id() -> Optional[str]:
    records = load_records()
    return records[0]["advisory_id"] if records else None
