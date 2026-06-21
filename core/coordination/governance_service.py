"""Number One — Governance Context Service (WP3A)

Stateless, on-demand governance assessment. Given a captured item (or any
entity with title/summary), retrieves relevant ADRs, decisions, and missions
from Supabase, assesses alignment, and returns a structured assessment dict.

Design:
  - Stateless: no side effects, no persistence (callers cache the result)
  - Best-effort: failures return a 'unknown' status, never raise to callers
  - Timeout-protected: 10s hard limit via threading
  - Advisory only: generates context, never makes decisions

Assessment shape:
  {
    'status': 'assessed' | 'conflicts_detected' | 'unknown',
    'assessed_at': ISO timestamp,
    'artefacts': {
        'missions': [{'id', 'title', 'alignment', 'confidence'}],
        'decisions': [{'id', 'title', 'alignment', 'confidence'}],
        'adrs': [{'id', 'title', 'alignment', 'confidence'}],
    },
    'conflicts': [{'type', 'severity', 'artefact_id', 'reason'}],
    'requires_review': bool,
    'assessment_confidence': float,
  }
"""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

_ASSESSMENT_TIMEOUT_S = 10
_STOPWORDS = frozenset(
    "the a an and or in of to for with on at from by is are was were be been "
    "this that these those it its not no nor so but yet".split()
)


# ---------------------------------------------------------------------------
# Keyword helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9_]+", (text or "").lower())
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def _overlap_score(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _is_relevant(entity_text: str, artefact_text: str, threshold: float = 0.08) -> bool:
    return _overlap_score(entity_text, artefact_text) >= threshold


# ---------------------------------------------------------------------------
# Supabase read helper
# ---------------------------------------------------------------------------

class _SupabaseReader:
    def __init__(self, client: object | None = None) -> None:
        self._client = client
        if self._client is None:
            url = os.environ.get("SUPABASE_URL", "").rstrip("/")
            key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            if url and key:
                try:
                    from supabase import create_client
                    self._client = create_client(url, key)
                except Exception:
                    pass

    def select_all(self, table: str, columns: str = "*", limit: int = 100) -> list[dict]:
        if self._client is None:
            return []
        try:
            result = self._client.table(table).select(columns).limit(limit).execute()
            return result.data or []
        except Exception as exc:
            log.warning("[governance-service] select failed on %s: %s", table, exc)
            return []


# ---------------------------------------------------------------------------
# GovernanceContextService
# ---------------------------------------------------------------------------

class GovernanceContextService:
    """
    Stateless governance assessment service.
    Generates assessments on-demand from Supabase registries.
    """

    def __init__(self, supabase_client: object | None = None) -> None:
        self._db = _SupabaseReader(supabase_client)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_governance(
        self,
        entity: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Assess how entity relates to existing governance.

        entity must have at least 'title'. 'summary' is used when available.
        Returns assessment dict (see module docstring). Never raises.
        """
        result: dict[str, Any] = {}
        error: list[Exception] = []

        def _run():
            try:
                result.update(self._do_assess(entity, context or {}))
            except Exception as exc:
                error.append(exc)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=_ASSESSMENT_TIMEOUT_S)

        if t.is_alive():
            log.warning("[governance-service] assessment timed out after %ds", _ASSESSMENT_TIMEOUT_S)
            return self._unknown_assessment("timeout")

        if error:
            log.warning("[governance-service] assessment error: %s", error[0])
            return self._unknown_assessment(str(error[0]))

        return result

    # ------------------------------------------------------------------
    # Internal assessment logic
    # ------------------------------------------------------------------

    def _do_assess(self, entity: dict, context: dict) -> dict:
        entity_text = f"{entity.get('title', '')} {entity.get('summary', '')} {entity.get('raw_text', '')}"

        missions = self._retrieve_relevant_missions(entity_text)
        decisions = self._retrieve_relevant_decisions(entity_text)
        adrs = self._retrieve_relevant_adrs(entity_text)

        all_artefacts = (
            [("mission", m) for m in missions]
            + [("decision", d) for d in decisions]
            + [("adr", a) for a in adrs]
        )

        alignments = []
        for artefact_type, artefact in all_artefacts:
            alignment = self._assess_alignment(entity_text, artefact_type, artefact)
            alignments.append(alignment)

        conflicts = self._detect_conflicts(alignments)

        status = "conflicts_detected" if conflicts else ("assessed" if alignments else "unknown")
        confidence = (
            sum(a["confidence"] for a in alignments) / len(alignments)
            if alignments else 0.0
        )

        return {
            "status": status,
            "assessed_at": datetime.now(timezone.utc).isoformat(),
            "artefacts": {
                "missions": [a for a in alignments if a["artefact_type"] == "mission"],
                "decisions": [a for a in alignments if a["artefact_type"] == "decision"],
                "adrs": [a for a in alignments if a["artefact_type"] == "adr"],
            },
            "conflicts": conflicts,
            "requires_review": len(conflicts) > 0,
            "assessment_confidence": round(confidence, 3),
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _retrieve_relevant_missions(self, entity_text: str) -> list[dict]:
        rows = self._db.select_all("missions", "mission_id,title,description,status", limit=50)
        relevant = []
        for row in rows:
            artefact_text = f"{row.get('title', '')} {row.get('description', '')}"
            if _is_relevant(entity_text, artefact_text):
                relevant.append({
                    "id": row.get("mission_id") or row.get("id", ""),
                    "title": row.get("title", ""),
                    "status": row.get("status", ""),
                    "artefact_text": artefact_text,
                    "score": _overlap_score(entity_text, artefact_text),
                })
        return sorted(relevant, key=lambda x: x["score"], reverse=True)[:5]

    def _retrieve_relevant_decisions(self, entity_text: str) -> list[dict]:
        rows = self._db.select_all(
            "decision_records",
            "id,mission_id,recommendation_text,decision_reason,human_decision",
            limit=50,
        )
        relevant = []
        for row in rows:
            artefact_text = (
                f"{row.get('mission_id', '')} {row.get('recommendation_text', '')} "
                f"{row.get('decision_reason', '')}"
            )
            if _is_relevant(entity_text, artefact_text):
                rec_text = row.get("recommendation_text") or ""
                relevant.append({
                    "id": row.get("id", ""),
                    "title": row.get("mission_id") or rec_text[:80],
                    "status": row.get("human_decision", ""),
                    "artefact_text": artefact_text,
                    "score": _overlap_score(entity_text, artefact_text),
                })
        return sorted(relevant, key=lambda x: x["score"], reverse=True)[:5]

    def _retrieve_relevant_adrs(self, entity_text: str) -> list[dict]:
        rows = self._db.select_all(
            "architecture_records",
            "id,title,problem_statement,decision_summary,recommended_option,status",
            limit=50,
        )
        relevant = []
        for row in rows:
            artefact_text = (
                f"{row.get('title', '')} {row.get('problem_statement', '')} "
                f"{row.get('decision_summary', '')}"
            )
            if _is_relevant(entity_text, artefact_text):
                relevant.append({
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "status": row.get("status", ""),
                    "artefact_text": artefact_text,
                    "score": _overlap_score(entity_text, artefact_text),
                })
        return sorted(relevant, key=lambda x: x["score"], reverse=True)[:5]

    # ------------------------------------------------------------------
    # Alignment assessment
    # ------------------------------------------------------------------

    def _assess_alignment(
        self, entity_text: str, artefact_type: str, artefact: dict
    ) -> dict:
        score = artefact.get("score", 0.0)
        artefact_id = artefact.get("id", "")
        artefact_title = artefact.get("title", "")

        # High-confidence semantic match → aligned
        if score >= 0.25:
            alignment_status = "aligned"
            confidence = min(0.5 + score, 0.95)
        elif score >= 0.08:
            alignment_status = "neutral"
            confidence = 0.4 + score
        else:
            alignment_status = "neutral"
            confidence = 0.3

        return {
            "artefact_type": artefact_type,
            "artefact_id": artefact_id,
            "title": artefact_title,
            "alignment": alignment_status,
            "confidence": round(confidence, 3),
            "overlap_score": round(score, 3),
        }

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflicts(self, alignments: list[dict]) -> list[dict]:
        """
        Conservative conflict detection for MVP.
        Flags items where status is 'superseded' or 'rejected' but still
        highly relevant (suggesting the entity may re-open a closed decision).
        """
        conflicts = []
        closed_statuses = {"superseded", "rejected", "deprecated", "cancelled", "closed"}

        for alignment in alignments:
            artefact_status = (alignment.get("status") or "").lower()
            if (
                artefact_status in closed_statuses
                and alignment.get("overlap_score", 0) >= 0.2
            ):
                conflicts.append({
                    "type": "precedence_question",
                    "severity": "medium",
                    "artefact_id": alignment["artefact_id"],
                    "artefact_type": alignment["artefact_type"],
                    "reason": (
                        f"Entity overlaps with {alignment['artefact_type']} "
                        f"'{alignment['title']}' which has status '{artefact_status}'. "
                        "New intelligence may warrant revisiting this decision."
                    ),
                })

        return conflicts

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _unknown_assessment(reason: str) -> dict:
        return {
            "status": "unknown",
            "assessed_at": datetime.now(timezone.utc).isoformat(),
            "artefacts": {"missions": [], "decisions": [], "adrs": []},
            "conflicts": [],
            "requires_review": False,
            "assessment_confidence": 0.0,
            "error": reason,
        }
