"""Evidence Collection Framework (EXEC-004 WP4).

Gathers evidence from Command Memory, mission history, and CycleContext
to support investigation analysis.

Evidence is stored in the decisions table as:
  statement : "[EVIDENCE] {inv_id}: {source} — {summary[:80]}"
  owner     : "investigation_evidence:{inv_id}"
  rationale : "SOURCE: {source} | DATA: {data[:200]} | CONFIDENCE: {conf}"

Public API:
    collect_evidence(inv_id, question, officer, ctx) -> EvidencePackage
    get_evidence(inv_id)                             -> EvidencePackage
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.investigation.framework import (
    EvidenceItem, EvidencePackage, EvidenceSource, EVIDENCE_OWNER_PREFIX,
)

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "why", "what", "how",
    "when", "where", "which", "who", "be", "to", "of", "in", "for", "on",
    "at", "by", "from", "with", "and", "or", "but", "if", "as", "that",
    "this", "it", "its", "we", "they", "their",
})


def _extract_keywords(text: str, max_k: int = 4) -> list[str]:
    words = text.lower().replace("?", "").replace(",", "").replace(".", "").split()
    return [w for w in words if w not in _STOP_WORDS and len(w) > 3][:max_k]


# ── Collection steps ──────────────────────────────────────────────────────────

def _collect_from_decisions(
    package: EvidencePackage,
    question: str,
    officer: str,
) -> None:
    """Query Command Memory (decisions) for entries relevant to the question."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return

        keywords = _extract_keywords(question)
        if not keywords:
            return

        rows: list[dict] = []
        for kw in keywords[:2]:
            res = (
                c.raw_client.table("decisions")
                .select("statement,rationale,owner,created_at")
                .ilike("statement", f"%{kw}%")
                .order("created_at", desc=True)
                .limit(8)
                .execute()
            )
            for row in res.data or []:
                # Skip investigation sub-records (avoid circular evidence)
                owner = str(row.get("owner") or "")
                if owner.startswith("investigation"):
                    continue
                rows.append(row)

        seen: set[str] = set()
        for row in rows:
            stmt = str(row.get("statement") or "")
            if stmt in seen:
                continue
            seen.add(stmt)
            package.items.append(EvidenceItem(
                source=EvidenceSource.DECISION_HISTORY,
                summary=stmt[:100],
                data=(str(row.get("rationale") or ""))[:200],
                confidence=0.6,
            ))
            if len(package.items) >= 8:
                break

    except Exception as exc:
        log.debug("[investigation.evidence] Decision evidence failed: %s", exc)


def _collect_from_missions(
    package: EvidencePackage,
    question: str,
) -> None:
    """Query missions table for patterns relevant to the investigation."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return

        keywords = _extract_keywords(question)
        blocked_statuses = {"blocked", "blocked_ops"}

        for kw in keywords[:2]:
            res = (
                c.raw_client.table("missions")
                .select("id,title,status,priority,owner")
                .ilike("title", f"%{kw}%")
                .order("updated_at", desc=True)
                .limit(6)
                .execute()
            )
            for row in res.data or []:
                status  = str(row.get("status") or "")
                is_blocked = status.lower() in blocked_statuses
                conf = 0.75 if is_blocked else 0.5
                package.items.append(EvidenceItem(
                    source=EvidenceSource.MISSION_HISTORY,
                    summary=f"Mission [{status}]: {str(row.get('title',''))[:80]}",
                    data=f"Priority: {row.get('priority','?')} | Owner: {row.get('owner','?')}",
                    confidence=conf,
                ))

    except Exception as exc:
        log.debug("[investigation.evidence] Mission evidence failed: %s", exc)


def _collect_from_context(
    package: EvidencePackage,
    ctx: Any,
    officer: str,
) -> None:
    """Extract directly observable evidence from CycleContext."""
    try:
        capacity = getattr(ctx, "capacity_status", "Unknown")
        blocked  = getattr(ctx, "engineering_blocked", 0)
        orphans  = getattr(ctx, "orphan_count", 0)
        risk     = getattr(ctx, "resilience_risk", "Unknown")
        comms    = getattr(ctx, "comms_ready_count", 0)

        snapshot_parts = [
            f"Capacity: {capacity}",
            f"Engineering blocked: {blocked}",
            f"Orphan missions: {orphans}",
            f"ORI risk: {risk}",
            f"Comms ready: {comms}",
        ]

        # Confidence higher when context shows anomalies
        conf = 0.7
        if capacity in ("Red", "Amber") or blocked > 1 or risk in ("RED", "AMBER"):
            conf = 0.85

        package.items.append(EvidenceItem(
            source=EvidenceSource.CYCLE_CONTEXT,
            summary=f"Operational snapshot (capacity={capacity}, blocked={blocked}, ORI={risk})",
            data=" | ".join(snapshot_parts),
            confidence=conf,
        ))

    except Exception as exc:
        log.debug("[investigation.evidence] Context evidence failed: %s", exc)


def _store_evidence(package: EvidencePackage) -> None:
    """Persist evidence package summary to Command Memory (non-blocking)."""
    if not package.items:
        return
    try:
        from command_memory_integration import log_decision_to_command_memory

        sources = list({i.source.value for i in package.items})
        log_decision_to_command_memory(
            statement=(
                f"[EVIDENCE] {package.investigation_id}: "
                f"{len(package.items)} item(s) from {', '.join(sources)}"
            ),
            rationale=(
                f"SOURCE: {', '.join(sources)} | "
                f"ITEMS: {len(package.items)} | "
                f"AVG_CONFIDENCE: {package.avg_confidence} | "
                f"SUMMARY: {package.summary[:200]}"
            ),
            owner=f"{EVIDENCE_OWNER_PREFIX}{package.investigation_id}",
        )
    except Exception as exc:
        log.debug("[investigation.evidence] Store evidence failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def collect_evidence(
    investigation_id: str,
    question: str,
    officer: str,
    ctx: Any = None,
) -> EvidencePackage:
    """Collect evidence from available sources for an open investigation.

    Evidence is collected from:
      1. Command Memory (decisions matching question keywords)
      2. Mission history (missions matching question keywords)
      3. CycleContext (current operational snapshot)

    A summary is persisted to Command Memory for audit.

    Args:
        investigation_id: The investigation being evidenced
        question:         The investigation question (used for keyword matching)
        officer:          Lead officer (for context scoping)
        ctx:              CycleContext if available

    Returns:
        EvidencePackage with all collected items.
    """
    package = EvidencePackage(investigation_id=investigation_id)

    _collect_from_decisions(package, question, officer)
    _collect_from_missions(package, question)
    if ctx is not None:
        _collect_from_context(package, ctx, officer)

    _store_evidence(package)

    log.info(
        "[investigation.evidence] %s: %d evidence item(s), avg confidence %.2f",
        investigation_id, len(package.items), package.avg_confidence,
    )
    return package


def get_evidence(investigation_id: str) -> EvidencePackage:
    """Retrieve the stored evidence summary for an investigation (lightweight)."""
    package = EvidencePackage(investigation_id=investigation_id)
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return package

        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,created_at")
            .eq("owner", f"{EVIDENCE_OWNER_PREFIX}{investigation_id}")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if rows:
            package.items.append(EvidenceItem(
                source=EvidenceSource.COMMAND_MEMORY,
                summary=str(rows[0].get("statement", ""))[:100],
                data=str(rows[0].get("rationale", ""))[:200],
                confidence=0.5,
            ))

    except Exception as exc:
        log.debug("[investigation.evidence] get_evidence failed: %s", exc)
    return package


__all__ = [
    "collect_evidence",
    "get_evidence",
]
