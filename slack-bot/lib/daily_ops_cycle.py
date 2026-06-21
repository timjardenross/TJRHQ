"""Daily Operating Cycle — Executive Staff Orchestrator (EXEC-001 WP5).

Sequences officer outputs in the prescribed order and assembles the Captain brief.
Officers consume outputs from previous officers — no isolated reporting.

Sequence:
  1. Human Systems    — capacity gate (governs everything downstream)
  2. Strategic Planning — portfolio decisions
  3. ORI              — resilience intelligence
  4. Engineering      — delivery status
  5. Communications   — pipeline status
  6. Number One       — consolidation + executive summary
  7. XO               — executive review
  8. Captain Brief    — Top 3 + exceptions + decisions + capacity

The Captain receives an executive brief, not raw operational data.

Public API:
    run_daily_cycle(missions: list[dict], capacity_entry: dict | None) -> str
    assemble_executive_brief(context: CycleContext) -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Context ───────────────────────────────────────────────────────────────────

@dataclass
class CycleContext:
    """All officer outputs collected during the daily cycle."""
    capacity_status: str = "Unknown"
    capacity_score: int | None = None
    capacity_actions: list[dict] = field(default_factory=list)

    portfolio_items: list[dict] = field(default_factory=list)
    orphan_count: int = 0
    strategic_snapshot_available: bool = False

    resilience_risk: str = "Unknown"
    resilience_summary: str | None = None
    resilience_available: bool = False

    engineering_in_progress: int = 0
    engineering_blocked: int = 0
    engineering_summary: str | None = None

    comms_pipeline: dict = field(default_factory=dict)
    comms_ready_count: int = 0

    number_one_summary: str | None = None
    number_one_items: list[dict] = field(default_factory=list)

    all_items: list[dict] = field(default_factory=list)
    data_freshness: dict[str, str] = field(default_factory=dict)
    cycle_started: datetime = field(default_factory=datetime.utcnow)


# ── Step 1: Human Systems ─────────────────────────────────────────────────────

def _step_human_systems(entry: dict | None, ctx: CycleContext) -> None:
    try:
        from core.health.capacity_score import compute_capacity_score
        from core.health.capacity_gate import CapacityGate

        score, status = compute_capacity_score(entry or {})
        ctx.capacity_score = score
        ctx.capacity_status = status or "Unknown"

        gate = CapacityGate()
        actions = gate.evaluate(score, status, [])
        ctx.capacity_actions = [{"type": a.action_type, "reason": a.reason} for a in actions]

        for a in actions:
            ctx.all_items.append({
                "type": a.item_type,
                "title": a.reason,
                "source": "human_systems",
                "priority": "P0" if status == "Red" else "P2",
            })
        ctx.data_freshness["human_systems"] = datetime.utcnow().isoformat()
    except Exception as exc:
        log.warning("[daily-cycle] Human Systems step failed (non-blocking): %s", exc)
        ctx.capacity_status = "Unknown"


# ── Step 2: Strategic Planning ────────────────────────────────────────────────

def _step_strategic_planning(ctx: CycleContext) -> None:
    try:
        from lib.strategy.portfolio_queries import run_portfolio_queries

        result = run_portfolio_queries()
        ctx.strategic_snapshot_available = result.get("available", False)
        ctx.orphan_count = result.get("orphan_count", 0)

        for item in result.get("items", []):
            ctx.portfolio_items.append(item)
            ctx.all_items.append({
                "type": item.get("type", "strategic_decision"),
                "title": item.get("title", ""),
                "source": "strategic_planning",
                "priority": item.get("priority", "P2"),
            })
        ctx.data_freshness["strategic_planning"] = datetime.utcnow().isoformat()
    except Exception as exc:
        log.warning("[daily-cycle] Strategic Planning step failed (non-blocking): %s", exc)


# ── Step 3: ORI ───────────────────────────────────────────────────────────────

def _step_ori(ctx: CycleContext) -> None:
    try:
        from tools.supabase.client import CommanderSupabaseClient

        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return

        res = c.raw_client.table("intelligence_briefs").select(
            "brief_id,overall_risk,executive_snapshot,bottom_line,generated_at"
        ).order("generated_at", desc=True).limit(1).execute()

        rows = list(res.data or [])
        if not rows:
            return

        brief = rows[0]
        ctx.resilience_risk = brief.get("overall_risk", "Unknown")
        ctx.resilience_summary = brief.get("bottom_line") or brief.get("executive_snapshot")
        ctx.resilience_available = True

        if ctx.resilience_risk in ("RED", "AMBER"):
            ctx.all_items.append({
                "type": "critical_resilience_event" if ctx.resilience_risk == "RED" else "resilience_advisory",
                "title": f"ORI: {ctx.resilience_risk} — {(ctx.resilience_summary or '')[:120]}",
                "source": "ori",
                "priority": "P0" if ctx.resilience_risk == "RED" else "P1",
                "mission_id": brief.get("brief_id", ""),
            })
        ctx.data_freshness["ori"] = datetime.utcnow().isoformat()
    except Exception as exc:
        log.warning("[daily-cycle] ORI step failed (non-blocking): %s", exc)


# ── Step 4: Engineering ───────────────────────────────────────────────────────

def _step_engineering(missions: list[dict], ctx: CycleContext) -> None:
    try:
        BLOCKED_STATUSES = {"blocked", "blocked_ops"}
        IN_PROGRESS = {"designed", "implemented", "tested", "active", "in_progress"}

        for m in missions:
            status = str(m.get("status") or "").lower()
            if status in BLOCKED_STATUSES:
                ctx.engineering_blocked += 1
                if str(m.get("priority", "P3")).upper() in ("P0", "P1"):
                    ctx.all_items.append({
                        "type": "stale_mission",
                        "title": f"Engineering blocked: {m.get('title', m.get('id', ''))}",
                        "source": "engineering",
                        "priority": str(m.get("priority", "P2")),
                        "mission_id": m.get("id") or m.get("mission_id", ""),
                    })
            elif status in IN_PROGRESS:
                ctx.engineering_in_progress += 1

        ctx.data_freshness["engineering"] = datetime.utcnow().isoformat()
    except Exception as exc:
        log.warning("[daily-cycle] Engineering step failed (non-blocking): %s", exc)


# ── Step 5: Communications ────────────────────────────────────────────────────

def _step_communications(ctx: CycleContext) -> None:
    try:
        from lib.comms.pipeline import get_pipeline_status

        status = get_pipeline_status()
        ctx.comms_pipeline = status
        ctx.comms_ready_count = status.get("ready_to_publish", 0)

        if ctx.comms_ready_count > 0:
            ctx.all_items.append({
                "type": "comms_ready",
                "title": f"{ctx.comms_ready_count} item(s) ready to publish — Captain approval required",
                "source": "communications",
                "priority": "P3",
            })
        ctx.data_freshness["communications"] = datetime.utcnow().isoformat()
    except Exception as exc:
        log.warning("[daily-cycle] Communications step failed (non-blocking): %s", exc)


# ── Step 6: Number One Consolidation ─────────────────────────────────────────

def _step_number_one(missions: list[dict], ctx: CycleContext) -> None:
    try:
        from core.coordination.execution_engine import NumberOneExecutionEngine

        engine = NumberOneExecutionEngine()
        summary = engine.generate_executive_summary(missions)
        ctx.number_one_summary = engine.format_captain_brief_section(summary)

        # Surface Number One escalations into all_items
        for e in summary.escalations:
            ctx.all_items.append({
                "type": "routine_escalation" if e.route_to == "number_one" else "stale_mission",
                "title": f"Number One escalation: {e.mission_id} ({e.escalation_type})",
                "source": "number_one",
                "priority": e.priority,
                "mission_id": e.mission_id,
            })
        ctx.data_freshness["number_one"] = datetime.utcnow().isoformat()
    except Exception as exc:
        log.warning("[daily-cycle] Number One step failed (non-blocking): %s", exc)


# ── Assembly ──────────────────────────────────────────────────────────────────

def assemble_executive_brief(ctx: CycleContext) -> str:
    """Route all items and format Captain brief. Step 7 + 8."""
    try:
        from core.coordination.exception_router import classify_all, format_captain_brief

        routed = classify_all(ctx.all_items)
        brief = format_captain_brief(
            routed,
            capacity_status=ctx.capacity_status,
            number_one_summary=ctx.number_one_summary,
        )
        return brief
    except Exception as exc:
        log.warning("[daily-cycle] Brief assembly failed, returning fallback: %s", exc)
        return _fallback_brief(ctx)


def _fallback_brief(ctx: CycleContext) -> str:
    """Minimal brief when routing is unavailable."""
    return (
        f"*CAPTAIN BRIEF — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*\n"
        f"Capacity: {ctx.capacity_status}\n"
        f"Engineering in progress: {ctx.engineering_in_progress} | Blocked: {ctx.engineering_blocked}\n"
        f"ORI Risk: {ctx.resilience_risk}\n"
        f"Comms ready: {ctx.comms_ready_count}\n"
        f"_(Full brief assembly unavailable — raw summary only)_"
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def run_daily_cycle(
    missions: list[dict[str, Any]],
    capacity_entry: dict[str, Any] | None = None,
) -> str:
    """Run the full daily operating cycle and return the Captain brief.

    Sequence:
      Human Systems → Strategic Planning → ORI → Engineering →
      Communications → Number One → Exception Router → Captain Brief

    Non-blocking: each step degrades gracefully if data is unavailable.
    Data freshness is tracked; stale inputs are labelled in the brief.
    """
    ctx = CycleContext()

    _step_human_systems(capacity_entry, ctx)
    _step_strategic_planning(ctx)
    _step_ori(ctx)
    _step_engineering(missions, ctx)
    _step_communications(ctx)
    _step_number_one(missions, ctx)

    return assemble_executive_brief(ctx)


__all__ = [
    "run_daily_cycle",
    "assemble_executive_brief",
    "CycleContext",
]
