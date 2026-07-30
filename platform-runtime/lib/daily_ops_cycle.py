"""Daily Operating Cycle — Executive Staff Orchestrator (EXEC-001 through EXEC-010A).

Sequences officer outputs in the prescribed order and assembles the Captain brief.
Officers consume outputs from previous officers — no isolated reporting.

Sequence:
   1. Human Systems                      — capacity gate (governs everything downstream)
   2. Strategic Planning                 — portfolio decisions
   3. ORI                                — resilience intelligence
   4. Engineering                        — delivery status
   5. Communications                     — pipeline status
   6. Number One                         — consolidation + executive summary
   6.5 Investigation Review              — D-059 questions, evidence, findings (EXEC-004)
   6.6 Learning Review                   — D-061 patterns, lessons, knowledge quality (EXEC-005)
   6.7 Strategic Outcomes                — D-062 initiative health, value progress (EXEC-006)
   6.8 Program Coordination              — D-063 Number One PMO, forecasts, risks (EXEC-007)
   6.9 Portfolio Optimisation            — D-064 value realisation, optimisation (EXEC-008)
   7.0 Enterprise Architecture           — D-065 capabilities, maturity, simulation (EXEC-009)
   7.1 Investment Governance             — D-066 investments, business cases, benefits assurance (EXEC-010)
   7.2 Autonomous Officers               — D-067 officer triggers, actions, handoffs, XO synthesis (EXEC-010A)
   7.  Exception Router                  — classify all items
   8.  Captain Brief                     — Top 3 + exceptions + decisions + capacity

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

    # EXEC-005: Collaborative Intelligence & Organisational Learning
    collaborative_investigations: int = 0
    integrated_findings: list[dict] = field(default_factory=list)
    lessons_generated_this_cycle: int = 0
    lesson_candidates_pending: int = 0
    patterns_detected: list[dict] = field(default_factory=list)
    cross_domain_opportunities: list[dict] = field(default_factory=list)
    knowledge_quality: dict = field(default_factory=dict)
    learning_summary: str | None = None

    # EXEC-006: Strategic Outcomes & Initiative Management
    initiative_health_summary: dict = field(default_factory=dict)   # green/amber/red counts
    initiatives_total: int = 0
    stop_recommendations: int = 0
    accelerate_recommendations: int = 0
    strategic_risks: list[str] = field(default_factory=list)
    alignment_coverage_pct: float = 0.0
    strategic_outcomes_summary: str | None = None
    executive_strategic_review: str | None = None

    # EXEC-007: Program Management & Dependency Coordination
    program_health_summary: dict = field(default_factory=dict)      # green/amber/red counts
    delivery_forecast_summary: dict = field(default_factory=dict)   # forecast band counts
    blocked_work_count: int = 0
    resource_conflicts_count: int = 0
    delivery_risks_count: int = 0
    program_interventions: int = 0
    program_summary: str | None = None
    executive_delivery_review: str | None = None

    # EXEC-008: Strategic Portfolio Optimisation & Value Realisation
    portfolio_value_pct: float = 0.0          # avg benefit realisation across portfolio
    portfolio_terminate_count: int = 0        # terminate decisions this cycle
    portfolio_pause_count: int = 0            # pause decisions this cycle
    portfolio_accelerate_count: int = 0       # accelerate decisions this cycle
    portfolio_at_risk_count: int = 0          # initiatives with benefit or delivery risk
    portfolio_review_summary: str | None = None
    portfolio_optimisation_headline: str = ""

    # EXEC-009: Enterprise Architecture, Capability Planning & Strategic Simulation
    capability_gap_count: int = 0             # critical capability gaps identified
    capability_total: int = 0                 # total registered capabilities
    capability_readiness_pct: float = 0.0     # % at Managed maturity or above
    simulation_low_readiness_count: int = 0   # simulations with low readiness
    tech_debt_critical_count: int = 0         # critical-severity tech debt items
    capability_review_summary: str | None = None

    # EXEC-010: Investment Governance, Roadmapping & Benefits Assurance
    investment_total: int = 0                 # total registered investments
    investment_active: int = 0               # active (approved) investments
    business_cases_approved: int = 0         # APPROVE/APPROVE_WITH_CONDITIONS this cycle
    business_cases_rejected: int = 0         # REJECT decisions this cycle
    benefit_leakage_critical: int = 0        # critical leakage items
    delivery_constraint_critical: int = 0    # critical delivery constraints
    blocked_initiatives_count: int = 0       # dependency-blocked initiatives
    investment_review_summary: str | None = None

    # EXEC-010A: Autonomous Officer Activation
    officer_triggers_fired: int = 0          # triggers fired across all officers this cycle
    officer_actions_created: int = 0         # actions created by officers
    officer_escalations_advanced: int = 0    # escalations advanced through the L0-L5 chain
    officer_handoffs_created: int = 0        # cross-officer handoffs initiated
    officer_assignments_made: int = 0        # missions assigned by Number One / officers
    officer_cycle_summary: str | None = None # XO synthesis section for Captain brief

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

                # EXEC-005 D-060: make significant investigations collaborative
                _make_collaborative_if_significant(ctx, inv, findings)

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


# ── EXEC-005 D-060: collaborative upgrade for significant investigations ──────

def _make_collaborative_if_significant(ctx: CycleContext, inv: Any, findings: Any) -> None:
    """Assemble a multi-officer team, synthesise findings, and run a challenge
    review when an investigation is significant (D-060).

    Significance test: lead recommendation calls for mission/improvement/decision,
    OR any high-confidence finding exists. Narrow domain-contained questions stay
    single-officer.
    """
    try:
        lead_rec = getattr(findings, "lead_recommendation", None)
        significant = bool(getattr(findings, "high_confidence_findings", [])) or (
            lead_rec is not None and lead_rec.action_type in ("mission", "improvement", "decision")
        )
        if not significant:
            return

        from lib.investigation.collaboration import (
            suggest_collaboration_team, assemble_collaboration,
        )
        from lib.investigation.synthesis import synthesize_findings, generate_challenge

        inv_id = inv.investigation_id
        suggestion = suggest_collaboration_team(inv.investigation_type.value, inv.officer)
        team = assemble_collaboration(
            inv_id, lead=inv.officer,
            contributors=suggestion.contributors, reviewer=suggestion.reviewer,
        )

        if not team.is_collaborative:
            return
        ctx.collaborative_investigations += 1

        # WP3 synthesis across participants
        integrated = synthesize_findings(inv_id, inv.question, team.all_officers)
        # WP4 challenge/review (reviewer challenges the synthesis)
        review = generate_challenge(inv_id, integrated, reviewer=team.reviewer or "xo")

        ctx.integrated_findings.append({
            "investigation_id": inv_id,
            "headline": integrated.headline,
            "confidence": integrated.integrated_confidence,
            "consensus_action": integrated.consensus_action,
            "participants": team.all_officers,
            "reviewer": team.reviewer,
            "revised_confidence": review.revised_confidence,
            "has_contradiction": integrated.has_contradiction,
        })

        # Significant integrated findings surface to XO via exception router
        ctx.all_items.append({
            "type": "investigation_finding",
            "title": f"[COLLAB] {inv_id}: {integrated.headline[:80]}",
            "source": f"investigation:{inv.officer}",
            "priority": "P1" if integrated.integrated_confidence >= 0.75 else "P2",
            "mission_id": inv_id,
        })

        log.info(
            "[daily-cycle] Investigation %s upgraded to collaborative: %d officers, action=%s, confidence=%.2f",
            inv_id, team.participant_count, integrated.consensus_action,
            integrated.integrated_confidence,
        )

    except Exception as exc:
        log.debug("[daily-cycle] Collaborative upgrade failed for %s: %s",
                  getattr(inv, "investigation_id", "?"), exc)


# ── Step 6.6: Organisational Learning (EXEC-005) ─────────────────────────────

def _step_learning_review(ctx: CycleContext) -> None:
    """EXEC-005 D-061 — pattern detection, cross-domain correlation, lesson
    candidates, knowledge quality, and the Executive Learning Brief.

    Runs after Investigation (so collaborative findings exist) and after
    Improvement Discovery (so backlog signals are current). Fully non-blocking.
    """
    try:
        from lib.learning.patterns import detect_patterns, pattern_to_investigation
        from lib.learning.cross_domain import (
            detect_cross_domain_opportunities, route_to_improvement_backlog,
        )
        from lib.learning.lessons import (
            lesson_from_investigation, get_lesson_candidate_count,
        )
        from lib.learning.learning_brief import assemble_learning_brief, format_learning_brief

        # WP8: pattern recognition — MEDIUM/HIGH patterns open investigations
        patterns = detect_patterns(lookback_days=30)
        ctx.patterns_detected = [
            {"theme": p.theme, "label": p.label, "occurrences": p.occurrences, "severity": p.severity}
            for p in patterns
        ]
        for p in patterns:
            if p.severity in ("MEDIUM", "HIGH"):
                pattern_to_investigation(p)  # dedup-safe inside

        # WP9: cross-domain opportunities — route into improvement backlog
        cross_opps = detect_cross_domain_opportunities(ctx)
        ctx.cross_domain_opportunities = [
            {"title": o.title, "domains": o.domains, "category": o.category,
             "confidence": o.confidence}
            for o in cross_opps
        ]
        for o in cross_opps:
            if o.confidence >= 0.6:
                route_to_improvement_backlog(o)

        # WP6: lesson candidates from this cycle's closed/concluded investigations
        lessons_created = 0
        for ifinding in ctx.integrated_findings:
            try:
                inv_id = ifinding.get("investigation_id", "")
                if not inv_id:
                    continue
                from lib.investigation.registry import get_investigation
                inv = get_investigation(inv_id)
                if inv and lesson_from_investigation(inv):
                    lessons_created += 1
            except Exception:
                pass
        ctx.lessons_generated_this_cycle = lessons_created
        ctx.lesson_candidates_pending = get_lesson_candidate_count(pending_only=True)

        # WP7 + WP10: assemble the Executive Learning Brief (computes knowledge quality)
        brief = assemble_learning_brief(ctx)
        if brief.knowledge_quality:
            ctx.knowledge_quality = brief.knowledge_quality.to_dict()
        ctx.learning_summary = format_learning_brief(brief)

        ctx.data_freshness["learning"] = datetime.utcnow().isoformat()

        log.info(
            "[daily-cycle] Learning step: %d patterns, %d cross-domain, %d lessons, KQ=%s",
            len(patterns), len(cross_opps), lessons_created,
            ctx.knowledge_quality.get("grade", "n/a") if ctx.knowledge_quality else "n/a",
        )

    except Exception as exc:
        log.warning("[daily-cycle] Learning step failed (non-blocking): %s", exc)


# ── Step 6.7: Strategic Outcomes & Initiative Management (EXEC-006) ───────────

def _step_strategic_outcomes(ctx: CycleContext, *, monthly_review: bool = False) -> None:
    """EXEC-006 D-062 — measure strategic progress through outcomes, not activity.

    Runs last (after investigation, learning, and improvement) so it can read
    every other officer's signals as health inputs. Refreshes initiative health,
    runs the alignment scan, generates stop/continue/accelerate recommendations,
    and assembles the Strategic Outcomes dashboard. Monthly: the full Executive
    Strategic Review. Fully non-blocking.
    """
    try:
        from lib.strategy.initiatives import list_initiatives
        from lib.strategy.outcomes import refresh_initiative_health
        from lib.strategy.portfolio_intelligence import recommend_all, Recommendation
        from lib.strategy.strategic_review import (
            build_strategic_dashboard, format_strategic_dashboard,
            run_executive_strategic_review, format_executive_review,
        )

        # Shared health inputs from the rest of the cycle
        inputs = {
            "capacity_status": ctx.capacity_status,
            "resilience_risk": ctx.resilience_risk,
            "blocked_missions": ctx.engineering_blocked,
            "total_missions": ctx.engineering_in_progress + ctx.engineering_blocked,
        }

        initiatives = list_initiatives(include_closed=False)
        if not initiatives:
            ctx.strategic_outcomes_summary = (
                "*Strategic Outcomes:* _No initiatives defined — work is not yet "
                "traced to measurable outcomes (D-062)._"
            )
            ctx.data_freshness["strategic_outcomes"] = datetime.utcnow().isoformat()
            return

        # Refresh health for each initiative (persisted)
        for init in initiatives:
            try:
                refresh_initiative_health(init.initiative_id, inputs)
            except Exception:
                pass

        # Dashboard (WP7)
        dash = build_strategic_dashboard(inputs)
        ctx.initiative_health_summary = dash.health_summary
        ctx.initiatives_total = dash.total_initiatives
        ctx.strategic_risks = dash.strategic_risks
        if dash.alignment:
            ctx.alignment_coverage_pct = dash.alignment.coverage_pct
        ctx.strategic_outcomes_summary = format_strategic_dashboard(dash)

        # Stop / Continue / Accelerate (WP5)
        recs = recommend_all(inputs)
        ctx.stop_recommendations = len([r for r in recs if r.recommendation in (
            Recommendation.STOP, Recommendation.PAUSE, Recommendation.MERGE)])
        ctx.accelerate_recommendations = len([r for r in recs if r.recommendation == Recommendation.ACCELERATE])

        # Surface disinvestment recommendations to XO; off-track initiatives + strategic risk to Captain
        for r in recs:
            if r.recommendation in (Recommendation.STOP, Recommendation.MERGE):
                ctx.all_items.append({
                    "type": "initiative_stop_recommendation",
                    "title": f"[{r.recommendation.value.upper()}] {r.title[:70]} — {r.rationale[:60]}",
                    "source": "strategic_planning",
                    "priority": "P2",
                    "mission_id": r.initiative_id,
                })
        for risk in dash.strategic_risks[:3]:
            ctx.all_items.append({
                "type": "strategic_decision",
                "title": f"[STRATEGIC RISK] {risk[:80]}",
                "source": "strategic_planning",
                "priority": "P1",
            })

        # Monthly Executive Strategic Review (WP9)
        if monthly_review:
            try:
                review = run_executive_strategic_review(inputs)
                ctx.executive_strategic_review = format_executive_review(review)
            except Exception as exc:
                log.debug("[daily-cycle] Executive strategic review failed: %s", exc)

        ctx.data_freshness["strategic_outcomes"] = datetime.utcnow().isoformat()
        log.info(
            "[daily-cycle] Strategic outcomes: %d initiatives (%s), %d stop, %d accelerate, alignment %.0f%%",
            ctx.initiatives_total, ctx.initiative_health_summary,
            ctx.stop_recommendations, ctx.accelerate_recommendations,
            ctx.alignment_coverage_pct * 100,
        )

    except Exception as exc:
        log.warning("[daily-cycle] Strategic outcomes step failed (non-blocking): %s", exc)


# ── Step 6.8: Program Coordination (EXEC-007) ────────────────────────────────

def _step_program_coordination(ctx: CycleContext, *, delivery_review: bool = False) -> None:
    """EXEC-007 D-063 — Number One coordinates execution across initiatives.

    Runs after strategic outcomes (so initiative health is fresh). Builds the
    PMO program portfolio: program health, forecasts, delivery risks, resource
    conflicts, critical-path blockers, and intervention recommendations.
    Surfaces blocked work / conflicts / interventions to the exception router
    and outcome-threatening criticals to the Captain. Fully non-blocking.
    """
    try:
        from lib.strategy.initiatives import list_initiatives
        from lib.program.pmo import (
            coordinate_programs, format_program_portfolio,
            run_executive_delivery_review, format_delivery_review,
        )
        from lib.program.forecasting import DeliveryForecast

        if not list_initiatives(include_closed=False):
            ctx.program_summary = (
                "*Program Coordination:* _No initiatives — nothing to coordinate (D-063)._"
            )
            ctx.data_freshness["program"] = datetime.utcnow().isoformat()
            return

        inputs = {
            "capacity_status": ctx.capacity_status,
            "resilience_risk": ctx.resilience_risk,
            "escalations": len(ctx.number_one_items),
        }

        portfolio = coordinate_programs(inputs)

        # Health summary
        hs = {"green": 0, "amber": 0, "red": 0, "unknown": 0}
        for ph in portfolio.program_health:
            hs[ph.health] = hs.get(ph.health, 0) + 1
        ctx.program_health_summary = hs

        # Forecast summary
        fs: dict[str, int] = {}
        for f in portfolio.forecasts:
            fs[f.forecast.value] = fs.get(f.forecast.value, 0) + 1
        ctx.delivery_forecast_summary = fs

        ctx.blocked_work_count = len(portfolio.blocked_work)
        ctx.resource_conflicts_count = len(portfolio.resource_conflicts)
        ctx.delivery_risks_count = len(portfolio.delivery_risks)
        ctx.program_interventions = len(portfolio.interventions)
        ctx.program_summary = format_program_portfolio(portfolio)

        # Surface blocked work → Number One
        if portfolio.blocked_work:
            ctx.all_items.append({
                "type": "delivery_blocker",
                "title": f"[DELIVERY] {len(portfolio.blocked_work)} blocked mission(s) across initiatives",
                "source": "number_one_pmo",
                "priority": "P1",
            })
        # Surface resource conflicts → Number One
        for conf in portfolio.resource_conflicts:
            if conf.severity in ("high", "medium"):
                ctx.all_items.append({
                    "type": "resource_conflict",
                    "title": f"[CONFLICT] {conf.description[:80]}",
                    "source": "number_one_pmo",
                    "priority": "P1" if conf.severity == "high" else "P2",
                })
        # Surface interventions
        for r in portfolio.interventions:
            if r.route_to == "captain":
                ctx.all_items.append({
                    "type": "strategic_decision",
                    "title": f"[DELIVERY CRITICAL] {r.action.upper()} {r.initiative_id} — {r.reason[:60]}",
                    "source": "number_one_pmo",
                    "priority": "P1",
                })
            elif r.route_to == "xo":
                ctx.all_items.append({
                    "type": "delivery_risk_escalation",
                    "title": f"[DELIVERY] {r.action.upper()} {r.initiative_id} — {r.reason[:60]}",
                    "source": "number_one_pmo",
                    "priority": "P2",
                })
            else:
                ctx.all_items.append({
                    "type": "delivery_intervention",
                    "title": f"[PMO] {r.action.upper()} {r.initiative_id} — {r.reason[:60]}",
                    "source": "number_one_pmo",
                    "priority": "P2",
                })

        # Executive Delivery Review (WP8)
        if delivery_review:
            try:
                review = run_executive_delivery_review(inputs)
                ctx.executive_delivery_review = format_delivery_review(review)
            except Exception as exc:
                log.debug("[daily-cycle] Executive delivery review failed: %s", exc)

        ctx.data_freshness["program"] = datetime.utcnow().isoformat()
        log.info(
            "[daily-cycle] Program coordination: %s health, %d blocked, %d conflicts, %d risks, %d interventions",
            hs, ctx.blocked_work_count, ctx.resource_conflicts_count,
            ctx.delivery_risks_count, ctx.program_interventions,
        )

    except Exception as exc:
        log.warning("[daily-cycle] Program coordination step failed (non-blocking): %s", exc)


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


# ── Step 6.9: Portfolio Optimisation (EXEC-008) ───────────────────────────────

def _step_portfolio_optimisation(
    ctx: CycleContext,
    *,
    portfolio_review: bool = False,
) -> None:
    """EXEC-008 D-064 — Strategic Portfolio Optimisation & Value Realisation.

    Runs after Program Coordination (so delivery forecasts are current) and
    after Strategic Outcomes (so initiative health is fresh). Answers:
      Can we deliver this? Should we deliver this? Did it create expected value?

    Surfaces terminate/pause decisions to XO; portfolio-level value degradation
    to Captain; scenario warnings and tradeoff alerts to Number One.
    Fully non-blocking.
    """
    try:
        from lib.strategy.initiatives import list_initiatives

        if not list_initiatives(include_closed=False):
            ctx.portfolio_review_summary = (
                "*Portfolio Optimisation:* _No initiatives — nothing to optimise (D-064)._"
            )
            ctx.data_freshness["portfolio"] = datetime.utcnow().isoformat()
            return

        inputs = {
            "capacity_status": ctx.capacity_status,
            "resilience_risk": ctx.resilience_risk,
            "cross_domain_opportunities": ctx.cross_domain_opportunities,
        }

        # WP4 — Portfolio optimisation decisions
        from lib.strategy.portfolio_optimisation import optimise_portfolio, format_optimisation, OptimisationDecision
        opt = optimise_portfolio(inputs)
        ctx.portfolio_terminate_count = opt.terminate_count
        ctx.portfolio_pause_count     = opt.pause_count
        ctx.portfolio_accelerate_count = opt.accelerate_count
        ctx.portfolio_optimisation_headline = opt.headline

        # Surface terminate/pause → XO; portfolio value escalation → Captain
        for d in opt.decisions:
            if d.decision == OptimisationDecision.TERMINATE:
                ctx.all_items.append({
                    "type": "portfolio_recommendation",
                    "title": f"[TERMINATE] {d.title[:60]} — {d.rationale[:50]}",
                    "source": "portfolio_optimisation",
                    "priority": "P1",
                    "mission_id": d.initiative_id,
                })
            elif d.decision == OptimisationDecision.PAUSE:
                ctx.all_items.append({
                    "type": "portfolio_recommendation",
                    "title": f"[PAUSE] {d.title[:60]} — {d.rationale[:50]}",
                    "source": "portfolio_optimisation",
                    "priority": "P2",
                    "mission_id": d.initiative_id,
                })

        # WP2 — Value realisation: surface benefit risks
        try:
            from lib.strategy.value_realisation import assess_all_value
            value_reports = assess_all_value()
            at_risk = [r for r in value_reports if r.at_risk_count > r.total_count // 2 and r.total_count > 0]
            ctx.portfolio_at_risk_count = len(at_risk)

            # Avg portfolio value realisation
            if value_reports:
                total_pct = sum(r.overall_realisation_pct for r in value_reports)
                ctx.portfolio_value_pct = round(total_pct / len(value_reports), 3)

            # Escalate serious benefit risk to XO; critical portfolio value decline to Captain
            for r in at_risk:
                ctx.all_items.append({
                    "type": "benefit_risk",
                    "title": f"[BENEFIT RISK] {r.initiative_title[:60]}: {r.headline[:60]}",
                    "source": "portfolio_optimisation",
                    "priority": "P2",
                    "mission_id": r.initiative_id,
                })
            if ctx.portfolio_value_pct < 0.2 and value_reports:
                ctx.all_items.append({
                    "type": "portfolio_escalation",
                    "title": (
                        f"[PORTFOLIO] Average benefit realisation {ctx.portfolio_value_pct:.0%} — "
                        f"portfolio value significantly below expectations"
                    ),
                    "source": "portfolio_optimisation",
                    "priority": "P1",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Value realisation assessment failed: %s", exc)

        # WP7 — Portfolio review (on delivery_review / portfolio_review flag)
        if portfolio_review:
            try:
                from lib.strategy.portfolio_review import (
                    generate_portfolio_review, format_portfolio_review,
                )
                review = generate_portfolio_review({
                    **inputs,
                    "cross_domain_opportunities": ctx.cross_domain_opportunities,
                })
                ctx.portfolio_review_summary = format_portfolio_review(review)
            except Exception as exc:
                log.debug("[daily-cycle] Portfolio review failed: %s", exc)

        # Build the optimisation summary for the Captain brief
        if not ctx.portfolio_review_summary:
            ctx.portfolio_review_summary = format_optimisation(opt)

        ctx.data_freshness["portfolio"] = datetime.utcnow().isoformat()
        log.info(
            "[daily-cycle] Portfolio optimisation: terminate=%d, pause=%d, accelerate=%d, value=%.0f%%, at_risk=%d",
            opt.terminate_count, opt.pause_count, opt.accelerate_count,
            ctx.portfolio_value_pct * 100, ctx.portfolio_at_risk_count,
        )

    except Exception as exc:
        log.warning("[daily-cycle] Portfolio optimisation step failed (non-blocking): %s", exc)


# ── Step 7.0: Enterprise Architecture & Capability Planning (EXEC-009) ───────

def _step_enterprise_architecture(
    ctx: CycleContext,
    *,
    capability_review: bool = False,
) -> None:
    """EXEC-009 D-065 — Enterprise Architecture, Capability Planning & Strategic Simulation.

    Runs after Portfolio Optimisation (so portfolio signals are current). Assesses
    capability maturity, identifies gaps, runs strategic simulations, and surfaces
    architecture risks. On capability_review=True generates the full 6-question
    executive capability review.

    Surfaces capability gaps and simulation warnings to Captain; future state
    recommendations and tech debt escalations to XO. Fully non-blocking.
    """
    try:
        from lib.strategy.capabilities import list_capabilities

        caps = list_capabilities()
        ctx.capability_total = len(caps)
        if not caps:
            ctx.capability_review_summary = (
                "*Enterprise Architecture:* _No capabilities registered — register capabilities to enable planning (D-065)._"
            )
            ctx.data_freshness["enterprise_architecture"] = datetime.utcnow().isoformat()
            return

        inputs = {
            "capacity_status": ctx.capacity_status,
            "resilience_risk": ctx.resilience_risk,
        }

        # Capability gap analysis (WP8) — surface critical gaps to Captain
        try:
            from lib.strategy.capability_gaps import analyse_capability_gaps, GapType
            gaps = analyse_capability_gaps()
            critical_gaps = [g for g in gaps if g.is_critical]
            ctx.capability_gap_count = len(critical_gaps)

            for g in critical_gaps[:3]:
                ctx.all_items.append({
                    "type": g.gap_type.value == "threatening" and "capability_risk" or "capability_gap",
                    "title": f"[CAP GAP] {g.description[:80]}",
                    "source": "enterprise_architecture",
                    "priority": "P1",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Capability gap analysis failed: %s", exc)

        # Maturity assessment (WP3) — track readiness
        try:
            from lib.strategy.capability_maturity import assess_all_maturity
            assessments = assess_all_maturity()
            if assessments:
                managed = sum(1 for a in assessments if a.assessed_maturity.value >= 3)
                ctx.capability_readiness_pct = round(managed / len(assessments), 3)
        except Exception as exc:
            log.debug("[daily-cycle] Maturity assessment failed: %s", exc)

        # Architecture view (WP4) — surface high-risk entities to Captain
        try:
            from lib.strategy.enterprise_architecture import get_architecture_view
            av = get_architecture_view()
            for e in av.high_risk[:2]:
                ctx.all_items.append({
                    "type": "architecture_risk",
                    "title": f"[ARCH RISK] {e.name} ({e.state.value}) — high risk",
                    "source": "enterprise_architecture",
                    "priority": "P1",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Architecture view failed: %s", exc)

        # Technical debt profile (WP5) — surface critical debt to XO
        try:
            from lib.strategy.technical_debt import compute_debt_profile, DebtTrend
            dp = compute_debt_profile()
            ctx.tech_debt_critical_count = dp.critical_count
            increasing_critical = [d for d in dp.top_debts if d.trend == DebtTrend.INCREASING and d.score >= 8]
            if increasing_critical:
                ctx.all_items.append({
                    "type": "technical_debt_escalation",
                    "title": f"[TECH DEBT] {len(increasing_critical)} critical item(s) with increasing trend",
                    "source": "enterprise_architecture",
                    "priority": "P2",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Technical debt profile failed: %s", exc)

        # Future state planning (WP6) — surface critical H1 needs to XO
        try:
            from lib.strategy.future_state import build_future_state_plan, FutureCapPriority
            fp = build_future_state_plan()
            for p in fp.critical_near_term[:2]:
                ctx.all_items.append({
                    "type": "future_state_recommendation",
                    "title": f"[FUTURE CAP H1] {p.name[:60]} — critical 12-month requirement",
                    "source": "enterprise_architecture",
                    "priority": "P2",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Future state planning failed: %s", exc)

        # Strategic simulation (WP7) — surface cross-scenario low readiness to Captain
        try:
            from lib.strategy.strategic_simulation import run_all_simulations
            sim_report = run_all_simulations(inputs)
            low_ready = [r for r in sim_report.results if r.overall_readiness == "low"]
            ctx.simulation_low_readiness_count = len(low_ready)
            if len(low_ready) >= 2:
                ctx.all_items.append({
                    "type": "simulation_warning",
                    "title": (
                        f"[SIMULATION] Low readiness in {len(low_ready)} strategic scenarios — "
                        f"capability base may not support strategic continuity"
                    ),
                    "source": "enterprise_architecture",
                    "priority": "P1",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Strategic simulation failed: %s", exc)

        # Full 6-question capability review (on flag)
        if capability_review:
            try:
                from lib.strategy.capability_review import (
                    generate_capability_review, format_capability_review,
                )
                review = generate_capability_review(inputs)
                ctx.capability_review_summary = format_capability_review(review)
            except Exception as exc:
                log.debug("[daily-cycle] Capability review failed: %s", exc)

        ctx.data_freshness["enterprise_architecture"] = datetime.utcnow().isoformat()
        log.info(
            "[daily-cycle] Enterprise architecture: %d caps, readiness=%.0f%%, critical gaps=%d, "
            "sim low=%d, tech debt critical=%d",
            ctx.capability_total, ctx.capability_readiness_pct * 100,
            ctx.capability_gap_count, ctx.simulation_low_readiness_count,
            ctx.tech_debt_critical_count,
        )

    except Exception as exc:
        log.warning("[daily-cycle] Enterprise architecture step failed (non-blocking): %s", exc)


# ── Step 7.1: Investment Governance & Benefits Assurance (EXEC-010) ───────────

def _step_investment_governance(
    ctx: CycleContext,
    *,
    investment_review: bool = False,
) -> None:
    """EXEC-010 D-066 — Investment Governance, Roadmapping & Benefits Assurance.

    Runs after Enterprise Architecture (so capability/architecture data is fresh).
    Assesses business cases, detects benefit leakage, analyses delivery constraints,
    coordinates dependencies, and provides the 6-question investment review.

    Surfaces critical leakage and major investment decisions to Captain;
    business case outcomes and capacity overload to XO; dependency and capacity
    coordination to Number One. Fully non-blocking.
    """
    try:
        # Investment registry counts
        try:
            from lib.strategy.investment_governance import list_investments
            investments = list_investments()
            ctx.investment_total = len(investments)
            ctx.investment_active = sum(1 for inv in investments if inv.is_active)
        except Exception as exc:
            log.debug("[daily-cycle] Investment registry unavailable: %s", exc)

        inputs = {
            "capacity_status": ctx.capacity_status,
            "resilience_risk": ctx.resilience_risk,
        }

        # Business case assessment (WP2) — surface approved/rejected cases to XO
        try:
            from lib.strategy.business_cases import (
                assess_all_business_cases, BusinessCaseOutcome,
            )
            bcs = assess_all_business_cases()
            approved = [bc for bc in bcs if bc.is_approved]
            rejected = [bc for bc in bcs if bc.outcome == BusinessCaseOutcome.REJECT]
            ctx.business_cases_approved = len(approved)
            ctx.business_cases_rejected = len(rejected)

            for bc in approved[:2]:
                ctx.all_items.append({
                    "type": "business_case_approval",
                    "title": f"[BUSINESS CASE {bc.outcome.value.upper()}] {bc.title[:60]}",
                    "source": "investment_governance",
                    "priority": "P2",
                    "mission_id": bc.initiative_id,
                })
        except Exception as exc:
            log.debug("[daily-cycle] Business case assessment failed: %s", exc)

        # Dependency analysis (WP3) — surface blocked initiatives to Number One
        try:
            from lib.strategy.dependency_management import analyse_dependencies
            dep_report = analyse_dependencies()
            ctx.blocked_initiatives_count = len(dep_report.blocked_initiative_ids)

            if dep_report.has_circular:
                ctx.all_items.append({
                    "type": "dependency_review",
                    "title": f"[CIRCULAR DEP] {len(dep_report.circular_chains)} circular dependency chain(s) — deadlock risk",
                    "source": "investment_governance",
                    "priority": "P1",
                })
            elif dep_report.blocked_initiative_ids:
                ctx.all_items.append({
                    "type": "dependency_review",
                    "title": f"[DEPENDENCIES] {len(dep_report.blocked_initiative_ids)} blocked initiative(s) awaiting resolution",
                    "source": "investment_governance",
                    "priority": "P2",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Dependency analysis failed: %s", exc)

        # Capacity planning (WP4) — surface overload to XO
        try:
            from lib.strategy.capacity_planning import assess_portfolio_capacity, CapacityState
            cap_plan = assess_portfolio_capacity(ctx.capacity_status, inputs)
            if cap_plan.state == CapacityState.OVERLOADED:
                ctx.all_items.append({
                    "type": "capacity_overload",
                    "title": (
                        f"[CAPACITY] Portfolio OVERLOADED at {cap_plan.utilisation_pct:.0%} — "
                        f"{len(cap_plan.overloaded_owners)} overloaded owner(s)"
                    ),
                    "source": "investment_governance",
                    "priority": "P1",
                })
            elif cap_plan.state == CapacityState.CONSTRAINED:
                ctx.all_items.append({
                    "type": "capacity_review",
                    "title": f"[CAPACITY] Portfolio constrained at {cap_plan.utilisation_pct:.0%} utilisation",
                    "source": "investment_governance",
                    "priority": "P2",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Capacity planning failed: %s", exc)

        # Benefit leakage (WP7) — critical → Captain, others → XO
        try:
            from lib.strategy.benefit_leakage import detect_benefit_leakage, LeakageRisk
            leakages = detect_benefit_leakage()
            critical_leakages = [l for l in leakages if l.is_critical]
            ctx.benefit_leakage_critical = len(critical_leakages)

            for l in critical_leakages[:2]:
                ctx.all_items.append({
                    "type": "benefit_leakage_critical",
                    "title": f"[CRITICAL LEAKAGE] {l.benefit_title[:50]}: {l.description[:50]}",
                    "source": "investment_governance",
                    "priority": "P1",
                    "mission_id": l.initiative_id,
                })
            non_critical = [l for l in leakages if not l.is_critical][:2]
            for l in non_critical:
                ctx.all_items.append({
                    "type": "benefit_leakage",
                    "title": f"[LEAKAGE] {l.benefit_title[:50]}: {l.leakage_type.value}",
                    "source": "investment_governance",
                    "priority": "P2",
                    "mission_id": l.initiative_id,
                })
        except Exception as exc:
            log.debug("[daily-cycle] Benefit leakage detection failed: %s", exc)

        # Delivery constraints (WP8) — critical → Captain routing
        try:
            from lib.strategy.delivery_constraints import analyse_delivery_constraints
            cr = analyse_delivery_constraints(inputs)
            ctx.delivery_constraint_critical = cr.critical_count
            if cr.critical_count >= 2:
                ctx.all_items.append({
                    "type": "investment_decision",
                    "title": (
                        f"[CONSTRAINTS] {cr.critical_count} critical delivery constraint(s) — "
                        f"portfolio risk: {cr.portfolio_risk}"
                    ),
                    "source": "investment_governance",
                    "priority": "P1",
                })
        except Exception as exc:
            log.debug("[daily-cycle] Delivery constraint analysis failed: %s", exc)

        # Full investment review (on flag)
        if investment_review:
            try:
                from lib.strategy.investment_review import (
                    generate_investment_review, format_investment_review,
                )
                ir = generate_investment_review(inputs)
                ctx.investment_review_summary = format_investment_review(ir)
                # Escalate to Captain when review is requested
                ctx.all_items.append({
                    "type": "investment_review",
                    "title": f"[INVESTMENT REVIEW] {ir.review_headline}",
                    "source": "investment_governance",
                    "priority": "P2",
                })
            except Exception as exc:
                log.debug("[daily-cycle] Investment review failed: %s", exc)

        ctx.data_freshness["investment_governance"] = datetime.utcnow().isoformat()
        log.info(
            "[daily-cycle] Investment governance: investments=%d/%d active, "
            "bc approved=%d rejected=%d, blocked=%d, leakage critical=%d, constraints critical=%d",
            ctx.investment_active, ctx.investment_total,
            ctx.business_cases_approved, ctx.business_cases_rejected,
            ctx.blocked_initiatives_count, ctx.benefit_leakage_critical,
            ctx.delivery_constraint_critical,
        )

    except Exception as exc:
        log.warning("[daily-cycle] Investment governance step failed (non-blocking): %s", exc)


# ── Step 7.2: Autonomous Officer Cycle (EXEC-010A) ───────────────────────────

def _step_autonomous_officers(
    ctx: CycleContext,
    missions: list[dict[str, Any]],
) -> None:
    """EXEC-010A D-067 — Autonomous Officer Activation.

    Runs after Investment Governance so all strategic, portfolio, investment, and
    architecture signals are populated. Officers evaluate their triggers, create
    actions, advance escalations, process handoffs, and produce an XO synthesis
    for injection into the Captain brief.

    Fully non-blocking — each sub-step degrades gracefully.
    """
    try:
        from lib.officers.daily_operations_cycle import run_officer_cycle, format_officer_cycle_summary

        result = run_officer_cycle(ctx, missions)
        ctx.officer_triggers_fired = result.triggers_fired
        ctx.officer_actions_created = result.actions_created
        ctx.officer_escalations_advanced = result.escalations_advanced
        ctx.officer_handoffs_created = result.handoffs_created
        ctx.officer_assignments_made = result.assignments_made

        if result.cycle_summary:
            ctx.officer_cycle_summary = result.cycle_summary
        elif result.triggers_fired or result.actions_created:
            ctx.officer_cycle_summary = format_officer_cycle_summary(result)

        ctx.data_freshness["autonomous_officers"] = datetime.utcnow().isoformat()
        log.info(
            "[daily-cycle] Autonomous officers: triggers=%d, actions=%d, escalations=%d, "
            "handoffs=%d, assignments=%d",
            result.triggers_fired, result.actions_created,
            result.escalations_advanced, result.handoffs_created, result.assignments_made,
        )
    except Exception as exc:
        log.warning("[daily-cycle] Autonomous officer cycle failed (non-blocking): %s", exc)


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
    if ctx.collaborative_investigations:
        lines.append(f"  Multi-officer (collaborative): {ctx.collaborative_investigations}")
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

        # Executive Learning Brief (EXEC-005 WP10) — separate from operational status
        if ctx.learning_summary:
            brief = f"{brief}\n\n{ctx.learning_summary}"

        # Strategic Outcomes (EXEC-006 WP7) — progress, not activity
        if ctx.strategic_outcomes_summary:
            brief = f"{brief}\n\n{ctx.strategic_outcomes_summary}"

        # Monthly Executive Strategic Review (EXEC-006 WP9)
        if ctx.executive_strategic_review:
            brief = f"{brief}\n\n{ctx.executive_strategic_review}"

        # Program Coordination (EXEC-007 WP7) — Number One PMO delivery view
        if ctx.program_summary:
            brief = f"{brief}\n\n{ctx.program_summary}"

        # Executive Delivery Review (EXEC-007 WP8)
        if ctx.executive_delivery_review:
            brief = f"{brief}\n\n{ctx.executive_delivery_review}"

        # Portfolio Optimisation (EXEC-008 D-064) — value realisation and investment decisions
        if ctx.portfolio_review_summary:
            brief = f"{brief}\n\n{ctx.portfolio_review_summary}"

        # Enterprise Architecture & Capability Planning (EXEC-009 D-065)
        if ctx.capability_review_summary:
            brief = f"{brief}\n\n{ctx.capability_review_summary}"

        # Investment Governance & Benefits Assurance (EXEC-010 D-066)
        if ctx.investment_review_summary:
            brief = f"{brief}\n\n{ctx.investment_review_summary}"

        # Autonomous Officer Layer (EXEC-010A D-067) — XO synthesis
        if ctx.officer_cycle_summary:
            brief = f"{brief}\n\n{ctx.officer_cycle_summary}"

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
    monthly_strategic_review: bool = False,
    delivery_review: bool = False,
    portfolio_review: bool = False,
    capability_review: bool = False,
    investment_review: bool = False,
) -> str:
    """Run the full daily operating cycle and return the Captain brief.

    Sequence:
      Human Systems → Strategic Planning → ORI → Engineering →
      Communications → Number One → Investigation Review (D-059/D-060) →
      Improvement Discovery (D-057/D-058) → Learning (D-061) →
      Strategic Outcomes (D-062) → Program Coordination (D-063) →
      Portfolio Optimisation (D-064) → Enterprise Architecture (D-065) →
      Investment Governance (D-066) → Autonomous Officers (D-067) →
      Exception Router → Captain Brief

    Args:
        missions:                 Active missions list
        capacity_entry:           Today's capacity log entry
        weekly_improvement_run:   If True, weekly officer reviews also run (WP10)
        monthly_strategic_review: If True, the full Executive Strategic Review runs (EXEC-006 WP9)
        delivery_review:          If True, the full Executive Delivery Review runs (EXEC-007 WP8)
        portfolio_review:         If True, the full Portfolio Review runs (EXEC-008 WP7)
        capability_review:        If True, the full Capability Review runs (EXEC-009 WP9)
        investment_review:        If True, the full Investment Review runs (EXEC-010 WP9)

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
    _step_investigation_review(ctx)                                          # EXEC-004 D-059 / EXEC-005 D-060
    _step_improvement_review(ctx, weekly_run=weekly_improvement_run)         # EXEC-002/003 D-057
    _step_learning_review(ctx)                                               # EXEC-005 D-061
    _step_strategic_outcomes(ctx, monthly_review=monthly_strategic_review)   # EXEC-006 D-062
    _step_program_coordination(ctx, delivery_review=delivery_review)         # EXEC-007 D-063
    _step_portfolio_optimisation(ctx, portfolio_review=portfolio_review)     # EXEC-008 D-064
    _step_enterprise_architecture(ctx, capability_review=capability_review)  # EXEC-009 D-065
    _step_investment_governance(ctx, investment_review=investment_review)     # EXEC-010 D-066
    _step_autonomous_officers(ctx, missions)                                  # EXEC-010A D-067

    return assemble_executive_brief(ctx)


__all__ = [
    "run_daily_cycle",
    "assemble_executive_brief",
    "CycleContext",
]
