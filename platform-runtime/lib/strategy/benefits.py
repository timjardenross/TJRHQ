"""Benefit Tracking (EXEC-008 WP1).

Tracks the expected and measured benefits of each initiative, bridging
the gap between activity (missions delivered) and value (change in outcomes).

Benefit types: Strategic / Operational / Financial / Capability /
               RiskReduction / Wellbeing

Storage: decisions table (zero new tables — ADR-0020).
  statement = "[BENEFIT] {benefit_id}: {title[:80]}"
  owner     = "benefit:{benefit_id}"
  rationale = "INITIATIVE: {id} | OBJECTIVE: {obj} | TYPE: {t} |
               BASELINE: {b} | TARGET: {tgt} | CURRENT: {cur} |
               REALISATION_PCT: {r} | CONFIDENCE: {conf} |
               REVIEW: {date} | OUTCOME: {outcome} | DESC: {desc}"

Public API:
    BenefitType
    Benefit
    register_benefit(title, initiative_id, ...) -> str | None
    update_benefit(benefit_id, **fields)        -> bool
    get_benefit(benefit_id)                     -> Benefit | None
    list_benefits(initiative_id)                -> list[Benefit]
    get_benefit_summary(initiative_id)          -> dict
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

BENEFIT_OWNER_PREFIX = "benefit:"
_BENEFIT_STATEMENT   = "[BENEFIT]"
_DEFAULT_REVIEW_DAYS = 90


class BenefitType(str, Enum):
    STRATEGIC      = "strategic"
    OPERATIONAL    = "operational"
    FINANCIAL      = "financial"
    CAPABILITY     = "capability"
    RISK_REDUCTION = "risk_reduction"
    WELLBEING      = "wellbeing"


@dataclass
class Benefit:
    benefit_id: str
    title: str
    initiative_id: str
    objective_id: str = ""
    outcome: str = ""
    benefit_type: BenefitType = BenefitType.OPERATIONAL
    baseline: str = ""
    target: str = ""
    current: str = ""
    realisation_pct: float = 0.0          # 0.0–1.0+
    confidence: str = "low"               # low | medium | high
    review_date: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_realised(self) -> bool:
        return self.realisation_pct >= 1.0

    @property
    def review_overdue(self) -> bool:
        if not self.review_date:
            return False
        try:
            return date.fromisoformat(self.review_date[:10]) < date.today()
        except ValueError:
            return False


def _build_rationale(b: Benefit) -> str:
    return " | ".join([
        f"INITIATIVE: {b.initiative_id}",
        f"OBJECTIVE: {b.objective_id}",
        f"TYPE: {b.benefit_type.value}",
        f"BASELINE: {b.baseline[:80]}",
        f"TARGET: {b.target[:80]}",
        f"CURRENT: {b.current[:80]}",
        f"REALISATION_PCT: {b.realisation_pct:.3f}",
        f"CONFIDENCE: {b.confidence}",
        f"REVIEW: {b.review_date}",
        f"OUTCOME: {b.outcome[:80]}",
        f"DESC: {b.description[:120]}",
    ])


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _row_to_benefit(row: dict[str, Any]) -> Benefit | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(BENEFIT_OWNER_PREFIX):
        return None
    benefit_id = owner[len(BENEFIT_OWNER_PREFIX):]

    p = _parse_rationale(str(row.get("rationale") or ""))
    stmt = str(row.get("statement") or "")
    prefix = f"{_BENEFIT_STATEMENT} {benefit_id}: "
    title = stmt[len(prefix):] if stmt.startswith(prefix) else stmt

    try:
        btype = BenefitType(p.get("TYPE", "operational"))
    except ValueError:
        btype = BenefitType.OPERATIONAL

    try:
        rpct = float(p.get("REALISATION_PCT", "0") or "0")
    except (ValueError, TypeError):
        rpct = 0.0

    return Benefit(
        benefit_id=benefit_id,
        title=title,
        initiative_id=p.get("INITIATIVE", ""),
        objective_id=p.get("OBJECTIVE", ""),
        outcome=p.get("OUTCOME", ""),
        benefit_type=btype,
        baseline=p.get("BASELINE", ""),
        target=p.get("TARGET", ""),
        current=p.get("CURRENT", ""),
        realisation_pct=rpct,
        confidence=p.get("CONFIDENCE", "low"),
        review_date=p.get("REVIEW", ""),
        description=p.get("DESC", ""),
    )


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[strategy.benefits] Supabase unavailable: %s", exc)
        return None


# ── CRUD ──────────────────────────────────────────────────────────────────────

def register_benefit(
    title: str,
    initiative_id: str,
    *,
    objective_id: str = "",
    outcome: str = "",
    benefit_type: BenefitType = BenefitType.OPERATIONAL,
    baseline: str = "",
    target: str = "",
    current: str = "",
    confidence: str = "low",
    description: str = "",
    review_days: int = _DEFAULT_REVIEW_DAYS,
) -> str | None:
    """Register a new benefit expectation for an initiative.

    Returns benefit_id (e.g. "ben-a1b2c3d4") or None on failure.
    """
    try:
        from command_memory_integration import log_decision_to_command_memory

        # Dedup: same title + initiative already registered?
        c = _client()
        if c is not None:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .like("owner", f"{BENEFIT_OWNER_PREFIX}%")
                .ilike("statement", f"%{title[:40]}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                log.debug("[strategy.benefits] benefit already registered: %s", title[:40])
                return None

        benefit_id = f"ben-{uuid4().hex[:8]}"
        review_date = (date.today() + timedelta(days=review_days)).isoformat()

        b = Benefit(
            benefit_id=benefit_id,
            title=title,
            initiative_id=initiative_id,
            objective_id=objective_id,
            outcome=outcome,
            benefit_type=benefit_type,
            baseline=baseline,
            target=target,
            current=current or baseline,
            confidence=confidence,
            review_date=review_date,
            description=description,
        )

        log_decision_to_command_memory(
            statement=f"{_BENEFIT_STATEMENT} {benefit_id}: {title[:80]}",
            rationale=_build_rationale(b),
            owner=f"{BENEFIT_OWNER_PREFIX}{benefit_id}",
        )
        log.info("[strategy.benefits] Registered %s — %s (initiative %s)", benefit_id, title[:60], initiative_id)
        return benefit_id

    except Exception as exc:
        log.warning("[strategy.benefits] register_benefit failed: %s", exc)
        return None


def update_benefit(benefit_id: str, **fields: Any) -> bool:
    """Update fields on a benefit. Accepts: baseline, target, current,
    realisation_pct, confidence, review_date, outcome, description."""
    try:
        c = _client()
        if c is None:
            return False

        owner_key = f"{BENEFIT_OWNER_PREFIX}{benefit_id}"
        res = (
            c.raw_client.table("decisions")
            .select("id,statement,rationale")
            .eq("owner", owner_key)
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return False

        b = _row_to_benefit({**rows[0], "owner": owner_key})
        if b is None:
            return False

        for k, v in fields.items():
            if not hasattr(b, k):
                continue
            if k == "benefit_type":
                v = v if isinstance(v, BenefitType) else BenefitType(str(v))
            setattr(b, k, v)

        c.raw_client.table("decisions").update({"rationale": _build_rationale(b)}).eq("id", rows[0]["id"]).execute()
        return True

    except Exception as exc:
        log.debug("[strategy.benefits] update_benefit failed: %s", exc)
        return False


def get_benefit(benefit_id: str) -> Benefit | None:
    try:
        c = _client()
        if c is None:
            return None
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .eq("owner", f"{BENEFIT_OWNER_PREFIX}{benefit_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        return _row_to_benefit(rows[0]) if rows else None
    except Exception as exc:
        log.debug("[strategy.benefits] get_benefit failed: %s", exc)
        return None


def list_benefits(initiative_id: str | None = None, limit: int = 100) -> list[Benefit]:
    """Return benefits, optionally filtered by initiative_id."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{BENEFIT_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[Benefit] = []
        for row in res.data or []:
            b = _row_to_benefit(row)
            if not b:
                continue
            if initiative_id and b.initiative_id != initiative_id:
                continue
            out.append(b)
        return out
    except Exception as exc:
        log.debug("[strategy.benefits] list_benefits failed: %s", exc)
        return []


def get_benefit_summary(initiative_id: str) -> dict:
    """Aggregate benefit metrics for an initiative."""
    benefits = list_benefits(initiative_id)
    if not benefits:
        return {"count": 0, "realised": 0, "avg_realisation_pct": 0.0, "overdue": 0}

    realised = sum(1 for b in benefits if b.is_realised)
    overdue  = sum(1 for b in benefits if b.review_overdue)
    avg_pct  = sum(b.realisation_pct for b in benefits) / len(benefits)

    by_type: dict[str, int] = {}
    for b in benefits:
        by_type[b.benefit_type.value] = by_type.get(b.benefit_type.value, 0) + 1

    return {
        "count": len(benefits),
        "realised": realised,
        "avg_realisation_pct": round(avg_pct, 3),
        "overdue": overdue,
        "by_type": by_type,
    }


__all__ = [
    "BenefitType",
    "Benefit",
    "register_benefit",
    "update_benefit",
    "get_benefit",
    "list_benefits",
    "get_benefit_summary",
    "BENEFIT_OWNER_PREFIX",
]
