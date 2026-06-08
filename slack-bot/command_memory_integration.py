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
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


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
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else None
        except urllib.error.HTTPError as e:
            # Surface the PostgREST error body (e.g. constraint violation,
            # missing column) so failures are diagnosable in logs.
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            log.error(
                f"[command-memory] HTTP {e.code} ({method} {path}): {detail}"
            )
            return None
        except Exception as e:
            log.error(f"[command-memory] Request failed ({method} {path}): {e}")
            return None

    def insert(self, table: str, record: dict[str, Any]) -> bool:
        """Insert a single record into Command Memory table.

        Uses ``Prefer: return=representation`` so PostgREST echoes the inserted
        row back — without it Supabase returns an empty body and a successful
        write is indistinguishable from a failure.
        """
        if not self._initialized:
            return False

        result = self.request(
            "POST",
            f"/rest/v1/{table}",
            record,
            extra_headers={"Prefer": "return=representation"},
        )
        if result:
            log.info(f"[command-memory] Inserted into {table}: {record.get('id', 'unknown')}")
            return True
        log.warning(f"[command-memory] Insert into {table} failed (non-blocking)")
        return False

    def update(self, table: str, record_id: str, updates: dict[str, Any]) -> bool:
        """Update a record in Command Memory table.

        Returns True only if a matching row was updated. ``return=representation``
        makes PostgREST echo the affected rows, so an update against a missing id
        returns an empty list and is correctly reported as a failure.
        """
        if not self._initialized:
            return False

        import urllib.parse

        path = f"/rest/v1/{table}?id=eq.{urllib.parse.quote(record_id)}"
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
        except Exception as e:
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
) -> bool:
    """Save a mission to Command Memory (non-blocking).

    Args:
        mission_id: Unique mission identifier (M-YYYYMMDD-HHMMSS)
        title: Mission title
        created_by: Slack user ID of mission creator
        owner: Mission owner (defaults to creator)

    Returns:
        True if write succeeded, False otherwise (non-blocking failure).
    """
    if owner is None:
        owner = created_by

    client = get_client()
    record = {
        "id": mission_id,
        "title": title,
        "created_by": created_by,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "Draft",
        "owner": owner,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": created_by,
    }

    success = client.insert("missions", record)
    if success:
        log.info(f"[command-memory] Mission {mission_id} saved to Command Memory")
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
    decision_id = f"DEC-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    record = {
        "id": decision_id,
        "statement": statement,
        "rationale": rationale,
        "created_by": owner,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "owner": owner,
        "status": "Active",
        "alternatives": None,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": owner,
    }

    success = client.insert("decisions", record)
    if success:
        log.info(f"[command-memory] Decision {decision_id} logged to Command Memory")
        return decision_id
    else:
        log.warning(f"[command-memory] Failed to log decision (non-blocking)")
        return None


def update_mission_status_in_command_memory(
    mission_id: str,
    new_status: str,
    user_id: str,
) -> bool:
    """Update mission status in Command Memory (non-blocking).

    Args:
        mission_id: Mission ID to update
        new_status: New status (Draft|Planned|Active|Blocked|Review|Completed)
        user_id: Slack user ID making the update

    Returns:
        True if update succeeded, False otherwise (non-blocking failure).
    """
    from datetime import datetime

    client = get_client()
    updates = {
        "status": new_status,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": user_id,
    }

    success = client.update("missions", mission_id, updates)
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
        columns="id,title,owner,created_at",
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
        "decisions",
        columns="id,statement,owner,created_at",
        filters={"status": "eq.Active"},
        limit=5,
    )
    if results:
        log.info(f"[command-memory] Retrieved {len(results)} active decisions")
    return results


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

    # SQL ILIKE search on decisions.statement
    decisions = client.select(
        "decisions",
        columns="id,statement",
        filters={
            "or": f"(statement.ilike.%{query}%,rationale.ilike.%{query}%)",
        },
        limit=5,
    )

    log.info(f"[command-memory] Search for '{query}' found {len(missions)} missions, {len(decisions)} decisions")

    return {
        "missions": missions,
        "decisions": decisions,
    }
