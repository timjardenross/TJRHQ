"""Operational State Model (MSN-0329 Phase 2, Step 1).

A continuously-queryable snapshot of the Captain's current operational
situation, built from `core_events` per MSN-0329 Phase 0's resolved
substrate decision (Option C: `core_events` mandatory for new
intelligence capability). Represents WHAT IS TRUE RIGHT NOW across
every domain with a real signal source today — no insight generation,
no cross-domain reasoning, no LLM calls. That's the Understanding/
Insight Engine (MSN-0329 Phase 2, Step 2+), deliberately not this
module's job (Step 1 must exist and be validated before Step 2 has
anything real to reason over).

No I/O of its own — pure function over an already-fetched event list,
matching this platform's established orchestrator convention
(captain_brief_orchestrator.py, attention_engine.py).

Honesty over completeness: MSN-0329's charter names 11 candidate
domains (missions, engineering, health, operational resilience,
knowledge, research, calendar, communications, documents, automation,
historical activity). Verified against real code before writing this
module, not assumed:
  - 5 have a real emitter today: missions (mission-lifecycle), health
    (health-intelligence, also covers decision/capacity per MSN-0328
    Wave 3), operational resilience (operational-resilience-intelligence),
    engineering delivery (engineering-delivery), communications
    (content-intelligence).
  - 1 is a dead mapping: `research-learning`/`research-learning-intelligence`
    are recognised by captain_brief_orchestrator.py's
    _DOMAIN_SECTION_MAP but zero real code calls publish_event with
    either domain string — confirmed by repo-wide grep, not assumed.
  - 4 have no intelligence layer at all: knowledge, calendar, documents,
    automation. No emitter, no mapping, nothing to read.
  - "Historical activity" is not a domain — it's `core_events` itself,
    over a wider `since` window; this module treats it as such.

A domain with no real signal is represented as `data_available=False`,
never fabricated as an empty-but-present state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# MSN-0329 §7: real domains only. Do not add a domain here until a real
# publish_event() call for it exists somewhere in the repo — this list
# is a claim about what's true, re-verify before extending it.
_REAL_DOMAINS: dict[str, str] = {
    "mission-lifecycle": "Missions",
    "engineering-delivery": "Engineering",
    "health-intelligence": "Health",
    "operational-resilience-intelligence": "Operational Resilience",
    "content-intelligence": "Communications",
    "wellness-coaching": "Wellness",
    "strategic-planning": "Strategic Alignment",
}

# Recognised by captain_brief_orchestrator.py's _DOMAIN_SECTION_MAP but
# confirmed (repo-wide grep, MSN-0329) to have zero real publish_event()
# caller — a mapped domain with structurally no data, not the same as
# "no mapping at all" below.
_MAPPED_BUT_DEAD_DOMAINS: dict[str, str] = {
    "research-learning": "Research",
    "research-learning-intelligence": "Research",
    "engineering": "Engineering (legacy mapping, superseded by engineering-delivery)",
    "engineering-intelligence": "Engineering (legacy mapping, superseded by engineering-delivery)",
}

# No domain mapping and no emitter exist for these at all, per MSN-0329's
# own charter naming them as candidate inputs. Listed explicitly so the
# gap is a documented fact, not a silent omission.
_NO_SIGNAL_SOURCE_DOMAINS: list[str] = ["Knowledge", "Calendar", "Documents", "Automation"]


@dataclass
class DomainState:
    """One domain's current state, derived entirely from real events —
    no fabricated defaults for a domain with no data this window."""

    domain_key: str
    label: str
    data_available: bool
    event_count: int = 0
    latest_event_at: Optional[str] = None
    latest_events: list[dict[str, Any]] = field(default_factory=list)
    # Merged from each event's own `metrics` field (MSN-0328) — last
    # non-null value per key wins, most-recent-first, so a repeated key
    # (e.g. successive mission.load_snapshot events) reflects the latest
    # real reading, not a stale earlier one.
    aggregated_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationalStateModel:
    generated_at: str
    window_hours: int
    total_events_considered: int
    domains: dict[str, DomainState]  # keyed by human label, e.g. "Missions"
    domains_with_no_signal_source: list[str]
    dead_mapping_domains: list[str]  # mapped in the brief pipeline, zero real emitters


def assemble_operational_state(
    events: list[dict[str, Any]],
    *,
    window_hours: int = 24,
) -> OperationalStateModel:
    """Pure function: group an already-fetched core_events batch into
    one DomainState per real domain. Caller is responsible for having
    already called event_bus.poll_events() with an appropriate `since`
    matching `window_hours` — this function does no I/O and does not
    itself enforce the window, only reports what it was told.
    """
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        domain = event.get("domain", "unknown")
        by_domain.setdefault(domain, []).append(event)

    domains: dict[str, DomainState] = {}
    for domain_key, label in _REAL_DOMAINS.items():
        rows = sorted(by_domain.get(domain_key, []), key=lambda e: e.get("occurred_at") or "", reverse=True)
        metrics: dict[str, Any] = {}
        # Oldest-first merge so the most recent real value wins per key.
        for row in reversed(rows):
            m = row.get("metrics") or {}
            metrics.update({k: v for k, v in m.items() if v is not None})
        domains[label] = DomainState(
            domain_key=domain_key,
            label=label,
            data_available=bool(rows),
            event_count=len(rows),
            latest_event_at=(rows[0].get("occurred_at") if rows else None),
            latest_events=rows[:10],
            aggregated_metrics=metrics,
        )

    return OperationalStateModel(
        generated_at=datetime.now(timezone.utc).isoformat(),
        window_hours=window_hours,
        total_events_considered=len(events),
        domains=domains,
        domains_with_no_signal_source=list(_NO_SIGNAL_SOURCE_DOMAINS),
        dead_mapping_domains=sorted(set(_MAPPED_BUT_DEAD_DOMAINS.values())),
    )


__all__ = [
    "DomainState",
    "OperationalStateModel",
    "assemble_operational_state",
]
