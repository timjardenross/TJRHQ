"""
Decision Extractor — WP4

Reads the Decision Register (memory/Decision-Register.md) and extracts
DecisionContextPackage objects. Identifies decisions awaiting Captain input.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))

from models import DecisionContextPackage
import config


def load_decisions(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Parse Decision Register markdown into list of raw decision dicts.
    Reads from config.DECISION_REGISTER_PATH by default.
    """
    source = path or config.DECISION_REGISTER_PATH
    if not source.exists():
        return []

    raw = source.read_text(encoding="utf-8")
    return _parse_decision_blocks(raw)


def assemble_decision_context(decision_dict: Dict[str, Any]) -> DecisionContextPackage:
    """Convert a raw decision dict to a DecisionContextPackage."""
    decision_id = decision_dict.get("id", "UNKNOWN")
    date_str = decision_dict.get("date", "")
    status = decision_dict.get("status", "")

    # A decision "awaits captain input" if it's Proposed and has no recorded action
    action = decision_dict.get("action", "") or ""
    pending = (
        "proposed" in status.lower() or "pending" in status.lower()
    ) and (not action or action.lower() in ("not recorded", "none", ""))

    urgency = _derive_urgency(decision_dict, pending)

    return DecisionContextPackage(
        decision_id=decision_id,
        assembled_at=datetime.utcnow().isoformat() + "Z",
        date=date_str,
        status=status,
        question=decision_dict.get("question", ""),
        action=action or None,
        bottleneck=decision_dict.get("bottleneck") or None,
        related_missions=_extract_mission_refs(decision_dict),
        awaiting_captain_input=pending,
        urgency=urgency,
    )


def get_decisions_awaiting_input(path: Optional[Path] = None) -> List[DecisionContextPackage]:
    """Return only decisions that require Captain action."""
    all_decisions = load_decisions(path)
    packages = [assemble_decision_context(d) for d in all_decisions]
    return [p for p in packages if p.awaiting_captain_input]


def get_recent_decisions(limit: int = 10, path: Optional[Path] = None) -> List[DecisionContextPackage]:
    """Return the N most recent decisions as context packages."""
    all_decisions = load_decisions(path)
    # Already ordered most-recent-first by Decision Register format
    return [assemble_decision_context(d) for d in all_decisions[:limit]]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# DEC-YYYYMMDD-HHMMSS-... format
_DEC_HEADING = re.compile(r"^###\s+(DEC-\d{8}-\S+)", re.MULTILINE)
_FIELD = re.compile(r"^\*\*(.+?)\*\*[:：]\s*(.*)$")


def _parse_decision_blocks(raw: str) -> List[Dict[str, Any]]:
    """Split Decision Register into individual decision dicts."""
    blocks = _DEC_HEADING.split(raw)
    # blocks[0] = preamble, then alternating [id, body, id, body, ...]
    decisions = []

    for i in range(1, len(blocks), 2):
        dec_id = blocks[i].strip()
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        dec = _parse_decision_body(dec_id, body)
        decisions.append(dec)

    return decisions


def _parse_decision_body(dec_id: str, body: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"id": dec_id, "raw_body": body}

    for line in body.splitlines():
        m = _FIELD.match(line.strip())
        if not m:
            continue
        key = m.group(1).strip().lower()
        value = m.group(2).strip()

        if key == "date":
            result["date"] = value
        elif key == "status":
            result["status"] = value
        elif key == "question":
            result["question"] = value
        elif key == "action":
            result["action"] = value
        elif key == "bottleneck":
            result["bottleneck"] = value

    return result


def _extract_mission_refs(decision_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find MSN-XXXX references in decision text."""
    text = decision_dict.get("question", "") + " " + (decision_dict.get("action") or "")
    msn_pattern = re.compile(r"\b(MSN-\d{4}[A-Z]?)\b", re.IGNORECASE)
    matches = list({m.group(1).upper() for m in msn_pattern.finditer(text)})
    return [{"id": m, "title": "", "relationship": "referenced"} for m in matches]


def _derive_urgency(decision_dict: Dict[str, Any], pending: bool) -> str:
    if not pending:
        return "none"
    # Check if date is recent (within 7 days → high urgency)
    date_str = decision_dict.get("date", "")
    if date_str:
        try:
            decision_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            age = (date.today() - decision_date).days
            if age <= 1:
                return "high"
            if age <= 7:
                return "medium"
        except ValueError:
            pass
    return "low"
