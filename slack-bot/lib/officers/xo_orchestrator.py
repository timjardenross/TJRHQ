"""XO Central Coordination Intelligence (EXEC-010A WP10).

The XO acts as the central coordinating intelligence layer. After all officers
have run their autonomous cycle steps, the XO synthesises their outputs,
prioritises what matters most, and produces a single cohesive signal for the
Captain brief.

The XO does not duplicate existing exception routing (core/coordination/
exception_router.py handles routing). The XO synthesises officer layer signals
into a coherent narrative the Captain can act on.

XO synthesis outputs:
  - Consolidated risk level for the officer layer
  - Priority items from each officer's domain
  - Recommended actions for the Captain (not raw data)
  - Status of each officer (active / quiet / flagged)

Storage: decisions table
  owner = `xo_synthesis:{date_str}`
  statement = `[XO SYNTHESIS] {date}: {risk_level}`
  rationale = `RISK: | SIGNALS: | ACTIONS: | OFFICERS_ACTIVE:`

Public API:
    OfficerStatus
    XOSynthesis
    synthesise_officer_outputs(signals, ctx)  -> XOSynthesis
    format_xo_synthesis(synthesis)            -> str
    get_officer_statuses(ctx)                 -> list[OfficerStatus]
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class OfficerStatus:
    officer: str
    is_active: bool = False
    active_escalations: int = 0
    pending_handoffs: int = 0
    last_signal_type: str = ""
    domain_health: str = "green"   # green / amber / red


@dataclass
class XOSynthesis:
    risk_level: str = "green"      # green / amber / red
    priorities: list[str] = field(default_factory=list)      # top officer priorities
    blockers: list[str] = field(default_factory=list)        # items blocking the organisation
    recommendations: list[str] = field(default_factory=list) # XO recommendations for Captain
    officer_statuses: list[OfficerStatus] = field(default_factory=list)
    signals_processed: int = 0
    synthesised_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_captain_items(self) -> bool:
        return self.risk_level == "red" or bool(self.blockers)

    @property
    def summary_line(self) -> str:
        risk_icon = {"green": "🟢", "amber": "🟡", "red": "🔴"}.get(self.risk_level, "⚪")
        parts = [f"{risk_icon} Officer layer: {self.risk_level.upper()}"]
        if self.priorities:
            parts.append(f"{len(self.priorities)} priority item(s)")
        if self.blockers:
            parts.append(f"{len(self.blockers)} blocker(s)")
        return " — ".join(parts)


# ── Risk aggregation ──────────────────────────────────────────────────────────

def _aggregate_risk(signals: list[dict[str, Any]], ctx: Any) -> str:
    """Determine overall officer layer risk level."""
    capacity = getattr(ctx, "capacity_status", "Unknown")
    ori_risk = getattr(ctx, "resilience_risk", "Unknown")
    blocked = getattr(ctx, "engineering_blocked", 0)
    tech_debt = getattr(ctx, "tech_debt_critical_count", 0)
    leakage = getattr(ctx, "benefit_leakage_critical", 0)

    if capacity == "Red" or ori_risk == "RED" or leakage >= 2:
        return "red"
    if capacity == "Amber" or ori_risk == "AMBER" or blocked >= 2 or tech_debt >= 1:
        return "amber"
    return "green"


# ── Officer status collection ─────────────────────────────────────────────────

def get_officer_statuses(ctx: Any) -> list[OfficerStatus]:
    """Collect status for each officer based on cycle context signals."""
    statuses = []

    officers = [
        ("medical",      getattr(ctx, "capacity_status", "Unknown") not in ("Unknown",),
         getattr(ctx, "capacity_status", "green")),
        ("research",     bool(getattr(ctx, "high_confidence_findings", [])),
         "amber" if getattr(ctx, "resilience_risk", "Unknown") in ("RED", "AMBER") else "green"),
        ("knowledge",    getattr(ctx, "lesson_candidates_pending", 0) > 0 or
                         bool(getattr(ctx, "cross_domain_opportunities", [])),
         "green"),
        ("engineering",  getattr(ctx, "engineering_blocked", 0) > 0 or
                         getattr(ctx, "tech_debt_critical_count", 0) > 0,
         "red" if getattr(ctx, "engineering_blocked", 0) >= 3 else
         "amber" if getattr(ctx, "engineering_blocked", 0) >= 1 else "green"),
        ("number_one",   getattr(ctx, "blocked_initiatives_count", 0) > 0 or
                         getattr(ctx, "delivery_risks_count", 0) > 0,
         "amber" if getattr(ctx, "delivery_risks_count", 0) >= 2 else "green"),
        ("qa",           getattr(ctx, "decision_packages_ready", 0) > 0,
         "amber" if getattr(ctx, "benefit_leakage_critical", 0) >= 1 else "green"),
        ("xo",           True, "green"),
    ]

    for officer, is_active, domain_health in officers:
        # Normalise capacity status to green/amber/red for domain_health
        if domain_health == "Unknown":
            domain_health = "green"
        elif domain_health not in ("green", "amber", "red"):
            domain_health = "amber" if domain_health in ("Amber",) else (
                "red" if domain_health in ("Red",) else "green"
            )
        statuses.append(OfficerStatus(
            officer=officer,
            is_active=is_active,
            domain_health=domain_health,
        ))

    return statuses


# ── Priority extraction ───────────────────────────────────────────────────────

def _extract_priorities(signals: list[dict[str, Any]], ctx: Any) -> list[str]:
    """Extract top officer priority items from signals."""
    priorities: list[str] = []
    seen: set[str] = set()

    for sig in signals:
        officer = sig.get("officer", "")
        sig_type = sig.get("type", "")
        key = f"{officer}:{sig_type}"
        if key in seen:
            continue
        seen.add(key)

        if sig_type == "readiness_assessment":
            status = sig.get("capacity_status", "Unknown")
            if status in ("Red", "Amber"):
                priorities.append(f"Medical: Capacity {status} — {sig.get('gate_actions', 0)} gate action(s)")
        elif sig_type == "engineering_assessment":
            blocked = sig.get("blocked", 0)
            debt = sig.get("critical_tech_debt", 0)
            if blocked or debt:
                priorities.append(
                    f"Engineering: {blocked} blocked mission(s), {debt} critical tech debt item(s)"
                )
        elif sig_type == "operational_review":
            idle = sig.get("idle_missions", 0)
            blocked_init = sig.get("blocked_initiatives", 0)
            if idle or blocked_init:
                priorities.append(
                    f"Operations: {idle} idle mission(s), {blocked_init} blocked initiative(s)"
                )
        elif sig_type == "intelligence_scan":
            findings = sig.get("findings", 0)
            ori = sig.get("ori_risk", "Unknown")
            if findings or ori not in ("Unknown", "GREEN"):
                priorities.append(f"Research: {findings} high-confidence finding(s), ORI={ori}")
        elif sig_type == "knowledge_capture":
            candidates = sig.get("lesson_candidates", 0)
            if candidates:
                priorities.append(f"Knowledge: {candidates} lesson candidate(s) pending capture")

    return priorities[:5]


def _extract_blockers(ctx: Any) -> list[str]:
    """Extract organisational blockers from cycle context."""
    blockers = []
    blocked = getattr(ctx, "engineering_blocked", 0)
    if blocked >= 2:
        blockers.append(f"{blocked} engineering missions concurrently blocked")
    blocked_init = getattr(ctx, "blocked_initiatives_count", 0)
    if blocked_init >= 2:
        blockers.append(f"{blocked_init} initiatives blocked by dependencies")
    leakage = getattr(ctx, "benefit_leakage_critical", 0)
    if leakage:
        blockers.append(f"{leakage} critical benefit leakage item(s)")
    constraint = getattr(ctx, "delivery_constraint_critical", 0)
    if constraint >= 2:
        blockers.append(f"{constraint} critical delivery constraint(s)")
    return blockers[:4]


def _build_recommendations(
    risk_level: str,
    priorities: list[str],
    blockers: list[str],
    statuses: list[OfficerStatus],
    ctx: Any,
) -> list[str]:
    """Build XO recommendations for the Captain."""
    recs = []
    if risk_level == "red":
        capacity = getattr(ctx, "capacity_status", "Unknown")
        if capacity == "Red":
            recs.append("Recommend: invoke capacity recovery protocol immediately")
        ori = getattr(ctx, "resilience_risk", "Unknown")
        if ori == "RED":
            recs.append("Recommend: ORI RED response — escalate to Captain for resilience decision")
        if getattr(ctx, "benefit_leakage_critical", 0) >= 2:
            recs.append("Recommend: XO-led benefit recovery review within 24 hours")

    if blockers:
        recs.append(f"Recommend: Number One unblocking focus — {len(blockers)} active blocker(s)")

    red_officers = [s for s in statuses if s.domain_health == "red"]
    if red_officers:
        names = ", ".join(s.officer for s in red_officers)
        recs.append(f"Recommend: Captain attention to officer domain(s) at RED: {names}")

    if not recs and risk_level == "green":
        recs.append("Officer layer nominal — no Captain action required")

    return recs[:4]


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist_synthesis(synthesis: XOSynthesis) -> None:
    """Persist XO synthesis record to decisions table."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return

        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        owner = f"xo_synthesis:{date_str}"
        statement = f"[XO SYNTHESIS] {date_str}: {synthesis.risk_level.upper()}"
        rationale = (
            f"RISK: {synthesis.risk_level} | SIGNALS: {synthesis.signals_processed} | "
            f"ACTIONS: {len(synthesis.recommendations)} | "
            f"OFFICERS_ACTIVE: {sum(1 for s in synthesis.officer_statuses if s.is_active)}"
        )

        existing = c.raw_client.table("decisions").select("id").eq("owner", owner).limit(1).execute()
        if list(existing.data or []):
            c.raw_client.table("decisions").update({
                "statement": statement,
                "rationale": rationale,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("owner", owner).execute()
        else:
            c.raw_client.table("decisions").insert({
                "owner": owner,
                "statement": statement,
                "rationale": rationale,
                "decision_type": "xo_synthesis",
                "status": "active",
            }).execute()
    except Exception as exc:
        log.debug("[xo_orchestrator] Persist failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def synthesise_officer_outputs(
    signals: list[dict[str, Any]],
    ctx: Any,
) -> XOSynthesis:
    """Synthesise all officer signals into a structured XO brief."""
    risk_level = _aggregate_risk(signals, ctx)
    priorities = _extract_priorities(signals, ctx)
    blockers = _extract_blockers(ctx)
    statuses = get_officer_statuses(ctx)
    recommendations = _build_recommendations(risk_level, priorities, blockers, statuses, ctx)

    synthesis = XOSynthesis(
        risk_level=risk_level,
        priorities=priorities,
        blockers=blockers,
        recommendations=recommendations,
        officer_statuses=statuses,
        signals_processed=len(signals),
    )

    _persist_synthesis(synthesis)
    log.info(
        "[xo_orchestrator] Synthesis: risk=%s, priorities=%d, blockers=%d, recs=%d",
        risk_level, len(priorities), len(blockers), len(recommendations),
    )
    return synthesis


def format_xo_synthesis(synthesis: XOSynthesis) -> str:
    """Format XO synthesis as a Slack-ready section for the Captain brief."""
    if not synthesis.priorities and not synthesis.blockers and synthesis.risk_level == "green":
        return ""

    risk_icons = {"green": ":large_green_circle:", "amber": ":large_yellow_circle:", "red": ":red_circle:"}
    icon = risk_icons.get(synthesis.risk_level, ":white_circle:")

    lines = [
        f"*XO Officer Layer Synthesis* {icon}",
        f"_{synthesis.summary_line}_",
        "",
    ]

    if synthesis.priorities:
        lines.append("*Officer Priorities:*")
        for p in synthesis.priorities:
            lines.append(f"  · {p}")
        lines.append("")

    if synthesis.blockers:
        lines.append("*Organisational Blockers:*")
        for b in synthesis.blockers:
            lines.append(f"  :warning: {b}")
        lines.append("")

    if synthesis.recommendations:
        lines.append("*XO Recommendations:*")
        for r in synthesis.recommendations:
            lines.append(f"  → {r}")

    # Officer health summary
    active_officers = [s for s in synthesis.officer_statuses if s.is_active]
    flagged = [s for s in synthesis.officer_statuses if s.domain_health in ("amber", "red")]
    if active_officers or flagged:
        lines.append("")
        active_names = ", ".join(s.officer for s in active_officers)
        lines.append(f"_Active officers: {active_names or 'none'}_")
        if flagged:
            flagged_names = ", ".join(f"{s.officer} ({s.domain_health})" for s in flagged)
            lines.append(f"_Flagged domains: {flagged_names}_")

    return "\n".join(lines)


__all__ = [
    "OfficerStatus",
    "XOSynthesis",
    "synthesise_officer_outputs",
    "format_xo_synthesis",
    "get_officer_statuses",
]
