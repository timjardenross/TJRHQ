---
status: "accepted"
date: 2026-09-12
decision-makers: {unknown — reconstructed from code, not from a governance-log entry}
consulted: {unknown}
informed: {unknown}
---

# Resilience Intelligence Convergence (RESIL-*): shared LLM provider chain, domain heartbeats, infra narrative

## Context and Problem Statement

Several independent "resilience"/operational-health subsystems
(RESIL-EXT / OR Intelligence, RESIL-HUMAN / human-systems, RESIL-INFRA /
platform verification) had each grown their own copy of Gemini/Mistral/Ollama
request mechanics, and their heartbeat/event-mirroring behaviour had drifted
out of sync with each other and with the domain registry that is supposed to
track them. ADR-024 is the convergence decision that consolidated the
duplicated mechanics and then, in a documented "second-pass audit," found and
fixed the drift this consolidation had not yet covered.

## Decision Drivers

* `intelligence/brief/llm_provider.py` (RESIL-EXT) and
  `core/health/health_llm.py` (RESIL-HUMAN) had implemented the same
  Gemini/Mistral/Ollama call mechanics twice.
* `domain_heartbeats`/`verification_state` (migration 0071) is meant to be
  the platform's single source of truth for "is this job/data domain
  actually running," but several real, live call sites were never wired to
  call `record_heartbeat()`, so verification silently under-reported health.
* `mission-registry-sync` (MSN-0145) had a single point of failure: it only
  ran as a side effect of `platform-runtime/proactive_scheduler.py` inside
  `starfleet-slack-bot.service`, which was disabled/retired 2026-07-07
  (MSN-0337) — and the sync silently missed 45 days, appending 94 missions
  in one catch-up run on 2026-08-10.

## Considered Options

* Consolidate shared LLM call mechanics into one module (`core/llm/provider_chain.py`)
  and reuse it from every resilience subsystem.
* Leave each subsystem's provider-call implementation independent.
* (For the sync gap) give `mission-registry-sync` its own independent
  systemd timer vs. continuing to depend on another service's scheduler as
  a side effect.

## Decision Outcome

Chosen option: consolidate the shared request/response mechanics into
`core/llm/provider_chain.py` ("ADR-024 fix #4" per `infra_narrative.py`'s
docstring) and reuse it from `core/health/health_llm.py` and the infra
narrative module, rather than adding a third bespoke provider
implementation; separately, give `mission-registry-sync` its own
`deploy/mission-registry-sync.service`/`.timer` (daily 06:45 Sydney time,
before the morning brief) so it "can never again go this long without
running, regardless of what happens to the Slack bot."

The decision also drove a "second-pass audit" that is cited repeatedly as
fixing specific, real gaps:
* fix #3: `mission_registry_sync` given its own `domain_registry` row
  (migration 0083) and its own daily job (`intelligence/proactive_cadences.py`,
  `name="Mission Registry Sync (ADR-024)"`).
* fix #4: shared LLM provider-chain mechanics (`core/llm/provider_chain.py`).
* fix #5: `core/platform/infra_narrative.py` — RESIL-INFRA narrative
  synthesis, closing the gap where `domain_heartbeats`/`verification_state`
  data existed but nothing turned it into human-readable narrative; wired
  into `intelligence/captains_brief.py` behind a guarded import so a problem
  in this one module degrades only its own section, never the whole brief.
* Several individually-cited domain-registry/heartbeat gaps found and
  fixed/flagged by the audit: `health_daily_logs` (health_check.py),
  `recovery_pulses` (recovery_pulse.py), `missions` (mission_lifecycle.py),
  `wellness-coaching` and `mission_registry_sync` domains (migration 0083),
  and the operational-state domain list in
  `core/platform/operational_state_model.py` (drifted from
  `captain_brief_orchestrator.py`'s domain-section map, silently dropping
  knowledge/research/platform-operations events), plus Event Bus
  mirroring gaps in `intelligence/ingestion/collection_engine.py` and
  `platform-runtime/human_systems_scheduler.py`.

### Consequences

* Good, because there is now exactly one place (`core/llm/provider_chain.py`)
  implementing the Gemini/Mistral/Ollama request mechanics for resilience
  subsystems, instead of two independently-drifting copies.
* Good, because `mission-registry-sync` no longer depends on an unrelated
  service's scheduler being alive.
* Bad, because the audit found (and in several cases only *flagged*, not
  fixed) multiple domain-registry rows that had "zero record_heartbeat()
  calls anywhere in the repo," meaning `verification_state` had been
  silently reporting `never_succeeded` for live, working write paths — a
  monitoring gap that existed for an unknown period before the audit.
* Neutral, because several of the audit's fixes are explicitly "best-effort,
  non-blocking" (Event Bus mirroring) — they improve observability but do
  not change the underlying data path's correctness.

### Confirmation

Grep `ADR-024` across the repo: every hit should be either (a) a shared
provider-chain reuse comment, (b) a "second-pass audit" fix/flag comment
tied to a specific `domain_registry`/heartbeat gap, or (c) the
`mission-registry-sync` systemd unit/cron citation. A verification pass can
check `domain_heartbeats`/`verification_state` for the specific domains named
above (`health_daily_logs`, `recovery_pulses`, `missions`,
`mission_registry_sync`, `wellness-coaching`) to confirm they are now
recording heartbeats rather than remaining `never_succeeded`.

## Pros and Cons of the Options

### Shared provider-chain module

* Good, because it removes duplicated request/response mechanics between
  RESIL-EXT and RESIL-HUMAN.
* Good, because RESIL-INFRA's narrative synthesis (fix #5) could then reuse
  it directly rather than writing a third implementation.

### Independent per-subsystem provider implementations (rejected)

* Bad, because it was the status quo this decision explicitly moved away
  from — `core/llm/provider_chain.py`'s own docstring names both prior
  duplicate implementations by file path.

## More Information

Evidence: 15+ real citations across
`core/platform/operational_state_model.py`, `core/platform/infra_narrative.py`,
`core/llm/provider_chain.py`, `core/health/health_llm.py`,
`intelligence/proactive_cadences.py`, `intelligence/ingestion/collection_engine.py`,
`intelligence/captains_brief.py`, `platform-runtime/human_systems_scheduler.py`,
`platform-runtime/commands/health_check.py`,
`platform-runtime/commands/recovery_pulse.py`,
`platform-runtime/commands/mission_lifecycle.py`,
`deploy/mission-registry-sync.service`, `deploy/mission-registry-sync.timer`,
and `core/infrastructure/supabase/migrations/0083_domain_registry_wellness_and_registry_sync.sql`.
Also referenced (title-only, "ADR-024 — ADR approval workflow (Captain
sign-off)" / "ADR-024-Deprecation-Protocol") in the stale, hand-maintained
`ArchitectureIndex.tsx`/`captainReview.ts` UI mock and a `temporal_entities`
ghost-table dump — both contradict the code-derived title above and are
**not** used as sourcing for this document; the code evidence is direct,
extensive, and internally consistent, so it is treated as authoritative over
those two placeholder/orphaned sources.
