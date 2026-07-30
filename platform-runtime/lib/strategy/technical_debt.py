"""Technical Debt & Sustainability Engine (EXEC-009 WP5).

Tracks, scores, and trends technical debt across the portfolio. Debt is an
investment risk — accumulating silently until it limits capacity, increases
failure probability, and crowds out strategic capability-building.

No new database tables. Stores debt records in the decisions table:
  statement = "[TECH DEBT] {debt_id}: {name[:80]}"
  owner     = "tech_debt:{debt_id}"
  rationale = "AREA: {a} | SEVERITY: {s} | SCORE: {n} | INITIATIVE: {i} |
               CAPABILITY: {c} | TREND: {t} | IMPACT: {imp} | DESC: {d}"

Debt scores: 1–10 (10 = most severe)
Severity bands: critical (8–10), high (6–7), medium (4–5), low (1–3)

Public API:
    DebtSeverity, DebtArea, DebtTrend
    TechDebt
    register_debt(...)              -> str | None
    update_debt(debt_id, **fields) -> bool
    get_debt(debt_id)              -> TechDebt | None
    list_debts(severity)           -> list[TechDebt]
    compute_debt_profile()         -> DebtProfile
    format_debt_profile(dp)        -> str
    TECH_DEBT_OWNER_PREFIX
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

TECH_DEBT_OWNER_PREFIX = "tech_debt:"
_DEBT_STATEMENT        = "[TECH DEBT]"


class DebtSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class DebtArea(str, Enum):
    ARCHITECTURE  = "architecture"
    CODE          = "code"
    PROCESS       = "process"
    KNOWLEDGE     = "knowledge"
    TOOLING       = "tooling"
    DATA          = "data"
    SECURITY      = "security"
    OPERATIONAL   = "operational"


class DebtTrend(str, Enum):
    INCREASING  = "increasing"
    STABLE      = "stable"
    DECREASING  = "decreasing"


@dataclass
class TechDebt:
    debt_id: str
    name: str
    area: DebtArea = DebtArea.CODE
    severity: DebtSeverity = DebtSeverity.MEDIUM
    score: int = 5                 # 1–10
    initiative_id: str = ""
    capability_id: str = ""
    trend: DebtTrend = DebtTrend.STABLE
    impact: str = ""
    description: str = ""

    @property
    def is_blocking(self) -> bool:
        return self.score >= 8

    @property
    def requires_escalation(self) -> bool:
        return self.severity in (DebtSeverity.CRITICAL, DebtSeverity.HIGH)


@dataclass
class DebtProfile:
    total: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    average_score: float = 0.0
    increasing_count: int = 0
    top_areas: list[tuple[str, int]] = field(default_factory=list)   # (area, count) sorted desc
    top_debts: list[TechDebt] = field(default_factory=list)

    @property
    def portfolio_risk(self) -> str:
        if self.critical_count >= 2 or self.average_score >= 7.5:
            return "high"
        if self.critical_count >= 1 or self.high_count >= 3 or self.average_score >= 5.5:
            return "medium"
        return "low"


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[technical_debt] Supabase unavailable: %s", exc)
        return None


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _build_rationale(d: TechDebt) -> str:
    return " | ".join([
        f"AREA: {d.area.value}",
        f"SEVERITY: {d.severity.value}",
        f"SCORE: {d.score}",
        f"INITIATIVE: {d.initiative_id}",
        f"CAPABILITY: {d.capability_id}",
        f"TREND: {d.trend.value}",
        f"IMPACT: {d.impact[:80]}",
        f"DESC: {d.description[:120]}",
    ])


def _row_to_debt(row: dict[str, Any]) -> TechDebt | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(TECH_DEBT_OWNER_PREFIX):
        return None
    debt_id = owner[len(TECH_DEBT_OWNER_PREFIX):]
    p = _parse_rationale(str(row.get("rationale") or ""))
    stmt = str(row.get("statement") or "")
    prefix = f"{_DEBT_STATEMENT} {debt_id}: "
    name = stmt[len(prefix):] if stmt.startswith(prefix) else stmt

    def _en(cls, val, default):
        try:
            return cls(val)
        except (ValueError, KeyError):
            return default

    try:
        score = max(1, min(10, int(p.get("SCORE", "5") or "5")))
    except (ValueError, TypeError):
        score = 5

    return TechDebt(
        debt_id=debt_id,
        name=name,
        area=_en(DebtArea, p.get("AREA", "code"), DebtArea.CODE),
        severity=_en(DebtSeverity, p.get("SEVERITY", "medium"), DebtSeverity.MEDIUM),
        score=score,
        initiative_id=p.get("INITIATIVE", ""),
        capability_id=p.get("CAPABILITY", ""),
        trend=_en(DebtTrend, p.get("TREND", "stable"), DebtTrend.STABLE),
        impact=p.get("IMPACT", ""),
        description=p.get("DESC", ""),
    )


def register_debt(
    name: str,
    area: DebtArea = DebtArea.CODE,
    *,
    severity: DebtSeverity = DebtSeverity.MEDIUM,
    score: int = 5,
    initiative_id: str = "",
    capability_id: str = "",
    trend: DebtTrend = DebtTrend.STABLE,
    impact: str = "",
    description: str = "",
) -> str | None:
    """Register a technical debt item. Returns debt_id or None."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        c = _client()
        if c is not None:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .like("owner", f"{TECH_DEBT_OWNER_PREFIX}%")
                .ilike("statement", f"%{name[:40]}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                log.debug("[technical_debt] debt already registered: %s", name[:40])
                return None

        debt_id = f"td-{uuid4().hex[:8]}"
        score = max(1, min(10, score))
        debt = TechDebt(
            debt_id=debt_id,
            name=name,
            area=area,
            severity=severity,
            score=score,
            initiative_id=initiative_id,
            capability_id=capability_id,
            trend=trend,
            impact=impact,
            description=description,
        )
        log_decision_to_command_memory(
            statement=f"{_DEBT_STATEMENT} {debt_id}: {name[:80]}",
            rationale=_build_rationale(debt),
            owner=f"{TECH_DEBT_OWNER_PREFIX}{debt_id}",
        )
        log.info("[technical_debt] Registered %s — %s (%s)", debt_id, name[:60], severity.value)
        return debt_id
    except Exception as exc:
        log.warning("[technical_debt] register_debt failed: %s", exc)
        return None


def update_debt(debt_id: str, **fields: Any) -> bool:
    """Update a debt record's fields."""
    try:
        c = _client()
        if c is None:
            return False
        owner_key = f"{TECH_DEBT_OWNER_PREFIX}{debt_id}"
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
        debt = _row_to_debt({**rows[0], "owner": owner_key})
        if debt is None:
            return False
        for k, v in fields.items():
            if hasattr(debt, k):
                setattr(debt, k, v)
        c.raw_client.table("decisions").update({"rationale": _build_rationale(debt)}).eq("id", rows[0]["id"]).execute()
        return True
    except Exception as exc:
        log.debug("[technical_debt] update_debt failed: %s", exc)
        return False


def get_debt(debt_id: str) -> TechDebt | None:
    try:
        c = _client()
        if c is None:
            return None
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .eq("owner", f"{TECH_DEBT_OWNER_PREFIX}{debt_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        return _row_to_debt(rows[0]) if rows else None
    except Exception as exc:
        log.debug("[technical_debt] get_debt failed: %s", exc)
        return None


def list_debts(
    severity: DebtSeverity | None = None,
    limit: int = 200,
) -> list[TechDebt]:
    """Return tech debt items, optionally filtered by severity."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{TECH_DEBT_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[TechDebt] = []
        for row in res.data or []:
            d = _row_to_debt(row)
            if not d:
                continue
            if severity is not None and d.severity != severity:
                continue
            out.append(d)
        return out
    except Exception as exc:
        log.debug("[technical_debt] list_debts failed: %s", exc)
        return []


def compute_debt_profile() -> DebtProfile:
    """Compute the portfolio-wide technical debt profile."""
    debts = list_debts()
    dp = DebtProfile(total=len(debts))
    if not debts:
        return dp

    area_counts: dict[str, int] = {}
    score_sum = 0.0
    for d in debts:
        if d.severity == DebtSeverity.CRITICAL:
            dp.critical_count += 1
        elif d.severity == DebtSeverity.HIGH:
            dp.high_count += 1
        elif d.severity == DebtSeverity.MEDIUM:
            dp.medium_count += 1
        else:
            dp.low_count += 1
        if d.trend == DebtTrend.INCREASING:
            dp.increasing_count += 1
        area_counts[d.area.value] = area_counts.get(d.area.value, 0) + 1
        score_sum += d.score

    dp.average_score = round(score_sum / len(debts), 1)
    dp.top_areas = sorted(area_counts.items(), key=lambda x: x[1], reverse=True)[:4]
    dp.top_debts = sorted(debts, key=lambda d: d.score, reverse=True)[:5]
    return dp


def format_debt_profile(dp: DebtProfile) -> str:
    if dp.total == 0:
        return "_No technical debt items registered._"
    risk_icon = {"high": ":red_circle:", "medium": ":large_yellow_circle:", "low": ":large_green_circle:"}.get(
        dp.portfolio_risk, "•"
    )
    lines = [f"*Technical Debt Profile:* {risk_icon} {dp.portfolio_risk.upper()} risk"]
    lines.append(f"  {dp.total} items | avg score {dp.average_score}/10 | {dp.increasing_count} increasing")
    lines.append(f"  Critical: {dp.critical_count} · High: {dp.high_count} · Medium: {dp.medium_count} · Low: {dp.low_count}")
    if dp.top_areas:
        lines.append(f"  Top areas: {', '.join(f'{a} ({n})' for a, n in dp.top_areas[:3])}")
    if dp.top_debts:
        lines.append("  Highest-score items:")
        for d in dp.top_debts[:3]:
            lines.append(f"    · [{d.score}/10] {d.name[:50]} ({d.area.value})")
    return "\n".join(lines)


__all__ = [
    "DebtSeverity",
    "DebtArea",
    "DebtTrend",
    "TechDebt",
    "DebtProfile",
    "register_debt",
    "update_debt",
    "get_debt",
    "list_debts",
    "compute_debt_profile",
    "format_debt_profile",
    "TECH_DEBT_OWNER_PREFIX",
]
