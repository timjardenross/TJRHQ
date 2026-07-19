"""Decision Registry memory adapter for advisory decision awareness.

This adapter reuses existing decision records and decision-log artifacts as the
canonical decision source. It only surfaces short related-decision references,
lineage hints, and conflict warnings. Failures are non-blocking.
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
class RelatedDecision:
    decision_id: str
    status: str
    summary: str
    reason: str
    source: str = "decision-registry"
    confidence: float = 0.0
    lineage: str = ""
    conflict: bool = False


@dataclass
class DecisionRegistryMemoryContext:
    found: bool = False
    confidence: float = 0.0
    summary: str = ""
    related_decisions: list[RelatedDecision] = field(default_factory=list)
    conflict_warnings: list[str] = field(default_factory=list)
    stale_context: bool = False


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[A-Za-z0-9_]+", (text or "").lower()) if len(token) > 2}


def _shorten(text: str, limit: int = 220) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _is_stale(timestamp: Any, days: int = 365) -> bool:
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


class DecisionRegistryMemoryAdapter:
    """Read-only advisory lookup over canonical decision records."""

    def __init__(self, supabase: object | None = None, repo_root: Path | None = None):
        self.supabase = supabase
        self.repo_root = repo_root or Path(__file__).resolve().parent.parent.parent

    def retrieve_related_decisions(
        self,
        *,
        title: str = "",
        objective: str = "",
        tags: list[str] | None = None,
        status: str = "",
        decision_type: str = "",
        mission_id: str = "",
        adr_reference: str = "",
        capability: str = "",
        text: str = "",
        limit: int = 5,
    ) -> DecisionRegistryMemoryContext:
        try:
            decisions = self._load_decisions()
        except Exception as exc:
            log.warning("[decision-registry-memory] load failed: %s", exc)
            log_memory_metric(
                source="decision_registry",
                action="fallback",
                outcome="load_failed",
                confidence=0.0,
                memory_type="decision",
                details={"error": type(exc).__name__},
            )
            return DecisionRegistryMemoryContext()

        if not decisions:
            return DecisionRegistryMemoryContext()

        query_text = " ".join(filter(None, [title, objective, status, decision_type, mission_id, adr_reference, capability, text] + (tags or [])))
        query_tokens = _tokenize(query_text)
        ranked: list[RelatedDecision] = []
        best_confidence = 0.0
        conflict_warnings: list[str] = []

        for decision in decisions:
            score, reasons, conflict, lineage = self._score_decision(
                decision,
                query_tokens,
                tags or [],
                title,
                objective,
                status,
                decision_type,
                mission_id,
                adr_reference,
                capability,
                text,
            )
            if score <= 0:
                continue
            best_confidence = max(best_confidence, score)
            related = RelatedDecision(
                decision_id=decision.get("decision_id") or decision.get("id") or "",
                status=decision.get("status") or decision.get("human_decision") or "",
                summary=self._summarize_decision(decision),
                reason="; ".join(reasons[:3]),
                confidence=min(score, 1.0),
                lineage=lineage,
                conflict=conflict,
            )
            ranked.append(related)
            if conflict:
                conflict_warnings.append(f"{related.decision_id}: {related.reason}")

        ranked.sort(key=lambda item: item.confidence, reverse=True)
        ranked = ranked[: max(limit, 0)]

        if not ranked:
            log_memory_metric(
                source="decision_registry",
                action="related_decisions_retrieved",
                outcome="no_match",
                confidence=0.0,
                memory_type="decision",
                details={"result_count": 0},
            )
            return DecisionRegistryMemoryContext()

        summary = " | ".join(
            f"{item.decision_id}:{item.status or 'UNKNOWN'}:{item.reason}"
            for item in ranked[:3]
            if item.decision_id
        )
        stale_count = sum(1 for decision in decisions if _is_stale(decision.get("decision_timestamp") or decision.get("captured_timestamp") or decision.get("created_at")))
        if stale_count:
            log_memory_metric(
                source="decision_registry",
                action="stale_context_flagged",
                outcome="stale_context_flagged",
                confidence=min(best_confidence, 1.0),
                memory_type="decision",
                details={"stale_count": stale_count, "result_count": len(ranked)},
            )
        log_memory_metric(
            source="decision_registry",
            action="related_decisions_retrieved",
            outcome="conflict" if conflict_warnings else "success",
            confidence=min(best_confidence, 1.0),
            memory_type="decision",
            details={"result_count": len(ranked), "conflict_count": len(conflict_warnings)},
        )
        return DecisionRegistryMemoryContext(
            found=True,
            confidence=min(best_confidence, 1.0),
            summary=summary + (" | stale context flagged" if stale_count else ""),
            related_decisions=ranked,
            conflict_warnings=conflict_warnings[:3],
            stale_context=bool(stale_count),
        )

    def _load_decisions(self) -> list[dict[str, Any]]:
        if self.supabase is not None:
            for table in ("decision_records", "commander_decisions"):
                try:
                    response = self.supabase.table(table).select("*").limit(25).execute()
                    rows = list(response.data or [])
                    if rows:
                        return rows
                except Exception:
                    continue
        return self._load_from_files()

    def _load_from_files(self) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        decisions_dir = self.repo_root / "knowledge" / "decisions"
        if not decisions_dir.exists():
            return decisions
        for path in sorted(decisions_dir.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            decision_id = self._extract_header(content, "Decision ID") or path.stem
            status = self._extract_header(content, "Status")
            decision = self._extract_section(content, "Decision")
            rationale = self._extract_section(content, "Rationale")
            related = self._extract_section(content, "Related")
            decisions.append({
                "id": decision_id,
                "decision_id": decision_id,
                "status": status,
                "decision": decision,
                "rationale": rationale,
                "related": related,
                "source": str(path),
            })
        return decisions

    def _summarize_decision(self, decision: dict[str, Any]) -> str:
        summary = (
            decision.get("decision")
            or decision.get("summary")
            or decision.get("decision_reason")
            or decision.get("recommendation_text")
            or decision.get("human_decision")
            or ""
        )
        return _shorten(str(summary), 220)

    def _score_decision(
        self,
        decision: dict[str, Any],
        query_tokens: set[str],
        tags: list[str],
        title: str,
        objective: str,
        status: str,
        decision_type: str,
        mission_id: str,
        adr_reference: str,
        capability: str,
        text: str,
    ) -> tuple[float, list[str], bool, str]:
        reasons: list[str] = []
        conflict = False
        lineage = ""
        haystacks = {
            "title": " ".join(filter(None, [str(decision.get("title") or ""), str(decision.get("decision") or "")])).lower(),
            "summary": " ".join(filter(None, [str(decision.get("summary") or ""), str(decision.get("decision_reason") or ""), str(decision.get("rationale") or "")])).lower(),
            "status": str(decision.get("status") or decision.get("human_decision") or "").lower(),
            "tags": " ".join(tags).lower(),
            "adr": str(decision.get("adr_reference") or decision.get("related") or "").lower(),
            "capability": str(decision.get("capability") or "").lower(),
            "mission": str(decision.get("mission_id") or "").lower(),
            "text": str(text or "").lower(),
        }

        score = 0.0
        overlap_fields = 0
        if title and title.lower() in haystacks["title"]:
            score += 0.24
            overlap_fields += 1
            reasons.append("title overlap")
        if objective and objective.lower() in haystacks["summary"]:
            score += 0.18
            overlap_fields += 1
            reasons.append("objective overlap")
        if status and status.lower() == haystacks["status"]:
            score += 0.1
            overlap_fields += 1
            reasons.append("status overlap")
        if decision_type and decision_type.lower() in haystacks["summary"]:
            score += 0.1
            overlap_fields += 1
            reasons.append("decision type overlap")
        if mission_id and mission_id.lower() in haystacks["mission"]:
            score += 0.15
            overlap_fields += 1
            reasons.append("mission overlap")
        if adr_reference and adr_reference.lower() in haystacks["adr"]:
            score += 0.15
            overlap_fields += 1
            reasons.append("ADR overlap")
        if capability and capability.lower() in haystacks["capability"]:
            score += 0.1
            overlap_fields += 1
            reasons.append("capability overlap")

        all_text = " ".join(haystacks.values())
        token_hits = sum(1 for token in query_tokens if token in all_text)
        if query_tokens:
            score += min(token_hits / max(len(query_tokens), 1), 1.0) * 0.25
            if token_hits:
                reasons.append("text similarity")

        if any(word in all_text for word in ("superseded", "rejected", "approved", "duplicate")):
            if "approved" in all_text and (title or objective or adr_reference or capability):
                conflict = True
                reasons.append("possible approved-decision overlap")
            if "superseded" in all_text:
                lineage = "superseded"
                reasons.append("lineage hint: superseded")
            if "duplicate" in all_text:
                conflict = True
                reasons.append("duplicate decision overlap")

        if not reasons and text and any(token in all_text for token in _tokenize(text)):
            score += 0.2
            reasons.append("fallback text similarity")

        if overlap_fields >= 3:
            score += 0.1
            reasons.append("cross-artifact agreement")

        if decision.get("related"):
            related_text = str(decision.get("related") or "").lower()
            if "superseded by" in related_text:
                lineage = related_text
                reasons.append("lineage reference")

        return min(score, 1.0), reasons, conflict, lineage

    def _extract_header(self, content: str, label: str) -> str:
        pattern = re.compile(rf"^{re.escape(label)}:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
        match = pattern.search(content or "")
        return match.group(1).strip() if match else ""

    def _extract_section(self, content: str, label: str) -> str:
        pattern = re.compile(rf"^{re.escape(label)}:\s*$", re.IGNORECASE | re.MULTILINE)
        match = pattern.search(content or "")
        if not match:
            return ""
        start = match.end()
        remainder = content[start:]
        next_header = re.search(r"^\w[^:\n]{0,40}:\s*$", remainder, re.MULTILINE)
        return _shorten(remainder[: next_header.start()] if next_header else remainder, 500)
