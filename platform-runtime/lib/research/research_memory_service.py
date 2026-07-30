#!/usr/bin/env python3
"""
Research Memory Service — Evidence Storage & Deduplication

Stores research results and tracks reuse. Uses query hash for deduplication
to enable cache hits on similar queries. Integrates with Learning Loop
to support quality scoring and adaptive routing.

Architecture:
    EvidencePack (from TaskExecutor)
        ↓
    ResearchMemoryService (THIS)
        ├─ Compute query hash
        ├─ Store evidence in Supabase
        ├─ Track reuse metrics
        └─ Enable future retrieval
        ↓
    Quality Scoring Service (MSN-0060B B1C)
        ↓
    Adaptive Routing (MSN-0060B B1A)

Provider-Agnostic Design:
    - Stores ONLY EvidencePack.to_dict()
    - Provider type is opaque (just a string)
    - Quality metrics are provider-independent
    - Learning Loop uses only EvidencePack fields
"""

from __future__ import annotations

import os
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

log = logging.getLogger(__name__)


# =====================================================================
# Research Memory Service
# =====================================================================


class ResearchMemoryService:
    """
    Store and retrieve research evidence with deduplication.

    Features:
    - Stores all EvidencePack objects
    - Query hash deduplication
    - Reuse tracking for analytics
    - Learning Loop integration
    - Quality score persistence

    Example:
        memory = ResearchMemoryService(supabase_client)
        memory.store_evidence(evidence_pack, query_hash)
        cached = memory.find_by_query_hash(query_hash)
        memory.record_reuse(query_hash)
    """

    def __init__(self, supabase_client: object):
        """
        Initialize Research Memory Service.

        Args:
            supabase_client: Supabase client instance
        """
        self.client = supabase_client
        self.table_name = "research_evidence"
        self.hits_table_name = "research_memory_hits"

        log.info("[research-memory] Service initialized")

    def store_evidence(
        self,
        evidence_pack: object,  # EvidencePack
        query_hash: str,
    ) -> bool:
        """
        Store evidence pack in Research Memory.

        Args:
            evidence_pack: EvidencePack to store
            query_hash: SHA256 hash of research query

        Returns:
            True if stored successfully
        """
        try:
            # Convert to dict
            data = evidence_pack.to_dict() if hasattr(evidence_pack, "to_dict") else {}

            # Add memory metadata
            data["query_hash"] = query_hash
            data["stored_at"] = datetime.utcnow().isoformat()

            # Store in Supabase
            response = self.client.table(self.table_name).insert(data).execute()

            log.info(
                f"[research-memory] Stored evidence: "
                f"task_id={data.get('task_id')}, "
                f"query_hash={query_hash[:8]}..."
            )

            return True

        except Exception as e:
            log.error(
                f"[research-memory] Failed to store evidence: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return False

    def find_by_query_hash(
        self,
        query_hash: str,
    ) -> Optional[object]:
        """
        Find cached evidence by query hash.

        Args:
            query_hash: SHA256 hash of research query

        Returns:
            EvidencePack if found, None otherwise
        """
        try:
            response = (
                self.client.table(self.table_name)
                .select("*")
                .eq("query_hash", query_hash)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if response.data and len(response.data) > 0:
                data = response.data[0]
                log.info(
                    f"[research-memory] Cache hit: "
                    f"query_hash={query_hash[:8]}..., "
                    f"age={self._age_in_hours(data.get('created_at'))}h"
                )
                # TODO: Convert dict back to EvidencePack
                # For now, return dict
                return data

            return None

        except Exception as e:
            log.warning(
                f"[research-memory] Lookup failed: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return None

    def find_by_mission(
        self,
        mission_id: str,
    ) -> List[object]:
        """
        Find all evidence from a mission.

        Args:
            mission_id: Mission identifier

        Returns:
            List of EvidencePack dicts
        """
        try:
            response = (
                self.client.table(self.table_name)
                .select("*")
                .eq("mission_id", mission_id)
                .order("task_index", desc=False)
                .execute()
            )

            results = response.data or []

            log.info(
                f"[research-memory] Found {len(results)} evidence packs "
                f"for mission {mission_id}"
            )

            return results

        except Exception as e:
            log.warning(
                f"[research-memory] Mission lookup failed: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return []

    def record_reuse(
        self,
        query_hash: str,
    ) -> bool:
        """
        Record that cached evidence was reused.

        Args:
            query_hash: SHA256 hash of research query

        Returns:
            True if recorded successfully
        """
        try:
            # Check if hit record exists
            response = (
                self.client.table(self.hits_table_name)
                .select("*")
                .eq("query_hash", query_hash)
                .execute()
            )

            if response.data and len(response.data) > 0:
                # Update existing record
                hit = response.data[0]
                self.client.table(self.hits_table_name).update(
                    {"reuse_count": (hit.get("reuse_count", 0) or 0) + 1}
                ).eq("query_hash", query_hash).execute()
            else:
                # Create new record
                self.client.table(self.hits_table_name).insert(
                    {
                        "query_hash": query_hash,
                        "reused_at": datetime.utcnow().isoformat(),
                        "reuse_count": 1,
                    }
                ).execute()

            log.info(
                f"[research-memory] Recorded reuse: "
                f"query_hash={query_hash[:8]}..."
            )

            return True

        except Exception as e:
            log.warning(
                f"[research-memory] Failed to record reuse: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return False

    def get_hit_metrics(self) -> Dict[str, Any]:
        """
        Get cache hit metrics for analytics.

        Returns:
            Dict with hit statistics
        """
        try:
            response = (
                self.client.table(self.hits_table_name)
                .select("*")
                .execute()
            )

            hits = response.data or []

            total_reuses = sum(hit.get("reuse_count", 0) or 0 for hit in hits)
            unique_queries = len(hits)

            metrics = {
                "unique_queries_cached": unique_queries,
                "total_reuses": total_reuses,
                "average_reuses_per_query": (
                    total_reuses / unique_queries if unique_queries > 0 else 0
                ),
                "cost_savings_estimate": f"{total_reuses * 2}s"
                # Each reuse saves ~2 seconds vs fresh research
            }

            log.info(
                f"[research-memory] Metrics: "
                f"{unique_queries} cached queries, "
                f"{total_reuses} total reuses"
            )

            return metrics

        except Exception as e:
            log.warning(
                f"[research-memory] Metrics retrieval failed: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return {}

    def _age_in_hours(self, created_at: str) -> int:
        """Calculate age of evidence in hours."""
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age = datetime.utcnow() - created
            return int(age.total_seconds() / 3600)
        except Exception:
            return 0
