"""Daily Operating Cycle — Executive Staff Orchestrator (EXEC-001 WP5 / EXEC-002).

Sequences officer outputs in the prescribed order and assembles the Captain brief.
Officers consume outputs from previous officers — no isolated reporting.

Sequence:
  1. Human Systems      — capacity gate (governs everything downstream)
  2. Strategic Planning — portfolio decisions
  3. ORI                — resilience intelligence
  4. Engineering        — delivery status
  5. Communications     — pipeline status
  6. Number One         — consolidation + executive summary
  7. Improvement Review — D-057 continuous improvement (EXEC-002)
  8. XO                 — executive review (via exception router)
  9. Captain Brief      — Top 3 + exceptions + decisions + capacity

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

    # EXEC-002/002A/003: Continuous Improvement Engine
    improvement_opportunities: list[dict] = field(default_factory=list)
    improvement_missions_created: int = 0
    improvement_missions_deferred: int = 0
    improvement_backlog_count: int = 0   # EXEC-003: persistent backlog depth
    improvement_backlog_drained: int = 0  # EXEC-003: items promoted from backlog
    improvement_summary: str | None = None
    improvement_budget: dict = field(default_factory=dict)

    # EXEC-004: Investigation Lifecycle
    open_investigations_count: int = 0
    high_confidence_findings: list[dict] = field(default_factory=list)
    decision_packages_ready: int = 0
    investigations_closed_this_cycle: int = 0
    new_investigations_opened: list[str] = field(default_factory=list)

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


# ── Step 6.5: Investigation Review (EXEC-004) ────────────────────────────────

def _step_investigation_review(ctx: CycleContext) -> None:
    """D-059 Investigation Lifecycle — run officer investigation triggers.

    Runs after Number One so all operational signals are available in ctx.
    Runs before Improvement Review so investigation findings can feed discovery.

    Sequence:
      1. Run officer investigation triggers (open new investigations on threshold)
      2. For each newly opened investigation: collect evidence + generate findings
      3. Surface high-confidence findings and decision packages in all_items
      4. Surface open investigation count in ctx
    """
    try:
        from lib.investigation.officer_investigations import run_all_investigation_triggers
        from lib.investigation.registry import get_open_investigations, get_investigations_summary
        from lib.investigation.evidence import collect_evidence
        from lib.investigation.findings import generate_findings
        from lib.investigation.decision_package import generate_decision_package, get_pending_decision_packages

        # Trigger new investigations from officer thresholds
        new_inv_ids = run_all_investigation_triggers(ctx)
        ctx.new_investigations_opened = new_inv_ids

        # Collect evidence and generate findings for newly opened investigations
        for inv_id in new_inv_ids[:3]:  # cap at 3 per cycle to bound latency
            try:
                from lib.investigation.registry import get_investigation
                from lib.investigation.registry import update_investigation_status
                from lib.investigation.framework import InvestigationStatus

                inv = get_investigation(inv_id)
                if not inv:
                    continue

                update_investigation_status(inv_id, InvestigationStatus.COLLECTING_EVIDENCE)
                evidence = collect_evidence(inv_id, inv.question, inv.officer, ctx)

                update_investigation_status(inv_id, InvestigationStatus.FINDINGS_READY)
                findings = generate_findings(inv_id, evidence, inv.question)

                # Generate decision package if findings warrant one
                if findings.lead_recommendation and findings.lead_recommendation.action_type in (
                    "mission", "improvement", "decision"
                ):
                    pkg = generate_decision_package(inv_id, findings, inv.question)
                    if pkg:
                        from lib.investigation.framework import InvestigationStatus
                        update_investigation_status(inv_id, InvestigationStatus.DECISION_PENDING)

                # Surface high-confidence findings in all_items
                for finding in findings.high_confidence_findings:
                    ctx.high_confidence_findings.append({
                        "investigation_id": inv_id,
                        "observation": finding.observation[:120],
                        "confidence": finding.confidence,
                        "lead_action": (
                            findings.lead_recommendation.action_type
                            if findings.lead_recommendation else "no_action"
                        ),
                    })
                    ctx.all_items.append({
                        "type": "investigation_finding",
                        "title": f"[INVESTIGATION] {inv_id}: {finding.observation[:80]}",
                        "source": f"investigation:{inv.officer}",
                        "priority": "P1" if finding.confidence >= 0.75 else "P2",
                        "mission_id": inv_id,
                    })

            except Exception as exc:
                log.warning("[daily-cycle] Investigation evidence/findings failed for %s: %s", inv_id, exc)

        # Surface pending decision packages
        try:
            pending_packages = get_pending_decision_packages(limit=5)
            ctx.decision_packages_ready = len(pending_packages)
            for pkg in pending_packages:
                ctx.all_items.append({
                    "type": "decision_package_ready",
                    "title": f"[DECISION PACKAGE] {pkg.investigation_id}: {pkg.problem_statement[:70]}",
                    "source": "investigation",
                    "priority": "P1",
                    "mission_id": pkg.investigation_id,
                })
        except Exception as exc:
            log.debug("[daily-cycle] Decision package surface failed: %s", exc)

        # Count all open investigations
        try:
            summary = get_investigations_summary()
            ctx.open_investigations_count = summary.get("open_total", 0)
        except Exception as exc:
            ctx.open_investigations_count = len(new_inv_ids)

        ctx.data_freshness["investigation"] = datetime.utcnow().isoformat()

        log.info(
            "[daily-cycle] Investigation step: %d new, %d open, %d high-confidence findings, %d decision packages",
            len(new_inv_ids), ctx.open_investigations_count,
            len(ctx.high_confidence_findings), ctx.decision_packages_ready,
        )

    except Exception as exc:
        log.warning("[daily-cycle] Investigation step failed (non-blocking): %s", exc)


# ── Step 7: Improvement Discovery (EXEC-002 / EXEC-002A) ─────────────────────

def _step_improvement_review(
    ctx: CycleContext,
    *,
    weekly_run: bool = False,
) -> None:
    """D-057 Continuous Improvement Discovery — schedule-aware officer reviews.

    Uses the discovery module (EXEC-002A WP10) which:
      - Runs daily officer reviews every cycle
      - Runs weekly officer reviews when weekly_run=True
      - Gates mission creation against the improvement budget (WP8)
      - Creates scorecards at mission creation (WP9)
      - Logs deferred candidates for next weekly review

    Runs after all operational steps so improvement observations have full context.
    """
    try:
        from lib.improvement.discovery import run_discovery, format_discovery_summary
        from lib.improvement.budget import budget_report

        result = run_discovery(ctx, weekly_run=weekly_run)

        ctx.improvement_opportunities     = [o.to_dict() for o in result.candidates]
        ctx.improvement_missions_created  = len(result.missions_created)
        ctx.improvement_missions_deferred = result.missions_deferred
        ctx.improvement_backlog_drained   = result.backlog_drained
        ctx.improvement_budget = result.budget.to_dict() if result.budget else {}
        ctx.improvement_summary = format_discovery_summary(result)

        # EXEC-003: surface backlog depth for Captain brief
        try:
            from lib.improvement.backlog import get_backlog_count
            ctx.improvement_backlog_count = get_backlog_count()
        except Exception:
            ctx.improvement_backlog_count = result.backlog_items_added

        # Surface High-band items to exception router (cap at 3 to avoid noise)
        for opp in result.high_band[:3]:
            ctx.all_items.append({
                "type": "strategic_decision",
                "title": f"[IMPROVE] {opp.suggested_action[:80]}",
                "source": f"improvement:{opp.source_officer}",
                "priority": "P2",
            })

        ctx.data_freshness["improvement"] = datetime.utcnow().isoformat()

        log.info(
            "[daily-cycle] Improvement step: %d candidates (%d High), "
            "%d missions created, %d deferred. Budget: %s",
            len(result.candidates), len(result.high_band),
            len(result.missions_created), result.missions_deferred,
            result.budget.status_label if result.budget else "unknown",
        )
    except Exception as exc:
        log.warning("[daily-cycle] Improvement step failed (non-blocking): %s", exc)


# ── Assembly ──────────────────────────────────────────────────────────────────

def _format_improvement_discovery_section(ctx: CycleContext) -> str:
    """Format the EXEC-003 improvement intelligence section for the Captain brief.

    Presents discovery (always-on) separately from execution (budget-gated)
    so the Captain can distinguish 'we stopped looking' from 'nothing to act on'.
    """
    lines: list[str] = []

    # Discovery summary
    if ctx.improvement_summary:
        lines.append(f"*Improvement Intelligence (D-058):*\n{ctx.improvement_summary}")
    elif ctx.improvement_opportunities:
        total = len(ctx.improvement_opportunities)
        lines.append(f"*Improvement Intelligence:* {total} candidate(s) discovered")

    # Execution status (separate from discovery)
    budget = ctx.improvement_budget
    if budget:
        active  = budget.get("active_improvement_missions", "?")
        maximum = budget.get("max_improvement_missions", "?")
        cap_st  = budget.get("capacity_status", "?")
        label   = budget.get("status_label", "")
        created = ctx.improvement_missions_created
        drained = ctx.improvement_backlog_drained
        backlog = ctx.improvement_backlog_count

        exec_parts = [f"Active: {active}/{maximum} slots ({cap_st})"]
        if created:
            exec_parts.append(f"{created} created this cycle")
        if drained:
            exec_parts.append(f"{drained} promoted from backlog")
        if backlog:
            exec_parts.append(f"Backlog depth: {backlog}")

        lines.append("*Improvement Execution:* " + " | ".join(exec_parts))

    return "\n".join(lines)


def _format_investigation_section(ctx: CycleContext) -> str:
    """Format the EXEC-004 investigation intelligence section for the Captain brief."""
    if not (ctx.open_investigations_count or ctx.high_confidence_findings
            or ctx.decision_packages_ready or ctx.new_investigations_opened):
        return ""

    lines: list[str] = ["*Investigations (D-059):*"]

    if ctx.open_investigations_count:
        lines.append(f"  Open: {ctx.open_investigations_count}")
    if ctx.new_investigations_opened:
        lines.append(f"  Opened this cycle: {len(ctx.new_investigations_opened)}")
    if ctx.high_confidence_findings:
        lines.append(f"  High-confidence findings: {len(ctx.high_confidence_findings)}")
    if ctx.decision_packages_ready:
        lines.append(f"  Decision packages awaiting XO: {ctx.decision_packages_ready}")
    if ctx.investigations_closed_this_cycle:
        lines.append(f"  Closed this cycle: {ctx.investigations_closed_this_cycle}")

    # Surface top finding
    if ctx.high_confidence_findings:
        top = ctx.high_confidence_findings[0]
        lines.append(
            f"  Top finding [{top.get('investigation_id','')}]: "
            f"{top.get('observation','')[:80]} "
            f"→ `{top.get('lead_action','?')}`"
        )

    return "\n".join(lines)


def assemble_executive_brief(ctx: CycleContext) -> str:
    """Route all items and format Captain brief. Steps 7-9."""
    try:
        from core.coordination.exception_router import classify_all, format_captain_brief

        routed = classify_all(ctx.all_items)
        brief = format_captain_brief(
            routed,
            capacity_status=ctx.capacity_status,
            number_one_summary=ctx.number_one_summary,
        )

        # Investigation intelligence section (EXEC-004 WP9)
        investigation_section = _format_investigation_section(ctx)
        if investigation_section:
            brief = f"{brief}\n\n{investigation_section}"

        # Improvement intelligence section (EXEC-003 WP6)
        discovery_section = _format_improvement_discovery_section(ctx)
        if discovery_section:
            brief = f"{brief}\n\n{discovery_section}"

        return brief
    except Exception as exc:
        log.warning("[daily-cycle] Brief assembly failed, returning fallback: %s", exc)
        return _fallback_brief(ctx)


def _fallback_brief(ctx: CycleContext) -> str:
    """Minimal brief when routing is unavailable."""
    budget = ctx.improvement_budget
    budget_line = ""
    if budget:
        backlog_part = f" | Backlog: {ctx.improvement_backlog_count}" if ctx.improvement_backlog_count else ""
        budget_line = (
            f"\nImprovement: {budget.get('active_improvement_missions', '?')}/"
            f"{budget.get('max_improvement_missions', '?')} slots "
            f"({budget.get('capacity_status', '?')})"
            f"{backlog_part}"
        )
    return (
        f"*CAPTAIN BRIEF — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*\n"
        f"Capacity: {ctx.capacity_status}\n"
        f"Engineering in progress: {ctx.engineering_in_progress} | Blocked: {ctx.engineering_blocked}\n"
        f"ORI Risk: {ctx.resilience_risk}\n"
        f"Comms ready: {ctx.comms_ready_count}"
        f"{budget_line}\n"
        f"_(Full brief assembly unavailable — raw summary only)_"
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def run_daily_cycle(
    missions: list[dict[str, Any]],
    capacity_entry: dict[str, Any] | None = None,
    *,
    weekly_improvement_run: bool = False,
) -> str:
    """Run the full daily operating cycle and return the Captain brief.

    Sequence:
      Human Systems → Strategic Planning → ORI → Engineering →
      Communications → Number One → Investigation Review (D-059) →
      Improvement Discovery (D-057/D-058) → Exception Router → Captain Brief

    Args:
        missions:               Active missions list
        capacity_entry:         Today's capacity log entry
        weekly_improvement_run: If True, weekly officer reviews also run (WP10)

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
    _step_investigation_review(ctx)                                 # EXEC-004 D-059
    _step_improvement_review(ctx, weekly_run=weekly_improvement_run)  # EXEC-002/003 D-057

    return assemble_executive_brief(ctx)


__all__ = [
    "run_daily_cycle",
    "assemble_executive_brief",
    "CycleContext",
]
