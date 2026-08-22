"""
Mission Lifecycle Commands — WP-4 + M-20260614-GOVERNANCE-LIFECYCLE-CLOSURE WP2+WP3

Provides /mission-list, /mission-status, /mission-close Slack commands.

WP2: /mission-status now supports lifecycle transitions:
  /mission-status <id> <new-status>
  Valid statuses: Idea, Planned, Active, Blocked, Review, Completed, Closed

WP3: /mission-list now supports `idea` filter:
  /mission-list idea  — Idea-status missions sorted by age (oldest first)

Data source: Supabase missions table (sole system of record)

Public API:
    handle_mission_list(text, user_id, channel_id) -> str
    handle_mission_status(text, user_id, channel_id) -> str
    handle_mission_close(text, user_id, channel_id) -> str
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Statuses considered "active" for /mission-list default view
_ACTIVE_STATUSES = {"in_progress", "active", "in progress", "planned", "blocked", "design"}

# Valid promotion targets for /mission-status <id> <status>
# Must match missions_status_check constraint in Supabase
_VALID_TRANSITIONS = {
    "Idea", "Designed", "Approved for Engineering", "Implemented",
    "Tested", "Awaiting Number One Review", "Validated",
    "Awaiting XO Approval", "Awaiting Captain Approval", "Approved",
    "Closed", "Blocked", "Archived", "Requires Rework",
}
# Multi-word statuses need special handling — exact match first, then prefix
_VALID_TRANSITIONS_LOWER = {s.lower(): s for s in _VALID_TRANSITIONS}

# Audit log directory for status transitions
_TRANSITION_LOG_DIR = _REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "transitions"


# ---------------------------------------------------------------------------
# Mission dossier builder — assembles QA context from available sources
# ---------------------------------------------------------------------------

_EXAMPLES_DIR = _REPO_ROOT / "core" / "mission-control" / "examples"
_MAX_REF_CHARS = 6000   # cap reference file content to avoid oversized prompts


def _load_mission_dossier(mission_id: str) -> dict:
    """
    Assemble a mission dossier dict from local sources.

    Sources (all optional, fail-silent):
      1. core/mission-control/examples/USS-TJR-MSN-XXXX.txt — structured mission file

    Returns a dict with keys:
        mission_id, title, priority, status, owner, specialist,
        reference_path, mission_file_content, reference_content
    Any missing field is an empty string.
    """
    dossier: dict = {
        "mission_id": mission_id,
        "title": "",
        "priority": "",
        "status": "",
        "owner": "",
        "specialist": "",
        "reference_path": "",
        "mission_file_content": "",
        "reference_content": "",
    }

    # Normalise mission_id to full form for file lookups
    bare_id = mission_id.replace("USS-TJR-", "")
    full_id = mission_id if mission_id.startswith("USS-TJR-") else f"USS-TJR-{mission_id}"

    # 2. Look for a structured mission file in examples/
    try:
        for candidate_name in (f"{full_id}.txt", f"{bare_id}.txt"):
            candidate = _EXAMPLES_DIR / candidate_name
            if candidate.exists():
                dossier["mission_file_content"] = candidate.read_text(encoding="utf-8")[:_MAX_REF_CHARS]
                break
    except Exception as exc:
        log.debug("[mission_lifecycle] dossier: mission file read failed: %s", exc)

    # 3. Read the reference file from the index
    try:
        ref_path = dossier.get("reference_path", "").strip()
        if ref_path:
            ref_file = _REPO_ROOT / ref_path
            if ref_file.exists():
                dossier["reference_content"] = ref_file.read_text(encoding="utf-8")[:_MAX_REF_CHARS]
    except Exception as exc:
        log.debug("[mission_lifecycle] dossier: reference file read failed: %s", exc)

    return dossier


def _format_qa_dossier(dossier: dict, closing_note: str = "") -> str:
    """
    Format a mission dossier as a structured text block for the QA agent prompt.
    """
    lines: list[str] = []

    lines.append("=== MISSION DOSSIER ===\n")
    lines.append(f"Mission ID : {dossier['mission_id']}")
    if dossier["title"]:
        lines.append(f"Title      : {dossier['title']}")
    if dossier["priority"]:
        lines.append(f"Priority   : {dossier['priority']}")
    if dossier["status"]:
        lines.append(f"Status     : {dossier['status']}")
    if dossier["owner"]:
        lines.append(f"Owner      : {dossier['owner']}")
    if dossier["specialist"]:
        lines.append(f"Specialist : {dossier['specialist']}")
    if closing_note:
        lines.append(f"Closing Note: {closing_note}")

    if dossier["mission_file_content"]:
        lines.append("\n--- MISSION FILE ---")
        lines.append(dossier["mission_file_content"])

    if dossier["reference_content"]:
        lines.append("\n--- REFERENCE / EVIDENCE ---")
        if dossier["reference_path"]:
            lines.append(f"Source: {dossier['reference_path']}")
        lines.append(dossier["reference_content"])

    if not dossier["mission_file_content"] and not dossier["reference_content"]:
        lines.append("\n(No structured mission file or reference document found in local sources.)")

    return "\n".join(lines)


def _supabase_missions(status_filter: Optional[str] = None, order: str = "created_at.desc") -> list[dict]:
    """Try to read missions from Supabase. Returns empty list on failure."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from tools.supabase.client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return []
        qs = f"missions?select=*&order={order}&limit=50"
        if status_filter:
            # Exact case-insensitive match for Idea; ilike for others
            qs += f"&status=ilike.{status_filter}"
        rows = client.get(qs)
        return rows or []
    except Exception as exc:
        log.debug("[mission_lifecycle] Supabase unavailable: %s", exc)
        return []


def _supabase_get_mission(mission_id: str) -> Optional[dict]:
    """Direct Supabase lookup by mission_id text column. Returns None on miss or error."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from tools.supabase.client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return None
        mission_id_full = mission_id if mission_id.startswith("USS-TJR-") else f"USS-TJR-{mission_id}"
        for mid_try in (mission_id_full, mission_id):
            rows = client.get(f"missions?select=*&mission_id=eq.{mid_try}&limit=1")
            if rows:
                return rows[0]
        return None
    except Exception as exc:
        log.debug("[mission_lifecycle] Supabase get_mission failed: %s", exc)
        return None


def _time_sensitivity_from_due_date(due_date: Optional[str]) -> Optional[int]:
    """0-100 urgency derived from days-until-due, for
    `PriorityInputs.time_sensitivity` (Priority Engine wiring fix — see
    core/platform/priority_engine.py). Mirrors the days-until-due curve
    core/coordination/recommendation_engine.py's `_due_date_score`/
    `_deadline_urgency` already use for missions (overdue/due-today highest,
    decaying by week/month) — rescaled 0-100 here instead of that module's
    own 0-0.25 additive bonus, not a new curve invented for this fix.
    Returns None (not 0) when there is no due date to derive from — absent
    means no signal, matching `event_bus.publish_event()`'s own contract
    for this field, not a fabricated "not urgent"."""
    if not due_date:
        return None
    try:
        from datetime import date as _date
        d = _date.fromisoformat(str(due_date)[:10])
        days_until = (d - _date.today()).days
        if days_until <= 0:
            return 100  # due today or overdue
        if days_until <= 3:
            return 80
        if days_until <= 7:
            return 60
        if days_until <= 30:
            return 30
        return 10
    except (ValueError, TypeError):
        return None


def _supabase_update_mission_status(mission_id: str, new_status: str, due_date: Optional[str] = None) -> bool:
    """Update mission status in Supabase. Returns True on success.

    `due_date`: the mission's own `due_date` column, if the caller already
    has it in scope (e.g. from a prior `_supabase_missions()` read) — used
    only to derive `time_sensitivity` for the Event Bus emission below.
    Optional and defaults to None (no urgency signal), never fetched here
    itself, so this function's own contract (one PATCH + one best-effort
    event) doesn't grow an extra read."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from tools.supabase.client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return False
        # Try both bare and prefixed IDs
        mission_id_full = mission_id if mission_id.startswith("USS-TJR-") else f"USS-TJR-{mission_id}"
        # updated_at is timestamp without time zone — omit timezone suffix
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for mid_try in (mission_id_full, mission_id):
            result = client._patch(
                f"missions?mission_id=eq.{mid_try}",
                {"status": new_status, "updated_at": now_str},
            )
            if result:
                # MSN-0328 Wave 2: canonical Captain Brief pipeline event.
                # Non-blocking, matches publish_event()'s own contract —
                # never affects this function's own success/failure.
                try:
                    if str(_REPO_ROOT) not in sys.path:
                        sys.path.insert(0, str(_REPO_ROOT))
                    from core.platform.event_bus import publish_event
                    publish_event(
                        "mission.status_changed", domain="mission-lifecycle",
                        source="slack-bot:mission_lifecycle",
                        time_sensitivity=_time_sensitivity_from_due_date(due_date),
                        linked_missions=[mid_try], recommended_action=new_status,
                    )
                except Exception:
                    pass
                # ADR-024 second-pass audit: the 'missions' domain_registry row
                # (migration 0071) has had zero record_heartbeat() calls anywhere
                # in the repo since it was registered — verification_state has
                # reported it never_succeeded despite the live table being
                # actively written to. Same non-blocking contract as the event
                # above.
                try:
                    if str(_REPO_ROOT) not in sys.path:
                        sys.path.insert(0, str(_REPO_ROOT))
                    from core.platform.heartbeat import record_heartbeat
                    record_heartbeat("missions", status="ok", detail=f"status_changed:{new_status}")
                except Exception:
                    pass
                return True
        return False
    except Exception as exc:
        log.debug("[mission_lifecycle] Supabase status update failed: %s", exc)
        return False


def _write_transition_audit(mission_id: str, from_status: str, to_status: str, user_id: str, note: str) -> None:
    """Record a status transition in Supabase mission_state_transitions and local JSON backup."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # Primary: Supabase mission_state_transitions (MSN-BOT-SOR)
    try:
        import uuid as _uuid
        from tools.supabase.client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if client.is_enabled():
            client.insert("mission_state_transitions", {
                "id":               str(_uuid.uuid4()),
                "mission_id":       mission_id,
                "from_state":       from_status or None,   # original NOT NULL-compatible col
                "to_state":         to_status,             # NOT NULL — required
                "from_status":      from_status or None,   # MSN-BOT-SOR extended col
                "to_status":        to_status,
                "actor":            user_id or "Captain",
                "transitioned_by":  user_id or "Captain",
                "transitioned_at":  now_iso,
                "note":             note or None,
                "source":           "slack-bot",
            })
    except Exception as exc:
        log.warning("[mission_lifecycle] Supabase transition record failed: %s", exc)

    # Secondary: local JSON backup (non-authoritative)
    try:
        _TRANSITION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        log_file = _TRANSITION_LOG_DIR / f"TRANSITION-{mission_id}-{ts}.json"
        log_file.write_text(json.dumps({
            "mission_id":      mission_id,
            "from_status":     from_status,
            "to_status":       to_status,
            "transitioned_by": user_id or "Captain",
            "transitioned_at": now_iso,
            "note":            note or None,
        }, indent=2))
    except Exception as exc:
        log.warning("[mission_lifecycle] Local transition backup write failed: %s", exc)


# ---------------------------------------------------------------------------
# /mission-list
# ---------------------------------------------------------------------------

def handle_mission_list(
    text: str,
    user_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> str:
    """
    List missions.

    Usage:
      /mission-list            — show all active/in-progress missions
      /mission-list all        — show all missions regardless of status
      /mission-list idea       — show Idea-status missions (dormant captures), oldest first
      /mission-list completed  — show completed missions
      /mission-list blocked    — show blocked missions
    """
    filter_arg = (text or "").strip().lower()
    show_all = filter_arg == "all"
    show_ideas = filter_arg == "idea"

    if show_ideas:
        # Idea-status missions: oldest first so longest-dormant surfaces at top
        db_missions = _supabase_missions(status_filter="Idea", order="created_at.asc")
        if db_missions:
            return _format_idea_list(db_missions)
        # Flat-file fallback does not track Idea status — inform clearly
        return (
            ":bulb: *Idea Registry*\n\n"
            "No Idea-status missions found in Supabase.\n"
            "Capture ideas with `/mission-capture <description>`.\n"
            "_Ideas are stored in Supabase — flat-file registry does not track Idea status._"
        )

    status_filter = filter_arg if filter_arg and not show_all else None

    db_missions = _supabase_missions(status_filter)
    if db_missions:
        return _format_mission_list(db_missions, source="Supabase", filter_arg=filter_arg)

    return ":warning: No missions returned from Supabase. Check that Supabase is configured and reachable."


def _format_idea_list(missions: list[dict]) -> str:
    """Format Idea-status missions with age display."""
    if not missions:
        return (
            ":bulb: *Idea Registry — empty*\n\n"
            "No Idea-status missions. Capture ideas with `/mission-capture <description>`."
        )
    lines = [f":bulb: *Idea Registry — {len(missions)} idea{'s' if len(missions) != 1 else ''}* _(oldest first)_", ""]
    now = datetime.now(timezone.utc)
    for m in missions[:25]:
        mid   = m.get("id") or m.get("mission_id", "?")
        title = m.get("title", "Untitled")
        created_raw = m.get("created_at", "")
        age_str = ""
        if created_raw:
            try:
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                age_days = (now - created).days
                age_str = f" · {age_days}d old"
                if age_days >= 14:
                    age_str += " :hourglass:"
            except (ValueError, TypeError):
                pass
        lines.append(f"  • `{mid}` — {title}{age_str}")
    if len(missions) > 25:
        lines.append(f"\n_...and {len(missions) - 25} more._")
    lines.append("")
    lines.append("_Use `/mission-status <id> planned` to promote. Number One reviews fortnightly._")
    return "\n".join(lines)


def _format_mission_list(missions: list[dict], source: str, filter_arg: str) -> str:
    if not missions:
        return f":information_source: No missions found (filter: `{filter_arg or 'active'}`, source: {source})."

    label = f"active missions" if not filter_arg or filter_arg == "active" else f"`{filter_arg}` missions"
    lines = [f"*:clipboard: {len(missions)} {label}* _(source: {source})_", ""]
    for m in missions[:20]:
        mid    = m.get("id") or m.get("mission_id", "")
        title  = m.get("title", "")
        status = m.get("status", "")
        owner  = m.get("owner") or m.get("mission_owner", "")
        lines.append(f"  • `{mid}` — {title}  `{status}`{f'  _{owner}_' if owner else ''}")

    if len(missions) > 20:
        lines.append(f"\n_...and {len(missions) - 20} more. Use `/mission-list all` to see everything._")

    lines.append(f"\n_Use `/mission-status <id>` for details._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /mission-status
# ---------------------------------------------------------------------------

def handle_mission_status(
    text: str,
    user_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> str:
    """
    Show or update the status of a mission.

    Read:
      /mission-status <id>               — show current status detail

    Transition (WP2):
      /mission-status <id> <new-status>  — promote or change lifecycle status
      /mission-status <id> <new-status> [note]

    Valid statuses: Idea, Designed, Approved for Engineering, Implemented,
    Tested, Awaiting Number One Review, Validated, Awaiting XO Approval,
    Awaiting Captain Approval, Approved, Closed, Blocked, Archived, Requires Rework
    """
    parts = (text or "").strip().split(None, 2)
    if not parts:
        return (
            ":warning: Usage:\n"
            "  `/mission-status <id>` — show status\n"
            "  `/mission-status <id> <new-status> [note]` — transition status\n"
            "  Valid statuses: Idea, Designed, Approved, Closed, Blocked, Archived, "
            "Implemented, Tested, Validated, Requires Rework\n"
            "  (Multi-word: use quotes or exact spelling)"
        )

    mission_id = parts[0].upper()
    new_status_raw = parts[1].strip() if len(parts) > 1 else ""
    note = parts[2].strip() if len(parts) > 2 else ""

    # Normalise: accept both MSN-0040A and USS-TJR-MSN-0040A
    if not mission_id.startswith("USS-TJR-"):
        mission_id_full = f"USS-TJR-{mission_id}"
    else:
        mission_id_full = mission_id

    # --- Transition mode ---
    if new_status_raw:
        canonical = _VALID_TRANSITIONS_LOWER.get(new_status_raw.lower())
        if not canonical:
            valid_list = ", ".join(sorted(_VALID_TRANSITIONS))
            return (
                f":x: Unknown status `{new_status_raw}`.\n"
                f"Valid statuses: {valid_list}"
            )
        return _handle_status_transition(mission_id, mission_id_full, canonical, user_id, note)

    # --- Read mode ---
    # Direct lookup by mission_id text column (avoids 50-row cap and UUID confusion)
    db_row = _supabase_get_mission(mission_id)
    if db_row:
        return _format_mission_detail(db_row)

    # Fallback: flat file
    all_missions = _parse_registry()
    for m in all_missions:
        mid = m["id"].upper()
        if mid in (mission_id, mission_id_full):
            return _format_mission_detail(m)

    return f":x: Mission `{mission_id}` not found. Use `/mission-list` to see active missions."


def _closure_outcome_prompt(mission_id: str, title: str) -> Optional[str]:
    """MSN-0079 WP1: surface an outcome-capture request when a mission closes.

    Delegates to outcome_capture.closure_prompt (which never invents a lesson and
    returns None if an outcome already exists). Graceful: any failure → None, so a
    closure is never blocked by the hook.
    """
    try:
        import sys
        from pathlib import Path
        kp = str(Path(__file__).resolve().parents[2] / "core" / "knowledge")
        if kp not in sys.path:
            sys.path.insert(0, kp)
        from outcome_capture import closure_prompt  # type: ignore
        return closure_prompt("mission", mission_id, title)
    except Exception:  # pragma: no cover
        return None


def _handle_status_transition(
    mission_id: str,
    mission_id_full: str,
    new_status: str,
    user_id: Optional[str],
    note: str,
) -> str:
    """Execute a lifecycle status transition and write audit record."""
    # Fetch current status for audit trail
    from_status = "Unknown"
    mission_title = ""
    due_date = None
    db_missions = _supabase_missions()
    for m in db_missions:
        mid = (m.get("id") or m.get("mission_id") or "").upper()
        if mid in (mission_id, mission_id_full):
            from_status = m.get("status", "Unknown")
            mission_title = m.get("title", "") or ""
            due_date = m.get("due_date")  # feeds time_sensitivity — see _time_sensitivity_from_due_date
            break

    # Apply the transition
    updated = _supabase_update_mission_status(mission_id, new_status, due_date=due_date)
    if not updated:
        # Try prefixed form
        updated = _supabase_update_mission_status(mission_id_full, new_status, due_date=due_date)

    # Write audit record regardless of Supabase outcome
    _write_transition_audit(mission_id, from_status, new_status, user_id or "Captain", note)

    if updated:
        lines = [
            f":arrows_counterclockwise: *Mission Status Updated*",
            f"*Mission:* `{mission_id}`",
            f"*Transition:* `{from_status}` → `{new_status}`",
        ]
        if user_id:
            lines.append(f"*By:* <@{user_id}>")
        if note:
            lines.append(f"*Note:* _{note}_")
        lines.append("")
        if new_status == "Active":
            lines.append("_Mission is now in the active work queue._")
        elif new_status == "Planned":
            lines.append("_Mission is now in the planning queue. Use `/build` when ready for engineering._")
        elif new_status in ("Closed", "Completed"):
            lines.append("_Mission closed. Consider capturing a lesson with `/lesson-log`._")
            # MSN-0079 WP1: request outcome capture if none exists. Never invents a lesson.
            prompt = _closure_outcome_prompt(mission_id, mission_title)
            if prompt:
                lines += ["", prompt]
        elif new_status == "Archived":
            lines.append("_Mission archived._")
        elif new_status == "Idea":
            lines.append("_Mission returned to Idea state. Number One will review fortnightly._")
        elif new_status == "Approved":
            lines.append("_Mission approved. Ready for engineering._")
        elif new_status == "Implemented":
            lines.append("_Mission implemented. Awaiting test validation._")
        return "\n".join(lines)
    else:
        # Supabase unavailable — audit was still written locally
        return (
            f":warning: *Status transition recorded locally* (Supabase unavailable)\n\n"
            f"*Mission:* `{mission_id}`\n"
            f"*Transition:* `{from_status}` → `{new_status}`\n\n"
            f"Audit written to `USS-TJR-Control/logs/missions/transitions/`.\n"
            f"Update Supabase manually when connectivity is restored."
        )


def _format_mission_detail(m: dict) -> str:
    mid      = m.get("mission_id") or m.get("id", "")
    title    = m.get("title", "")
    status   = m.get("status", "")
    priority = m.get("priority", "")
    owner    = m.get("owner") or m.get("mission_owner", "")
    spec     = m.get("specialist") or m.get("assigned_specialist", "")
    ref      = m.get("reference") or m.get("ref", "")

    lines = [
        f"*:mag: Mission: `{mid}`*",
        f"*Title:* {title}",
        f"*Status:* `{status}`",
    ]
    if priority:
        lines.append(f"*Priority:* {priority}")
    if owner:
        lines.append(f"*Owner:* {owner}")
    if spec:
        lines.append(f"*Specialist:* {spec}")
    if ref:
        lines.append(f"*Reference:* `{ref}`")
    lines.append(f"\n_Use `/mission-status {mid} <new-status>` to transition. Use `/mission-close {mid}` to close._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /mission-close
# ---------------------------------------------------------------------------

def handle_mission_close(
    text: str,
    user_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    include_qa_advisory: bool = False,
) -> str:
    """
    Mark a mission as closed.

    Usage: /mission-close MSN-0040A [optional closing note]

    Writes a closure record to logs/missions/closed/ and (if Supabase is
    configured) updates the missions table status to 'Closed'.

    Args:
        include_qa_advisory: When False (default), the QA Validation Officer
            advisory is NOT embedded in the return string. The caller (app.py)
            posts it as a separate thread reply so it is public and threaded.
            Set True only when the caller cannot manage thread posting
            (e.g. the not_in_channel fallback path).
    """
    if not text or not text.strip():
        return ":warning: Usage: `/mission-close <mission-id> [closing note]`"

    parts = text.strip().split(None, 1)
    mission_id = parts[0].upper()
    note = parts[1] if len(parts) > 1 else ""

    if not mission_id.startswith("USS-TJR-"):
        mission_id_full = f"USS-TJR-{mission_id}"
    else:
        mission_id_full = mission_id

    # QA advisory is only embedded here when the caller cannot post it separately.
    qa_block = ""
    if include_qa_advisory:
        try:
            import sys as _sys
            _bot_dir = str(Path(__file__).resolve().parents[1])
            if _bot_dir not in _sys.path:
                _sys.path.insert(0, _bot_dir)
            from lib.mistral_agents import qa_validation_officer_slack_block
            dossier = _load_mission_dossier(mission_id_full)
            dossier_text = _format_qa_dossier(dossier, closing_note=note)
            qa_block = "\n\n" + qa_validation_officer_slack_block(
                mission_id=mission_id_full,
                mission_dossier=dossier_text,
                closing_note=note,
            )
        except Exception as _qa_exc:
            log.warning("[mission_lifecycle] QA Validation Officer block error: %s", _qa_exc)
            qa_block = "\n\n:white_check_mark: *QA Validation Officer Pre-Closure Review*\n_:robot_face: Agent advisory unavailable._"

    closed_in_db = False
    closed_in_file = False

    # Try Supabase update — reuse _supabase_update_mission_status (known-good PATCH path)
    closed_in_db = _supabase_update_mission_status(mission_id, "Closed")
    if closed_in_db:
        # Separately stamp closed_at (timestamptz column)
        try:
            sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
            from tools.supabase.client import CommanderSupabaseClient
            _cl = CommanderSupabaseClient()
            if _cl.is_enabled():
                mid_full = mission_id if mission_id.startswith("USS-TJR-") else f"USS-TJR-{mission_id}"
                _cl._patch(
                    f"missions?mission_id=eq.{mid_full}",
                    {"closed_at": datetime.now(timezone.utc).isoformat()},
                )
        except Exception as _ca_exc:
            log.warning("[mission_lifecycle] closed_at stamp failed: %s", _ca_exc)

    # Write closure log
    try:
        from datetime import datetime
        import json
        log_dir = _REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "closed"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        log_file = log_dir / f"CLOSED-{mission_id}-{ts}.json"
        log_file.write_text(json.dumps({
            "mission_id": mission_id_full,
            "closed_at": datetime.utcnow().isoformat() + "Z",
            "closed_by": user_id or "Captain",
            "closing_note": note or None,
        }, indent=2))
        closed_in_file = True
    except Exception as exc:
        log.warning("[mission_lifecycle] Closure log write failed: %s", exc)

    if closed_in_db:
        return (
            f":white_check_mark: Mission `{mission_id}` marked *Closed* in Supabase."
            f"{f' Note: _{note}_' if note else ''}"
            f"{qa_block}"
        )
    elif closed_in_file:
        return (
            f":white_check_mark: Mission `{mission_id}` closure recorded locally."
            f"{f' Note: _{note}_' if note else ''}\n"
            f"_Supabase unavailable — update `core/mission-control/registry/mission-index.txt` manually if needed._"
            f"{qa_block}"
        )
    else:
        return f":x: Could not close mission `{mission_id}`. Check logs.{qa_block}"
