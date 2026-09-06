# HQ Evolution

Retitled from "Self-Improvement Findings" (route unchanged: `/self-improvement-findings`).
Registry entry: `lcars-portal/src/lib/workbenches.ts`.

> HQ works on HQ while you're away. Overnight autonomy = discover, research,
> investigate, evaluate, prepare. Morning authority = yours.

## What changed

The original pipeline — `EvidenceCollector -> model analysis -> PolicyEngine
-> Finding -> human decision -> auto-remediation -> git commit -> tests ->
rollback on failure` — is preserved **unmodified** underneath. It now lives
inside the "Improve" tab's "Bounded remediation queue" section, using the
exact same API routes (`/api/self-improvement/findings`, `/api/self-
improvement/decide`) it always has.

Added around it: an **Opportunity** model that generalises a "finding" to
also cover external discoveries (repos, models, concepts) and internal
capability/product/architecture ideas that are not bounded remediations —
see `scripts/self_improvement/opportunity_store.py`.

```
OBSERVE
  -> INTERNAL VALIDATION      (state_validation.py — is each watchlist
                                gap_hypothesis still true? checked against
                                real repo evidence BEFORE spending any
                                external-research budget on it)
  -> DISCOVER (internal + external, external only for still-active topics)
  -> RELEVANCE GATE + DEDUP   (relevance.py)
  -> SHORTLIST                (bounded, config/self_improvement_policy.json "evolution")
  -> INVESTIGATE              (evolution_orchestrator.py + Model Router's
                                hq-evolution-investigate task, schema-
                                validated output, honest template fallback
                                if the model is unreachable)
  -> PREPARE opportunity      (opportunity_store.py)
  -> HUMAN DECISION           (dashboard.py /api/opportunity/decide)
  -> bounded remediation (existing engine) OR Mission handoff (/api/missions)
  -> VERIFY -> OUTCOME -> LEARN
```

A resolved gap_hypothesis (its underlying problem no longer exists) never
reaches external discovery at all — it's recorded as
`resolved_before_research` with its validation evidence, and the historical
hypothesis is retained rather than deleted (spec sections 11-17).

## New files

| File | Purpose |
|---|---|
| `scripts/self_improvement/opportunity_store.py` | Opportunity schema + append-only JSONL store (`data/self-improvement/review/opportunities.jsonl`), fingerprint dedup |
| `scripts/self_improvement/relevance.py` | Deterministic relevance scoring + dedup gate — LLM opinion never controls permission |
| `scripts/self_improvement/internal_discovery.py` | Maps existing classified findings + a few evidence-derived candidates into opportunities |
| `scripts/self_improvement/external_discovery.py` | Bounded GitHub-based discovery driven by `config/evolution_watchlist.json` |
| `scripts/self_improvement/evolution_orchestrator.py` | The overnight cycle entry point (`--dry-run` supported) |
| `scripts/self_improvement/migration.py` | One-time, idempotent migration of the latest legacy run's findings/decisions into opportunities |
| `scripts/self_improvement/state_validation.py` | Follow-up: deterministic current-state validation of watchlist `gap_hypothesis`es before external research |
| `scripts/self_improvement/investigation_schema.py` | Follow-up: schema-validates model investigation output; honest template fallback |
| `config/evolution_watchlist.json` | HQ-aware external discovery topics — `gap_hypothesis` (a hypothesis, not a fact) + `why_relevant` + an optional deterministic `validation` block |
| `lcars-portal/src/app/self-improvement-findings/page.tsx` | Discover / Investigate / Improve / Learned UI |
| `deploy/hq-evolution.service` / `.timer` | Follow-up: the actual overnight systemd timer, 03:00 Australia/Melbourne |
| `core/infrastructure/supabase/migrations/0191_domain_registry_hq_evolution_cycle.sql` | Follow-up: registers `hq_evolution_cycle` so its heartbeats don't 409 |

`scripts/self_improvement/dashboard.py` gained `/api/opportunities`,
`/api/opportunity/<id>`, `/api/opportunity/decide`, `/api/evolution-summary`
— additive; every pre-existing route is untouched.

`core/model-router/app.py` gained the `hq-evolution-investigate` task type
(`TASK_POLICY` + `route_map`, same Gemini/`GEMINI_API_KEY` convention as the
other `self-improvement-*` tasks, 300s timeout) — the real model-assisted
investigation step, not just a client-side stub.

## Running it

```
# Overnight cycle (internal + external discovery, bounded — see the
# "evolution" section of config/self_improvement_policy.json for the bounds)
python3 scripts/self_improvement/evolution_orchestrator.py --dry-run   # no writes, no network, no lock
python3 scripts/self_improvement/evolution_orchestrator.py             # real cycle

# One-time migration of the existing findings/decisions history
python3 scripts/self_improvement/migration.py
```

Scheduling: `deploy/hq-evolution.timer` runs this daily at 03:00 Australia/
Melbourne — the quiet window between `brief_qa_agent_nightly` (02:00,
LLM-heavy) and `downdetector_threshold_recompute` (05:00), well clear of
the 06:00+ morning-collection jobs and the 07:00 morning-brief /
`self-improving-system.timer` pair (see the timer file's own comment for
the full audited timeline from `intelligence/scheduler.py`). Overlapping
runs are prevented by a non-blocking `flock` inside
`evolution_orchestrator.py` itself (auto-released if the process crashes —
no stale-lock cleanup needed), not by systemd.

## Phase 0 audit — capability classification

| Capability | Status | Notes |
|---|---|---|
| EvidenceCollector, PolicyEngine, decisions.jsonl, rollback, dry-run | READY | Unmodified, reused directly |
| Retitle + Discover/Investigate/Improve/Learned IA | READY | This change |
| Additive opportunity data model | READY | This change |
| Internal discovery from existing findings | READY | This change |
| Deterministic relevance gate + dedup + rejection/watch history | READY | This change |
| External discovery (GitHub, bounded, HQ-aware) | READY | This change — public API, no token required at these bounds |
| Mission handoff for capability/product/architecture | READY | Reuses the existing canonical `POST /api/missions` |
| Captain's Chair morning signal | READY | This change — one Needs You item, not the full dashboard |
| Migration of existing findings/decisions | READY | This change — scoped to the latest run + its decisions (see migration.py's own docstring for why not the full cross-run history) |
| Overnight scheduler wiring (systemd timer) | READY | Follow-up mission — `deploy/hq-evolution.timer`, audited against `intelligence/scheduler.py`'s real job timeline, domain registered in migration 0191 |
| Model-assisted investigation narrative | READY | Follow-up mission — real `hq-evolution-investigate` Model Router task, schema-validated output (`investigation_schema.py`), honest fallback wording when the model is unreachable |
| Current-state validation of watchlist hypotheses | READY | Follow-up mission — `state_validation.py`; a `gap_hypothesis` that no longer holds is recorded `resolved_before_research` and never reaches external discovery. Duplicate-synthesis regression test (`tests/test_hq_evolution_followup.py`) validates this against the real repo: `telegram-bots/xo/app.py` already renders the canonical `intelligence_briefs` row for `/brief` rather than re-synthesising it, so that watchlist topic correctly resolves and is suppressed |
| Cross-workbench outcome learning (Briefs/Advisory/Weekly Review as evidence inputs) | FUTURE | Spec section 12 explicitly scopes this incrementally; not built this pass |
| Learning-feedback-adjusted prioritisation | FUTURE | relevance.py's scoring is static; feeding outcome history back into it is a natural next increment |
| LifeOS Hub summary consumer | FUTURE | No LifeOS Hub exists yet to consume `/api/evolution-summary` |
| MCP-integration / local-inference-cost-review watchlist topics | FUTURE (validation) | No honest deterministic check exists yet for these two topics specifically — they validate as `unclear` and proceed cautiously rather than being marked confirmed/resolved on a guess |

## Governance notes

- `MISSION_ONLY_CLASSES` (`opportunity_store.py`) and the `manual_only`
  categories in `config/self_improvement_policy.json` must agree — enforced
  by `tests/test_hq_evolution.py::TestOpportunityStore::test_mission_only_classes_match_policy_manual_only`.
- The API refuses `approve_improvement` for a Mission-only change class
  server-side (`dashboard.py`), not just in the UI — covered by
  `tests/test_hq_evolution_followup.py::TestMissionOnlyServerSideEnforcement`.
- External discovery degrades to an empty result on any network failure —
  it never blocks or fails the overnight cycle (confirmed live: this repo's
  sandboxed test environment gets a real `403 Forbidden` from the GitHub
  API and the cycle completes normally regardless).
- `evolution_orchestrator.py --dry-run` performs zero writes, zero network
  calls, and never takes the overlap-prevention lock — verified in both
  `tests/test_hq_evolution.py` and `tests/test_hq_evolution_followup.py`.
- The model's `recommendation` field is advisory only: `classify_finding()`
  (PolicyEngine) never reads the `investigation` dict at all, so no
  recommendation value can change `automation_eligibility` — regression-
  tested across every allowed recommendation value in
  `TestResearchOrderAndBounds::test_llm_recommendation_never_changes_automation_eligibility`.
- Overnight Evolution never writes to `config/self_improvement_policy.json`
  or `config/evolution_watchlist.json` — it only ever reads them and writes
  to `data/self-improvement/review/opportunities.jsonl` and
  `evolution_summary.json`.
