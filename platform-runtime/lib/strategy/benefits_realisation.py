"""Benefits Realisation Tracking (EXEC-010 WP6).

Extends EXEC-008 benefits with a full lifecycle:

  EXPECTED → PLANNED → IN_PROGRESS → REALISED → VERIFIED → SUSTAINED

Answers:
  - Did the benefit occur?
  - Was it verified independently?
  - Is it still occurring (sustained)?

No new tables. Lifecycle state stored in decisions table:
  statement = "[BENEFIT RL] {benefit_id}: {lifecycle_status}"
  owner     = "benefit_rl:{benefit_id}"
  rationale = "BENEFIT_ID: {b} | INITIATIVE: {i} | STATUS: {s} |
               EVIDENCE: {e} | VERIFIED_BY: {v} | VERIFIED_DATE: {d} |
               SUSTAINED_SINCE: {ss} | NOTES: {n}"

Reuses lib.strategy.benefits and lib.strategy.value_realisation (EXEC-008).

Public API:
    BenefitLifecycleStatus
    BenefitRealisationRecord
    advance_benefit_lifecycle(benefit_id, new_status, evidence, ...)  -> bool
    get_benefit_lifecycle(benefit_id)                                  -> BenefitRealisationRecord | None
    list_benefit_lifecycles(status)                                    -> list[BenefitRealisationRecord]
    assess_lifecycle_health()                                          -> dict[str, Any]
    format_lifecycle_summary(records)                                  -> str
    BENEFIT_RL_OWNER_PREFIX
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

BENEFIT_RL_OWNER_PREFIX = "benefit_rl:"
_BENEFIT_RL_STATEMENT   = "[BENEFIT RL]"

_LIFECYCLE_ORDER = [
    "expected", "planned", "in_progress", "realised", "verified", "sustained"
]


class BenefitLifecycleStatus(str, Enum):
    EXPECTED    = "expected"
    PLANNED     = "planned"
    IN_PROGRESS = "in_progress"
    REALISED    = "realised"
    VERIFIED    = "verified"
    SUSTAINED   = "sustained"

    @property
    def order(self) -> int:
        return _LIFECYCLE_ORDER.index(self.value)

    @property
    def is_complete(self) -> bool:
        return self in (BenefitLifecycleStatus.REALISED, BenefitLifecycleStatus.VERIFIED,
                        BenefitLifecycleStatus.SUSTAINED)


@dataclass
class BenefitRealisationRecord:
    benefit_id: str
    initiative_id: str = ""
    lifecycle_status: BenefitLifecycleStatus = BenefitLifecycleStatus.EXPECTED
    evidence: str = ""
    verified_by: str = ""
    verified_date: str = ""
    sustained_since: str = ""
    notes: str = ""

    @property
    def is_at_risk(self) -> bool:
        return self.lifecycle_status == BenefitLifecycleStatus.EXPECTED and not self.evidence

    @property
    def has_regressed(self) -> bool:
        """True if realised but no sustained evidence after verified."""
        return (
            self.lifecycle_status == BenefitLifecycleStatus.REALISED
            and not self.sustained_since
            and not self.verified_by
        )


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[benefits_realisation] Supabase unavailable: %s", exc)
        return None


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _build_rationale(r: BenefitRealisationRecord) -> str:
    return " | ".join([
        f"BENEFIT_ID: {r.benefit_id}",
        f"INITIATIVE: {r.initiative_id}",
        f"STATUS: {r.lifecycle_status.value}",
        f"EVIDENCE: {r.evidence[:80]}",
        f"VERIFIED_BY: {r.verified_by}",
        f"VERIFIED_DATE: {r.verified_date}",
        f"SUSTAINED_SINCE: {r.sustained_since}",
        f"NOTES: {r.notes[:80]}",
    ])


def _row_to_record(row: dict[str, Any]) -> BenefitRealisationRecord | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(BENEFIT_RL_OWNER_PREFIX):
        return None
    benefit_id = owner[len(BENEFIT_RL_OWNER_PREFIX):]
    p = _parse_rationale(str(row.get("rationale") or ""))

    def _en(cls, val, default):
        try:
            return cls(val)
        except (ValueError, KeyError):
            return default

    return BenefitRealisationRecord(
        benefit_id=benefit_id,
        initiative_id=p.get("INITIATIVE", ""),
        lifecycle_status=_en(BenefitLifecycleStatus, p.get("STATUS", "expected"), BenefitLifecycleStatus.EXPECTED),
        evidence=p.get("EVIDENCE", ""),
        verified_by=p.get("VERIFIED_BY", ""),
        verified_date=p.get("VERIFIED_DATE", ""),
        sustained_since=p.get("SUSTAINED_SINCE", ""),
        notes=p.get("NOTES", ""),
    )


def advance_benefit_lifecycle(
    benefit_id: str,
    new_status: BenefitLifecycleStatus,
    *,
    evidence: str = "",
    verified_by: str = "",
    notes: str = "",
    initiative_id: str = "",
) -> bool:
    """Advance a benefit to a new lifecycle stage. Creates or updates the record."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        c = _client()
        owner_key = f"{BENEFIT_RL_OWNER_PREFIX}{benefit_id}"
        today = date.today().isoformat()

        # Check if record exists
        existing_rec = get_benefit_lifecycle(benefit_id)
        if existing_rec is not None:
            # Only advance, not regress
            if new_status.order < existing_rec.lifecycle_status.order:
                log.warning("[benefits_realisation] Cannot regress %s from %s to %s",
                            benefit_id, existing_rec.lifecycle_status.value, new_status.value)
                return False
            existing_rec.lifecycle_status = new_status
            if evidence:
                existing_rec.evidence = evidence
            if verified_by:
                existing_rec.verified_by = verified_by
                existing_rec.verified_date = today
            if new_status == BenefitLifecycleStatus.SUSTAINED and not existing_rec.sustained_since:
                existing_rec.sustained_since = today
            if notes:
                existing_rec.notes = notes

            if c is not None:
                res = (
                    c.raw_client.table("decisions")
                    .select("id")
                    .eq("owner", owner_key)
                    .limit(1)
                    .execute()
                )
                rows = list(res.data or [])
                if rows:
                    c.raw_client.table("decisions").update({
                        "statement": f"{_BENEFIT_RL_STATEMENT} {benefit_id}: {new_status.value}",
                        "rationale": _build_rationale(existing_rec),
                    }).eq("id", rows[0]["id"]).execute()
                    return True

        # Create new record
        rec = BenefitRealisationRecord(
            benefit_id=benefit_id,
            initiative_id=initiative_id,
            lifecycle_status=new_status,
            evidence=evidence,
            verified_by=verified_by,
            verified_date=today if verified_by else "",
            sustained_since=today if new_status == BenefitLifecycleStatus.SUSTAINED else "",
            notes=notes,
        )
        log_decision_to_command_memory(
            statement=f"{_BENEFIT_RL_STATEMENT} {benefit_id}: {new_status.value}",
            rationale=_build_rationale(rec),
            owner=owner_key,
        )
        log.info("[benefits_realisation] %s advanced to %s", benefit_id, new_status.value)
        return True
    except Exception as exc:
        log.warning("[benefits_realisation] advance_benefit_lifecycle failed: %s", exc)
        return False


def get_benefit_lifecycle(benefit_id: str) -> BenefitRealisationRecord | None:
    try:
        c = _client()
        if c is None:
            return None
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .eq("owner", f"{BENEFIT_RL_OWNER_PREFIX}{benefit_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        return _row_to_record(rows[0]) if rows else None
    except Exception as exc:
        log.debug("[benefits_realisation] get_benefit_lifecycle failed: %s", exc)
        return None


def list_benefit_lifecycles(
    status: BenefitLifecycleStatus | None = None,
    limit: int = 300,
) -> list[BenefitRealisationRecord]:
    """Return benefit realisation records, optionally filtered by lifecycle status."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{BENEFIT_RL_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[BenefitRealisationRecord] = []
        for row in res.data or []:
            r = _row_to_record(row)
            if not r:
                continue
            if status is not None and r.lifecycle_status != status:
                continue
            out.append(r)
        return out
    except Exception as exc:
        log.debug("[benefits_realisation] list_benefit_lifecycles failed: %s", exc)
        return []


def assess_lifecycle_health() -> dict[str, Any]:
    """Summarise benefit lifecycle health across the portfolio."""
    records = list_benefit_lifecycles()
    dist: dict[str, int] = {}
    at_risk = 0
    for r in records:
        dist[r.lifecycle_status.value] = dist.get(r.lifecycle_status.value, 0) + 1
        if r.is_at_risk:
            at_risk += 1

    total = len(records)
    sustained_count = dist.get("sustained", 0) + dist.get("verified", 0)
    realisation_rate = sustained_count / total if total > 0 else 0.0

    return {
        "total": total,
        "distribution": dist,
        "at_risk_count": at_risk,
        "realisation_rate": round(realisation_rate, 3),
        "sustained_count": sustained_count,
    }


def format_lifecycle_summary(records: list[BenefitRealisationRecord]) -> str:
    if not records:
        return "_No benefit lifecycle records._"
    dist: dict[str, int] = {}
    for r in records:
        dist[r.lifecycle_status.value] = dist.get(r.lifecycle_status.value, 0) + 1
    icons = {
        "expected": "○", "planned": "◐", "in_progress": "◑",
        "realised": "●", "verified": ":white_check_mark:", "sustained": ":large_green_circle:"
    }
    lines = [f"*Benefit Lifecycle ({len(records)} benefits):*"]
    for status in _LIFECYCLE_ORDER:
        count = dist.get(status, 0)
        if count:
            icon = icons.get(status, "·")
            lines.append(f"  {icon} {status.replace('_', ' ').title()}: {count}")
    at_risk = sum(1 for r in records if r.is_at_risk)
    if at_risk:
        lines.append(f"  :warning: {at_risk} expected benefit(s) with no evidence")
    return "\n".join(lines)


__all__ = [
    "BenefitLifecycleStatus",
    "BenefitRealisationRecord",
    "advance_benefit_lifecycle",
    "get_benefit_lifecycle",
    "list_benefit_lifecycles",
    "assess_lifecycle_health",
    "format_lifecycle_summary",
    "BENEFIT_RL_OWNER_PREFIX",
]
