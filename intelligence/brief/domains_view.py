"""Domains — merged cross-domain assembly (Briefs/Captain's Brief
consolidation, Phase 2. See BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md §4.1/§6).

Two pipelines synthesise domain pictures independently today:

- Briefs' OSINT `domain_picture` (technical/regulatory/environmental/
  payments + Health OSINT + Emergency Alert Hub, intelligence_briefs table,
  `intelligence/brief/domain_picture.py`) — a stored snapshot from the most
  recent morning brief.
- Captain's Brief's event-bus domain sections (health/operational_
  intelligence/engineering/learning/opportunities,
  `core/platform/captain_brief_orchestrator.py`) — always live, computed
  fresh from `core_events` on every call.

Per the consolidation doc's own recommendation (§4.1), this module is the
one shared assembly step that normalises both into a single list of
`DomainSummary` objects — the mission's own schema (posture, confidence,
what changed, what matters, watch conditions, evidence count with
drill-down) — so the Briefs "Domains" tab renders one document instead of
reconciling two structurally incompatible shapes itself. Nothing here
recomputes either pipeline's own synthesis (`compute_domain_picture()` /
`assemble_captain_brief_document()` are both reused verbatim) — this only
normalises their already-computed output into one shape and derives the
handful of summary fields (posture/confidence/what-matters/watch) neither
pipeline expresses per-domain today.

Pure function, no I/O — same contract as `assemble_captain_brief_document()`:
takes already-fetched events and the already-fetched latest brief row as
arguments, so it's testable without a live DB or event bus.

Signal-leakage fix (post-Phase 3 bug, same class PR #275 fixed elsewhere):
this module's first pass built `what_matters`/`watch_conditions` straight
from `CaptainBriefItem.reason` — the Attention Engine's own internal audit
trail (a scoring formula, an aggregation note, or a persistence-gate
suppression narrative), not a synthesized finding. In production this
surfaced raw aggregation logic ("9 events sharing domain=.../event_type=...
— aggregate as a count/trend") and suppression-gate reasoning ("recurrence
of already-acknowledged event <uuid> ... — not re-interrupting...") as if
they were "What Matters" bullets. Fixed by `_readable_text()` (never
`reason`; recommendation -> description -> nothing, matching PR #275's own
established fallback order minus its last-resort `reason` step, which that
push-notification call site needs and this one doesn't) and by
`_aggregation_constraints()` (aggregated groups become one synthesized
`constraints` coverage sentence, never a per-event `what_matters` bullet).
`evidence` is unchanged and still shows `item.reason` verbatim — that is
its job, an explicit one-click-away audit drill-down, not a headline.

Unscored-risk fix (priority_engine.py): `_posture_for_items()` used to
carry a known blind spot here — `priority_engine.py::_risk_from_importance_
confidence()` defaulted a missing importance/confidence to 0, so an event
that never sets either (e.g. `intelligence.source.failed`, published with
no importance/confidence at all) got a real-looking `risk_score` of 0.0
instead of `None`, indistinguishable here from a genuinely low-risk,
fully-scored event. That upstream engine now returns `None` for this case
instead of fabricating 0.0; every risk-consuming function below
(`_risk_label`, `_posture_for_items`, the `watch_conditions` filter) was
already written to exclude `None` on `is not None` grounds, so the fix
took effect automatically here with no logic change needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.platform.attention_engine import AttentionCategory
from core.platform.captain_brief_contract import CaptainBriefItem
from core.platform.captain_brief_orchestrator import assemble_captain_brief_document

# Posture thresholds mirror captain_brief_orchestrator.py's own
# _WARNING_RISK_THRESHOLD (60.0) for RED; AMBER is this module's own choice
# for a mid-tier "worth watching" cut, kept local rather than importing that
# module's private constant.
_POSTURE_RED = 60.0
_POSTURE_AMBER = 30.0

# The five event-bus domain sections CaptainBriefDocument exposes as public
# fields (captain_brief_orchestrator.py's _DOMAIN_SECTION_MAP targets) —
# labels kept in parity with captains-brief-workbench/_components/types.ts's
# DOMAIN_SECTIONS so the two UIs describe the same domains the same way.
_EVENT_BUS_DOMAIN_LABELS: dict[str, str] = {
    "health": "Health",
    "operational_intelligence": "Operational Intelligence",
    "engineering": "Engineering",
    "learning": "Learning",
    "opportunities": "Opportunities",
}


@dataclass
class DomainEvidenceItem:
    """One drill-down preview row — never the full underlying event, just
    enough to decide whether to follow `DomainSummary.detail_href`."""

    title: str
    detail: str | None = None
    risk: str | None = None  # RED/AMBER/GREEN/UNKNOWN, when known


@dataclass
class DomainSummary:
    key: str
    label: str
    source: str  # "osint" | "event_bus"
    posture: str  # RED/AMBER/GREEN/UNKNOWN
    confidence: float | None  # 0-100 mean, None if not computable — never fabricated
    what_changed: str | None
    what_matters: list[str] = field(default_factory=list)
    watch_conditions: list[str] = field(default_factory=list)
    # Coverage/data-quality caveats — distinct from `what_matters` (individual
    # findings) and `watch_conditions` (near-threshold risk items). Holds
    # signals like "N events of this type were aggregated as a count/trend"
    # that describe the *shape* of the data behind this domain, not a
    # synthesized finding about it. See `_event_bus_domain_summary()` for why
    # aggregated groups are routed here instead of into `what_matters`.
    constraints: list[str] = field(default_factory=list)
    evidence_count: int = 0
    evidence: list[DomainEvidenceItem] = field(default_factory=list)
    as_of: str | None = None
    availability: str = "ok"  # "ok" | "no_data" | "degraded" | "unavailable"
    detail_href: str | None = None


@dataclass
class DomainsDocument:
    generated_at: str
    domains: list[DomainSummary] = field(default_factory=list)
    event_bus_as_of: str | None = None
    osint_as_of: str | None = None
    osint_available: bool = True
    warnings: list[str] = field(default_factory=list)


def _risk_label(risk_score: float | None) -> str | None:
    # None here means priority_engine.py never scored the item (no
    # importance/confidence signal at all) — genuinely unknown risk, not a
    # real 0.0. Must stay its own branch, never fall through to GREEN.
    if risk_score is None:
        return None
    if risk_score >= _POSTURE_RED:
        return "RED"
    if risk_score >= _POSTURE_AMBER:
        return "AMBER"
    return "GREEN"


def _posture_for_items(items: list[CaptainBriefItem]) -> str:
    # Unscored items (risk_score is None) are excluded from the max(), not
    # coerced to 0 — an all-unscored domain reports posture "UNKNOWN"
    # below rather than a fabricated "GREEN". A domain with both scored and
    # unscored items still ranks by its scored items only; an unscored item
    # can't push posture to RED/AMBER, matching this module's "never
    # fabricate" contract (see priority_engine.py's own risk_score docstring
    # and the module docstring's "Unscored-risk fix" paragraph above — this
    # used to be a known blind spot before that upstream fix landed).
    risk_scores = [i.risk_score for i in items if i.risk_score is not None]
    if not risk_scores:
        return "UNKNOWN"
    return _risk_label(max(risk_scores)) or "UNKNOWN"


def _readable_text(item: CaptainBriefItem) -> str | None:
    """The genuine, human-readable content for a user-facing bullet
    (`what_matters`/`watch_conditions`) — a real recommendation or the
    event's own `description`, never `item.reason`.

    `reason` is an internal Attention Engine audit trail: a scoring
    formula ("importance=X >= Y AND confidence=Z >= W"), an aggregation
    note ("N events sharing domain=.../event_type=... — aggregate as a
    count/trend"), or a persistence-gate suppression narrative
    ("recurrence of already-acknowledged event <uuid> ... — not
    re-interrupting a stable, already-surfaced condition"). None of that
    is a synthesized finding, and the PR #275 signal-leakage fix already
    established `description` as the correct home for readable content —
    this mirrors that fallback chain (recommendation -> description) but
    stops there: unlike `interrupt_dispatcher.py`'s push body, a
    materiality/watch bullet has no "must never be empty" requirement, so
    an item with nothing genuinely readable is simply left out rather than
    falling back to `reason`. `evidence` (below) is the one place `reason`
    is still shown — an explicit, one-click-away drill-down, not a
    headline.
    """
    if item.recommendation is not None:
        return item.recommendation.description
    return item.description


def _confidence_for_items(items: list[CaptainBriefItem]) -> float | None:
    scores = [
        i.recommendation.confidence
        for i in items
        if i.recommendation is not None and i.recommendation.confidence is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def _aggregation_constraints(items: list[CaptainBriefItem]) -> list[str]:
    """Coverage signal for aggregated groups (`evaluate_batch()`'s
    SHOULD_BE_AGGREGATED branch: 3+ events sharing a (domain, event_type)
    pair in one batch, `aggregation_key` set on every member). A count/
    trend across N events — a large source-failure aggregate among
    them — is real information, but it is not a synthesized finding about
    any one event, and showing the same (or a diagnostic aggregation-trace)
    line as a `what_matters` bullet either repeats it 3+ times or leaks the
    raw trace text. Both are wrong; this builds one fresh, honest sentence
    per group instead, keyed only by the group's own size and event_type —
    never by parsing `item.reason`.
    """
    groups: dict[str, list[CaptainBriefItem]] = {}
    for item in items:
        if item.aggregation_key:
            groups.setdefault(item.aggregation_key, []).append(item)

    constraints: list[str] = []
    for agg_key in sorted(groups):
        group = groups[agg_key]
        event_type = group[0].event_type or agg_key
        constraints.append(
            f"{len(group)} {event_type} event(s) aggregated as a count/trend this cycle — "
            "a coverage signal, not an individual finding; see Evidence for the raw events."
        )
    return constraints


def _event_bus_domain_summary(
    key: str, label: str, items: list[CaptainBriefItem], generated_at: str
) -> DomainSummary:
    interrupt_count = sum(1 for i in items if i.category == AttentionCategory.INTERRUPT_NOW)
    what_changed = f"{interrupt_count} item(s) need attention now" if interrupt_count else None

    # Aggregated items (3+ sharing an aggregation_key) are excluded from
    # what_matters/watch_conditions below — they become a `constraints`
    # coverage signal instead (`_aggregation_constraints()`), not a
    # per-event materiality bullet.
    individual_items = [i for i in items if not i.aggregation_key]

    what_matters: list[str] = []
    for item in sorted(individual_items, key=lambda i: i.priority_score or 0, reverse=True):
        text = _readable_text(item)
        if text and text not in what_matters:
            what_matters.append(text)
        if len(what_matters) >= 3:
            break

    watch_conditions: list[str] = []
    for item in individual_items:
        # Same "None is not 0.0" exclusion as _posture_for_items above — an
        # unscored item never qualifies as a watch condition, but it also
        # never gets miscounted as safe; it simply carries no risk verdict.
        if item.risk_score is None or item.risk_score < _POSTURE_AMBER:
            continue
        text = _readable_text(item)
        if text and text not in watch_conditions:
            watch_conditions.append(text)
        if len(watch_conditions) >= 3:
            break

    evidence = [
        DomainEvidenceItem(title=item.event_type or item.domain, detail=item.reason, risk=_risk_label(item.risk_score))
        for item in items[:5]
    ]

    return DomainSummary(
        key=key,
        label=label,
        source="event_bus",
        posture=_posture_for_items(items),
        confidence=_confidence_for_items(items),
        what_changed=what_changed,
        what_matters=what_matters,
        watch_conditions=watch_conditions,
        constraints=_aggregation_constraints(items),
        evidence_count=len(items),
        evidence=evidence,
        as_of=generated_at,
        availability="ok" if items else "no_data",
        # Phase 5 (Captain's Brief retirement): /captains-brief-workbench no
        # longer exists as a standalone page (redirects to /briefs). This
        # card's own Coverage Notes/Evidence already surface everything that
        # page's per-domain filter view showed — there is no more-detailed
        # destination left to link to, so this points at Briefs itself
        # rather than a dead or redirect-then-disorienting link.
        detail_href="/briefs",
    )


def _osint_domain_summary(bucket_key: str, bucket: dict[str, Any], as_of: str | None, degraded: bool) -> DomainSummary:
    events = bucket.get("events") or []
    evidence = [
        DomainEvidenceItem(title=e.get("title") or "Untitled", risk=(e.get("risk_rating") or None))
        for e in events[:5]
    ]
    watch_conditions = [
        e["title"] for e in events if e.get("title") and (e.get("risk_rating") or "").upper() in ("RED", "AMBER")
    ][:3]

    return DomainSummary(
        key=bucket_key,
        label=bucket.get("label") or bucket_key.title(),
        source="osint",
        posture=(bucket.get("worst_risk") or "UNKNOWN"),
        # domain_picture.py's buckets don't carry a numeric confidence today
        # — left None rather than fabricated.
        confidence=None,
        # comparison.py's new/escalated/improved isn't bucket-scoped today
        # — left None rather than fabricated.
        what_changed=None,
        what_matters=[e.get("title") for e in events[:3] if e.get("title")],
        watch_conditions=watch_conditions,
        evidence_count=int(bucket.get("count") or len(events)),
        evidence=evidence,
        as_of=as_of,
        availability="degraded" if degraded else "ok",
        detail_href=None,  # filled in by the caller once brief_id is known
    )


def assemble_domains_document(events: list[dict[str, Any]], latest_brief: dict[str, Any] | None) -> DomainsDocument:
    """Merge Captain's Brief's live event-bus domains with Briefs' latest
    stored OSINT `domain_picture` into one cross-domain document.

    `events`: already-polled `core_events` rows (event_bus.poll_events()'s
    return shape) — passed through to `assemble_captain_brief_document()`
    unchanged.
    `latest_brief`: the raw `intelligence_briefs` row from
    `intelligence_store.load_latest_brief()`, or None if no brief has been
    generated yet (a real, honestly-represented state — see the
    `osint_available` field — not an error).
    """
    cb_doc = assemble_captain_brief_document(events)
    generated_at = cb_doc.generated_at.isoformat() if hasattr(cb_doc.generated_at, "isoformat") else str(cb_doc.generated_at)

    domains: list[DomainSummary] = [
        _event_bus_domain_summary(key, label, getattr(cb_doc, key), generated_at)
        for key, label in _EVENT_BUS_DOMAIN_LABELS.items()
    ]

    warnings: list[str] = []
    osint_as_of: str | None = None
    osint_available = latest_brief is not None

    if latest_brief is None:
        warnings.append(
            "No OSINT brief has been generated yet — Technical/Regulatory/Environmental/"
            "Payments/Health/Emergency domains are unavailable."
        )
    else:
        osint_as_of = latest_brief.get("published_at") or latest_brief.get("generated_at")
        coverage = latest_brief.get("coverage") or {}
        degraded = bool(coverage.get("degraded"))
        picture = latest_brief.get("domain_picture") or {}
        brief_id = latest_brief.get("brief_id")

        if not picture:
            warnings.append("The latest brief has no domain picture to group — nothing to show for OSINT domains.")
        for bucket_key, bucket in picture.items():
            summary = _osint_domain_summary(bucket_key, bucket, osint_as_of, degraded)
            summary.detail_href = f"/briefs/{brief_id}" if brief_id else None
            domains.append(summary)

        if degraded:
            warnings.append("The latest brief's collection cycle was degraded — OSINT domain coverage may be incomplete.")

    return DomainsDocument(
        generated_at=generated_at,
        domains=domains,
        event_bus_as_of=generated_at,
        osint_as_of=osint_as_of,
        osint_available=osint_available,
        warnings=warnings,
    )
