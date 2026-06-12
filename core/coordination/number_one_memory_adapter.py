"""Number One memory adapter for advisory-only historical context retrieval.

This reuses the ADR-006 Supabase memory pattern without changing governance or
assignment authority. Retrieval failures are non-blocking.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.coordination.advisory_memory_formatter import format_memory_block
from core.coordination.memory_metrics import log_memory_metric

log = logging.getLogger(__name__)

try:
    from core.coordination.mission_registry_memory_adapter import (
        MissionRegistryMemoryAdapter,
        MissionRegistryMemoryContext,
        RelatedMission,
    )
except Exception:  # pragma: no cover - advisory-only fallback
    MissionRegistryMemoryAdapter = None
    MissionRegistryMemoryContext = None
    RelatedMission = None

try:
    from core.coordination.decision_registry_memory_adapter import (
        DecisionRegistryMemoryAdapter,
        DecisionRegistryMemoryContext,
        RelatedDecision,
    )
except Exception:  # pragma: no cover - advisory-only fallback
    DecisionRegistryMemoryAdapter = None
    DecisionRegistryMemoryContext = None
    RelatedDecision = None


@dataclass
class MemoryContext:
    found: bool = False
    confidence: float = 0.0
    summary: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    duplicates: list[dict[str, str]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def _build_supabase_client():
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if client.is_enabled():
            return client
    except Exception as exc:
        log.warning("[number-one-memory] Supabase client unavailable: %s", exc)
    return None


def _compute_query_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


class NumberOneMemoryAdapter:
    """Read-only advisory memory for Number One."""

    def __init__(self, repo_root: Path | None = None):
        self.repo_root = repo_root or Path(__file__).resolve().parent.parent.parent
        self.supabase = _build_supabase_client()
        self.mission_registry_memory = MissionRegistryMemoryAdapter() if MissionRegistryMemoryAdapter else None
        self.decision_registry_memory = DecisionRegistryMemoryAdapter(self.supabase, self.repo_root) if DecisionRegistryMemoryAdapter else None

    def retrieve_context(self, missions: list[dict[str, Any]], routing_results: dict[str, Any] | None = None) -> MemoryContext:
        queries = self._build_queries(missions, routing_results or {})
        sources = []
        duplicates = []
        snippets = []
        confidence = 0.0

        for query_type, query_text in queries:
            if not query_text:
                continue
            retrieved = self._retrieve_from_supabase(query_type, query_text)
            for item in retrieved:
                sources.append(item)
                snippets.append(item.get("summary", ""))
                confidence = max(confidence, float(item.get("confidence", 0.0) or 0.0))
                if item.get("duplicate", False):
                    duplicates.append(item)

        registry_context = self._retrieve_mission_registry_context(missions, routing_results or {})
        if registry_context and registry_context.found:
            confidence = max(confidence, registry_context.confidence)
            for related in registry_context.related_missions:
                sources.append({
                    "source_type": "mission_registry",
                    "source_id": related.mission_id,
                    "source": "mission-registry",
                    "summary": f"{related.mission_id} {related.title} [{related.status}]",
                    "confidence": related.confidence,
                    "duplicate": "duplicate" in related.reason.lower() or "overlap" in related.reason.lower(),
                })
                snippets.append(f"{related.mission_id}: {related.reason}")
                if "duplicate" in related.reason.lower() or "overlap" in related.reason.lower():
                    duplicates.append({"source_type": "mission_registry", "source_id": related.mission_id, "summary": related.reason})
            log_memory_metric(
                source="number_one",
                action="mission_registry_context_used",
                outcome="duplicate_warning" if duplicates else "success",
                confidence=registry_context.confidence,
                memory_type="mission",
                details={"result_count": len(registry_context.related_missions)},
            )
            if getattr(registry_context, "stale_context", False):
                snippets.append("stale context flagged")

        decision_context = self._retrieve_decision_registry_context(missions, routing_results or {})
        if decision_context and decision_context.found:
            confidence = max(confidence, decision_context.confidence)
            for related in decision_context.related_decisions:
                sources.append({
                    "source_type": "decision_registry",
                    "source_id": related.decision_id,
                    "source": related.source,
                    "summary": f"{related.decision_id} [{related.status}] {related.summary}",
                    "confidence": related.confidence,
                    "duplicate": related.conflict,
                    "lineage": related.lineage,
                })
                if related.conflict:
                    duplicates.append({
                        "source_type": "decision_registry",
                        "source_id": related.decision_id,
                        "summary": related.reason,
                    })
                snippets.append(f"{related.decision_id}: {related.reason}")
            log_memory_metric(
                source="number_one",
                action="decision_registry_context_used",
                outcome="conflict" if getattr(decision_context, "conflict_warnings", []) else "success",
                confidence=decision_context.confidence,
                memory_type="decision",
                details={
                    "result_count": len(decision_context.related_decisions),
                    "conflict_count": len(getattr(decision_context, "conflict_warnings", []) or []),
                },
            )
            if getattr(decision_context, "stale_context", False):
                snippets.append("stale context flagged")

        if not sources:
            return MemoryContext()

        summary = self._format_summary(snippets, sources)
        recommendations = self._build_recommendations(duplicates, sources)
        return MemoryContext(
            found=True,
            confidence=min(confidence, 1.0),
            summary=summary,
            sources=sources,
            duplicates=duplicates,
            recommendations=recommendations,
        )

    def persist_brief(self, brief: dict[str, Any]) -> bool:
        if self.supabase is None:
            return False
        try:
            payload = {
                "id": brief.get("brief_id") or f"NUM1-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "mission_id": brief.get("mission_id") or "",
                "summary": brief.get("summary") or "",
                "recommendations": brief.get("recommendations") or [],
                "confidence": float(brief.get("confidence") or 0.0),
                "query_hash": _compute_query_hash(brief.get("summary", "") + str(brief.get("mission_id", ""))),
                "created_at": datetime.utcnow().isoformat(),
                "source": "number-one",
            }
            result = self.supabase.insert("number_one_memory", payload)
            return bool(result.ok)
        except Exception as exc:
            log.warning("[number-one-memory] persist failed: %s", exc)
            return False

    def _build_queries(self, missions: list[dict[str, Any]], routing_results: dict[str, Any]) -> list[tuple[str, str]]:
        queries: list[tuple[str, str]] = []
        mission_titles = [str(m.get("title") or m.get("mission_id") or "") for m in missions[:10]]
        active_statuses = [str(m.get("status") or "") for m in missions[:10]]
        queue_terms = " ".join(filter(None, mission_titles + active_statuses))
        if queue_terms:
            queries.append(("missions", queue_terms))
        queries.append(("adr", "ADR Number One assignment authority governance memory duplicate work prevention"))
        queries.append(("decisions", "number one decisions approvals rejections escalations"))
        queries.append(("capabilities", "knowledge retrieval governance operations orchestration"))
        queries.append(("research_memory", "research reuse historical context"))
        return queries

    def _retrieve_from_supabase(self, query_type: str, query_text: str) -> list[dict[str, Any]]:
        if self.supabase is None:
            return self._retrieve_from_files(query_type, query_text)
        try:
            query_hash = _compute_query_hash(query_text)
            if query_type == "research_memory":
                response = (
                    self.supabase.table("research_memory")
                    .select("*")
                    .gt("created_at", (datetime.utcnow() - timedelta(days=180)).isoformat())
                    .limit(5)
                    .execute()
                )
                return [self._normalize_row(row, "research_memory") for row in (response.data or [])]

            if query_type == "missions":
                response = self.supabase.table("missions").select("*").limit(10).execute()
                return [self._normalize_row(row, "mission") for row in (response.data or [])]

            if query_type == "decisions":
                response = self.supabase.table("decision_records").select("*").limit(10).execute()
                return [self._normalize_row(row, "decision") for row in (response.data or [])]

            if query_type == "capabilities":
                response = self.supabase.table("capabilities").select("*").limit(10).execute()
                return [self._normalize_row(row, "capability") for row in (response.data or [])]

            if query_type == "adr":
                response = self.supabase.table("architecture_records").select("*").limit(10).execute()
                return [self._normalize_row(row, "adr") for row in (response.data or [])]

            return []
        except Exception as exc:
            log.warning("[number-one-memory] Supabase retrieval failed: %s", exc)
            return self._retrieve_from_files(query_type, query_text)

    def _retrieve_from_files(self, query_type: str, query_text: str) -> list[dict[str, Any]]:
        text = query_text.lower()
        results: list[dict[str, Any]] = []
        files = {
            "adr": [
                self.repo_root / "core" / "governance" / "architecture-decision-records" / "ADR-004-Knowledge-Architecture.txt",
                self.repo_root / "core" / "governance" / "architecture-decision-records" / "ADR-006-Supabase-Memory-Layer-Architecture.txt",
            ],
            "capabilities": [
                self.repo_root / "core" / "product" / "capabilities" / "CAP-003-Knowledge-Retrieval-Capability.txt",
            ],
        }.get(query_type, [])
        for file_path in files:
            content = _load_text(file_path)
            if not content:
                continue
            if any(term in content.lower() for term in text.split()[:6]):
                results.append({
                    "source": str(file_path),
                    "summary": content.splitlines()[0][:200] if content.splitlines() else file_path.name,
                    "confidence": 0.5,
                    "duplicate": False,
                })
        return results

    def _normalize_row(self, row: dict[str, Any], source_type: str) -> dict[str, Any]:
        summary = row.get("summary") or row.get("consolidated_findings") or row.get("recommendation") or row.get("title") or ""
        if not summary and row.get("original_question"):
            summary = row["original_question"]
        duplicates = str(row.get("title") or row.get("mission_id") or "").lower()
        return {
            "source_type": source_type,
            "source_id": row.get("id") or row.get("mission_id") or row.get("decision_id") or "",
            "source": row.get("source") or source_type,
            "summary": summary[:500],
            "confidence": float(row.get("confidence_level") or row.get("confidence") or 0.0),
            "duplicate": "duplicate" in duplicates or "repeated" in duplicates,
        }

    def _build_recommendations(self, duplicates: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[str]:
        recommendations = []
        if duplicates:
            recommendations.append("Check related missions before creating a new item")
        if any(item.get("source_type") == "adr" for item in sources):
            recommendations.append("Reference existing ADRs before proposing a new approach")
        if any(item.get("source_type") == "capability" for item in sources):
            recommendations.append("Reuse existing capability rather than building a duplicate")
        if any(item.get("source_type") == "mission_registry" for item in sources):
            recommendations.append("Review related missions for overlap before recommending new work")
        if any(item.get("source_type") == "decision_registry" for item in sources):
            recommendations.append("Review related decisions and lineage before changing course")
        return recommendations

    def _format_summary(self, snippets: list[str], sources: list[dict[str, Any]]) -> str:
        summary_parts = [snippet for snippet in snippets if snippet][:3]
        summary = " | ".join(summary_parts)
        source_types: list[str] = []
        for source_type in ("mission_registry", "decision_registry", "adr", "capability", "research_memory"):
            if any(item.get("source_type") == source_type for item in sources):
                source_types.append(source_type.replace("_", " "))
        return format_memory_block(
            label="Memory context",
            items=[
                {"summary": part}
                for part in summary_parts
            ],
            source_types=source_types,
            summary=summary,
            confidence=confidence_for_summary(sources),
        )[:500]

    def _stale_context_flags(self, sources: list[dict[str, Any]]) -> list[str]:
        flags: list[str] = []
        for item in sources:
            if item.get("source_type") in {"mission_registry", "decision_registry", "research_memory", "adr", "capability"}:
                summary = str(item.get("summary") or "")
                if "old" in summary.lower() or "stale" in summary.lower():
                    flags.append("stale context flagged")
        return flags

    def _retrieve_mission_registry_context(self, missions: list[dict[str, Any]], routing_results: dict[str, Any]) -> Any:
        if not self.mission_registry_memory:
            return None
        try:
            titles = [str(m.get("title") or "") for m in missions if m.get("title")]
            objectives = [str(m.get("description") or m.get("objective") or "") for m in missions if m.get("description") or m.get("objective")]
            status = str(missions[0].get("status") or "") if missions else ""
            specialist = str(missions[0].get("assigned_role") or "") if missions else ""
            capability = str(missions[0].get("capability") or missions[0].get("domain") or "") if missions else ""
            adr_reference = str(missions[0].get("adr_reference") or "") if missions else ""
            text = " ".join(filter(None, titles + objectives))
            return self.mission_registry_memory.retrieve_related_missions(
                title=" ".join(titles[:3]),
                objective=" ".join(objectives[:3]),
                tags=list(routing_results.keys())[:5] if routing_results else [],
                status=status,
                specialist=specialist,
                capability=capability,
                adr_reference=adr_reference,
                text=text,
                limit=5,
            )
        except Exception as exc:
            log.warning("[number-one-memory] mission registry retrieval failed: %s", exc)
            return None

    def _retrieve_decision_registry_context(self, missions: list[dict[str, Any]], routing_results: dict[str, Any]) -> Any:
        if not self.decision_registry_memory:
            return None
        try:
            titles = [str(m.get("title") or "") for m in missions if m.get("title")]
            objectives = [str(m.get("description") or m.get("objective") or "") for m in missions if m.get("description") or m.get("objective")]
            status = str(missions[0].get("status") or "") if missions else ""
            specialist = str(missions[0].get("assigned_role") or "") if missions else ""
            capability = str(missions[0].get("capability") or missions[0].get("domain") or "") if missions else ""
            adr_reference = str(missions[0].get("adr_reference") or missions[0].get("decision_log") or "") if missions else ""
            text = " ".join(filter(None, titles + objectives))
            return self.decision_registry_memory.retrieve_related_decisions(
                title=" ".join(titles[:3]),
                objective=" ".join(objectives[:3]),
                tags=list(routing_results.keys())[:5] if routing_results else [],
                status=status,
                decision_type=str(routing_results.get("intent") or "") if routing_results else "",
                mission_id=str(missions[0].get("mission_id") or missions[0].get("id") or "") if missions else "",
                adr_reference=adr_reference,
                capability=capability,
                text=text,
                limit=5,
            )
        except Exception as exc:
            log.warning("[number-one-memory] decision registry retrieval failed: %s", exc)
            return None


def confidence_for_summary(sources: list[dict[str, Any]]) -> float | None:
    if not sources:
        return None
    confidence_values = [float(item.get("confidence", 0.0) or 0.0) for item in sources if item.get("confidence") is not None]
    if not confidence_values:
        return None
    avg_conf = sum(confidence_values) / len(confidence_values)
    if avg_conf < 0.6:
        return None
    return min(avg_conf, 1.0)
