"""MSN-0040A Command Memory Integration Layer.

Provides non-blocking writes to Command Memory (Supabase) for missions, decisions,
capabilities, and architecture records.

All operations are wrapped in try/except to ensure Slack Commander continues
even if Supabase is temporarily unavailable.

Public API:
    save_mission_to_command_memory(mission_id, title, created_by) -> bool
    log_decision_to_command_memory(statement, rationale, owner) -> bool
    update_mission_status_in_command_memory(mission_id, new_status, user_id) -> bool
    get_active_missions() -> list[dict]
    get_active_decisions() -> list[dict]
    search_memory(query) -> dict
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import id_registry

log = logging.getLogger(__name__)

# The live `missions` table (created outside the migration system) is stricter
# than these writers used to assume: `mission_id` is required and unique (`id`
# is a generated uuid), `repo` is required with no default, `status` is limited
# by CHECK missions_status_check and `priority` by CHECK to P0-P3, and there is
# no `owner` or `updated_by` column. Writes that ignored this were rejected
# with a 400 every time.
LIVE_MISSION_STATUSES = frozenset({
    "Idea", "Designed", "Approved for Engineering", "Implemented", "Tested",
    "Awaiting Number One Review", "Validated", "Awaiting XO Approval",
    "Awaiting Captain Approval", "Approved", "Closed", "Blocked", "Archived",
    "Requires Rework",
})
LIVE_MISSION_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
MISSIONS_DEFAULT_REPO = os.environ.get("MISSIONS_DEFAULT_REPO", "timjardenross/TJRHQ")


class CommandMemoryClient:
    """Supabase-backed Command Memory client with non-blocking error handling."""

    def __init__(self):
        """Initialize Supabase client from environment."""
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        )
        self._initialized = bool(self.url and self.key)
        if not self._initialized:
            log.warning(
                "[command-memory] Supabase credentials not configured. "
                "Command Memory writes will be skipped."
            )

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build HTTP headers for Supabase API requests."""
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Execute HTTP request to Supabase REST API.

        Returns parsed JSON on success, or None on any failure (network error,
        non-2xx status). HTTP error bodies are logged for diagnostics but never
        raised — all Command Memory operations are non-blocking.
        """
        import json
        import urllib.error
        import urllib.request

        if not self._initialized:
            return None

        try:
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{self.url}{path}",
                data=body,
                method=method,
                headers=self._headers(extra_headers),
            )
            with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310 - url is built from self.url (SUPABASE_URL env var) plus a fixed internal REST path, not user input - reviewed 2026-09-12
                data = response.read().decode("utf-8")
                return json.loads(data) if data else None
        except urllib.error.HTTPError as e:
            # Surface the PostgREST error body (e.g. constraint violation,
            # missing column) so failures are diagnosable in logs.
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception as _exc:  # noqa: BLE001 - best-effort error-body decode for logging, already logged
                log.debug("[command_memory_integration] best-effort step failed, continuing: %s", _exc)
            log.error(
                f"[command-memory] HTTP {e.code} ({method} {path}): {detail}"
            )
            return None
        except Exception as e:  # noqa: BLE001 - best-effort HTTP request, already logged
            log.error(f"[command-memory] Request failed ({method} {path}): {e}")
            return None

    def insert(self, table: str, record: dict[str, Any], *, on_conflict: str | None = None) -> bool:
        """Insert a single record into Command Memory table.

        Uses ``Prefer: return=representation`` so PostgREST echoes the inserted
        row back — without it Supabase returns an empty body and a successful
        write is indistinguishable from a failure.

        ``on_conflict`` names a unique column (e.g. ``mission_id``): a row that
        already exists is then left as it is and counts as success, so saving
        the same record twice is harmless rather than a 409.
        """
        if not self._initialized:
            return False

        path = f"/rest/v1/{table}"
        prefer = "return=representation"
        if on_conflict:
            path += f"?on_conflict={on_conflict}"
            prefer = "resolution=ignore-duplicates," + prefer
        result = self.request("POST", path, record, extra_headers={"Prefer": prefer})
        if on_conflict and result is not None:
            # PostgREST answers an ignored duplicate with an empty list.
            log.info(f"[command-memory] Inserted into {table}: {record.get('id') or record.get(on_conflict, 'unknown')}")
            return True
        if result:
            log.info(f"[command-memory] Inserted into {table}: {record.get('id', 'unknown')}")
            return True
        log.warning(f"[command-memory] Insert into {table} failed (non-blocking)")
        return False

    def update(self, table: str, record_id: str, updates: dict[str, Any], *, key: str = "id") -> bool:
        """Update a record in Command Memory table.

        Returns True only if a matching row was updated. ``return=representation``
        makes PostgREST echo the affected rows, so an update against a missing id
        returns an empty list and is correctly reported as a failure.

        ``key`` is the column matched against ``record_id`` — ``mission_id`` for
        missions, whose ``id`` is a generated uuid.
        """
        if not self._initialized:
            return False

        import urllib.parse

        path = f"/rest/v1/{table}?{key}=eq.{urllib.parse.quote(record_id, safe='')}"
        result = self.request(
            "PATCH",
            path,
            updates,
            extra_headers={"Prefer": "return=representation"},
        )
        if result:
            log.info(f"[command-memory] Updated {table}:{record_id}")
            return True
        log.warning(f"[command-memory] Update to {table}:{record_id} failed (non-blocking)")
        return False

    def select(self, table: str, columns: str = "*", filters: dict | None = None, limit: int | None = None) -> list:
        """Query records from Command Memory table."""
        if not self._initialized:
            return []

        try:
            import urllib.parse

            params = {"select": columns}
            if filters:
                params.update(filters)
            if limit is not None:
                params["limit"] = str(limit)
            query = urllib.parse.urlencode(params, safe="*,().")
            result = self.request("GET", f"/rest/v1/{table}?{query}")
            return result if isinstance(result, list) else []
        except Exception as e:  # noqa: BLE001 - best-effort table query, already logged
            log.error(f"[command-memory] Query to {table} failed: {e}")
            return []


# Singleton instance
_client = None


def get_client() -> CommandMemoryClient:
    """Get or create the Command Memory client."""
    global _client
    if _client is None:
        _client = CommandMemoryClient()
    return _client


def save_mission_to_command_memory(
    mission_id: str,
    title: str,
    created_by: str,
    owner: str | None = None,
    description: str | None = None,
    status: str = "Idea",
) -> bool:
    """Save a mission to Command Memory (non-blocking).

    Args:
        mission_id: Unique mission identifier (M-YYYYMMDD-HHMMSS or DEC-REC-…)
        title: Mission title
        created_by: Slack user ID of mission creator
        owner: Accepted for compatibility with existing callers; the missions
               table has no owner column, so it is not stored.
        description: LLM-generated structured capture body (optional)
        status: A status from the live missions lifecycle (LIVE_MISSION_STATUSES).
                Defaults to "Idea" (dormant capture state). An unrecognised
                status is stored as "Idea" rather than failing the whole write.

    Returns:
        True if the mission is saved (or already was), False otherwise
        (non-blocking failure).
    """
    if status not in LIVE_MISSION_STATUSES:
        log.warning(
            "[command-memory] Mission %s: status %r is not in the live lifecycle; saving as 'Idea'",
            mission_id, status,
        )
        status = "Idea"

    client = get_client()
    record = {
        "mission_id": mission_id,
        "title": title,
        "created_by": created_by,
        "status": status,
        "repo": MISSIONS_DEFAULT_REPO,
    }
    if description is not None:
        record["description"] = description

    # on_conflict: mission_logger.py may already have inserted this mission.
    success = client.insert("missions", record, on_conflict="mission_id")
    if success:
        log.info(f"[command-memory] Mission {mission_id} saved to Command Memory (status={status})")
    else:
        log.warning(f"[command-memory] Failed to save mission {mission_id} (non-blocking)")
    return success


def log_decision_to_command_memory(
    statement: str,
    rationale: str,
    owner: str,
) -> str | None:
    """Log a decision to Command Memory (non-blocking).

    Args:
        statement: Decision statement (e.g., "We will use Supabase")
        rationale: Why this decision was made
        owner: Slack user ID of decision authority

    Returns:
        Decision ID if successful, None otherwise (non-blocking failure).
    """
    from datetime import datetime

    client = get_client()

    # Generate decision ID
    decision_id = id_registry.next_id("DEC")

    record = {
        "id": decision_id,
        "statement": statement,
        "rationale": rationale,
        "created_by": owner,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "owner": owner,
        "status": "Active",
        "alternatives": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": owner,
    }

    success = client.insert("command_memory_records", record)
    if success:
        log.info(f"[command-memory] Decision {decision_id} logged to Command Memory")
        return decision_id
    else:
        log.warning("[command-memory] Failed to log decision (non-blocking)")
        return None


def update_mission_status_in_command_memory(
    mission_id: str,
    new_status: str,
    user_id: str,
) -> bool:
    """Update mission status in Command Memory (non-blocking).

    Args:
        mission_id: Mission ID to update
        new_status: New status — one of LIVE_MISSION_STATUSES
        user_id: Slack user ID making the update (the missions table has no
                 updated_by column, so it is only logged)

    Returns:
        True if update succeeded, False otherwise (non-blocking failure).
    """
    from datetime import datetime

    if new_status not in LIVE_MISSION_STATUSES:
        # The live CHECK constraint would reject it; don't send a request that
        # can only 400.
        log.warning(
            "[command-memory] Mission %s: status %r is not in the live lifecycle %s; not updated (by %s)",
            mission_id, new_status, sorted(LIVE_MISSION_STATUSES), user_id,
        )
        return False

    client = get_client()
    updates = {
        "status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    success = client.update("missions", mission_id, updates, key="mission_id")
    if success:
        log.info(f"[command-memory] Mission {mission_id} status updated to {new_status}")
    else:
        log.warning(f"[command-memory] Failed to update mission {mission_id} status (non-blocking)")
    return success


def get_active_missions() -> list[dict[str, Any]]:
    """Get all active missions from Command Memory.

    Returns:
        List of mission dicts, empty list if unavailable.
    """
    client = get_client()
    results = client.select(
        "missions",
        # missions has no `owner` column (400'd ~285/day) — created_by is the closest.
        columns="id,title,created_by,created_at",
        filters={"status": "eq.Active"},
    )
    if results:
        log.info(f"[command-memory] Retrieved {len(results)} active missions")
    return results


def get_active_decisions() -> list[dict[str, Any]]:
    """Get all active decisions from Command Memory.

    Returns:
        List of decision dicts, empty list if unavailable.
    """
    client = get_client()
    results = client.select(
        "command_memory_records",
        columns="id,statement,owner,created_at",
        # Excludes the ~45 EXEC-002A..EXEC-007 key-value writers, which
        # share this table under owner-prefixed keys (initiative:,
        # dep_link:, capability:, ...) rather than real Command Memory
        # decisions.
        filters={"status": "eq.Active", "owner": "not.like.*:*"},
        limit=5,
    )
    if results:
        log.info(f"[command-memory] Retrieved {len(results)} active decisions")
    return results


def create_mission_from_officer(
    officer: str,
    title: str,
    summary: str,
    priority: str = "P2",
    strategic_alignment: str | None = None,
    recommended_owner: str | None = None,
    expected_outcome: str | None = None,
    success_criteria: str | None = None,
    requires_approval: str = "xo",
    mission_id: str | None = None,
    captain_override: bool = False,
) -> str | None:
    """Officer creates an actionable mission draft (EXEC-001 WP2).

    Any officer may call this to convert an observation, risk, opportunity,
    or blocker into a mission. The mission starts in 'Idea' state and routes
    to the XO approval queue before Number One can action it.

    Authority is validated against the officer's manifest before writing.
    All creation events are logged to Command Memory for auditability.

    Args:
        officer:            Officer slug (e.g. 'human_systems', 'number_one')
        title:              Mission title
        summary:            Mission rationale / description
        priority:           P0–P5 (defaults P2)
        strategic_alignment: Directive or strategic domain (e.g. 'D-055')
        recommended_owner:  Suggested mission owner after approval
        expected_outcome:   What success looks like
        success_criteria:   Measurable success criteria
        requires_approval:  Approval authority: 'xo' (default) | 'captain' | 'number_one'
        mission_id:         Optional explicit ID (auto-generated if not provided)
        captain_override:   Bypass authority gate; logged to audit trail

    Returns:
        Mission ID string if write succeeded, None otherwise (non-blocking).
    """
    try:
        from core.governance.authority_validator import (
            ManifestGapError,
            audit_authority_action,
            can_officer,
        )
        try:
            approved, reason = can_officer(officer, "create_mission_draft")
        except ManifestGapError as exc:
            # 2026-09-15 adversarial review: this used to propagate to the
            # broad `except Exception` below, which logged it as "skipped
            # (non-blocking)" and let mission creation proceed anyway —
            # silently defeating Wave 3/4's fail-closed-by-default design
            # for every officer, since governance/authority/ had no
            # manifests at all until this same review added them. Treat a
            # gap the same as an explicit denial (captain_override still
            # bypasses it) instead of silently permitting.
            approved, reason = False, exc.reason
        if not approved and not captain_override:
            log.warning(
                "[command-memory] Officer '%s' denied create_mission_draft: %s", officer, reason
            )
            audit_authority_action(
                officer=officer, action="create_mission_draft",
                approved=False, reason=reason, captain_override=False,
            )
            return None
        audit_authority_action(
            officer=officer, action="create_mission_draft",
            approved=True, reason=reason,
            captain_override=captain_override,
        )
    except Exception as exc:  # noqa: BLE001 - genuinely unexpected failure (e.g. Supabase down for the audit write) — best-effort authority check, already logged
        log.warning("[command-memory] Authority check skipped (non-blocking): %s", exc)

    # Build mission ID
    if mission_id is None:
        mission_id = id_registry.next_id("MSN")

    # Compose description from structured fields
    parts = [f"**Rationale:** {summary}"]
    if strategic_alignment:
        parts.append(f"**Strategic Alignment:** {strategic_alignment}")
    if recommended_owner:
        parts.append(f"**Recommended Owner:** {recommended_owner}")
    if expected_outcome:
        parts.append(f"**Expected Outcome:** {expected_outcome}")
    if success_criteria:
        parts.append(f"**Success Criteria:** {success_criteria}")
    parts.append(f"**Requires Approval:** {requires_approval.upper()}")
    parts.append(f"**Created By Officer:** {officer}")
    description = "\n".join(parts)

    client = get_client()
    record = {
        "mission_id": mission_id,
        "title": title,
        "created_by": f"officer:{officer}",
        "status": "Idea",
        "description": description,  # includes the Recommended Owner line
        "repo": MISSIONS_DEFAULT_REPO,
    }
    # missions.priority only allows P0-P3; the docstring's P4/P5 would be rejected.
    if priority in LIVE_MISSION_PRIORITIES:
        record["priority"] = priority
    else:
        log.warning("[command-memory] Mission %s: priority %r is not P0-P3; omitted", mission_id, priority)

    success = client.insert("missions", record, on_conflict="mission_id")
    if success:
        log.info(
            "[command-memory] Officer '%s' created mission %s (priority=%s, approval=%s)",
            officer, mission_id, priority, requires_approval
        )
        # Log the creation as a decision for auditability
        log_decision_to_command_memory(
            statement=f"Officer mission created: {mission_id} — {title}",
            rationale=(
                f"Officer '{officer}' created mission from {strategic_alignment or 'operational observation'}. "
                f"Priority: {priority}. Requires {requires_approval.upper()} approval before execution."
            ),
            owner=f"officer:{officer}",
        )
        return mission_id
    else:
        log.warning("[command-memory] Officer '%s' mission creation failed (non-blocking)", officer)
        return None


def search_memory(query: str) -> dict[str, list[dict]]:
    """Search missions and decisions by keyword.

    Args:
        query: Search keyword

    Returns:
        Dict with 'missions' and 'decisions' lists, empty if unavailable.
    """
    client = get_client()

    # SQL ILIKE search on missions.title
    missions = client.select(
        "missions",
        columns="id,title",
        filters={
            "or": f"(title.ilike.%{query}%)",
        },
        limit=5,
    )

    # SQL ILIKE search on command_memory_records.statement
    decisions = client.select(
        "command_memory_records",
        columns="id,statement",
        filters={
            "or": f"(statement.ilike.%{query}%,rationale.ilike.%{query}%)",
            # Excludes owner-prefixed key-value rows (initiative:,
            # dep_link:, ...) from the ~45 EXEC-002A..EXEC-007 writers.
            "owner": "not.like.*:*",
        },
        limit=5,
    )

    log.info(f"[command-memory] Search for '{query}' found {len(missions)} missions, {len(decisions)} decisions")

    return {
        "missions": missions,
        "decisions": decisions,
    }
