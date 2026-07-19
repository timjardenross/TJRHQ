"""Organisational Learning Pipeline & Automatic Lesson Generation
(EXEC-005 WP5 / WP6).

Learning is a deliverable, not an optional activity. Every investigation,
mission, improvement, decision, and incident produces a lesson candidate at
closure.

WP5 lifecycle:  Event → Outcome → Lesson → Knowledge → Future Reuse

WP6 behaviour:  At closure, generate a lesson CANDIDATE (not a finalised
lesson). Candidates live in Command Memory (decisions table) with a confidence
score. The Knowledge officer (or XO) promotes accepted candidates into the
curated `lessons_learned` table — preventing low-quality auto-generated noise
from polluting institutional memory.

Reuse:
  - `lessons_learned` table (curated lessons — promotion target)
  - decisions table (lesson candidates — suggestion workflow)
  - No duplicate knowledge systems.

Storage (lesson candidates, decisions table):
  statement = "[LESSON] {trigger}:{ref}: {title[:70]}"
  owner     = "lesson_candidate:{trigger}"
  rationale = "REF: {ref} | TRIGGER: {trigger} | CONFIDENCE: {c} |
               CONTEXT: {ctx} | LESSON: {text} | GUIDANCE: {g} | STATUS: {s}"

Public API:
    LessonCandidate
    generate_lesson_candidate(trigger, ref_id, title, context, lesson_text,
                              guidance, outcome, confidence) -> str | None
    lesson_from_investigation(inv) -> str | None
    lesson_from_mission(mission)   -> str | None
    lesson_from_improvement(...)   -> str | None
    get_lesson_candidates(limit, pending_only) -> list[LessonCandidate]
    promote_lesson_candidate(candidate_id)      -> str | None  (lesson_id)
    record_lesson_reuse(lesson_id, context)     -> None
    get_reuse_count(lesson_id)                  -> int
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

LESSON_CANDIDATE_OWNER_PREFIX = "lesson_candidate:"
LESSON_REUSE_OWNER_PREFIX     = "lesson_reuse:"
_LESSON_STATEMENT             = "[LESSON]"

# Valid `lessons_learned.source` values (per migration 0010 CHECK constraint)
_VALID_LESSON_SOURCE = "mission_closure"


@dataclass
class LessonCandidate:
    candidate_id: str
    trigger: str          # investigation | mission | improvement | decision | incident
    ref_id: str           # source object id (inv_id, mission_id, etc.)
    title: str
    context: str = ""
    lesson_text: str = ""
    guidance: str = ""
    outcome: str = ""
    confidence: float = 0.5
    status: str = "pending"  # pending | promoted | rejected
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.75:
            return "HIGH"
        if self.confidence >= 0.5:
            return "MEDIUM"
        return "LOW"


# ── Generation ────────────────────────────────────────────────────────────────

def generate_lesson_candidate(
    trigger: str,
    ref_id: str,
    title: str,
    *,
    context: str = "",
    lesson_text: str = "",
    guidance: str = "",
    outcome: str = "",
    confidence: float = 0.5,
) -> str | None:
    """Create a lesson candidate in Command Memory (dedup-safe).

    Returns the candidate decision id, or None on failure/duplicate.
    """
    try:
        from command_memory_integration import log_decision_to_command_memory
        from tools.supabase.client import CommanderSupabaseClient

        owner = f"{LESSON_CANDIDATE_OWNER_PREFIX}{trigger}"

        # Dedup: candidate for the same ref already exists?
        try:
            c = CommanderSupabaseClient()
            if c.is_enabled() and c.raw_client:
                res = (
                    c.raw_client.table("decisions")
                    .select("id")
                    .eq("owner", owner)
                    .ilike("statement", f"%{trigger}:{ref_id}:%")
                    .limit(1)
                    .execute()
                )
                if res.data:
                    return None
        except Exception as exc:
            log.debug("[learning.lessons] Lesson dedup skipped: %s", exc)

        candidate_id = log_decision_to_command_memory(
            statement=f"{_LESSON_STATEMENT} {trigger}:{ref_id}: {title[:70]}",
            rationale=(
                f"REF: {ref_id} | TRIGGER: {trigger} | "
                f"CONFIDENCE: {round(confidence, 2)} | "
                f"CONTEXT: {context[:150]} | "
                f"LESSON: {lesson_text[:200]} | "
                f"GUIDANCE: {guidance[:150]} | "
                f"OUTCOME: {outcome[:100]} | "
                f"STATUS: pending"
            ),
            owner=owner,
        )

        if candidate_id:
            log.info(
                "[learning.lessons] Lesson candidate created: %s (%s:%s, %s confidence)",
                candidate_id, trigger, ref_id,
                "HIGH" if confidence >= 0.75 else "MEDIUM" if confidence >= 0.5 else "LOW",
            )
        return candidate_id

    except Exception as exc:
        log.debug("[learning.lessons] generate_lesson_candidate failed: %s", exc)
        return None


def lesson_from_investigation(investigation: Any) -> str | None:
    """Generate a lesson candidate at investigation closure (WP6)."""
    try:
        outcome = getattr(investigation, "outcome", None)
        outcome_str = outcome.value if outcome else "closed"
        inv_id = getattr(investigation, "investigation_id", "")
        question = getattr(investigation, "question", "")
        officer = getattr(investigation, "officer", "")

        # Confidence: investigations that reached a clear outcome teach more
        confidence = 0.7 if outcome_str in (
            "decision_made", "mission_created", "improvement_created", "knowledge_updated"
        ) else 0.45

        return generate_lesson_candidate(
            trigger="investigation",
            ref_id=inv_id,
            title=f"Investigation outcome: {question[:60]}",
            context=f"Lead officer: {officer}. Outcome: {outcome_str}.",
            lesson_text=(
                f"Investigation '{question[:100]}' concluded with outcome '{outcome_str}'. "
                f"Capture what the evidence showed and whether the conclusion held."
            ),
            guidance=(
                f"When similar conditions arise, reference investigation {inv_id} "
                f"before opening a new one."
            ),
            outcome=outcome_str,
            confidence=confidence,
        )
    except Exception as exc:
        log.debug("[learning.lessons] lesson_from_investigation failed: %s", exc)
        return None


def lesson_from_mission(mission: dict[str, Any]) -> str | None:
    """Generate a lesson candidate at mission closure (WP6)."""
    try:
        mission_id = str(mission.get("id") or mission.get("mission_id") or "")
        title      = str(mission.get("title") or "")
        status     = str(mission.get("status") or "")

        is_improvement = title.startswith("[IMPROVE]")
        confidence = 0.6 if status.lower() in ("completed", "validated") else 0.4

        return generate_lesson_candidate(
            trigger="improvement" if is_improvement else "mission",
            ref_id=mission_id,
            title=f"Mission closure: {title[:60]}",
            context=f"Final status: {status}.",
            lesson_text=(
                f"Mission '{title[:100]}' closed as '{status}'. "
                f"Record what worked, what blocked progress, and what to repeat or avoid."
            ),
            guidance="Reference this lesson when scoping similar missions.",
            outcome=status,
            confidence=confidence,
        )
    except Exception as exc:
        log.debug("[learning.lessons] lesson_from_mission failed: %s", exc)
        return None


def lesson_from_decision(
    decision_ref: str,
    statement: str,
    rationale: str,
    *,
    confidence: float = 0.5,
) -> str | None:
    """Generate a lesson candidate from a significant decision (WP6)."""
    return generate_lesson_candidate(
        trigger="decision",
        ref_id=decision_ref,
        title=f"Decision: {statement[:60]}",
        context=rationale[:150],
        lesson_text=f"Decision '{statement[:100]}' was made. Track whether the rationale held.",
        guidance="Revisit this decision's rationale if the same choice recurs.",
        confidence=confidence,
    )


# ── Retrieval ─────────────────────────────────────────────────────────────────

def _parse_candidate(row: dict[str, Any]) -> LessonCandidate | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(LESSON_CANDIDATE_OWNER_PREFIX):
        return None
    trigger = owner[len(LESSON_CANDIDATE_OWNER_PREFIX):]

    parts: dict[str, str] = {}
    for seg in str(row.get("rationale") or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()

    try:
        conf = float(parts.get("CONFIDENCE", "0.5"))
    except ValueError:
        conf = 0.5

    stmt = str(row.get("statement") or "")
    title = stmt
    if ": " in stmt:
        title = stmt.split(": ", 2)[-1]

    return LessonCandidate(
        candidate_id=str(row.get("id") or ""),
        trigger=trigger,
        ref_id=parts.get("REF", ""),
        title=title[:120],
        context=parts.get("CONTEXT", ""),
        lesson_text=parts.get("LESSON", ""),
        guidance=parts.get("GUIDANCE", ""),
        outcome=parts.get("OUTCOME", ""),
        confidence=conf,
        status=parts.get("STATUS", "pending"),
    )


def get_lesson_candidates(
    limit: int = 30,
    *,
    pending_only: bool = True,
) -> list[LessonCandidate]:
    """Return lesson candidates, highest-confidence first."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("id,statement,rationale,owner,created_at")
            .like("owner", f"{LESSON_CANDIDATE_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit * 2)
            .execute()
        )

        candidates: list[LessonCandidate] = []
        for row in res.data or []:
            cand = _parse_candidate(row)
            if not cand:
                continue
            if pending_only and cand.status != "pending":
                continue
            candidates.append(cand)

        candidates.sort(key=lambda x: x.confidence, reverse=True)
        return candidates[:limit]

    except Exception as exc:
        log.debug("[learning.lessons] get_lesson_candidates failed: %s", exc)
        return []


def get_lesson_candidate_count(*, pending_only: bool = True) -> int:
    """Count lesson candidates."""
    return len(get_lesson_candidates(limit=200, pending_only=pending_only))


# ── Promotion to curated lessons_learned ──────────────────────────────────────

def promote_lesson_candidate(candidate_id: str) -> str | None:
    """Promote a lesson candidate into the curated `lessons_learned` table.

    Reuses the existing lessons_learned table (no new table). Marks the
    candidate STATUS=promoted. Returns the new lesson_id, or None on failure.
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None

        # Fetch candidate
        res = (
            c.raw_client.table("decisions")
            .select("id,statement,rationale,owner")
            .eq("id", candidate_id)
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return None

        cand = _parse_candidate(rows[0])
        if not cand:
            return None

        lesson_id = f"LL-{uuid4().hex[:6].upper()}"

        # Insert into curated lessons_learned table
        record = {
            "lesson_id": lesson_id,
            "title": cand.title[:200],
            "date_recorded": date.today().isoformat(),
            "context": cand.context,
            "lesson_text": cand.lesson_text,
            "outcome": cand.outcome,
            "future_guidance": cand.guidance,
            "mission_id": cand.ref_id if cand.trigger in ("mission", "improvement") else None,
            "source": _VALID_LESSON_SOURCE,
        }
        ok = c.raw_client.table("lessons_learned").insert(record).execute()
        if not ok:
            return None

        # Mark candidate promoted
        new_rationale = str(rows[0].get("rationale") or "").replace(
            "STATUS: pending", f"STATUS: promoted | LESSON_ID: {lesson_id}"
        )
        c.raw_client.table("decisions").update(
            {"rationale": new_rationale, "status": "Closed"}
        ).eq("id", candidate_id).execute()

        log.info("[learning.lessons] Promoted candidate %s → lesson %s", candidate_id, lesson_id)
        return lesson_id

    except Exception as exc:
        log.warning("[learning.lessons] promote_lesson_candidate failed: %s", exc)
        return None


# ── Reuse tracking (WP5: future reuse) ────────────────────────────────────────

def record_lesson_reuse(lesson_id: str, context: str = "") -> None:
    """Record that a lesson was reused, for the knowledge reuse-rate metric."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        log_decision_to_command_memory(
            statement=f"[LESSON REUSE] {lesson_id}: {context[:80]}",
            rationale=f"LESSON_ID: {lesson_id} | REUSED_AT: {datetime.utcnow().isoformat()} | CONTEXT: {context[:120]}",
            owner=f"{LESSON_REUSE_OWNER_PREFIX}{lesson_id}",
        )
    except Exception as exc:
        log.debug("[learning.lessons] record_lesson_reuse failed: %s", exc)


def get_reuse_count(lesson_id: str) -> int:
    """Return how many times a lesson has been reused."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return 0
        res = (
            c.raw_client.table("decisions")
            .select("id", count="exact")
            .eq("owner", f"{LESSON_REUSE_OWNER_PREFIX}{lesson_id}")
            .execute()
        )
        return int(getattr(res, "count", None) or 0)
    except Exception:
        return 0


__all__ = [
    "LessonCandidate",
    "generate_lesson_candidate",
    "lesson_from_investigation",
    "lesson_from_mission",
    "lesson_from_decision",
    "get_lesson_candidates",
    "get_lesson_candidate_count",
    "promote_lesson_candidate",
    "record_lesson_reuse",
    "get_reuse_count",
    "LESSON_CANDIDATE_OWNER_PREFIX",
]
