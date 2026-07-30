"""Capability Framework (EXEC-009 WP1).

Introduces the Capability layer between strategic objectives and delivery:

    Strategic Objective → Capability → Systems / Processes / Resources

Capability types:
  Strategic    — organisational direction and decision-making
  Operational  — reliable execution at scale
  Technology   — systems, platforms, and tooling
  Knowledge    — intellectual capital and organisational learning
  Human        — people capacity, skills, and team effectiveness
  Resilience   — ability to withstand, adapt, and recover from disruption

Reuse: decisions table (zero new tables — ADR-0020). Capability records
reference objectives and initiatives established in EXEC-006.

Storage:
  statement = "[CAPABILITY] {cap_id}: {name[:80]}"
  owner     = "capability:{cap_id}"
  rationale = "TYPE: {t} | OBJECTIVE: {obj} | INITIATIVE: {init} |
               SYSTEM: {sys} | MATURITY: {m} | OWNER: {o} |
               STATUS: {s} | DEPS: {deps} | PURPOSE: {p} | DESC: {d}"

  Capability–system links (separate sub-records, not matched by LIKE 'capability:%'):
  owner     = "capability_link:{cap_id}"
  statement = "[CAP LINK] {cap_id} > {system_id}"

Public API:
    CapabilityType, CapabilityStatus, MaturityLevel
    Capability
    register_capability(name, cap_type, ...) -> str | None
    update_capability(cap_id, **fields)      -> bool
    get_capability(cap_id)                   -> Capability | None
    list_capabilities(cap_type)              -> list[Capability]
    get_capabilities_for_objective(obj_id)   -> list[Capability]
    CAPABILITY_OWNER_PREFIX
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

CAPABILITY_OWNER_PREFIX  = "capability:"
_CAPABILITY_LINK_PREFIX  = "capability_link:"
_CAP_STATEMENT           = "[CAPABILITY]"
_CAP_LINK_STATEMENT      = "[CAP LINK]"


class CapabilityType(str, Enum):
    STRATEGIC   = "strategic"
    OPERATIONAL = "operational"
    TECHNOLOGY  = "technology"
    KNOWLEDGE   = "knowledge"
    HUMAN       = "human"
    RESILIENCE  = "resilience"


class CapabilityStatus(str, Enum):
    ACTIVE      = "active"
    DEVELOPING  = "developing"
    DEPRECATED  = "deprecated"
    REQUIRED    = "required"      # gap: required but not yet built


class MaturityLevel(int, Enum):
    AD_HOC             = 1
    EMERGING           = 2
    MANAGED            = 3
    OPTIMISED          = 4
    STRATEGIC_ADVANTAGE = 5

    @property
    def label(self) -> str:
        _labels = {1: "Ad Hoc", 2: "Emerging", 3: "Managed", 4: "Optimised", 5: "Strategic Advantage"}
        return _labels[self.value]


@dataclass
class Capability:
    capability_id: str
    name: str
    cap_type: CapabilityType = CapabilityType.OPERATIONAL
    objective_id: str = ""
    initiative_id: str = ""
    system_id: str = ""
    maturity: MaturityLevel = MaturityLevel.AD_HOC
    owner: str = "number_one"
    status: CapabilityStatus = CapabilityStatus.ACTIVE
    dependencies: str = ""
    purpose: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def maturity_label(self) -> str:
        return self.maturity.label

    @property
    def is_gap(self) -> bool:
        return self.status == CapabilityStatus.REQUIRED

    @property
    def is_weak(self) -> bool:
        return self.maturity.value <= 2 and self.status == CapabilityStatus.ACTIVE


def _build_rationale(c: Capability) -> str:
    return " | ".join([
        f"TYPE: {c.cap_type.value}",
        f"OBJECTIVE: {c.objective_id}",
        f"INITIATIVE: {c.initiative_id}",
        f"SYSTEM: {c.system_id[:60]}",
        f"MATURITY: {c.maturity.value}",
        f"OWNER: {c.owner}",
        f"STATUS: {c.status.value}",
        f"DEPS: {c.dependencies[:80]}",
        f"PURPOSE: {c.purpose[:100]}",
        f"DESC: {c.description[:120]}",
    ])


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _row_to_capability(row: dict[str, Any]) -> Capability | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(CAPABILITY_OWNER_PREFIX):
        return None
    cap_id = owner[len(CAPABILITY_OWNER_PREFIX):]
    p = _parse_rationale(str(row.get("rationale") or ""))
    stmt = str(row.get("statement") or "")
    prefix = f"{_CAP_STATEMENT} {cap_id}: "
    name = stmt[len(prefix):] if stmt.startswith(prefix) else stmt

    def _en(cls, val, default):
        try:
            return cls(val)
        except (ValueError, KeyError):
            return default

    try:
        maturity = MaturityLevel(int(p.get("MATURITY", "1") or "1"))
    except (ValueError, TypeError):
        maturity = MaturityLevel.AD_HOC

    return Capability(
        capability_id=cap_id,
        name=name,
        cap_type=_en(CapabilityType, p.get("TYPE", "operational"), CapabilityType.OPERATIONAL),
        objective_id=p.get("OBJECTIVE", ""),
        initiative_id=p.get("INITIATIVE", ""),
        system_id=p.get("SYSTEM", ""),
        maturity=maturity,
        owner=p.get("OWNER", "number_one"),
        status=_en(CapabilityStatus, p.get("STATUS", "active"), CapabilityStatus.ACTIVE),
        dependencies=p.get("DEPS", ""),
        purpose=p.get("PURPOSE", ""),
        description=p.get("DESC", ""),
    )


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[strategy.capabilities] Supabase unavailable: %s", exc)
        return None


# ── CRUD ──────────────────────────────────────────────────────────────────────

def register_capability(
    name: str,
    cap_type: CapabilityType = CapabilityType.OPERATIONAL,
    *,
    objective_id: str = "",
    initiative_id: str = "",
    system_id: str = "",
    maturity: MaturityLevel = MaturityLevel.AD_HOC,
    owner: str = "number_one",
    status: CapabilityStatus = CapabilityStatus.ACTIVE,
    dependencies: str = "",
    purpose: str = "",
    description: str = "",
) -> str | None:
    """Register a new capability in the capability catalogue.

    Returns capability_id (e.g. "cap-a1b2c3d4") or None on failure.
    Dedup-safe: same name + type + objective will not create duplicates.
    """
    try:
        from command_memory_integration import log_decision_to_command_memory

        c = _client()
        if c is not None:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .like("owner", f"{CAPABILITY_OWNER_PREFIX}%")
                .ilike("statement", f"%{name[:40]}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                log.debug("[strategy.capabilities] capability already registered: %s", name[:40])
                return None

        cap_id = f"cap-{uuid4().hex[:8]}"
        cap = Capability(
            capability_id=cap_id,
            name=name,
            cap_type=cap_type,
            objective_id=objective_id,
            initiative_id=initiative_id,
            system_id=system_id,
            maturity=maturity,
            owner=owner,
            status=status,
            dependencies=dependencies,
            purpose=purpose,
            description=description,
        )
        log_decision_to_command_memory(
            statement=f"{_CAP_STATEMENT} {cap_id}: {name[:80]}",
            rationale=_build_rationale(cap),
            owner=f"{CAPABILITY_OWNER_PREFIX}{cap_id}",
        )
        log.info("[strategy.capabilities] Registered %s — %s (%s)", cap_id, name[:60], cap_type.value)
        return cap_id

    except Exception as exc:
        log.warning("[strategy.capabilities] register_capability failed: %s", exc)
        return None


def update_capability(capability_id: str, **fields: Any) -> bool:
    """Update capability fields: maturity, status, objective_id, initiative_id,
    system_id, owner, dependencies, purpose, description."""
    try:
        c = _client()
        if c is None:
            return False
        owner_key = f"{CAPABILITY_OWNER_PREFIX}{capability_id}"
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
        cap = _row_to_capability({**rows[0], "owner": owner_key})
        if cap is None:
            return False
        for k, v in fields.items():
            if not hasattr(cap, k):
                continue
            if k == "cap_type":
                v = v if isinstance(v, CapabilityType) else CapabilityType(str(v))
            elif k == "maturity":
                v = v if isinstance(v, MaturityLevel) else MaturityLevel(int(v))
            elif k == "status":
                v = v if isinstance(v, CapabilityStatus) else CapabilityStatus(str(v))
            setattr(cap, k, v)
        c.raw_client.table("decisions").update({"rationale": _build_rationale(cap)}).eq("id", rows[0]["id"]).execute()
        return True
    except Exception as exc:
        log.debug("[strategy.capabilities] update_capability failed: %s", exc)
        return False


def get_capability(capability_id: str) -> Capability | None:
    try:
        c = _client()
        if c is None:
            return None
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .eq("owner", f"{CAPABILITY_OWNER_PREFIX}{capability_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        return _row_to_capability(rows[0]) if rows else None
    except Exception as exc:
        log.debug("[strategy.capabilities] get_capability failed: %s", exc)
        return None


def list_capabilities(
    cap_type: CapabilityType | None = None,
    limit: int = 200,
) -> list[Capability]:
    """Return capabilities, optionally filtered by type."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{CAPABILITY_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[Capability] = []
        for row in res.data or []:
            cap = _row_to_capability(row)
            if not cap:
                continue
            if cap_type is not None and cap.cap_type != cap_type:
                continue
            out.append(cap)
        return out
    except Exception as exc:
        log.debug("[strategy.capabilities] list_capabilities failed: %s", exc)
        return []


def get_capabilities_for_objective(objective_id: str) -> list[Capability]:
    """Return capabilities linked to a strategic objective."""
    return [c for c in list_capabilities() if c.objective_id == objective_id]


__all__ = [
    "CapabilityType",
    "CapabilityStatus",
    "MaturityLevel",
    "Capability",
    "register_capability",
    "update_capability",
    "get_capability",
    "list_capabilities",
    "get_capabilities_for_objective",
    "CAPABILITY_OWNER_PREFIX",
]
