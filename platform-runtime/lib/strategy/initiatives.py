"""Initiative Framework (EXEC-006 WP1).

Introduces Initiatives as the organisational layer between strategic objectives
and mission portfolios:

    Strategic Objective → Initiative → Mission Portfolio

An initiative is a coherent body of work pursuing a measurable outcome in
service of a strategic objective. Missions, investigations, and improvements
attach to an initiative; the initiative attaches to an objective.

Reuse: decisions table for the initiative record + mission-link records
(zero new tables — ADR-0020). strategic_objectives for objective linkage.

Storage (decisions table):
  Initiative record:
    statement = "[INITIATIVE] {init_id}: {title[:80]}"
    owner     = "initiative:{init_id}"
    rationale = "OBJECTIVE: {obj} | OWNER: {o} | HEALTH: {h} | BASELINE: {b} |
                 TARGET: {t} | CURRENT: {c} | TREND: {tr} | CONFIDENCE: {conf} |
                 REVIEW: {date} | STATUS: {s} | DESC: {desc}"
  Mission link:
    statement = "[INITIATIVE LINK] {init_id} > {mission_id}"
    owner     = "initiative_mission:{init_id}"

Public API:
    InitiativeStatus, InitiativeHealth
    Initiative
    create_initiative(...)             -> str | None  (init_id)
    update_initiative(init_id, **fields) -> bool
    get_initiative(init_id)            -> Initiative | None
    list_initiatives(include_closed)   -> list[Initiative]
    link_mission(init_id, mission_id)  -> bool
    get_linked_missions(init_id)       -> list[str]
    close_initiative(init_id, status)  -> bool
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

INITIATIVE_OWNER_PREFIX      = "initiative:"
INITIATIVE_MISSION_PREFIX    = "initiative_mission:"
_INITIATIVE_STATEMENT        = "[INITIATIVE]"
_INITIATIVE_LINK_STATEMENT   = "[INITIATIVE LINK]"

_DEFAULT_REVIEW_DAYS = 30


class InitiativeStatus(str, Enum):
    PROPOSED  = "proposed"
    ACTIVE    = "active"
    PAUSED    = "paused"
    MERGED    = "merged"
    COMPLETED = "completed"
    STOPPED   = "stopped"


class InitiativeHealth(str, Enum):
    GREEN   = "green"    # on track
    AMBER   = "amber"    # at risk
    RED     = "red"      # off track
    UNKNOWN = "unknown"


class OutcomeTrend(str, Enum):
    IMPROVING = "improving"
    STABLE    = "stable"
    DECLINING = "declining"
    UNKNOWN   = "unknown"


@dataclass
class Initiative:
    initiative_id: str
    title: str
    description: str = ""
    objective_id: str = ""
    owner: str = "strategic_planning"
    health: InitiativeHealth = InitiativeHealth.UNKNOWN
    baseline: str = ""
    target: str = ""
    current: str = ""
    trend: OutcomeTrend = OutcomeTrend.UNKNOWN
    confidence: str = "medium"        # low | medium | high
    review_date: str = ""             # ISO date
    status: InitiativeStatus = InitiativeStatus.PROPOSED
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_active(self) -> bool:
        return self.status in (InitiativeStatus.ACTIVE, InitiativeStatus.PROPOSED)

    @property
    def is_orphan(self) -> bool:
        """An initiative with no objective linkage cannot explain why it exists."""
        return not self.objective_id

    @property
    def review_overdue(self) -> bool:
        if not self.review_date:
            return False
        try:
            return date.fromisoformat(self.review_date[:10]) < date.today()
        except ValueError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "initiative_id": self.initiative_id,
            "title": self.title,
            "objective_id": self.objective_id,
            "owner": self.owner,
            "health": self.health.value,
            "baseline": self.baseline,
            "target": self.target,
            "current": self.current,
            "trend": self.trend.value,
            "confidence": self.confidence,
            "review_date": self.review_date,
            "status": self.status.value,
        }


# ── Rationale (de)serialisation ───────────────────────────────────────────────

def _build_rationale(init: Initiative) -> str:
    return " | ".join([
        f"OBJECTIVE: {init.objective_id}",
        f"OWNER: {init.owner}",
        f"HEALTH: {init.health.value}",
        f"BASELINE: {init.baseline[:80]}",
        f"TARGET: {init.target[:80]}",
        f"CURRENT: {init.current[:80]}",
        f"TREND: {init.trend.value}",
        f"CONFIDENCE: {init.confidence}",
        f"REVIEW: {init.review_date}",
        f"STATUS: {init.status.value}",
        f"DESC: {init.description[:120]}",
    ])


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _row_to_initiative(row: dict[str, Any]) -> Initiative | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(INITIATIVE_OWNER_PREFIX):
        return None
    init_id = owner[len(INITIATIVE_OWNER_PREFIX):]

    p = _parse_rationale(str(row.get("rationale") or ""))
    stmt = str(row.get("statement") or "")
    prefix = f"{_INITIATIVE_STATEMENT} {init_id}: "
    title = stmt[len(prefix):] if stmt.startswith(prefix) else stmt

    def _enum(cls, val, default):
        try:
            return cls(val)
        except ValueError:
            return default

    return Initiative(
        initiative_id=init_id,
        title=title,
        description=p.get("DESC", ""),
        objective_id=p.get("OBJECTIVE", ""),
        owner=p.get("OWNER", "strategic_planning"),
        health=_enum(InitiativeHealth, p.get("HEALTH", "unknown"), InitiativeHealth.UNKNOWN),
        baseline=p.get("BASELINE", ""),
        target=p.get("TARGET", ""),
        current=p.get("CURRENT", ""),
        trend=_enum(OutcomeTrend, p.get("TREND", "unknown"), OutcomeTrend.UNKNOWN),
        confidence=p.get("CONFIDENCE", "medium"),
        review_date=p.get("REVIEW", ""),
        status=_enum(InitiativeStatus, p.get("STATUS", "proposed"), InitiativeStatus.PROPOSED),
    )


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[strategy.initiatives] Supabase unavailable: %s", exc)
        return None


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_initiative(
    title: str,
    objective_id: str,
    *,
    description: str = "",
    owner: str = "strategic_planning",
    baseline: str = "",
    target: str = "",
    current: str = "",
    confidence: str = "medium",
    review_days: int = _DEFAULT_REVIEW_DAYS,
    status: InitiativeStatus = InitiativeStatus.PROPOSED,
) -> str | None:
    """Create an initiative linked to a strategic objective.

    Returns the initiative id (e.g. "init-a1b2c3d4") or None on failure.
    """
    try:
        from command_memory_integration import log_decision_to_command_memory

        init_id = f"init-{uuid4().hex[:8]}"
        review_date = (date.today() + timedelta(days=review_days)).isoformat()

        init = Initiative(
            initiative_id=init_id,
            title=title,
            description=description,
            objective_id=objective_id,
            owner=owner,
            baseline=baseline,
            target=target,
            current=current or baseline,
            confidence=confidence,
            review_date=review_date,
            status=status,
        )

        log_decision_to_command_memory(
            statement=f"{_INITIATIVE_STATEMENT} {init_id}: {title[:80]}",
            rationale=_build_rationale(init),
            owner=f"{INITIATIVE_OWNER_PREFIX}{init_id}",
        )
        log.info("[strategy.initiatives] Created %s — %s (objective %s)", init_id, title[:60], objective_id)
        return init_id

    except Exception as exc:
        log.warning("[strategy.initiatives] create_initiative failed: %s", exc)
        return None


def update_initiative(initiative_id: str, **fields: Any) -> bool:
    """Update fields on an initiative. Accepts: health, baseline, target,
    current, trend, confidence, review_date, status, objective_id, description,
    owner (enum or str values accepted)."""
    try:
        c = _client()
        if c is None:
            return False

        owner_key = f"{INITIATIVE_OWNER_PREFIX}{initiative_id}"
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

        init = _row_to_initiative({**rows[0], "owner": owner_key})
        if init is None:
            return False

        for k, v in fields.items():
            if not hasattr(init, k):
                continue
            # Coerce enums
            if k == "health":
                v = v if isinstance(v, InitiativeHealth) else InitiativeHealth(str(v))
            elif k == "trend":
                v = v if isinstance(v, OutcomeTrend) else OutcomeTrend(str(v))
            elif k == "status":
                v = v if isinstance(v, InitiativeStatus) else InitiativeStatus(str(v))
            setattr(init, k, v)

        update = {"rationale": _build_rationale(init)}
        # Keep title in sync if changed
        if "title" in fields:
            update["statement"] = f"{_INITIATIVE_STATEMENT} {initiative_id}: {init.title[:80]}"

        c.raw_client.table("decisions").update(update).eq("id", rows[0]["id"]).execute()
        return True

    except Exception as exc:
        log.debug("[strategy.initiatives] update_initiative failed: %s", exc)
        return False


def get_initiative(initiative_id: str) -> Initiative | None:
    try:
        c = _client()
        if c is None:
            return None
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .eq("owner", f"{INITIATIVE_OWNER_PREFIX}{initiative_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        return _row_to_initiative(rows[0]) if rows else None
    except Exception as exc:
        log.debug("[strategy.initiatives] get_initiative failed: %s", exc)
        return None


def list_initiatives(include_closed: bool = False, limit: int = 100) -> list[Initiative]:
    """Return initiatives, newest first. Excludes closed statuses by default."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{INITIATIVE_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        closed = {InitiativeStatus.COMPLETED, InitiativeStatus.STOPPED, InitiativeStatus.MERGED}
        out: list[Initiative] = []
        for row in res.data or []:
            init = _row_to_initiative(row)
            if not init:
                continue
            if not include_closed and init.status in closed:
                continue
            out.append(init)
        return out
    except Exception as exc:
        log.debug("[strategy.initiatives] list_initiatives failed: %s", exc)
        return []


def close_initiative(initiative_id: str, status: InitiativeStatus = InitiativeStatus.COMPLETED) -> bool:
    """Close an initiative with a terminal status (completed/stopped/merged)."""
    return update_initiative(initiative_id, status=status)


# ── Mission portfolio linkage ─────────────────────────────────────────────────

def link_mission(initiative_id: str, mission_id: str) -> bool:
    """Attach a mission to an initiative's portfolio (dedup-safe)."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        c = _client()
        owner = f"{INITIATIVE_MISSION_PREFIX}{initiative_id}"

        if c is not None:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .eq("owner", owner)
                .ilike("statement", f"%{mission_id}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                return False

        log_decision_to_command_memory(
            statement=f"{_INITIATIVE_LINK_STATEMENT} {initiative_id} > {mission_id}",
            rationale=f"INITIATIVE: {initiative_id} | MISSION: {mission_id} | LINKED: {datetime.utcnow().isoformat()}",
            owner=owner,
        )
        return True
    except Exception as exc:
        log.debug("[strategy.initiatives] link_mission failed: %s", exc)
        return False


def get_linked_missions(initiative_id: str) -> list[str]:
    """Return mission ids attached to an initiative."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("rationale")
            .eq("owner", f"{INITIATIVE_MISSION_PREFIX}{initiative_id}")
            .execute()
        )
        out: list[str] = []
        for row in res.data or []:
            for seg in str(row.get("rationale") or "").split(" | "):
                if seg.startswith("MISSION: "):
                    out.append(seg[len("MISSION: "):].strip())
        return out
    except Exception as exc:
        log.debug("[strategy.initiatives] get_linked_missions failed: %s", exc)
        return []


__all__ = [
    "InitiativeStatus",
    "InitiativeHealth",
    "OutcomeTrend",
    "Initiative",
    "create_initiative",
    "update_initiative",
    "get_initiative",
    "list_initiatives",
    "close_initiative",
    "link_mission",
    "get_linked_missions",
    "INITIATIVE_OWNER_PREFIX",
]
