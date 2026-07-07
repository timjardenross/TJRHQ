"""Enterprise Architecture Layer (EXEC-009 WP4).

Tracks Current State, Target State, and Transition State of the enterprise
architecture. Reuses the existing `architecture_records` table (populated by
EXEC-005 / knowledge_quality ADR coverage) for the source of truth. Supplements
with decisions-table records (`arch_entity:{entity_id}`) for richer metadata not
covered by the raw ADR count.

No new database tables. Reads from `architecture_records` first; falls back to
decisions table supplemental records.

Public API:
    ArchEntityState, ArchEntity
    ArchitectureView
    get_architecture_view()          -> ArchitectureView
    register_arch_entity(...)        -> str | None
    list_arch_entities(state)        -> list[ArchEntity]
    format_architecture_view(av)     -> str
    ARCH_ENTITY_OWNER_PREFIX
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

ARCH_ENTITY_OWNER_PREFIX = "arch_entity:"
_ARCH_STATEMENT          = "[ARCH ENTITY]"


class ArchEntityState(str, Enum):
    CURRENT    = "current"
    TARGET     = "target"
    TRANSITION = "transition"
    DEPRECATED = "deprecated"


class ArchEntityType(str, Enum):
    SYSTEM      = "system"
    SERVICE     = "service"
    PLATFORM    = "platform"
    PROCESS     = "process"
    INTEGRATION = "integration"
    DATA_STORE  = "data_store"
    CAPABILITY  = "capability"


@dataclass
class ArchEntity:
    entity_id: str
    name: str
    entity_type: ArchEntityType = ArchEntityType.SYSTEM
    state: ArchEntityState = ArchEntityState.CURRENT
    capability_id: str = ""
    initiative_id: str = ""
    description: str = ""
    owner: str = "number_one"
    risk_level: str = "low"   # low | medium | high


@dataclass
class ArchitectureView:
    current: list[ArchEntity] = field(default_factory=list)
    target: list[ArchEntity] = field(default_factory=list)
    transition: list[ArchEntity] = field(default_factory=list)
    deprecated: list[ArchEntity] = field(default_factory=list)
    adr_count: int = 0
    adr_coverage_pct: float = 0.0

    @property
    def total(self) -> int:
        return len(self.current) + len(self.target) + len(self.transition)

    @property
    def high_risk(self) -> list[ArchEntity]:
        return [e for e in self.current + self.transition if e.risk_level == "high"]


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[enterprise_architecture] Supabase unavailable: %s", exc)
        return None


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _build_rationale(e: ArchEntity) -> str:
    return " | ".join([
        f"TYPE: {e.entity_type.value}",
        f"STATE: {e.state.value}",
        f"CAPABILITY: {e.capability_id}",
        f"INITIATIVE: {e.initiative_id}",
        f"RISK: {e.risk_level}",
        f"OWNER: {e.owner}",
        f"DESC: {e.description[:120]}",
    ])


def _row_to_entity(row: dict[str, Any]) -> ArchEntity | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(ARCH_ENTITY_OWNER_PREFIX):
        return None
    entity_id = owner[len(ARCH_ENTITY_OWNER_PREFIX):]
    p = _parse_rationale(str(row.get("rationale") or ""))
    stmt = str(row.get("statement") or "")
    prefix = f"{_ARCH_STATEMENT} {entity_id}: "
    name = stmt[len(prefix):] if stmt.startswith(prefix) else stmt

    def _en(cls, val, default):
        try:
            return cls(val)
        except (ValueError, KeyError):
            return default

    return ArchEntity(
        entity_id=entity_id,
        name=name,
        entity_type=_en(ArchEntityType, p.get("TYPE", "system"), ArchEntityType.SYSTEM),
        state=_en(ArchEntityState, p.get("STATE", "current"), ArchEntityState.CURRENT),
        capability_id=p.get("CAPABILITY", ""),
        initiative_id=p.get("INITIATIVE", ""),
        description=p.get("DESC", ""),
        owner=p.get("OWNER", "number_one"),
        risk_level=p.get("RISK", "low"),
    )


def register_arch_entity(
    name: str,
    entity_type: ArchEntityType = ArchEntityType.SYSTEM,
    *,
    state: ArchEntityState = ArchEntityState.CURRENT,
    capability_id: str = "",
    initiative_id: str = "",
    description: str = "",
    owner: str = "number_one",
    risk_level: str = "low",
) -> str | None:
    """Register an architecture entity. Returns entity_id or None."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        c = _client()
        if c is not None:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .like("owner", f"{ARCH_ENTITY_OWNER_PREFIX}%")
                .ilike("statement", f"%{name[:40]}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                log.debug("[enterprise_architecture] entity already registered: %s", name[:40])
                return None

        entity_id = f"ae-{uuid4().hex[:8]}"
        entity = ArchEntity(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            state=state,
            capability_id=capability_id,
            initiative_id=initiative_id,
            description=description,
            owner=owner,
            risk_level=risk_level,
        )
        log_decision_to_command_memory(
            statement=f"{_ARCH_STATEMENT} {entity_id}: {name[:80]}",
            rationale=_build_rationale(entity),
            owner=f"{ARCH_ENTITY_OWNER_PREFIX}{entity_id}",
        )
        log.info("[enterprise_architecture] Registered %s — %s (%s)", entity_id, name[:60], state.value)
        return entity_id
    except Exception as exc:
        log.warning("[enterprise_architecture] register_arch_entity failed: %s", exc)
        return None


def list_arch_entities(
    state: ArchEntityState | None = None,
    limit: int = 200,
) -> list[ArchEntity]:
    """Return architecture entities, optionally filtered by state."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{ARCH_ENTITY_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[ArchEntity] = []
        for row in res.data or []:
            e = _row_to_entity(row)
            if not e:
                continue
            if state is not None and e.state != state:
                continue
            out.append(e)
        return out
    except Exception as exc:
        log.debug("[enterprise_architecture] list_arch_entities failed: %s", exc)
        return []


def get_architecture_view() -> ArchitectureView:
    """Return the full current/target/transition architecture view."""
    av = ArchitectureView()

    entities = list_arch_entities()
    for e in entities:
        if e.state == ArchEntityState.CURRENT:
            av.current.append(e)
        elif e.state == ArchEntityState.TARGET:
            av.target.append(e)
        elif e.state == ArchEntityState.TRANSITION:
            av.transition.append(e)
        elif e.state == ArchEntityState.DEPRECATED:
            av.deprecated.append(e)

    # Pull ADR metrics from architecture_records table (reused from EXEC-005)
    try:
        c = _client()
        if c is not None:
            res = c.raw_client.table("architecture_records").select("id,coverage_pct", count="exact").limit(1).execute()
            av.adr_count = res.count or 0
            rows = list(res.data or [])
            if rows and rows[0].get("coverage_pct") is not None:
                av.adr_coverage_pct = float(rows[0]["coverage_pct"])
    except Exception as exc:
        log.debug("[enterprise_architecture] adr read failed: %s", exc)

    log.info("[enterprise_architecture] current=%d target=%d transition=%d",
             len(av.current), len(av.target), len(av.transition))
    return av


def format_architecture_view(av: ArchitectureView) -> str:
    if av.total == 0:
        return "_No architecture entities registered._"
    lines = ["*Enterprise Architecture View:*"]
    lines.append(f"  Current: {len(av.current)} | Target: {len(av.target)} | Transition: {len(av.transition)} | Deprecated: {len(av.deprecated)}")
    if av.adr_count:
        lines.append(f"  ADR coverage: {av.adr_coverage_pct:.0%} ({av.adr_count} records)")
    if av.high_risk:
        lines.append(f"  :red_circle: High-risk entities: {len(av.high_risk)}")
        for e in av.high_risk[:3]:
            lines.append(f"    · {e.name} [{e.state.value}]")
    return "\n".join(lines)


__all__ = [
    "ArchEntityState",
    "ArchEntityType",
    "ArchEntity",
    "ArchitectureView",
    "get_architecture_view",
    "register_arch_entity",
    "list_arch_entities",
    "format_architecture_view",
    "ARCH_ENTITY_OWNER_PREFIX",
]
