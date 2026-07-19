"""Future State Planning (EXEC-009 WP6).

Plans required future capabilities across three horizons:
  H1 — 12 months: near-term capability requirements
  H2 — 24 months: medium-term capability gaps to address
  H3 — 36 months: long-term strategic differentiation needs

No new tables. Future capability requirements stored in decisions table:
  statement = "[FUTURE CAP] H{horizon}: {name[:80]}"
  owner     = "future_cap:{horizon}:{plan_id}"
  rationale = "HORIZON: {h} | PRIORITY: {p} | CURRENT_CAP: {c} |
               OBJECTIVE: {o} | CONFIDENCE: {conf} | RATIONALE: {r} | DESC: {d}"

Public API:
    HorizonPlan, FuturePlan
    register_future_capability(...)         -> str | None
    list_future_capabilities(horizon)       -> list[HorizonPlan]
    build_future_state_plan()               -> FuturePlan
    format_future_state_plan(fp)            -> str
    FUTURE_CAP_OWNER_PREFIX
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

FUTURE_CAP_OWNER_PREFIX = "future_cap:"
_FUTURE_CAP_STATEMENT   = "[FUTURE CAP]"

HORIZONS = (1, 2, 3)   # 12, 24, 36 months
_HORIZON_MONTHS = {1: 12, 2: 24, 3: 36}


class FutureCapPriority(str, Enum):
    CRITICAL   = "critical"
    HIGH       = "high"
    MEDIUM     = "medium"
    LOW        = "low"


@dataclass
class HorizonPlan:
    plan_id: str
    name: str
    horizon: int               # 1, 2, or 3
    priority: FutureCapPriority = FutureCapPriority.MEDIUM
    current_cap_id: str = ""   # existing capability being extended (if any)
    objective_id: str = ""
    confidence: float = 0.5    # 0.0–1.0 confidence this will be needed
    rationale: str = ""
    description: str = ""

    @property
    def horizon_months(self) -> int:
        return _HORIZON_MONTHS.get(self.horizon, 12)


@dataclass
class FuturePlan:
    h1: list[HorizonPlan] = field(default_factory=list)   # 12-month
    h2: list[HorizonPlan] = field(default_factory=list)   # 24-month
    h3: list[HorizonPlan] = field(default_factory=list)   # 36-month

    @property
    def total(self) -> int:
        return len(self.h1) + len(self.h2) + len(self.h3)

    @property
    def critical_near_term(self) -> list[HorizonPlan]:
        return [p for p in self.h1 if p.priority == FutureCapPriority.CRITICAL]


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[future_state] Supabase unavailable: %s", exc)
        return None


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _build_rationale(p: HorizonPlan) -> str:
    return " | ".join([
        f"HORIZON: {p.horizon}",
        f"PRIORITY: {p.priority.value}",
        f"CURRENT_CAP: {p.current_cap_id}",
        f"OBJECTIVE: {p.objective_id}",
        f"CONFIDENCE: {p.confidence:.2f}",
        f"RATIONALE: {p.rationale[:80]}",
        f"DESC: {p.description[:120]}",
    ])


def _row_to_plan(row: dict[str, Any]) -> HorizonPlan | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(FUTURE_CAP_OWNER_PREFIX):
        return None
    # owner format: future_cap:{horizon}:{plan_id}
    remainder = owner[len(FUTURE_CAP_OWNER_PREFIX):]
    parts = remainder.split(":", 1)
    if len(parts) != 2:
        return None
    try:
        horizon = int(parts[0])
    except ValueError:
        return None
    plan_id = parts[1]

    p = _parse_rationale(str(row.get("rationale") or ""))
    stmt = str(row.get("statement") or "")
    prefix = f"{_FUTURE_CAP_STATEMENT} H{horizon}: "
    name = stmt[len(prefix):] if stmt.startswith(prefix) else stmt

    def _en(cls, val, default):
        try:
            return cls(val)
        except (ValueError, KeyError):
            return default

    try:
        confidence = float(p.get("CONFIDENCE", "0.5") or "0.5")
    except (ValueError, TypeError):
        confidence = 0.5

    return HorizonPlan(
        plan_id=plan_id,
        name=name,
        horizon=horizon,
        priority=_en(FutureCapPriority, p.get("PRIORITY", "medium"), FutureCapPriority.MEDIUM),
        current_cap_id=p.get("CURRENT_CAP", ""),
        objective_id=p.get("OBJECTIVE", ""),
        confidence=confidence,
        rationale=p.get("RATIONALE", ""),
        description=p.get("DESC", ""),
    )


def register_future_capability(
    name: str,
    horizon: int,
    *,
    priority: FutureCapPriority = FutureCapPriority.MEDIUM,
    current_cap_id: str = "",
    objective_id: str = "",
    confidence: float = 0.5,
    rationale: str = "",
    description: str = "",
) -> str | None:
    """Register a future capability requirement. Returns plan_id or None."""
    if horizon not in HORIZONS:
        log.warning("[future_state] invalid horizon %s", horizon)
        return None
    try:
        from command_memory_integration import log_decision_to_command_memory
        c = _client()
        if c is not None:
            owner_pattern = f"{FUTURE_CAP_OWNER_PREFIX}{horizon}:%"
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .like("owner", owner_pattern)
                .ilike("statement", f"%{name[:40]}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                log.debug("[future_state] future cap already registered: H%d %s", horizon, name[:40])
                return None

        plan_id = f"fp-{uuid4().hex[:8]}"
        plan = HorizonPlan(
            plan_id=plan_id,
            name=name,
            horizon=horizon,
            priority=priority,
            current_cap_id=current_cap_id,
            objective_id=objective_id,
            confidence=confidence,
            rationale=rationale,
            description=description,
        )
        log_decision_to_command_memory(
            statement=f"{_FUTURE_CAP_STATEMENT} H{horizon}: {name[:80]}",
            rationale=_build_rationale(plan),
            owner=f"{FUTURE_CAP_OWNER_PREFIX}{horizon}:{plan_id}",
        )
        log.info("[future_state] Registered H%d future cap %s — %s", horizon, plan_id, name[:60])
        return plan_id
    except Exception as exc:
        log.warning("[future_state] register_future_capability failed: %s", exc)
        return None


def list_future_capabilities(
    horizon: int | None = None,
    limit: int = 300,
) -> list[HorizonPlan]:
    """Return future capability plans, optionally filtered by horizon."""
    try:
        c = _client()
        if c is None:
            return []
        if horizon is not None:
            owner_filter = f"{FUTURE_CAP_OWNER_PREFIX}{horizon}:%"
        else:
            owner_filter = f"{FUTURE_CAP_OWNER_PREFIX}%"
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", owner_filter)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[HorizonPlan] = []
        for row in res.data or []:
            p = _row_to_plan(row)
            if p:
                out.append(p)
        return out
    except Exception as exc:
        log.debug("[future_state] list_future_capabilities failed: %s", exc)
        return []


def build_future_state_plan() -> FuturePlan:
    """Build the full 3-horizon future state plan."""
    all_plans = list_future_capabilities()
    fp = FuturePlan()
    for p in all_plans:
        if p.horizon == 1:
            fp.h1.append(p)
        elif p.horizon == 2:
            fp.h2.append(p)
        elif p.horizon == 3:
            fp.h3.append(p)
    log.info("[future_state] H1=%d H2=%d H3=%d future capability plans", len(fp.h1), len(fp.h2), len(fp.h3))
    return fp


def format_future_state_plan(fp: FuturePlan) -> str:
    if fp.total == 0:
        return "_No future capability plans registered._"
    lines = ["*Future State Capability Plan:*"]
    for horizon, plans, months in ((1, fp.h1, 12), (2, fp.h2, 24), (3, fp.h3, 36)):
        if not plans:
            continue
        critical = [p for p in plans if p.priority == FutureCapPriority.CRITICAL]
        lines.append(f"  H{horizon} ({months}-month): {len(plans)} requirement(s)" +
                     (f" — {len(critical)} critical" if critical else ""))
        for p in sorted(plans, key=lambda x: (x.priority.value, x.name))[:3]:
            icon = ":red_circle:" if p.priority == FutureCapPriority.CRITICAL else "·"
            lines.append(f"    {icon} {p.name[:55]} [{p.priority.value}]")
    return "\n".join(lines)


__all__ = [
    "HorizonPlan",
    "FuturePlan",
    "FutureCapPriority",
    "register_future_capability",
    "list_future_capabilities",
    "build_future_state_plan",
    "format_future_state_plan",
    "FUTURE_CAP_OWNER_PREFIX",
    "HORIZONS",
]
