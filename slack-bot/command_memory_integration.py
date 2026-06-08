"""MSN-0040A: Command Memory Integration — Supabase client for capability tracking.

This module provides non-blocking Supabase integration for:
- Mission creation logging
- Decision logging
- Mission status updates
- Capability query commands

All operations are non-blocking: Supabase failures do not crash Slack Commander.
"""

import logging
import os
from typing import Optional, List, Dict, Any

try:
    from supabase import create_client, Client
except ImportError:
    # Graceful degradation if supabase not installed
    create_client = None
    Client = None

log = logging.getLogger(__name__)

# Singleton pattern for connection efficiency
_supabase_client: Optional[Any] = None


def get_supabase_client() -> Optional[Any]:
    """Get or create Supabase client (singleton)."""
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    # Check if Supabase is configured
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        log.debug("Supabase not configured (SUPABASE_URL or SUPABASE_ANON_KEY missing)")
        return None

    if create_client is None:
        log.warning("supabase-py not installed; Command Memory unavailable")
        return None

    try:
        _supabase_client = create_client(url, key)
        log.info("✅ Supabase client initialized")
        return _supabase_client
    except Exception as e:
        log.warning(f"Failed to initialize Supabase client: {e}")
        return None


def save_mission_to_memory(
    mission_id: str,
    title: str,
    status: str = "draft",
    user_id: str = "slack-bot",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Save mission to Supabase (non-blocking).

    Args:
        mission_id: Mission ID (e.g., 'M-20260608-120000')
        title: Mission title
        status: Mission status (e.g., 'draft', 'active', 'completed')
        user_id: User who created the mission
        metadata: Optional metadata dict (ignored; not in schema)

    Returns:
        True if successful, False if failed (non-blocking)
    """
    client = get_supabase_client()
    if not client:
        return False

    try:
        data = {
            "id": mission_id,
            "title": title,
            "status": status,
            "created_by": user_id,
            "owner": user_id,
        }
        client.table("missions").insert(data).execute()
        log.debug(f"[command-memory] Mission saved: {mission_id}")
        return True
    except Exception as e:
        log.warning(f"[command-memory] Failed to save mission {mission_id}: {e}")
        return False


def save_decision_to_memory(
    decision_text: str,
    status: str = "proposed",
    user_id: str = "slack-bot",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Save decision to Supabase (non-blocking).

    Args:
        decision_text: Decision statement
        status: Decision status (e.g., 'proposed', 'accepted')
        user_id: User who logged the decision
        metadata: Optional metadata dict (ignored; not in schema)

    Returns:
        True if successful, False if failed (non-blocking)
    """
    client = get_supabase_client()
    if not client:
        return False

    try:
        data = {
            "statement": decision_text,
            "status": status,
            "created_by": user_id,
            "owner": user_id,
        }
        client.table("decisions").insert(data).execute()
        log.debug(f"[command-memory] Decision saved")
        return True
    except Exception as e:
        log.warning(f"[command-memory] Failed to save decision: {e}")
        return False


def update_mission_status_in_memory(
    mission_id: str,
    new_status: str,
    user_id: str = "slack-bot",
) -> bool:
    """Update mission status in Supabase (non-blocking).

    Args:
        mission_id: Mission ID to update
        new_status: New status value
        user_id: User making the update

    Returns:
        True if successful, False if failed (non-blocking)
    """
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table("missions").update(
            {"status": new_status, "updated_by": user_id}
        ).eq("mission_id", mission_id).execute()
        log.debug(f"[command-memory] Mission status updated: {mission_id} → {new_status}")
        return True
    except Exception as e:
        log.warning(f"[command-memory] Failed to update mission {mission_id}: {e}")
        return False


def get_active_missions() -> List[Dict[str, Any]]:
    """Query active missions from Supabase (non-blocking).

    Returns:
        List of missions with status='active', or empty list if unavailable
    """
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = (
            client.table("missions")
            .select("*")
            .eq("status", "active")
            .limit(5)
            .execute()
        )
        return result.data or []
    except Exception as e:
        log.debug(f"[command-memory] Failed to query active missions: {e}")
        return []


def get_active_decisions() -> List[Dict[str, Any]]:
    """Query active decisions from Supabase (non-blocking).

    Returns:
        List of decisions, or empty list if unavailable
    """
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = (
            client.table("decisions")
            .select("*")
            .limit(5)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        log.debug(f"[command-memory] Failed to query decisions: {e}")
        return []


def search_memory(query: str) -> List[Dict[str, Any]]:
    """Full-text search over missions and decisions (non-blocking).

    Args:
        query: Search query string

    Returns:
        List of matching results, or empty list if unavailable
    """
    client = get_supabase_client()
    if not client:
        return []

    try:
        # Search missions
        missions = (
            client.table("missions")
            .select("*")
            .ilike("title", f"%{query}%")
            .limit(3)
            .execute()
        )

        # Search decisions
        decisions = (
            client.table("decisions")
            .select("*")
            .ilike("decision_text", f"%{query}%")
            .limit(2)
            .execute()
        )

        results = (missions.data or []) + (decisions.data or [])
        log.debug(f"[command-memory] Search query '{query}' returned {len(results)} results")
        return results
    except Exception as e:
        log.debug(f"[command-memory] Search failed for query '{query}': {e}")
        return []
