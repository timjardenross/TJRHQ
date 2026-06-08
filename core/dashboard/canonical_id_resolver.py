"""
Canonical ID Resolution for Dashboard and Queries
Maps legacy IDs to canonical format using mapping layer.
Part of P2b (Identifier Mapping Layer) implementation.
"""

from typing import Optional, Dict, Any
from supabase import create_client


class CanonicalIDResolver:
    """Resolve legacy mission IDs to canonical format (MSN-XXXX, ADR-XXXX, etc.)"""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize resolver with Supabase client."""
        self.supabase = create_client(supabase_url, supabase_key)

    def get_canonical_id(self, mission_id: str) -> str:
        """
        Resolve legacy ID to canonical format.

        Args:
            mission_id: Either legacy (M-05) or canonical (MSN-0005)

        Returns:
            Canonical ID (MSN-XXXX format), or original if not found
        """
        try:
            result = (
                self.supabase.table("missions")
                .select("legacy_id_map")
                .eq("mission_id", mission_id)
                .single()
                .execute()
            )

            if result.data and result.data.get("legacy_id_map"):
                canonical = result.data["legacy_id_map"].get("canonical_id")
                return canonical if canonical else mission_id

            return mission_id

        except Exception as e:
            # Graceful degradation: return original ID if lookup fails
            print(f"[WARN] Canonical ID resolution failed for {mission_id}: {e}")
            return mission_id

    def list_missions_normalized(self, limit: int = 50) -> list:
        """
        List missions with normalized display IDs.

        Returns:
            List of missions with 'display_id' field set to canonical format
        """
        try:
            result = (
                self.supabase.table("missions")
                .select(
                    """
                    mission_id,
                    title,
                    status,
                    legacy_id_map
                    """
                )
                .limit(limit)
                .execute()
            )

            # Add computed display_id to each record
            for mission in result.data:
                canonical = (
                    mission.get("legacy_id_map", {}).get("canonical_id")
                    if mission.get("legacy_id_map")
                    else None
                )
                mission["display_id"] = canonical or mission["mission_id"]

            return result.data

        except Exception as e:
            print(f"[ERROR] Failed to list missions: {e}")
            return []

    def search_by_id(self, search_id: str) -> Optional[Dict[str, Any]]:
        """
        Search for mission by either legacy or canonical ID.

        Args:
            search_id: Can be M-05 (legacy) or MSN-0005 (canonical)

        Returns:
            Mission record with display_id, or None if not found
        """
        try:
            # Query: direct match OR mapping array contains
            result = (
                self.supabase.table("missions")
                .select("*")
                .or_(
                    f"mission_id.eq.{search_id},"
                    f"legacy_id_map->'legacy_ids'.cs.\"{search_id}\""
                )
                .single()
                .execute()
            )

            if result.data:
                mission = result.data
                canonical = (
                    mission.get("legacy_id_map", {}).get("canonical_id")
                    if mission.get("legacy_id_map")
                    else None
                )
                mission["display_id"] = canonical or mission["mission_id"]
                return mission

            return None

        except Exception as e:
            print(f"[WARN] Search failed for {search_id}: {e}")
            return None

    def get_missions_by_status(
        self, status: str, limit: int = 50
    ) -> list:
        """
        List missions by status with normalized IDs.

        Args:
            status: Mission status (e.g., 'Validated', 'Closed')
            limit: Result limit

        Returns:
            List of missions with display_id normalized
        """
        try:
            result = (
                self.supabase.table("missions")
                .select("*")
                .eq("status", status)
                .limit(limit)
                .execute()
            )

            for mission in result.data:
                canonical = (
                    mission.get("legacy_id_map", {}).get("canonical_id")
                    if mission.get("legacy_id_map")
                    else None
                )
                mission["display_id"] = canonical or mission["mission_id"]

            return result.data

        except Exception as e:
            print(f"[ERROR] Failed to get missions by status {status}: {e}")
            return []
