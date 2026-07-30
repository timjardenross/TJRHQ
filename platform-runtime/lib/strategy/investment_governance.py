"""Investment Registry (EXEC-010 WP1).

Tracks investment entities linked directly to initiatives. Answers:
  - What are we investing in?
  - Who approved it?
  - What value is expected?

No new tables. Decisions table reused:
  statement = "[INVESTMENT] {inv_id}: {name[:80]}"
  owner     = "investment:{inv_id}"
  rationale = "INITIATIVE: {i} | SPONSOR: {s} | COST: {c} | EXPECTED_BENEFITS: {b} |
               ALIGNMENT: {a} | STATUS: {st} | REVIEW: {r} | DESC: {d}"

Public API:
    ApprovalStatus, Investment
    register_investment(...)            -> str | None
    update_investment(inv_id, **fields) -> bool
    get_investment(inv_id)              -> Investment | None
    get_investment_for_initiative(init_id) -> Investment | None
    list_investments(status)            -> list[Investment]
    INVESTMENT_OWNER_PREFIX
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
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

INVESTMENT_OWNER_PREFIX = "investment:"
_INVESTMENT_STATEMENT   = "[INVESTMENT]"


class ApprovalStatus(str, Enum):
    PROPOSED               = "proposed"
    UNDER_REVIEW           = "under_review"
    APPROVED               = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    DEFERRED               = "deferred"
    REJECTED               = "rejected"
    ACTIVE                 = "active"
    CLOSED                 = "closed"


@dataclass
class Investment:
    investment_id: str
    name: str
    initiative_id: str = ""
    sponsor: str = "number_one"
    estimated_cost: float = 0.0        # abstract units (e.g. £k, FTE-months)
    expected_benefits: str = ""        # narrative or comma-sep benefit IDs
    strategic_alignment: float = 0.0   # 0.0–1.0
    approval_status: ApprovalStatus = ApprovalStatus.PROPOSED
    review_date: str = ""              # ISO date or empty
    description: str = ""

    @property
    def is_active(self) -> bool:
        return self.approval_status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.APPROVED_WITH_CONDITIONS,
            ApprovalStatus.ACTIVE,
        )

    @property
    def needs_review(self) -> bool:
        if not self.review_date:
            return False
        try:
            return date.fromisoformat(self.review_date) <= date.today()
        except ValueError:
            return False


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[investment_governance] Supabase unavailable: %s", exc)
        return None


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _build_rationale(inv: Investment) -> str:
    return " | ".join([
        f"INITIATIVE: {inv.initiative_id}",
        f"SPONSOR: {inv.sponsor}",
        f"COST: {inv.estimated_cost}",
        f"EXPECTED_BENEFITS: {inv.expected_benefits[:80]}",
        f"ALIGNMENT: {inv.strategic_alignment:.2f}",
        f"STATUS: {inv.approval_status.value}",
        f"REVIEW: {inv.review_date}",
        f"DESC: {inv.description[:120]}",
    ])


def _row_to_investment(row: dict[str, Any]) -> Investment | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(INVESTMENT_OWNER_PREFIX):
        return None
    inv_id = owner[len(INVESTMENT_OWNER_PREFIX):]
    p = _parse_rationale(str(row.get("rationale") or ""))
    stmt = str(row.get("statement") or "")
    prefix = f"{_INVESTMENT_STATEMENT} {inv_id}: "
    name = stmt[len(prefix):] if stmt.startswith(prefix) else stmt

    def _en(cls, val, default):
        try:
            return cls(val)
        except (ValueError, KeyError):
            return default

    try:
        cost = float(p.get("COST", "0") or "0")
    except (ValueError, TypeError):
        cost = 0.0
    try:
        alignment = float(p.get("ALIGNMENT", "0") or "0")
    except (ValueError, TypeError):
        alignment = 0.0

    return Investment(
        investment_id=inv_id,
        name=name,
        initiative_id=p.get("INITIATIVE", ""),
        sponsor=p.get("SPONSOR", "number_one"),
        estimated_cost=cost,
        expected_benefits=p.get("EXPECTED_BENEFITS", ""),
        strategic_alignment=alignment,
        approval_status=_en(ApprovalStatus, p.get("STATUS", "proposed"), ApprovalStatus.PROPOSED),
        review_date=p.get("REVIEW", ""),
        description=p.get("DESC", ""),
    )


def register_investment(
    name: str,
    *,
    initiative_id: str = "",
    sponsor: str = "number_one",
    estimated_cost: float = 0.0,
    expected_benefits: str = "",
    strategic_alignment: float = 0.0,
    approval_status: ApprovalStatus = ApprovalStatus.PROPOSED,
    review_date: str = "",
    description: str = "",
) -> str | None:
    """Register a new investment. Returns investment_id or None."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        c = _client()
        if c is not None:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .like("owner", f"{INVESTMENT_OWNER_PREFIX}%")
                .ilike("statement", f"%{name[:40]}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                log.debug("[investment_governance] investment already registered: %s", name[:40])
                return None

        inv_id = f"inv-{uuid4().hex[:8]}"
        inv = Investment(
            investment_id=inv_id,
            name=name,
            initiative_id=initiative_id,
            sponsor=sponsor,
            estimated_cost=estimated_cost,
            expected_benefits=expected_benefits,
            strategic_alignment=strategic_alignment,
            approval_status=approval_status,
            review_date=review_date,
            description=description,
        )
        log_decision_to_command_memory(
            statement=f"{_INVESTMENT_STATEMENT} {inv_id}: {name[:80]}",
            rationale=_build_rationale(inv),
            owner=f"{INVESTMENT_OWNER_PREFIX}{inv_id}",
        )
        log.info("[investment_governance] Registered %s — %s (%s)", inv_id, name[:60], approval_status.value)
        return inv_id
    except Exception as exc:
        log.warning("[investment_governance] register_investment failed: %s", exc)
        return None


def update_investment(investment_id: str, **fields: Any) -> bool:
    """Update investment fields."""
    try:
        c = _client()
        if c is None:
            return False
        owner_key = f"{INVESTMENT_OWNER_PREFIX}{investment_id}"
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
        inv = _row_to_investment({**rows[0], "owner": owner_key})
        if inv is None:
            return False
        for k, v in fields.items():
            if hasattr(inv, k):
                setattr(inv, k, v)
        c.raw_client.table("decisions").update({"rationale": _build_rationale(inv)}).eq("id", rows[0]["id"]).execute()
        return True
    except Exception as exc:
        log.debug("[investment_governance] update_investment failed: %s", exc)
        return False


def get_investment(investment_id: str) -> Investment | None:
    try:
        c = _client()
        if c is None:
            return None
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .eq("owner", f"{INVESTMENT_OWNER_PREFIX}{investment_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        return _row_to_investment(rows[0]) if rows else None
    except Exception as exc:
        log.debug("[investment_governance] get_investment failed: %s", exc)
        return None


def get_investment_for_initiative(initiative_id: str) -> Investment | None:
    """Return the investment linked to a given initiative."""
    for inv in list_investments():
        if inv.initiative_id == initiative_id:
            return inv
    return None


def list_investments(
    status: ApprovalStatus | None = None,
    limit: int = 200,
) -> list[Investment]:
    """Return investments, optionally filtered by approval status."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{INVESTMENT_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[Investment] = []
        for row in res.data or []:
            inv = _row_to_investment(row)
            if not inv:
                continue
            if status is not None and inv.approval_status != status:
                continue
            out.append(inv)
        return out
    except Exception as exc:
        log.debug("[investment_governance] list_investments failed: %s", exc)
        return []


__all__ = [
    "ApprovalStatus",
    "Investment",
    "register_investment",
    "update_investment",
    "get_investment",
    "get_investment_for_initiative",
    "list_investments",
    "INVESTMENT_OWNER_PREFIX",
]
