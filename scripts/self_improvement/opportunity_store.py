"""
HQ Evolution opportunity model and store.

An Opportunity is the unit the Discover/Investigate/Improve/Learned surfaces
render. It generalises a self-improvement "finding" to also cover external
discoveries (repos, models, concepts) and internal capability/product/
architecture opportunities that are not bounded remediations.

This module only defines the schema and an append-only JSONL store with
dedup/lookup helpers. It does not decide relevance (relevance.py), does not
discover anything (internal_discovery.py / external_discovery.py), and does
not grant automation authority (policy.py remains the sole authority for
that — see PolicyEngine.classify_finding, reused here unchanged).
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("opportunity_store")


# Section 18: opportunity lifecycle states. Deliberately a superset that
# maps existing finding/decision vocabulary onto it (see migration.py)
# rather than a second, competing state machine.
LIFECYCLE_STATES = (
    "discovered",
    "investigating",
    "proposed",
    "approved",
    "implementing",
    "verifying",
    "learned",
    "watching",
    "rejected",
    # Follow-up mission (current-state validation, spec section 15): a
    # watchlist gap_hypothesis that no longer holds against current repo
    # evidence, checked *before* any external research was spent on it.
    # Distinct from "rejected" (a human decided against it) and "watching"
    # (premature, not yet worth acting on) — this one HQ itself determined
    # is no longer applicable, and the record exists so the hypothesis is
    # never silently re-researched from scratch.
    "resolved_before_research",
)

# Section 24: change classes. "maintenance"/"configuration"/"reliability"/
# "cost_optimisation" may flow through the existing bounded-remediation path
# when the PolicyEngine (policy.py, unchanged) permits it; "capability",
# "product_improvement" and "architecture" are Mission-only, always.
CHANGE_CLASSES = (
    "maintenance",
    "configuration",
    "reliability",
    "cost_optimisation",
    "capability",
    "product_improvement",
    "architecture",
)

MISSION_ONLY_CLASSES = frozenset({"capability", "product_improvement", "architecture"})

DISCOVERY_SOURCES = ("internal", "external")

# V2 section 10: canonical outcome-evaluation vocabulary. NOT_YET_READY is
# the state while an observation window is still open — it is a valid,
# calm, non-urgent result (section 42), never converted to success.
OUTCOME_RESULTS = ("improved", "no_material_change", "regressed", "inconclusive", "not_yet_ready")
MEASUREMENT_TYPES = ("quantitative", "deterministic", "qualitative", "mixed", "unknown")
CONFIDENCE_LEVELS = ("low", "moderate", "high")


def new_fingerprint(title: str, source: str, discovery_source: str) -> str:
    """Stable identity for dedup — section 17. Normalises whitespace/case so
    trivial rewording of the same idea doesn't evade dedup. Each component
    is whitespace-collapsed *before* joining — collapsing the joined string
    instead would let leading/trailing whitespace on one component leak an
    extra separator space into the string and change the hash."""
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    normalized = f"{norm(discovery_source)}:{norm(source)}:{norm(title)}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class Opportunity:
    opportunity_id: str
    title: str
    change_class: str  # one of CHANGE_CLASSES
    discovery_source: str  # "internal" | "external"
    lifecycle_state: str = "discovered"
    fingerprint: str = ""

    # What/why (sections 6-10)
    summary: str = ""
    why_relevant: str = ""

    # Evaluation (sections 11, 16, 22)
    value: Optional[str] = None  # "low" | "medium" | "high"
    cost_impact: Optional[str] = None  # "lower" | "neutral" | "higher" | "unknown"
    complexity: Optional[str] = None  # "low" | "moderate" | "high"
    fit: Optional[str] = None  # "weak" | "moderate" | "strong"
    risk_level: Optional[str] = None  # set by PolicyEngine, not the LLM
    relevance_score: Optional[float] = None
    confidence: float = 0.0
    evidence_strength: str = "weak"

    # Investigation record (section 22)
    investigation: dict[str, Any] = field(default_factory=dict)

    # Provenance (section 44) — list of {source, retrieved_at, location, detail}
    provenance: list[dict[str, Any]] = field(default_factory=list)

    # Watch / rejection reasoning (sections 32-33)
    watch_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    missing_evidence: list[str] = field(default_factory=list)

    # Outcome / learning (V1 sections 27-29; V2 sections 5-21).
    #
    # `outcome_contract` — set once, at approval time, before implementation
    # (V2 section 5-6). Shape (all keys optional/defaulted, never required
    # to match exactly — this is a dict, not a second dataclass, precisely
    # so evaluation code can degrade gracefully on a missing key):
    #   expected_benefit: str
    #   measurement_type: "quantitative"|"deterministic"|"qualitative"|"mixed"|"unknown"
    #   baseline: {"available": bool, "value": Any, "description": str,
    #              "provenance": str, "captured_at": iso} — or
    #             {"available": False, "reason": str} when no honest
    #             baseline exists (V2 section 8: never fabricate one)
    #   success_signal / regression_signal: str (human-readable) with an
    #     optional structured "success_threshold" / "regression_threshold"
    #     dict for deterministic comparison — regression_signal is the
    #     no-self-reward-loop guardrail (V2 section 30)
    #   observation_window: {"type": "cycles"|"events"|"immediate"|"days", "count": int}
    #   evidence_sources: [str, ...] naming which evidence_sources.py reader(s) apply
    #   evaluation_status: "pending_implementation"|"observing"|"ready_to_evaluate"|"evaluated"
    #   observation_started_at: iso|None — set once implementation is confirmed
    #   created_at: iso
    #
    # `outcome` — the evaluation record (also holds the V1 legacy-migration
    # shape: implementation_success/improvement_success/improvement_success_note/
    # remediation_history — untouched, still written by migration.py). V2 adds:
    #   implementation_source: "remediation"|"mission"|"manual"|None
    #   implementation_verified_at: iso|None
    #   outcome_result: "improved"|"no_material_change"|"regressed"|"inconclusive"|"not_yet_ready"|None
    #   evidence_summary / what_worked / what_did_not / future_implication: str
    #   unexpected_effects: [str]
    #   attribution_risk: str|None — set when concurrent changes make attribution unsafe
    #   confidence: "low"|"moderate"|"high"|None — never a fabricated percentage
    #   method: "deterministic"|"model_synthesis"|"template_fallback"|None
    #   evaluation_history: [{outcome_result, confidence, evidence_summary,
    #     evaluated_at, method}, ...] — V2 section 37: re-evaluation appends,
    #     never silently overwrites the prior verdict
    outcome: dict[str, Any] = field(default_factory=dict)
    outcome_contract: dict[str, Any] = field(default_factory=dict)

    # Current-state validation (follow-up mission, sections 11-17): the
    # result of checking a watchlist gap_hypothesis against real repo
    # evidence, before any external research money was spent on it.
    validation_result: Optional[str] = None  # "confirmed" | "resolved" | "unclear"
    validation_evidence: list[str] = field(default_factory=list)
    validated_at: Optional[str] = None

    # V2 section 6/8: set by a discovery module (e.g. internal_discovery.py's
    # call-log-rotation candidate) when a concrete, honestly re-checkable
    # quantitative signal exists for THIS specific opportunity — e.g.
    # {"type": "file_size_mb", "path": "core/model-router/call_log.jsonl"}.
    # outcome_contract.py reads it to capture a real baseline at approval
    # time; outcome_evaluation.py reads the SAME hint post-window for an
    # apples-to-apples comparison. Must survive from the discovery candidate
    # dict onto the persisted Opportunity — see evolution_orchestrator.py's
    # discovery-persistence step.
    measurement_hint: Optional[dict[str, Any]] = None

    # Links to the existing engine (section 34 migration) — never re-surfaced
    # as a "new" opportunity once linked.
    source_finding_id: Optional[str] = None
    mission_id: Optional[str] = None

    # Policy classification, reusing policy.py's existing output shape
    automation_eligibility: Optional[str] = None
    policy_decision_rationale: Optional[str] = None

    created_at: str = ""
    updated_at: str = ""
    run_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpportunityStore:
    """Append-only JSONL store, mirroring decisions.jsonl's own durability
    model (section 34: history stays history). update_opportunity() appends
    a new full record rather than mutating in place; latest_by_id() folds
    that back into "current state" — the same pattern decision_processor.py
    already uses for decisions.jsonl."""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "review" / "opportunities.jsonl"
        self.counter_path = data_root / "review" / "opportunity_id_counter.txt"

    def _next_id(self) -> str:
        self.counter_path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        if self.counter_path.exists():
            try:
                n = int(self.counter_path.read_text().strip() or "0")
            except ValueError:
                n = 0
        n += 1
        self.counter_path.write_text(str(n))
        return f"EVO-{n:04d}"

    def all_records(self) -> list[dict[str, Any]]:
        """Every record ever appended, oldest first. Use latest_by_id() for
        current state — this is the raw audit trail."""
        if not self.path.exists():
            return []
        records = []
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        log.warning(f"Skipping malformed opportunities.jsonl line: {exc}")
        return records

    def latest_by_id(self) -> dict[str, dict[str, Any]]:
        """Fold the append-only log into current-state-per-opportunity."""
        latest: dict[str, dict[str, Any]] = {}
        for rec in self.all_records():
            oid = rec.get("opportunity_id")
            if oid:
                latest[oid] = rec
        return latest

    def all_current(self) -> list[dict[str, Any]]:
        return list(self.latest_by_id().values())

    def get(self, opportunity_id: str) -> Optional[dict[str, Any]]:
        return self.latest_by_id().get(opportunity_id)

    def find_by_fingerprint(self, fingerprint: str) -> Optional[dict[str, Any]]:
        for rec in self.all_current():
            if rec.get("fingerprint") == fingerprint:
                return rec
        return None

    def append(self, opportunity: Opportunity) -> Opportunity:
        """Persist a new opportunity or a new state for an existing one.
        Caller sets opportunity_id explicitly when updating; use
        create_new() to get a fresh id."""
        now = datetime.now(timezone.utc).isoformat()
        if not opportunity.created_at:
            opportunity.created_at = now
        opportunity.updated_at = now

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(opportunity.to_dict(), default=str) + "\n")
        return opportunity

    def create_new(self, **kwargs) -> Opportunity:
        kwargs.setdefault("opportunity_id", self._next_id())
        opp = Opportunity(**kwargs)
        if not opp.fingerprint:
            opp.fingerprint = new_fingerprint(opp.title, kwargs.get("source", ""), opp.discovery_source)
        return self.append(opp)

    def update(self, opportunity_id: str, **changes) -> Optional[Opportunity]:
        """Append a new record for opportunity_id with `changes` merged over
        its current state. Returns None if opportunity_id is unknown."""
        current = self.get(opportunity_id)
        if current is None:
            return None
        merged = {**current, **changes, "opportunity_id": opportunity_id}
        # Drop any keys Opportunity doesn't know about (forward-compat safety)
        valid_fields = {f for f in Opportunity.__dataclass_fields__}
        merged = {k: v for k, v in merged.items() if k in valid_fields}
        opp = Opportunity(**merged)
        return self.append(opp)
