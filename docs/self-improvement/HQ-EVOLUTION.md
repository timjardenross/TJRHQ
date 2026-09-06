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
| `core/infrastructure/supabase/migrations/0192_domain_registry_hq_evolution_cycle.sql` | Follow-up: registers `hq_evolution_cycle` so its heartbeats don't 409 |

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
| Overnight scheduler wiring (systemd timer) | READY | Follow-up mission — `deploy/hq-evolution.timer`, audited against `intelligence/scheduler.py`'s real job timeline, domain registered in migration 0192 |
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

## V2 — Outcome Learning & Evidence Feedback

### What V2 adds

V1 closes the loop up to "a human decided, and the change was implemented."
It never asked whether the change actually delivered what it was approved
for — implementation success and improvement success are different claims,
and V1 only ever measured the first. V2 adds the rest of the loop: observe
what actually happened after a change lands, evaluate it honestly against
what was expected, record the verdict as `learned`, and feed that
experience back in as context for future investigations of similar
opportunities. It never feeds back as automation authority — see
Governance notes below.

### Outcome Contract

Built once, at approval time — `dashboard.py` calls
`outcome_contract.build_outcome_contract(opportunity, repo_root)` inside
the `approve_improvement` and `create_mission` decision handlers — and
never rebuilt afterward, so it stays a fixed target to evaluate against
rather than a moving one. Stored on the opportunity as `outcome_contract`:

| Field | Shape |
|---|---|
| `expected_benefit` | str — from the investigation's `potential_benefits`, falling back to `why_relevant`/`summary` |
| `measurement_type` | `quantitative` \| `deterministic` \| `qualitative` \| `mixed` \| `unknown` — defaulted per `change_class` |
| `baseline` | `{available, value, description, provenance, captured_at}`, or `{available: False, reason}` when no honest baseline exists — **never fabricated** |
| `success_signal` / `regression_signal` | human-readable; `regression_signal` is the no-self-reward-loop guardrail |
| `observation_window` | `{type, count}` — event/cycle-based, not elapsed-days |
| `evidence_sources` | which `evidence_sources.py` reader(s) apply |
| `evaluation_status` | `pending_implementation` \| `observing` \| `ready_to_evaluate` \| `evaluated` |
| `observation_started_at` | iso \| `None`, set once implementation is confirmed |

Baseline capture (`outcome_contract._capture_baseline`) is honest by
construction: a candidate carrying a `measurement_hint` gets a real reading
via `evidence_sources.read_measurement`; a `deterministic`-class candidate
with no hint falls back to its own discovery-time `provenance` as the
baseline description; everything else — including `quantitative`-class
candidates with no `measurement_hint` — records
`{available: False, reason: ...}` rather than guessing.

The four per-`change_class` defaults (`outcome_contract.py`):

| change_class | measurement_type | observation_window | example regression guardrail |
|---|---|---|---|
| maintenance | deterministic | immediate (1) | The removed/changed file or config is referenced elsewhere and something now fails to load |
| configuration | deterministic | immediate (1) | A consumer of the changed configuration now fails or behaves unexpectedly |
| reliability | quantitative | 5 cycles | The affected job's failure rate increases, or it stops running/heartbeating entirely |
| cost_optimisation | quantitative | 7 cycles | A call-count drop caused by suppressing real work is a regression, not a saving |
| capability | mixed | 7 cycles | The new capability introduces a new failure mode, security gap, or measurably worse behaviour |
| product_improvement | mixed | 7 cycles | The targeted surface's assessed behaviour gets measurably worse, not just different |
| architecture | mixed | 14 cycles | The replaced/restructured subsystem's dependents fail, regress in latency/reliability, or lose a capability they relied on |

"Cycles" means completed HQ Evolution overnight cycles specifically (the
unit `evolution_orchestrator.py`'s `run_cycle()` advances once per real
invocation) — available everywhere, unlike a domain-specific job cadence a
generic contract-builder has no way to know per-opportunity.

### Implementation confirmation

An opportunity moves from `approved` to `implementing`/`verifying` only
once implementation is actually confirmed, via one of three signals
(`outcome_evaluation.check_implementation_status`):

1. Legacy bounded-remediation success in `remediation_results.jsonl`,
   keyed by `source_finding_id`.
2. A Mission reaching one of `evidence_sources.MISSION_IMPLEMENTED_STATUSES`
   (`Implemented`, `Tested`, `Validated`), keyed by `mission_id`.
3. A human manually asserting implementation via the `mark_implemented`
   decision type (`dashboard.py`'s `DECISION_TRANSITIONS`), which starts
   the observation window immediately rather than waiting for the next
   overnight cycle to detect it.

Be honest about why (3) matters: most Evolution-discovered
`cost_optimisation`/`reliability` opportunities that are not linked to a
legacy finding or a Mission currently have **no automated execution path
at all** — nothing in this codebase implements them on their own.
`mark_implemented` is the load-bearing gap-closer for that class of
opportunity. This is a known V1 gap; V2 closes it gracefully by giving a
human a way to say "I did this by hand, start watching it" rather than by
building new remediation automation, which was explicitly out of scope
for this pass.

### Evaluation engine

`outcome_evaluation.evaluate_outcome` is deterministic-first and never
raises — a bug in this engine, or evidence that simply isn't there, must
degrade to an honest `inconclusive`/`not_yet_ready` result, never crash
the overnight cycle and never fabricate a favourable verdict:

- **Deterministic comparison** (`evaluate_deterministic`) runs whenever a
  real numeric baseline and a real numeric current reading both exist —
  in practice, whenever a `measurement_hint` was captured at discovery
  time. It compares relative change against a 20%-default materiality
  threshold (`material_change_threshold=0.20`) to classify
  `improved`/`regressed`/`no_material_change`, with no model call needed.
- **Concurrent-change detection** (`detect_concurrent_changes`) checks
  whether another opportunity of the *same* `change_class` was
  implementing/verifying/landed during this opportunity's observation
  window. If so, the evaluation is **forced** to `inconclusive` regardless
  of what the deterministic or model path found — attribution is never
  asserted as clean when it might be confounded, though the underlying
  finding stays visible in `evidence_summary` for transparency.
- **Model-assisted synthesis** is the fallback, used only for
  `qualitative`/`mixed` measurement types where real evidence exists to
  interpret — via the new `hq-evolution-evaluate-outcome` Model Router
  task, with output schema-validated by `outcome_schema.validate_outcome_evaluation`
  (an unparseable or missing `outcome_result` degrades to `inconclusive`,
  never `improved`).
- **Honest degradation**: when the Model Router is unreachable, or there's
  no quantitative evidence and no qualitative content to interpret,
  evaluation degrades to `outcome_schema.honest_fallback_outcome_evaluation`
  — `inconclusive`, low confidence, and a stated reason — never a
  fabricated verdict.
- **Provenance retention**: every evaluation keeps `evidence_detail`
  (the current measurement plus the contract's baseline) for later
  inspection, not just the verdict.
- **`evaluation_history` retention**: a re-evaluation appends to
  `outcome.evaluation_history` rather than overwriting the prior verdict —
  nothing about a past evaluation is silently erased.

`not_yet_ready` is not a lifecycle_state — it's a calm, real
`evaluation_status`/`outcome_result` meaning the observation window hasn't
elapsed yet; the opportunity simply stays `verifying`.

### Evolution memory

Before investigating a new candidate, `evolution_memory.find_related_outcomes`
retrieves up to 3 relevant prior opportunities sharing the candidate's
`change_class` and meaningful keyword overlap (deterministic word-set
intersection, `_MIN_SHARED_WORDS = 2`, plus a near-duplicate-title
fallback check) — pure stdlib, no embeddings, no model call for retrieval
itself. `format_related_experience` renders that list as one short
natural-language string, injected as extra context into the investigation
model call and shown in the UI's "Related HQ Experience" section.

`learned` outcomes, `rejected` decisions, and `watching` items are always
described as distinct relationship types, never merged into one score:
`outcome_result`/`confidence`/`evidence_summary` come only from `learned`
records (system evidence — an observed technical result); `rejection_reason`
comes only from `rejected` records (a human decision that may have nothing
to do with whether the underlying technical proposition was true — cost,
timing, priorities, taste); `watch_reason` comes only from `watching`
records. The module never computes or states one aggregate confidence
number across multiple prior items, and a rejection never borrows the
vocabulary ("regressed", "confidence: high") that belongs to an observed
outcome.

### New files

| File | Purpose |
|---|---|
| `scripts/self_improvement/outcome_contract.py` | Builds the Outcome Contract once, at approval time — measurement type, baseline, success/regression signal, observation window per `change_class` |
| `scripts/self_improvement/evidence_sources.py` | Thin, read-only evidence readers (call log stats, domain heartbeats, mission status, file size) — always degrade to `{available: False, reason}`, never fabricate |
| `scripts/self_improvement/outcome_schema.py` | Schema-validates model outcome-evaluation output; honest `inconclusive` fallback, never a favourable default |
| `scripts/self_improvement/outcome_evaluation.py` | The evaluation engine — implementation confirmation, observation-window gating, concurrent-change/attribution-risk detection, deterministic-then-model evaluation |
| `scripts/self_improvement/evolution_memory.py` | Deterministic keyword-based retrieval of related prior opportunities for investigation context — keeps outcomes/rejections/watches distinct |

### Model Router addition

`core/model-router/app.py` gained the `hq-evolution-evaluate-outcome` task
type (`TASK_POLICY` + `route_map`, same Gemini/`GEMINI_API_KEY` convention
and 300s timeout as `hq-evolution-investigate`). Input is a bounded
evidence bundle (outcome contract + baseline + collected evidence), not a
re-run of the original investigation.

### Phase 0 V2 audit — capability classification

| Capability | Status | Notes |
|---|---|---|
| Outcome Contract construction | READY | This change — built once at approval time, honest-baseline-or-explicit-gap |
| Deterministic evaluation for `measurement_hint`-tagged candidates | READY | This change — 20%-default materiality threshold, no model call needed |
| Model-assisted qualitative evaluation | READY | This change — `hq-evolution-evaluate-outcome`, schema-validated, honest template fallback |
| Evolution memory retrieval | READY | This change — deterministic keyword overlap, no embeddings, no model call |
| Concurrent-change / attribution-risk detection | READY | This change — forces `inconclusive` rather than asserting a confounded verdict |
| Per-opportunity `domain_key`/`task_type` tagging for more candidates to get real quantitative baselines | NEEDS SMALL UPLIFT | The only concrete `measurement_hint` currently wired by any discovery path is the Model Router call-log-size candidate in `internal_discovery.py` (`{"type": "file_size_mb", "path": "core/model-router/call_log.jsonl"}`); every other `quantitative`-class candidate with no hint records an honest "no baseline available" rather than a real number. This is the main current limitation of the evaluation engine, not a design gap — the machinery is ready, the candidates aren't tagged yet. |
| Automated bounded-remediation execution for newly-discovered (non-legacy-finding) `cost_optimisation`/`reliability` opportunities | FUTURE | Out of scope for this pass; `mark_implemented` is the interim human-asserted bridge |
| Cross-workbench evidence beyond Model Router / domain_heartbeats / missions (Briefs, Ready Room, Advisory, Weekly Review, Human Systems) | FUTURE | Per the mission's own explicit non-goals |
| Sophisticated causal inference / A/B testing / experimentation platform | FUTURE | Explicitly out of scope |

### Governance notes (V2 additions)

- Learning may change the *evidence, rationale, or confidence* a future
  investigation is given (via `evolution_memory`) — it never changes
  PolicyEngine output, `automation_eligibility`, Mission-only
  classification, or any permission state. `outcome_evaluation.py` never
  calls `OpportunityStore.update()` itself and never touches PolicyEngine;
  the caller (`evolution_orchestrator.py`) decides what, if anything, to
  persist from the dict it returns.
- A prior `improved` outcome cannot auto-approve a similar future
  opportunity — it still requires its own human decision. Related
  experience is contextual input to the investigation, not a bypass of it.
- Human Systems evidence (capacity, pain, burnout, sleep, stimulation
  metrics) is **not** used anywhere in this V2 evidence set. This is an
  explicit boundary, not an oversight: technical HQ changes are evaluated
  on technical evidence (`evidence_sources.py`'s three readers plus local
  file checks), not human-capacity metrics — see the FUTURE row above.
