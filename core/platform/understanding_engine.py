"""Understanding Engine (MSN-0329 Phase 2, Step 2).

Interprets the Operational State Model — builds an Operational Context
Graph of real, evidence-backed relationships between events across
domains. Every relationship traces to a checkable fact (a shared
`linked_missions` reference, or real `occurred_at` ordering) — never a
fabricated or LLM-guessed connection. Per MSN-0329's resolved hybrid
design, articulating WHY a relationship matters is the Insight
Engine's job (Step 3, uses the `captain-insight-synthesis` model-router
task); this module only finds and evidences that connections exist.

Reuses rather than re-derives: "emerging situations" are the Attention
Engine's own SHOULD_BE_AGGREGATED groups (`evaluate_batch()` already
detects 3+ events sharing domain+event_type in a batch) — this module
does not re-implement that grouping, only surfaces it as a named
Relationship kind, satisfying MSN-0329 §7's "no duplicate intelligence
logic" requirement.

No I/O — pure functions over an already-fetched events/decisions batch,
matching this platform's established orchestrator convention
(captain_brief_orchestrator.py, operational_state_model.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.platform.attention_engine import AttentionDecision


@dataclass
class Relationship:
    """One real, evidenced connection between 2+ events. `kind` names
    HOW it was detected — every kind traces to a specific, checkable
    rule (below), not a black box:
      - 'shared_mission'    — 2+ events, different domains, same linked_missions entry.
      - 'temporal_sequence' — 2 events sharing a mission, real occurred_at ordering
                               (named a sequence, never asserted as causation).
      - 'aggregation'       — the Attention Engine's own SHOULD_BE_AGGREGATED group,
                               surfaced here, not re-derived.
    """

    kind: str
    event_ids: list[str]
    domains: list[str]
    evidence: str
    strength: float
    # 2026-08-10: domain:event_type identity of the SHOULD_BE_AGGREGATED
    # group this Relationship surfaces, when kind == 'aggregation' — lets
    # downstream (insight_engine.generate_insights) recognise the same
    # structurally-permanent cluster across runs instead of re-synthesizing
    # it every time. None for shared_mission/temporal_sequence, which have
    # no single (domain, event_type) identity to dedupe on.
    aggregation_key: Optional[str] = None


@dataclass
class Conflict:
    """A detected tension between two real signals — a specific named
    rule with the actual metric values that triggered it, not a vague
    'something feels off'."""

    rule: str
    domains: list[str]
    description: str
    evidence: dict[str, Any]


@dataclass
class OperationalContextGraph:
    generated_at: str
    domain_nodes: list[str]
    relationships: list[Relationship]
    conflicts: list[Conflict]
    emerging_situations: list[Relationship]


def _shared_mission_relationships(events: list[dict[str, Any]]) -> list[Relationship]:
    """Rule: 2+ events from DIFFERENT domains reference the same
    linked_missions entry. This is the one relationship kind the
    Attention Engine cannot see (it only groups same domain+event_type
    within a batch) — genuinely new detection, not a duplicate."""
    by_mission: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        for mid in e.get("linked_missions") or []:
            by_mission.setdefault(mid, []).append(e)

    relationships: list[Relationship] = []
    for mission_id, group in by_mission.items():
        domains = sorted({e.get("domain", "unknown") for e in group})
        if len(domains) < 2:
            continue  # same-domain-only reference isn't a cross-domain relationship
        event_ids = [e.get("event_id") for e in group if e.get("event_id")]
        relationships.append(Relationship(
            kind="shared_mission",
            event_ids=event_ids,
            domains=domains,
            evidence=f"{len(group)} event(s) across {len(domains)} domain(s) ({', '.join(domains)}) reference mission {mission_id}",
            strength=min(1.0, len(domains) / 4.0),
        ))

        # Temporal sequence: order the same group by real occurred_at,
        # name consecutive cross-domain pairs — never asserted as
        # causation, just a real, timestamped ordering.
        ordered = sorted(
            (e for e in group if e.get("occurred_at")),
            key=lambda e: e["occurred_at"],
        )
        for a, b in zip(ordered, ordered[1:]):
            if a.get("domain") == b.get("domain"):
                continue
            relationships.append(Relationship(
                kind="temporal_sequence",
                event_ids=[a.get("event_id"), b.get("event_id")],
                domains=[a.get("domain"), b.get("domain")],
                evidence=(
                    f"{a.get('domain')}/{a.get('event_type')} at {a.get('occurred_at')} "
                    f"preceded {b.get('domain')}/{b.get('event_type')} at {b.get('occurred_at')}, "
                    f"both referencing mission {mission_id}"
                ),
                strength=0.5,
            ))

    return relationships


def _aggregation_relationships(decisions: list[AttentionDecision]) -> list[Relationship]:
    """Surfaces the Attention Engine's own SHOULD_BE_AGGREGATED groups
    (evaluate_batch() already computed aggregation_key) as 'emerging
    situation' relationships. Does not recompute the grouping."""
    by_key: dict[str, list[AttentionDecision]] = {}
    for d in decisions:
        if d.aggregation_key:
            by_key.setdefault(d.aggregation_key, []).append(d)

    return [
        Relationship(
            kind="aggregation",
            event_ids=[d.event_id for d in group if d.event_id],
            domains=sorted({d.domain for d in group}),
            evidence=f"{len(group)} events sharing {key} in this batch (Attention Engine SHOULD_BE_AGGREGATED)",
            strength=min(1.0, len(group) / 5.0),
            aggregation_key=key,
        )
        for key, group in by_key.items()
    ]


# Conflict rules — a starting, disclosed set, not an exhaustive library.
# Each rule reads only real metrics already emitted (MSN-0328), never
# invents a new score.

def _capacity_vs_demand_conflict(state) -> Optional[Conflict]:
    delivery = state.domains.get("Engineering")
    missions = state.domains.get("Missions")
    if not delivery or not missions or not delivery.data_available or not missions.data_available:
        return None
    high_risk = delivery.aggregated_metrics.get("high_risk_count")
    open_delivery = delivery.aggregated_metrics.get("open_count")
    open_missions = missions.aggregated_metrics.get("open_count")
    if high_risk is None or open_delivery is None or open_missions is None or open_delivery == 0:
        return None
    risk_ratio = high_risk / open_delivery
    if risk_ratio >= 0.3 and open_missions >= 10:
        return Conflict(
            rule="capacity_vs_demand",
            domains=["Engineering", "Missions"],
            description=(
                f"Delivery risk ratio is high ({high_risk}/{open_delivery} open items "
                f"= {risk_ratio:.0%} high-risk) while mission load is also high "
                f"({open_missions} open) — capacity is constrained exactly when demand is elevated."
            ),
            evidence={"high_risk_count": high_risk, "delivery_open_count": open_delivery,
                      "mission_open_count": open_missions, "risk_ratio": round(risk_ratio, 2)},
        )
    return None


def _strategic_misalignment_conflict(state) -> Optional[Conflict]:
    strategy = state.domains.get("Strategic Alignment")
    if not strategy or not strategy.data_available:
        return None
    orphans = strategy.aggregated_metrics.get("orphan_count")
    if not orphans:
        return None
    return Conflict(
        rule="strategic_misalignment",
        domains=["Strategic Alignment"],
        description=(
            f"{orphans} open mission(s) are not aligned to any active strategic objective — "
            "work is proceeding without a documented strategic link."
        ),
        evidence={"orphan_count": orphans},
    )


_CONFLICT_RULES = [_capacity_vs_demand_conflict, _strategic_misalignment_conflict]


def build_understanding(state, events: list[dict[str, Any]], decisions: list[AttentionDecision]) -> OperationalContextGraph:
    """Pure function: state (OperationalStateModel), the same events
    batch it was built from, and the Attention Engine's own decisions
    for that batch. No I/O, no LLM call — this is the deterministic
    half of the resolved hybrid design."""
    relationships = _shared_mission_relationships(events) + _aggregation_relationships(decisions)
    conflicts = [c for c in (rule(state) for rule in _CONFLICT_RULES) if c is not None]

    return OperationalContextGraph(
        generated_at=datetime.now(timezone.utc).isoformat(),
        domain_nodes=[label for label, d in state.domains.items() if d.data_available],
        relationships=relationships,
        conflicts=conflicts,
        emerging_situations=[r for r in relationships if r.kind == "aggregation"],
    )


__all__ = [
    "Relationship",
    "Conflict",
    "OperationalContextGraph",
    "build_understanding",
]
