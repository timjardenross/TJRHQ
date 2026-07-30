"""Mission Registry memory adapter for advisory-related mission discovery.

This adapter reuses the existing Mission Registry as the canonical mission
source and exposes short, read-only related-mission references for memory-aware
workflows. Failures are non-blocking.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.coordination.memory_metrics import log_memory_metric

log = logging.getLogger(__name__)


@dataclass
class RelatedMission:
    mission_id: str
    title: str
    status: str
    reason: str
    source: str = "mission-registry"
    confidence: float = 0.0


@dataclass
class MissionRegistryMemoryContext:
    found: bool = False
    confidence: float = 0.0
    summary: str = ""
    related_missions: list[RelatedMission] = field(default_factory=list)
    stale_context: bool = False


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[A-Za-z0-9_]+", (text or "").lower()) if len(token) > 2}


def _is_stale(timestamp: Any, days: int = 180) -> bool:
    try:
        if not timestamp:
            return False
        dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        return age > timedelta(days=days)
    except Exception:
        return False


class MissionRegistryMemoryAdapter:
    """Read-only advisory lookup over the canonical Mission Registry."""

    def __init__(self, registry: object | None = None, db_path: str | None = None):
        self.registry = registry
        self.db_path = db_path

    def retrieve_related_missions(
        self,
        *,
        title: str = "",
        objective: str = "",
        tags: list[str] | None = None,
        status: str = "",
        specialist: str = "",
        capability: str = "",
        adr_reference: str = "",
        text: str = "",
        limit: int = 5,
    ) -> MissionRegistryMemoryContext:
        try:
            missions = self._load_missions()
        except Exception as exc:
            log.warning("[mission-registry-memory] load failed: %s", exc)
            log_memory_metric(
                source="mission_registry",
                action="fallback",
                outcome="load_failed",
                confidence=0.0,
                memory_type="mission",
                details={"error": type(exc).__name__},
            )
            return MissionRegistryMemoryContext()

        if not missions:
            return MissionRegistryMemoryContext()

        query_text = " ".join(filter(None, [title, objective, status, specialist, capability, adr_reference, text] + (tags or [])))
        query_tokens = _tokenize(query_text)
        ranked: list[RelatedMission] = []
        best_confidence = 0.0

        for mission in missions:
            score, reasons = self._score_mission(mission, query_tokens, tags or [], title, objective, status, specialist, capability, adr_reference, text)
            if score <= 0:
                continue
            best_confidence = max(best_confidence, score)
            ranked.append(
                RelatedMission(
                    mission_id=mission.get("mission_id") or mission.get("id") or "",
                    title=mission.get("title") or mission.get("name") or "",
                    status=mission.get("status") or "",
                    reason="; ".join(reasons[:3]),
                    confidence=min(score, 1.0),
                )
            )

        ranked.sort(key=lambda item: item.confidence, reverse=True)
        ranked = ranked[: max(limit, 0)]

        if not ranked:
            log_memory_metric(
                source="mission_registry",
                action="related_missions_retrieved",
                outcome="no_match",
                confidence=0.0,
                memory_type="mission",
                details={"result_count": 0},
            )
            return MissionRegistryMemoryContext()

        summary = " | ".join(f"{m.mission_id}:{m.reason}" for m in ranked[:3] if m.reason)
        stale_count = sum(1 for mission in missions if _is_stale(mission.get("updated_at") or mission.get("last_updated") or mission.get("created_at")))
        if stale_count:
            log_memory_metric(
                source="mission_registry",
                action="stale_context_flagged",
                outcome="stale_context_flagged",
                confidence=min(best_confidence, 1.0),
                memory_type="mission",
                details={"stale_count": stale_count, "result_count": len(ranked)},
            )
        log_memory_metric(
            source="mission_registry",
            action="related_missions_retrieved",
            outcome="success" if ranked else "no_match",
            confidence=min(best_confidence, 1.0),
            memory_type="mission",
            details={"result_count": len(ranked)},
        )
        return MissionRegistryMemoryContext(
            found=True,
            confidence=min(best_confidence, 1.0),
            summary=summary + (" | stale context flagged" if stale_count else ""),
            related_missions=ranked,
            stale_context=bool(stale_count),
        )

    def _load_missions(self) -> list[dict[str, Any]]:
        if self.registry is not None:
            if hasattr(self.registry, "list_missions"):
                return list(self.registry.list_missions())
            if hasattr(self.registry, "get_history"):
                return []

        registry = self._build_registry_from_db_path()
        if registry is not None:
            return list(registry.list_missions())

        return self._load_from_files()

    def _build_registry_from_db_path(self):
        # The SQLite mission registry was retired under MSN-EDO-005: it was dead
        # at runtime (db_path was never set by any caller) and one of four
        # competing mission stores. The adapter uses the canonical file/Supabase
        # path via _load_from_files(). Kept as a no-op so any future caller that
        # passes db_path degrades gracefully to the file loader.
        return None

    def _load_from_files(self) -> list[dict[str, Any]]:
        # Fallback is intentionally thin and advisory only.
        candidates: list[dict[str, Any]] = []
        for path in [
            Path(__file__).resolve().parent.parent.parent / "core" / "mission-control" / "registry" / "mission-index.txt",
            Path(__file__).resolve().parent.parent.parent / "Missions" / "Active",
        ]:
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    if "MSN-" in line:
                        candidates.append({"mission_id": line[:32], "title": line[:120], "status": "UNKNOWN"})
            elif path.is_dir():
                for mission_file in sorted(path.glob("*.md")):
                    text = mission_file.read_text(encoding="utf-8", errors="ignore")
                    candidates.append({
                        "mission_id": mission_file.stem,
                        "title": mission_file.stem,
                        "status": "UNKNOWN",
                        "description": text[:500],
                    })
        return candidates

    def _score_mission(
        self,
        mission: dict[str, Any],
        query_tokens: set[str],
        tags: list[str],
        title: str,
        objective: str,
        status: str,
        specialist: str,
        capability: str,
        adr_reference: str,
        text: str,
    ) -> tuple[float, list[str]]:
        reasons: list[str] = []
        haystacks = {
            "title": " ".join(filter(None, [str(mission.get("title") or ""), str(mission.get("name") or "")])).lower(),
            "description": str(mission.get("description") or mission.get("objective") or "").lower(),
            "tags": " ".join(tags).lower(),
            "status": str(mission.get("status") or "").lower(),
            "specialist": str(mission.get("assigned_role") or mission.get("owner") or "").lower(),
            "capability": str(mission.get("capability") or mission.get("domain") or "").lower(),
            "adr": str(mission.get("adr_reference") or mission.get("decision_log") or "").lower(),
            "text": str(text or "").lower(),
        }

        score = 0.0
        overlap_fields = 0
        if title and title.lower() in haystacks["title"]:
            score += 0.25
            overlap_fields += 1
            reasons.append("title overlap")
        if objective and objective.lower() in haystacks["description"]:
            score += 0.22
            overlap_fields += 1
            reasons.append("objective overlap")
        if status and status.lower() == haystacks["status"]:
            score += 0.1
            overlap_fields += 1
            reasons.append("status overlap")
        if specialist and specialist.lower() in haystacks["specialist"]:
            score += 0.1
            overlap_fields += 1
            reasons.append("specialist overlap")
        if capability and capability.lower() in haystacks["capability"]:
            score += 0.1
            overlap_fields += 1
            reasons.append("capability overlap")
        if adr_reference and adr_reference.lower() in haystacks["adr"]:
            score += 0.18
            overlap_fields += 1
            reasons.append("ADR overlap")

        all_text = " ".join(haystacks.values())
        token_hits = sum(1 for token in query_tokens if token in all_text)
        if query_tokens:
            score += min(token_hits / max(len(query_tokens), 1), 1.0) * 0.25
            if token_hits:
                reasons.append("text similarity")

        if not reasons and text and any(token in all_text for token in _tokenize(text)):
            score += 0.2
            reasons.append("fallback text similarity")

        if overlap_fields >= 3:
            score += 0.1
            reasons.append("cross-artifact agreement")
        return min(score, 1.0), reasons
