#!/usr/bin/env python3
"""Phase 1 (D-054): READ-ONLY ingestion of approved engineering handoffs.

Surfaces approved `/build` engineering-handoff artifacts (ENG-HANDOFF-*.md under
`Missions/Engineering-Handoffs/`) into Number One's advisory work queue, daily
brief, recommendations, and prioritisation — WITHOUT requiring the manual
`batch_worker`. This closes the *visibility / prioritisation* loop only.

Operating boundaries (Captain decision D-054; upholds D-011 Number One MVP):
  * READ-ONLY     — only reads `.md` files; never writes/mutates a handoff.
  * ADVISORY      — surfaces work for the Captain; never executes it.
  * NON-BLOCKING  — missing dir / empty / malformed file degrade gracefully to
                    [] or a skipped item (the MSN-0053 graceful-parse approach);
                    Number One still works when there are zero handoffs.
  * NO AUTONOMY   — does not trigger the Engineering Router or any execution
                    pipeline (Option 5 deferred per D-054).

Each handoff is normalised into the same mission-dict shape Number One already
consumes (see `Mission.from_registry` in number_one.py and the registry parser
in number_one_exporter.py), so it flows through the existing work-queue / brief /
prioritisation logic with no engine changes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# repo root: core/coordination/ -> core/ -> <repo>
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HANDOFFS_DIR = _REPO_ROOT / "Missions" / "Engineering-Handoffs"


# ---------------------------------------------------------------------------
# Engineering handoff lifecycle (M-20260614-ENGINEERING-HANDOFF-LIFECYCLE)
# ---------------------------------------------------------------------------
# A read-only status PROJECTION over the engineering handoff. Derived purely
# from what the handoff file already declares (its `Batch Status`); this module
# never writes a status and never advances one — surfacing only. The vocabulary
# lives in its OWN namespace and is deliberately NOT merged into number_one's
# MissionStatus enum, so mission lifecycle handling is untouched (advisory,
# read-only; upholds D-011 and the Phase-1 non-invasive principle).
class EngineeringStatus(Enum):
    PENDING_TRIAGE = "Pending Triage"   # approved, not yet picked up
    ASSIGNED = "Assigned"               # claimed by a batch group / owner
    IN_PROGRESS = "In Progress"         # work underway
    AWAITING_REVIEW = "Awaiting Review"  # delivered, pending review
    COMPLETED = "Completed"             # done (terminal — excluded from active queue)


# Canonical ordering, most-needs-attention → terminal. Used for display/grouping.
ENGINEERING_LIFECYCLE = (
    EngineeringStatus.PENDING_TRIAGE,
    EngineeringStatus.ASSIGNED,
    EngineeringStatus.IN_PROGRESS,
    EngineeringStatus.AWAITING_REVIEW,
    EngineeringStatus.COMPLETED,
)

# Raw `Batch Status` token (normalised: upper, no spaces/-/_) → lifecycle status.
_BATCH_STATUS_MAP = {
    # Pending Triage
    "": EngineeringStatus.PENDING_TRIAGE,
    "PENDING": EngineeringStatus.PENDING_TRIAGE,
    "PENDINGTRIAGE": EngineeringStatus.PENDING_TRIAGE,
    "UNASSIGNED": EngineeringStatus.PENDING_TRIAGE,
    "TRIAGE": EngineeringStatus.PENDING_TRIAGE,
    "NEW": EngineeringStatus.PENDING_TRIAGE,
    "OPEN": EngineeringStatus.PENDING_TRIAGE,
    # Assigned
    "SUBMITTED": EngineeringStatus.ASSIGNED,
    "ASSIGNED": EngineeringStatus.ASSIGNED,
    "CLAIMED": EngineeringStatus.ASSIGNED,
    "QUEUED": EngineeringStatus.ASSIGNED,
    # In Progress
    "INPROGRESS": EngineeringStatus.IN_PROGRESS,
    "WIP": EngineeringStatus.IN_PROGRESS,
    "STARTED": EngineeringStatus.IN_PROGRESS,
    "ACTIVE": EngineeringStatus.IN_PROGRESS,
    # Awaiting Review
    "DELIVERED": EngineeringStatus.AWAITING_REVIEW,
    "AWAITINGREVIEW": EngineeringStatus.AWAITING_REVIEW,
    "REVIEW": EngineeringStatus.AWAITING_REVIEW,
    "INREVIEW": EngineeringStatus.AWAITING_REVIEW,
    "READYFORREVIEW": EngineeringStatus.AWAITING_REVIEW,
    "SUBMITTEDFORREVIEW": EngineeringStatus.AWAITING_REVIEW,
    # Completed (terminal)
    "COMPLETED": EngineeringStatus.COMPLETED,
    "COMPLETE": EngineeringStatus.COMPLETED,
    "DONE": EngineeringStatus.COMPLETED,
    "MERGED": EngineeringStatus.COMPLETED,
    "CLOSED": EngineeringStatus.COMPLETED,
}

# Raw statuses that are terminal/closed but NOT part of the 5-status active
# vocabulary (a handoff that failed/was cancelled is not outstanding advisory
# work in this model). Excluded from the active queue, same as Completed.
_NON_ACTIVE_TERMINAL = {"FAILED", "CANCELLED", "CANCELED", "ARCHIVED"}

# Lifecycle statuses that are terminal (not outstanding work → excluded).
_TERMINAL_ENGINEERING_STATUSES = {EngineeringStatus.COMPLETED}


def _normalise_token(value: Optional[str]) -> str:
    """Uppercase and strip spaces/hyphens/underscores for tolerant matching."""
    return (value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def derive_engineering_status(batch_status: Optional[str]) -> Optional[EngineeringStatus]:
    """Map a handoff's raw `Batch Status` to a lifecycle status (read-only).

    Returns None when the raw status is terminal-but-not-Completed (FAILED /
    CANCELLED / ARCHIVED) — those are excluded from the active advisory queue.
    Unknown non-terminal values degrade gracefully to PENDING_TRIAGE so the work
    still surfaces for a human to triage (never fabricated as further along).
    """
    token = _normalise_token(batch_status)
    if token in _NON_ACTIVE_TERMINAL:
        return None
    return _BATCH_STATUS_MAP.get(token, EngineeringStatus.PENDING_TRIAGE)


def _parse_handoff_file(path: Path) -> Optional[dict[str, str]]:
    """Parse one ENG-HANDOFF markdown file into a flat field dict.

    Reads the `- Key: Value` header block and the `## Mission Title` section.
    Returns None only when the file cannot be read at all (never raises).
    Missing individual fields are simply absent from the returned dict — callers
    apply defaults (graceful degradation; no fabricated data).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fields: dict[str, str] = {}
    current_section: Optional[str] = None
    section_lines: dict[str, list[str]] = {}

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip().lower()
            section_lines.setdefault(current_section, [])
            continue
        if stripped.startswith("# "):
            current_section = None
            continue
        # Header key/value lines look like "- Key: Value"
        if current_section is None and stripped.startswith("- ") and ":" in stripped:
            key, _, value = stripped[2:].partition(":")
            key_norm = key.strip().lower().replace(" ", "_")
            if key_norm and key_norm not in fields:
                fields[key_norm] = value.strip()
            continue
        if current_section is not None and stripped:
            section_lines[current_section].append(stripped)

    # Prefer the explicit "## Mission Title" section for the title.
    title_section = section_lines.get("mission title") or []
    if title_section:
        fields["__mission_title__"] = title_section[0].strip()

    return fields


def _coerce_approved_at(value: Optional[str], fallback_path: Path) -> str:
    """Return an ISO timestamp for staleness from the 'Approved At' field.

    Handoffs are written as "%Y-%m-%d %H:%M:%S". Falls back to the file mtime,
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
    """Map parsed handoff fields into a Number One mission-dict, or None to skip.

    Skips (returns None) when the handoff is not approved-for-engineering or its
    batch status is terminal — those are not outstanding advisory work.
    """
    status = (fields.get("status") or "").strip()
    # Only surface approved engineering handoffs. Do not fabricate approval.
    if "APPROVED" not in status.upper():
        return None

    batch_status = (fields.get("batch_status") or "").strip()
    eng_status = derive_engineering_status(batch_status)
    # Excluded from the active advisory queue: terminal-but-not-completed
    # (None) and Completed — neither is outstanding work, mirroring how
    # completed missions drop out of the active queue.
    if eng_status is None or eng_status in _TERMINAL_ENGINEERING_STATUSES:
        return None

    # ID: prefer a real router/mission id; else fall back to the filename stem.
    raw_mission_id = (fields.get("mission_id") or "").strip()
    if raw_mission_id and raw_mission_id.lower() not in {"unassigned", "unknown", ""}:
        mission_id = raw_mission_id
    else:
        mission_id = path.stem  # e.g. ENG-HANDOFF-20260614-...-slug

    title = (fields.get("__mission_title__") or "Engineering Handoff").strip()
    display_title = f"[ENG-HANDOFF] {title}"

    priority = (fields.get("priority") or "P2").strip() or "P2"
    approved_at = _coerce_approved_at(fields.get("approved_at"), path)

    batch_status_label = batch_status or "PENDING"

    # Pointer to the review-only code artifact, once batch_coding has delivered it.
    # The writer stamps `- Batch Artifact: <path>`; accept the synonyms a manual
    # or alternate pipeline might use too. Keys are normalised lower_snake_case
    # by _parse_handoff_file, so match the normalised forms.
    artifact_ref = ""
    for _artifact_key in ("batch_artifact", "output_artifact", "review_artifact"):
        candidate = (fields.get(_artifact_key) or "").strip()
        if candidate:
            artifact_ref = candidate
            break

    # Pointer to the draft GitHub PR, once batch_coding has opened one (the diff
    # applied cleanly). Stamped as `- PR URL: <url>`. Preferred over the raw patch
    # pointer below — a PR is the higher-fidelity review surface.
    pr_url = (fields.get("pr_url") or "").strip()

    # Advisory next-action keyed to the lifecycle stage (read-only guidance).
    _next_action_by_stage = {
        EngineeringStatus.PENDING_TRIAGE: "Triage and assign this approved engineering handoff",
        EngineeringStatus.ASSIGNED: "Engineering handoff assigned — begin implementation",
        EngineeringStatus.IN_PROGRESS: "Engineering handoff in progress — track to delivery",
        EngineeringStatus.AWAITING_REVIEW: "Engineering handoff delivered — review and sign off",
    }
    # When a draft PR exists, point straight at it. Else, if the code artifact has
    # landed, point at the patch. Else fall back to the generic stage guidance.
    if eng_status is EngineeringStatus.AWAITING_REVIEW and pr_url:
        next_action = (
            f"Engineering handoff delivered — review the draft PR at {pr_url} "
            f"and approve/merge (lifecycle: {eng_status.value}; batch status: {batch_status_label})"
        )
    elif eng_status is EngineeringStatus.AWAITING_REVIEW and artifact_ref:
        next_action = (
            f"Engineering handoff delivered — review the generated patch at {artifact_ref} "
            f"and sign off (lifecycle: {eng_status.value}; batch status: {batch_status_label})"
        )
    else:
        next_action = (
            f"{_next_action_by_stage.get(eng_status, 'Review engineering handoff')} "
            f"(lifecycle: {eng_status.value}; batch status: {batch_status_label})"
        )

    try:
        rel_path = str(path.relative_to(_REPO_ROOT))
    except ValueError:
        rel_path = str(path)

    return {
        "mission_id": mission_id,
        "title": display_title,
        "status": "ACTIVE",  # approved + open -> active advisory work
        "priority": priority,
        "domain": "engineering",
        "assigned_role": "Chief Engineer",
        "assigned_specialists": ["Chief Engineer"],
        "dependencies": [],
        "blockers": [],
        "created_at": approved_at,
        "last_updated": approved_at,
        "next_action": next_action,
        "metadata": {
            "source": "engineering_handoff",
            "engineering_status": eng_status.value,
            "handoff_file": rel_path,
            "decision_id": fields.get("decision_id", ""),
            "batch_status": batch_status_label,
            "batch_artifact": artifact_ref,
            "pr_url": pr_url,
            "batch_group": fields.get("batch_group", ""),
            "approved_by": fields.get("approved_by", ""),
            "approved_at": fields.get("approved_at", ""),
            "router_mission_id": raw_mission_id,
        },
    }


def load_engineering_handoffs(
    handoffs_dir: Optional[str | Path] = None,
    command_memory_mission_ids: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Return approved, outstanding engineering handoffs as mission dicts.

    READ-ONLY and NON-BLOCKING: returns [] when the directory is missing or
    empty, and silently skips any file that cannot be parsed or is not an
    outstanding approved handoff. Never raises.

    Args:
        handoffs_dir: Directory to scan. Defaults to DEFAULT_HANDOFFS_DIR.
        command_memory_mission_ids: Optional set of mission IDs already present
            in Command Memory. Handoffs whose ``decision_id`` appears in this set
            are skipped — Command Memory is the authoritative record after
            approval (WP5: deduplication, M-20260614-ENGINEERING-HANDOFF-E2E-CLOSURE).
    """
    base = Path(handoffs_dir) if handoffs_dir is not None else DEFAULT_HANDOFFS_DIR
    if not base.exists() or not base.is_dir():
        return []

    skip_ids: set[str] = command_memory_mission_ids or set()

    missions: list[dict[str, Any]] = []
    try:
        candidates = sorted(base.glob("ENG-HANDOFF-*.md"))
    except OSError:
        return []

    for path in candidates:
        fields = _parse_handoff_file(path)
        if not fields:
            continue
        # Skip if already registered in Command Memory (avoid duplicate queue entries)
        if skip_ids and fields.get("decision_id", "") in skip_ids:
            continue
        mission = _normalise_to_mission(fields, path)
        if mission is not None:
            missions.append(mission)

    return missions


def summarise_engineering_handoffs(missions: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a read-only engineering-handoff summary for Number One reporting.

    Accepts the full missions list (registry + handoffs) and projects only the
    handoff items, grouped by lifecycle status. Non-handoff missions are ignored.
    Returns a zeroed-but-well-formed summary when there are no handoffs.
    """
    by_status: dict[str, int] = {s.value: 0 for s in ENGINEERING_LIFECYCLE
                                 if s not in _TERMINAL_ENGINEERING_STATUSES}
    items: list[dict[str, Any]] = []
    for m in missions or []:
        meta = m.get("metadata") or {}
        if meta.get("source") != "engineering_handoff":
            continue
        es = meta.get("engineering_status") or EngineeringStatus.PENDING_TRIAGE.value
        by_status[es] = by_status.get(es, 0) + 1
        items.append({
            "mission_id": m.get("mission_id"),
            "title": m.get("title"),
            "priority": m.get("priority"),
            "engineering_status": es,
            "next_action": m.get("next_action"),
            "handoff_file": meta.get("handoff_file"),
        })
    return {"total": len(items), "by_status": by_status, "items": items}


if __name__ == "__main__":
    import json

    items = load_engineering_handoffs()
    print(f"Loaded {len(items)} approved engineering handoff(s) from {DEFAULT_HANDOFFS_DIR}")
    print(json.dumps(items, indent=2))
