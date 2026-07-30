"""Knowledge Quality Framework (EXEC-005 WP7).

Measures organisational knowledge health across eight dimensions. Knowledge
retention is a strategic asset; this framework makes its health measurable.

Metrics (each 0.0–1.0):
  adr_coverage                 — architecture decisions documented as ADRs
  decision_rationale_coverage  — decisions with substantive rationale
  lesson_coverage              — closed work that produced a lesson
  mission_outcome_coverage     — completed missions with captured outcome
  investigation_outcome_coverage — closed investigations with recorded outcome
  knowledge_reuse_rate         — lessons actually reused
  documentation_freshness      — recency of lessons/ADR activity
  knowledge_fragmentation      — inverse of consolidation (lower is better, reported as health)

Reuse: decisions, missions, lessons_learned, architecture_records tables.
No new tables. Computation is read-only and fully non-blocking.

Public API:
    KnowledgeQualityScore
    compute_knowledge_quality()        -> KnowledgeQualityScore
    format_knowledge_quality(score)    -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

_MIN_RATIONALE_LEN = 40       # rationale shorter than this is "thin"
_COMPLETED_STATUSES = frozenset({"completed", "validated", "closed", "done"})


@dataclass
class KnowledgeQualityScore:
    adr_coverage: float = 0.0
    decision_rationale_coverage: float = 0.0
    lesson_coverage: float = 0.0
    mission_outcome_coverage: float = 0.0
    investigation_outcome_coverage: float = 0.0
    knowledge_reuse_rate: float = 0.0
    documentation_freshness: float = 0.0
    knowledge_fragmentation_health: float = 0.0
    computed_at: datetime = field(default_factory=datetime.utcnow)
    notes: list[str] = field(default_factory=list)

    @property
    def composite(self) -> float:
        dims = [
            self.adr_coverage,
            self.decision_rationale_coverage,
            self.lesson_coverage,
            self.mission_outcome_coverage,
            self.investigation_outcome_coverage,
            self.knowledge_reuse_rate,
            self.documentation_freshness,
            self.knowledge_fragmentation_health,
        ]
        return round(sum(dims) / len(dims), 3)

    @property
    def grade(self) -> str:
        c = self.composite
        if c >= 0.8:
            return "A — Strong"
        if c >= 0.65:
            return "B — Healthy"
        if c >= 0.5:
            return "C — Adequate"
        if c >= 0.35:
            return "D — Weak"
        return "F — At Risk"

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite": self.composite,
            "grade": self.grade,
            "adr_coverage": self.adr_coverage,
            "decision_rationale_coverage": self.decision_rationale_coverage,
            "lesson_coverage": self.lesson_coverage,
            "mission_outcome_coverage": self.mission_outcome_coverage,
            "investigation_outcome_coverage": self.investigation_outcome_coverage,
            "knowledge_reuse_rate": self.knowledge_reuse_rate,
            "documentation_freshness": self.documentation_freshness,
            "knowledge_fragmentation_health": self.knowledge_fragmentation_health,
        }


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(min(1.0, numerator / denominator), 3)


def _count(client, table: str, *, like: tuple[str, str] | None = None,
           ilike: tuple[str, str] | None = None) -> int:
    try:
        q = client.table(table).select("id", count="exact")
        if like:
            q = q.like(like[0], like[1])
        if ilike:
            q = q.ilike(ilike[0], ilike[1])
        res = q.execute()
        return int(getattr(res, "count", None) or 0)
    except Exception:
        return 0


def compute_knowledge_quality() -> KnowledgeQualityScore:
    """Compute the eight-dimension knowledge quality score (read-only)."""
    score = KnowledgeQualityScore()

    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            score.notes.append("Command Memory unavailable — scores are zero.")
            return score
        rc = c.raw_client
    except Exception as exc:
        score.notes.append(f"Client unavailable: {exc}")
        return score

    # 1. Decision rationale coverage — sample recent decisions
    try:
        res = rc.table("decisions").select("rationale").order(
            "created_at", desc=True
        ).limit(200).execute()
        rows = list(res.data or [])
        if rows:
            substantive = sum(
                1 for r in rows
                if len(str(r.get("rationale") or "").strip()) >= _MIN_RATIONALE_LEN
            )
            score.decision_rationale_coverage = _safe_ratio(substantive, len(rows))
    except Exception as exc:
        score.notes.append(f"decision_rationale: {exc}")

    # 2. Mission outcome coverage — completed missions with a lesson candidate or outcome note
    try:
        mres = rc.table("missions").select("id,title,status").limit(300).execute()
        missions = list(mres.data or [])
        completed = [m for m in missions if str(m.get("status") or "").lower() in _COMPLETED_STATUSES]
        if completed:
            # A mission has "captured outcome" if a lesson candidate references it
            lres = rc.table("decisions").select("statement").like(
                "owner", "lesson_candidate:%"
            ).limit(500).execute()
            lesson_refs = " ".join(str(r.get("statement") or "") for r in (lres.data or []))
            with_outcome = sum(1 for m in completed if str(m.get("id") or "") in lesson_refs)
            score.mission_outcome_coverage = _safe_ratio(with_outcome, len(completed))
            score.lesson_coverage = score.mission_outcome_coverage  # lessons track outcomes
        else:
            score.notes.append("No completed missions to score.")
    except Exception as exc:
        score.notes.append(f"mission_outcome: {exc}")

    # 3. Investigation outcome coverage — closed investigations with OUTCOME recorded
    try:
        ires = rc.table("decisions").select("rationale").like(
            "owner", "investigation:%"
        ).limit(200).execute()
        invs = list(ires.data or [])
        closed = [r for r in invs if "STATUS: closed" in str(r.get("rationale") or "")]
        if closed:
            with_outcome = sum(1 for r in closed if "OUTCOME:" in str(r.get("rationale") or ""))
            score.investigation_outcome_coverage = _safe_ratio(with_outcome, len(closed))
        else:
            # No closed investigations yet — neutral, not penalised
            score.investigation_outcome_coverage = 1.0 if invs else 0.0
            if not invs:
                score.notes.append("No investigations recorded yet.")
    except Exception as exc:
        score.notes.append(f"investigation_outcome: {exc}")

    # 4. ADR coverage — architecture_records vs architecture-flagged decisions
    try:
        adr_count = _count(rc, "architecture_records")
        arch_decisions = _count(rc, "decisions", ilike=("statement", "%architecture%"))
        if arch_decisions > 0:
            score.adr_coverage = _safe_ratio(adr_count, arch_decisions)
        elif adr_count > 0:
            score.adr_coverage = 1.0
        else:
            score.notes.append("No architecture records found.")
    except Exception as exc:
        score.notes.append(f"adr_coverage: {exc}")

    # 5. Knowledge reuse rate — lesson reuse events vs lessons
    try:
        reuse_count = _count(rc, "decisions", like=("owner", "lesson_reuse:%"))
        lesson_count = _count(rc, "lessons_learned")
        cand_count = _count(rc, "decisions", like=("owner", "lesson_candidate:%"))
        denom = max(lesson_count + cand_count, 1)
        score.knowledge_reuse_rate = _safe_ratio(reuse_count, denom)
    except Exception as exc:
        score.notes.append(f"reuse_rate: {exc}")

    # 6. Documentation freshness — lessons/ADR activity in last 30 days
    try:
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
        recent_lessons = 0
        try:
            lr = rc.table("lessons_learned").select("id", count="exact").gte(
                "created_at", cutoff
            ).execute()
            recent_lessons = int(getattr(lr, "count", None) or 0)
        except Exception:
            pass
        recent_candidates = 0
        try:
            cr = rc.table("decisions").select("id", count="exact").like(
                "owner", "lesson_candidate:%"
            ).gte("created_at", cutoff).execute()
            recent_candidates = int(getattr(cr, "count", None) or 0)
        except Exception:
            pass
        # Freshness saturates at 5 recent knowledge events
        score.documentation_freshness = _safe_ratio(recent_lessons + recent_candidates, 5)
    except Exception as exc:
        score.notes.append(f"freshness: {exc}")

    # 7. Knowledge fragmentation health — consolidation indicator
    #    Healthy when lessons are consolidated in lessons_learned rather than
    #    scattered as un-promoted candidates. health = promoted / (promoted+pending)
    try:
        promoted = _count(rc, "lessons_learned")
        pending = _count(rc, "decisions", like=("owner", "lesson_candidate:%"))
        total = promoted + pending
        if total > 0:
            score.knowledge_fragmentation_health = _safe_ratio(promoted, total)
        else:
            score.knowledge_fragmentation_health = 0.5  # neutral when no data
    except Exception as exc:
        score.notes.append(f"fragmentation: {exc}")

    log.info(
        "[learning.knowledge_quality] Composite %.2f (%s)",
        score.composite, score.grade,
    )
    return score


def format_knowledge_quality(score: KnowledgeQualityScore) -> str:
    """Format the knowledge quality score as Slack-ready text."""
    def bar(v: float) -> str:
        filled = int(round(v * 5))
        return "█" * filled + "░" * (5 - filled)

    lines = [
        f"*Knowledge Quality: {score.grade}* ({score.composite:.0%})",
        f"  ADR coverage              {bar(score.adr_coverage)} {score.adr_coverage:.0%}",
        f"  Decision rationale        {bar(score.decision_rationale_coverage)} {score.decision_rationale_coverage:.0%}",
        f"  Lesson coverage           {bar(score.lesson_coverage)} {score.lesson_coverage:.0%}",
        f"  Mission outcomes          {bar(score.mission_outcome_coverage)} {score.mission_outcome_coverage:.0%}",
        f"  Investigation outcomes    {bar(score.investigation_outcome_coverage)} {score.investigation_outcome_coverage:.0%}",
        f"  Knowledge reuse           {bar(score.knowledge_reuse_rate)} {score.knowledge_reuse_rate:.0%}",
        f"  Documentation freshness   {bar(score.documentation_freshness)} {score.documentation_freshness:.0%}",
        f"  Consolidation health      {bar(score.knowledge_fragmentation_health)} {score.knowledge_fragmentation_health:.0%}",
    ]
    return "\n".join(lines)


__all__ = [
    "KnowledgeQualityScore",
    "compute_knowledge_quality",
    "format_knowledge_quality",
]
