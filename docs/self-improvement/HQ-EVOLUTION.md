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
OBSERVE/DISCOVER (internal + external)
  -> RELEVANCE GATE + DEDUP   (relevance.py)
  -> SHORTLIST                (bounded, config/self_improvement_policy.json "evolution")
  -> INVESTIGATE              (evolution_orchestrator.py, LLM-assisted, evidence-only)
  -> PREPARE opportunity      (opportunity_store.py)
  -> HUMAN DECISION           (dashboard.py /api/opportunity/decide)
  -> bounded remediation (existing engine) OR Mission handoff (/api/missions)
  -> VERIFY -> OUTCOME -> LEARN
```

## New files

| File | Purpose |
|---|---|
| `scripts/self_improvement/opportunity_store.py` | Opportunity schema + append-only JSONL store (`data/self-improvement/review/opportunities.jsonl`), fingerprint dedup |
| `scripts/self_improvement/relevance.py` | Deterministic relevance scoring + dedup gate — LLM opinion never controls permission |
| `scripts/self_improvement/internal_discovery.py` | Maps existing classified findings + a few evidence-derived candidates into opportunities |
| `scripts/self_improvement/external_discovery.py` | Bounded GitHub-based discovery driven by `config/evolution_watchlist.json` |
| `scripts/self_improvement/evolution_orchestrator.py` | The overnight cycle entry point (`--dry-run` supported) |
| `scripts/self_improvement/migration.py` | One-time, idempotent migration of the latest legacy run's findings/decisions into opportunities |
| `config/evolution_watchlist.json` | HQ-aware external discovery topics, each with a `why_relevant` |
| `lcars-portal/src/app/self-improvement-findings/page.tsx` | Discover / Investigate / Improve / Learned UI |

`scripts/self_improvement/dashboard.py` gained `/api/opportunities`,
`/api/opportunity/<id>`, `/api/opportunity/decide`, `/api/evolution-summary`
— additive; every pre-existing route is untouched.

## Running it

```
# Overnight cycle (internal + external discovery, bounded — see the
# "evolution" section of config/self_improvement_policy.json for the bounds)
python3 scripts/self_improvement/evolution_orchestrator.py --dry-run   # no writes, no network
python3 scripts/self_improvement/evolution_orchestrator.py             # real cycle

# One-time migration of the existing findings/decisions history
python3 scripts/self_improvement/migration.py
```

Scheduling: this is a separate script from `orchestrator.py` (the existing
daily self-improvement cycle) and does not touch its systemd timer. Wiring
an actual overnight timer for `evolution_orchestrator.py` is a **FUTURE**
step — see below — pending an audit of the existing quiet-period schedule
this mission's spec called for but which this pass didn't reach.

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
| Model-assisted investigation narrative | DERIVABLE | `ModelRouterClient.investigate_opportunity()` added; needs a live `/api/model/hq-evolution-investigate` route on the Model Router side to actually synthesize (falls back to a deterministic template today) |
| Overnight scheduler wiring (systemd timer) | NEEDS SMALL UPLIFT | Script exists and is bounded; needs an actual timer unit audited against existing quiet-period jobs (spec section 13) |
| Cross-workbench outcome learning (Briefs/Advisory/Weekly Review as evidence inputs) | FUTURE | Spec section 12 explicitly scopes this incrementally; not built this pass |
| Learning-feedback-adjusted prioritisation (section 29) | FUTURE | relevance.py's scoring is static; feeding outcome history back into it is a natural next increment |
| LifeOS Hub summary consumer | FUTURE | No LifeOS Hub exists yet to consume `/api/evolution-summary` |

## Governance notes

- `MISSION_ONLY_CLASSES` (`opportunity_store.py`) and the `manual_only`
  categories in `config/self_improvement_policy.json` must agree — enforced
  by `tests/test_hq_evolution.py::TestOpportunityStore::test_mission_only_classes_match_policy_manual_only`.
- The API refuses `approve_improvement` for a Mission-only change class
  server-side (`dashboard.py`), not just in the UI.
- External discovery degrades to an empty result on any network failure —
  it never blocks or fails the overnight cycle.
- `evolution_orchestrator.py --dry-run` performs zero writes and zero
  network calls — verified in `tests/test_hq_evolution.py`.
