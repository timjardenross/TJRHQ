#!/usr/bin/env python3
"""READ-ONLY ingestion of Telegram Chief-Engineer build requests.

Surfaces the build requests the Telegram agent appends to
``Missions/Telegram-Inbox/BREQ-*.md`` into Number One's advisory work queue,
daily brief, recommendations, and prioritisation — so a conversation that
produced actionable work becomes visible to Number One / XO governance as a
``PENDING_TRIAGE`` item. This closes the Telegram → governance loop.

It is a sibling of ``engineering_handoff_reader.py`` and follows the same
boundaries (Captain decision; upholds D-011 Number One MVP):
  * READ-ONLY     — only reads ``.md`` files; never writes/mutates a request.
  * ADVISORY      — surfaces work for the Captain; never executes it.
  * NON-BLOCKING  — missing dir / empty / malformed file degrade gracefully to
                    [] or a skipped item; Number One still works with zero
                    requests.
  * NO AUTONOMY   — does not approve, route, or execute anything. Requests stay
                    ``PENDING_TRIAGE`` for a human to triage.

Loop closure: only requests whose ``Status`` is still pending-triage are
surfaced. Once a human advances the request (editing its ``- Status:`` to
triaged / approved / rejected / closed, or archiving the file), it drops out of
the active advisory queue — so the queue reflects only outstanding triage work.

Each request is normalised into the same mission-dict shape Number One already
consumes (matching ``engineering_handoff_reader._normalise_to_mission``), so it
flows through the existing work-queue / brief / prioritisation logic with no
engine changes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# repo root: core/coordination/ -> core/ -> <repo>
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INBOX_DIR = _REPO_ROOT / "Missions" / "Telegram-Inbox"

# Raw `Status` tokens (normalised: upper, no spaces/-/_) that mean the request
# is still outstanding triage work and should surface. The Telegram agent always
# writes PENDING_TRIAGE; the empty string covers a request that omitted it.
_PENDING_TOKENS = {"", "PENDINGTRIAGE", "PENDING", "TRIAGE", "NEW", "OPEN", "UNTRIAGED"}


def _normalise_token(value: Optional[str]) -> str:
    """Uppercase and strip spaces/hyphens/underscores for tolerant matching."""
    return (value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def is_pending_triage(status: Optional[str]) -> bool:
    """True when a request's raw `Status` still represents outstanding triage.

    Anything outside the pending vocabulary (triaged / approved / rejected /
    closed / done / archived / …) is treated as already-handled and excluded —
    that exclusion is what closes the loop.
    """
    return _normalise_token(status) in _PENDING_TOKENS


def _parse_request_file(path: Path) -> Optional[dict[str, str]]:
    """Parse one BREQ markdown file into a flat field dict.

    Reads the ``- Key: Value`` header block and each ``## Section`` (full
    multi-line body, list bullets preserved). Returns None only when the file
    cannot be read at all (never raises). Missing fields are simply absent from
    the returned dict — callers apply defaults (graceful degradation).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fields: dict[str, str] = {}
    section_lines: dict[str, list[str]] = {}
    current_section: Optional[str] = None

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip().lower()
            section_lines.setdefault(current_section, [])
            continue
        if stripped.startswith("# "):
            current_section = None
            continue
        # Header key/value lines look like "- Key: Value" (before any section).
        if current_section is None and stripped.startswith("- ") and ":" in stripped:
            key, _, value = stripped[2:].partition(":")
            key_norm = key.strip().lower().replace(" ", "_")
            if key_norm and key_norm not in fields:
                fields[key_norm] = value.strip()
            continue
        if current_section is not None and stripped:
            section_lines[current_section].append(stripped)

    # Flatten each section into a field. Sections named like the BREQ template
    # (title/summary/rationale/risks/suggested next step/conversation context).
    for name, lines in section_lines.items():
        key_norm = name.replace(" ", "_")
        fields.setdefault(f"__section_{key_norm}__", "\n".join(lines).strip())

    return fields


def _coerce_timestamp(value: Optional[str], fallback_path: Path) -> str:
    """Return an ISO timestamp for staleness from the 'Timestamp' field.

    BREQ files are written as "%Y-%m-%d %H:%M:%S". Falls back to the file mtime,
    then to now() — never raises.
    """
    if value:
        try:
            dt = datetime.strptime(value.strip()[:19], "%Y-%m-%d %H:%M:%S")
            return dt.isoformat() + "Z"
        except ValueError:
            pass
    try:
        return datetime.utcfromtimestamp(fallback_path.stat().st_mtime).isoformat() + "Z"
    except OSError:
        return datetime.utcnow().isoformat() + "Z"


def _normalise_to_mission(fields: dict[str, str], path: Path) -> Optional[dict[str, Any]]:
    """Map a parsed BREQ into a Number One mission-dict, or None to skip.

    Skips (returns None) when the request is no longer pending triage — that is
    what keeps the advisory queue limited to outstanding work and closes the
    loop once a human acts.
    """
    if not is_pending_triage(fields.get("status")):
        return None

    # ID: prefer the request's own id; else fall back to the filename stem.
    raw_id = (fields.get("request_id") or "").strip()
    mission_id = raw_id if raw_id else path.stem  # e.g. BREQ-20260616-120000-add-x

    title = (fields.get("__section_title__") or "Telegram Build Request").strip()
    # Title section may carry several lines; keep the first as the display title.
    title = title.splitlines()[0].strip() if title else "Telegram Build Request"
    display_title = f"[TELEGRAM] {title}"

    summary = (fields.get("__section_summary__") or "").strip()
    rationale = (fields.get("__section_rationale__") or "").strip()
    risks = (fields.get("__section_risks__") or "").strip()
    suggested = (fields.get("__section_suggested_next_step__") or "").strip()

    created_at = _coerce_timestamp(fields.get("timestamp"), path)

    # Read-only advisory guidance: a build request is unprioritised by design,
    # so it enters as P2 and asks a human to triage it. We fold the agent's own
    # suggested next step into the guidance without treating it as approved work.
    if suggested:
        next_action = f"Triage this Telegram build request (suggested next step: {suggested})"
    else:
        next_action = "Triage this Telegram build request"

    try:
        rel_path = str(path.relative_to(_REPO_ROOT))
    except ValueError:
        rel_path = str(path)

    return {
        "mission_id": mission_id,
        "title": display_title,
        "status": "ACTIVE",  # pending + open -> active advisory work
        "priority": "P2",
        "domain": "engineering",
        "assigned_role": "Chief Engineer",
        "assigned_specialists": ["Chief Engineer"],
        "dependencies": [],
        "blockers": [],
        "created_at": created_at,
        "last_updated": created_at,
        "next_action": next_action,
        "metadata": {
            "source": "telegram_build_request",
            "engineering_status": "Pending Triage",
            "request_file": rel_path,
            "requested_by": fields.get("requested_by", ""),
            "request_source": fields.get("source", "telegram"),
            "summary": summary,
            "rationale": rationale,
            "risks": risks,
            "suggested_next_step": suggested,
        },
    }


def load_telegram_build_requests(
    inbox_dir: Optional[str | Path] = None,
) -> list[dict[str, Any]]:
    """Return outstanding (pending-triage) Telegram build requests as mission dicts.

    READ-ONLY and NON-BLOCKING: returns [] when the directory is missing or
    empty, and silently skips any file that cannot be parsed or is no longer
    pending triage. Never raises.

    Args:
        inbox_dir: Directory to scan. Defaults to DEFAULT_INBOX_DIR.
    """
    base = Path(inbox_dir) if inbox_dir is not None else DEFAULT_INBOX_DIR
    if not base.exists() or not base.is_dir():
        return []

    missions: list[dict[str, Any]] = []
    try:
        candidates = sorted(base.glob("BREQ-*.md"))
    except OSError:
        return []

    for path in candidates:
        fields = _parse_request_file(path)
        if not fields:
            continue
        mission = _normalise_to_mission(fields, path)
        if mission is not None:
            missions.append(mission)

    return missions


def summarise_telegram_build_requests(missions: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a read-only Telegram-build-request summary for Number One reporting.

    Accepts the full missions list (registry + handoffs + telegram) and projects
    only the telegram items. Non-telegram missions are ignored. Returns a
    zeroed-but-well-formed summary when there are none.
    """
    items: list[dict[str, Any]] = []
    for m in missions or []:
        meta = m.get("metadata") or {}
        if meta.get("source") != "telegram_build_request":
            continue
        items.append({
            "mission_id": m.get("mission_id"),
            "title": m.get("title"),
            "priority": m.get("priority"),
            "engineering_status": meta.get("engineering_status"),
            "next_action": m.get("next_action"),
            "request_file": meta.get("request_file"),
            "requested_by": meta.get("requested_by"),
        })
    return {
        "total": len(items),
        "by_status": {"Pending Triage": len(items)},
        "items": items,
    }


if __name__ == "__main__":
    import json

    items = load_telegram_build_requests()
    print(f"Loaded {len(items)} pending Telegram build request(s) from {DEFAULT_INBOX_DIR}")
    print(json.dumps(items, indent=2))
