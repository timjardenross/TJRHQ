---
status: "accepted"
date: 2026-09-19
decision-makers: {Chief Engineer}
consulted: {unknown — reconstructed from code, not from a governance-log entry}
informed: {Captain}
---

# Captain Brief Convergence Review: three pipelines stay separate — canonical base, reasoning layer, narrative producer

## Context and Problem Statement

`knowledge/SUOC-Platform-Registry.md`'s "Continuous Captain Brief
Orchestration" record has carried an open action since 2026-07-08 (first
raised MSN-0342/0343): **"Formal Captain Brief Convergence review
(MSN-0342/0343) vs. `captains_brief.py`/`captain_brief_evolution.py`"** —
a request to either formally document three "Captain Brief" pipelines as
one coherent architecture, or converge them, rather than leaving them as
three independently-tracked capabilities that read as unreconciled
duplication.

A separate, already-completed mission
(`BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md`) did the *UI-consolidation* half
of this ask: it retired the competing `/captains-brief-workbench` frontend,
made `/briefs`'s Domains tab the single canonical cross-domain briefing
surface, and fixed real signal-leakage bugs along the way. That mission's
own §1 explicitly named this remaining half as unrelated to its scope:
"the joint-documentation half — formally documenting this module /
`captain_brief_evolution.py` / `intelligence/captains_brief.py` as one
architecture — stays open." This ADR is that remaining half.

The three systems in question, read from their actual code (not from the
Registry's or the mission doc's prior descriptions of them):

1. **System A — `core/platform/captain_brief_orchestrator.py`**
   (`CaptainBriefDocument`, `assemble_captain_brief_document()`), plus its
   three real dependencies: `attention_engine.py` (`evaluate_batch()` /
   `evaluate_event()`, the six-category Cognitive Model routing table),
   `priority_engine.py` (`rank_events()` / `score_event()`, comparative
   0-100 scoring across urgency/importance/time-sensitivity/value/risk/
   opportunity), and `captain_brief_contract.py` (`CaptainBriefItem`,
   `Recommendation`, `assemble_captain_brief()`). Pure functions only — no
   I/O beyond the caller having already run `event_bus.poll_events()`, a
   contract the orchestrator's own module docstring states explicitly and
   that `captain_brief_evolution.py`'s docstring (see System B) says by
   name is why it exists as a separate module rather than an edit to this
   one.

2. **System B — `core/platform/captain_brief_evolution.py`**
   (`assemble_evolved_captain_brief()`), plus `understanding_engine.py`
   (`build_understanding()` — deterministic, evidence-bound relationship/
   conflict detection: `shared_mission`, `temporal_sequence`, and
   `aggregation` relationship kinds, each traceable to a real
   `linked_missions` reference, a real `occurred_at` ordering, or the
   Attention Engine's own `SHOULD_BE_AGGREGATED` grouping — reused, not
   re-derived), `insight_engine.py` (`generate_insights()` — sends only
   already-deterministically-verified relationships/conflicts, capped at
   `DEFAULT_MAX_CANDIDATES = 3`, to the Model Router's
   `captain-insight-synthesis` task, strictly evidence-bound prompts,
   rejects rather than fabricates on a malformed response), and
   `reasoning_engine.py` (`build_recommendation()` — converts one Insight
   into a structured `Recommendation` via `captain-reasoning-synthesis`,
   then nudges `confidence` from real recorded outcomes in
   `insight_outcomes`, never from the model's own self-assessment).

3. **System C — `intelligence/captains_brief.py`** (`generate_morning_
   brief()`, `generate_midday_update()`, `generate_eod_summary()`,
   `generate_weekly_report()`) — a Telegram-formatted digest generator.
   Reads the canonical OSINT view deterministically from
   `intelligence/brief/render.py` (no re-synthesis, per
   `BRIEFS_CANONICAL_UPLIFT.md`), health capacity
   (`capacity_checkins_today`), an infra-verification narrative
   (`core/platform/infra_narrative.py`, ADR-024 fix #5), and — critically —
   the platform's own multi-domain events via
   `intelligence/brief/daily_digest.py::build_daily_digest()`, which
   itself calls **System A's `assemble_captain_brief_document()` directly**
   for the health/engineering/learning/opportunities/operational-
   intelligence sections, then feeds that through its own separate LLM
   narration call (`intelligence/brief/llm_provider.py`, built on
   `core/llm/provider_chain.py`, ADR-024's consolidated Gemini/Mistral/
   Ollama primitives). Output is plain narrative text, persisted to
   `captains_daily_briefs` (`_persist_brief()`), consumed by Telegram push
   and by Captain's Chair's `TodaysBriefPanel.tsx` (a read-only render of
   the persisted text, via `/api/captains-daily-brief`).

**Real, verified consumers today** (not design-only claims):

- System A: `intelligence/brief/domains_view.py::assemble_domains_document()`
  (Briefs' Domains tab, the mission's own canonical merged view);
  `intelligence/scheduler.py::_attention_evaluation_job` (every 10 minutes,
  `continuous_attention_evaluation` — uses only the `AttentionDecision`
  output, not the full document); System B and System C, both of which
  call into it directly rather than reimplementing it (see above).
- System B: LCARS Captain's Chair's `CaptainIntelligencePanel.tsx` → `POST
  /api/captain-intelligence/generate` → `core/context-assembly/
  context_service.py`'s `POST /brief/evolved` →
  `assemble_evolved_captain_brief()` (manual "Generate New Insights"
  trigger, 50-260s real Model Router latency); and
  `intelligence/scheduler.py::_evolved_insight_generation_job` (every
  `CAPTAIN_INSIGHT_INTERVAL_MINUTES`, default 240 = 4x/day — added because
  the manual button alone left `insight_outcomes` at 3 rows after weeks);
  `core/platform/captain_brief_cli.py --evolved`.
- System C: `intelligence/scheduler.py`'s `send_brief`/
  `check_midday_signals` cron jobs (morning/midday/eod/weekly, Telegram);
  `captains_daily_briefs` → `TodaysBriefPanel.tsx` on Captain's Chair.

The Registry's own dashboard framed this as "Architectural Debt (3
unreconciled pipelines)" before this review. The decision this ADR needs
to record: is that framing accurate — should these converge further — or
does the actual code already show a defensible, deliberate separation
that should simply be documented as such?

## Decision Drivers

* System A's own contract ("no I/O beyond `event_bus.poll_events()`") is
  load-bearing for a real, live, 10-minute-cadence scheduled caller
  (`_attention_evaluation_job`). Any change that gives System A's own
  module real network I/O would regress that caller's latency profile.
* System B needs real HTTP round-trips to the Model Router (observed
  50-260s per synthesis call, MSN-0329 Phase 3) to do a job System A's
  deterministic threshold/scoring logic structurally cannot do — explain
  *why* a cross-domain relationship matters and *what* a Captain could
  do about it, in prose reasoned over real evidence.
  `captain_brief_evolution.py`'s own docstring names this exact reason for
  being a separate module: keeping System A's "no I/O" guarantee intact
  for its existing callers (LCARS, Slack) who are "completely unaffected
  by this module's existence."
* System B degrades gracefully to *exactly* System A's own output when the
  Model Router is unreachable ("the returned document is then IDENTICAL to
  calling `assemble_captain_brief_document()` directly, never a
  partially-broken one" — the module's own docstring). That guarantee only
  holds because B wraps A rather than being fused into it.
  Confidence-adjustment for LLM output uses `insight_outcomes` evidence
  (`_MIN_OUTCOMES_FOR_ADJUSTMENT = 3`, same discipline as
  `mission_knowledge_store.get_intelligence_evidence()`) — never treats a
  handful of rows as proof.
* System C serves a structurally different audience and product shape: a
  Telegram-formatted text digest plus a historical `captains_daily_briefs`
  row, blending OSINT/geopolitical content (out of System A's domain
  entirely) with platform events — and it already reuses System A's
  assembly function directly for the platform-events slice rather than
  re-deriving routing/priority logic, so the actual code contradicts a
  "three independent, duplicated implementations" reading.
* A prior architecture sweep (`BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md` §1)
  already found the platform's "two workbenches" framing understated the
  real landscape (five systems share the "Captain Brief" name, not two) —
  the same discipline applies here: read the real code before assuming
  either "fine as three" or "should be one" is correct.
* A genuine, disclosed inefficiency exists and should be named honestly
  rather than hidden: `evaluate_batch()` runs twice per System B call (once
  inside `assemble_captain_brief_document()`, again inside
  `build_understanding()`) — both calls are pure and deterministic, so this
  is wasted CPU, not a correctness risk, and `captain_brief_evolution.py`'s
  own docstring already discloses it as "left as-is rather than refactoring
  the orchestrator's internals, which would carry more regression risk than
  the inefficiency it removes."
* A second, separate finding surfaced by this review (not previously
  registry-tracked): System B's LLM calls (`captain-insight-synthesis`,
  `captain-reasoning-synthesis`) route through the Model Router's
  `_gemini_generate()` and are therefore covered by ADR-032's LLM
  guardrails layer. System C's narrative call
  (`intelligence/brief/llm_provider.py`) prefers the Model Router's
  `intelligence-brief` task first (also guardrail-covered) but falls
  through, on Model Router unavailability, to `core/llm/provider_chain.py`'s
  direct `call_gemini`/`call_mistral`/`call_ollama` primitives — a
  call path ADR-032's Gaps section does not list as wrapped. This is real,
  disclosed architectural debt adjacent to this review, not evidence the
  three brief pipelines themselves should merge.

## Considered Options

* Leave the three systems as independently-tracked Registry capabilities
  with no joint documentation (the status quo this ADR was opened
  against).
* Merge all three into one module/pipeline.
* Fold System B (Understanding/Insight/Reasoning) directly into System A's
  orchestrator module.
* Fold System C's platform-domain narration into System A/B and have
  Telegram consume `CaptainBriefDocument` directly, dropping
  `daily_digest.py`'s and `captains_brief.py`'s own text assembly.
* Formally document the three as one layered architecture — canonical
  base (A), reasoning/enrichment layer built on top of A for Captain's
  Chair (B), and a separate narrative producer for a different channel
  that reuses A rather than duplicating it (C) — with no code change, and
  name the real, disclosed follow-ups (the guardrail-coverage gap above,
  the `evaluate_batch()` double-call) as their own separately-tracked
  items rather than folding them into a forced merge.

## Decision Outcome

Chosen option: **"Formally document the three as one layered
architecture,"** because it is the only option that matches what the code
actually does, rather than what the Registry's "3 unreconciled pipelines"
label assumed before this review read it closely.

The architecture, stated plainly:

```
core_events (Event Bus)
        │  poll_events()
        ▼
System A — captain_brief_orchestrator.py (+ attention_engine.py,
           priority_engine.py, captain_brief_contract.py)
           Pure, deterministic, no I/O. THE canonical assembly:
           CaptainBriefDocument.
        │
        ├──────────────► System B — captain_brief_evolution.py (+
        │                 understanding_engine.py, insight_engine.py,
        │                 reasoning_engine.py). Wraps A's document,
        │                 adds real Model Router I/O for cross-domain
        │                 reasoning ("why it matters" / "what to do").
        │                 Consumer: LCARS Captain's Chair.
        │
        └──────────────► System C — intelligence/captains_brief.py (+
                          daily_digest.py, calling A directly for its
                          platform-events section). Blends A's platform
                          output with OSINT/health/infra content into a
                          Telegram-formatted narrative digest.
                          Consumer: Telegram push, Captain's Chair's
                          TodaysBriefPanel (passive render of persisted
                          text).
```

System A is the canonical base every other Captain-facing "what does the
Captain need to know" surface should compose, not reimplement — and, per
the consumer evidence in Context above, every real surface today already
does exactly that. System B is a legitimate second layer, not a competing
implementation: it exists specifically to give System A's synchronous,
deterministic callers (the 10-minute scheduled attention-evaluation job
chief among them) continued freedom from Model Router latency, while still
letting a slower, LLM-reasoned enrichment reach Captain's Chair through its
own module and its own schedule. System C is a legitimate third producer:
a different channel (Telegram), a different content mix (OSINT +
capacity + infra + platform events), and a different output shape (prose
text + a historical row, not a structured document) — and it already
reuses System A's assembly function directly for the one section where
their domains overlap (platform events), which is the correct pattern, not
the anti-pattern the "3 unreconciled pipelines" framing implied.

No further code-level convergence is recommended by this review. Merging
B into A would force System A's existing pure/fast callers to either
accept LLM latency they don't need or fork into two code paths inside one
module — worse, not better, than today's two-module split. Merging C into
A/B would collapse a genuinely different audience (a solo Captain's
Telegram feed, cron-scheduled, historically archived) into a document
shape built for a live UI panel, for no real simplification — System C
already avoids duplicating A's logic where it matters.

### Consequences

* Good, because System A keeps its "no I/O beyond `poll_events()`"
  contract intact for its real 10-minute-cadence scheduled caller — no
  regression risk introduced by this ADR to the platform's
  fastest-running Captain Brief consumer.
* Good, because System B's graceful-degradation guarantee (identical
  output to System A alone when the Model Router is unreachable) stays
  true — it depends on B remaining a wrapper around A, not a fusion with
  it.
* Good, because System C's existing reuse of System A (rather than a
  fourth reimplementation of domain routing/scoring) is now the
  documented, endorsed pattern for any future Captain-facing surface that
  needs A's platform-event content, closing off the temptation to build a
  fifth copy.
* Good, because the Registry's open "Formal Captain Brief Convergence
  review (MSN-0342/0343)" action can now be closed honestly — this ADR is
  a documentation artefact, not a promise of a future merge that was never
  actually warranted by the code.
* Bad, because three genuinely different scheduled/triggered cadences for
  related content still exist after this ADR (10-minute attention
  evaluation, a 4x/day evolved-insight job, and cron-scheduled Telegram
  briefs) — anyone auditing "when does the Captain get told X" still needs
  to know all three; this ADR documents that reality, it does not simplify
  it.
* Bad, because the guardrail-coverage gap this review surfaced (System C's
  `core/llm/provider_chain.py` fallback tiers are not confirmed wrapped by
  ADR-032's LLM guardrails layer, unlike System B's Model-Router-routed
  calls) remains open — flagged here, not fixed, consistent with how
  ADR-032 itself discloses gaps rather than silently deferring them.
* Neutral, because this ADR changes no code in `core/platform/*.py`,
  `intelligence/brief/*.py`, or `intelligence/captains_brief.py` — it is a
  documentation-only decision, matching the joint-documentation half of
  the Convergence Review this ADR closes (the code-level UI-consolidation
  half was already done by `BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md`).

### Confirmation

Grep `ADR-033` across the repo: today that should show exactly this file
plus one citation in `knowledge/SUOC-Platform-Registry.md`'s "Continuous
Captain Brief Orchestration" record (the Registry edit this ADR is paired
with). The layering claim itself is independently checkable without
trusting this document: `core/platform/captain_brief_evolution.py` imports
and calls `captain_brief_orchestrator.assemble_captain_brief_document()`
rather than reimplementing any of its routing/scoring logic, and
`intelligence/brief/daily_digest.py` does the same — both are `import`
statements, not duplicated function bodies, and remain the fitness check
for "these are layers, not reimplementations" going forward.

## Pros and Cons of the Options

### Leave as three independently-tracked capabilities, undocumented (rejected — the status quo this ADR was opened against)

* Good, because it requires no work.
* Bad, because it is exactly the ambiguity the Registry's own "3
  unreconciled pipelines" label created — a future reader (or agent) has
  no way to tell "this is deliberate layering" from "nobody has looked at
  this yet," and risks a well-intentioned future merge that breaks System
  A's I/O-free contract for no real gain.

### Merge all three into one module/pipeline (rejected)

* Bad, because it would force System A's fast, pure, 10-minute-cadence
  scheduled caller to either inherit 50-260s LLM latency or the merged
  module would need an internal fork back into "fast path" / "slow path"
  — reproducing today's two-module split, just inside one file, with more
  regression risk during the merge itself.
* Bad, because System C's OSINT/health/infra content has no natural home
  inside System A's `core_events`-only domain model — merging would force
  System A to either grow OSINT-awareness it doesn't need for its other
  callers, or System C to lose the OSINT/health/infra sections that are
  most of its actual value.

### Fold System B into System A's orchestrator module (rejected)

* Good, because it would remove one `import` hop and the disclosed
  double-`evaluate_batch()`-call inefficiency.
* Bad, because it directly contradicts `captain_brief_evolution.py`'s own
  documented reason for existing as a separate module — preserving
  System A's "no I/O" guarantee for its existing callers — and would make
  every one of System A's current callers newly exposed to Model Router
  reachability/latency as a hidden dependency.
* Bad, because System B's graceful-degradation guarantee (falls back to
  exactly System A's own output on Model Router failure) is easiest to
  keep correct specifically because B wraps A rather than replacing parts
  of it — a fused module would need to reproduce that fallback logic
  in-place rather than getting it for free via delegation.

### Fold System C's platform narration into System A/B, Telegram consumes `CaptainBriefDocument` directly (rejected)

* Good, because it would remove `daily_digest.py`'s separate LLM
  narration call, leaving one fewer LLM code path to keep consistent with
  ADR-032's guardrails.
* Bad, because System A/B produce a structured `CaptainBriefDocument` for
  a UI panel to render, not Telegram-HTML prose for a chat surface — a
  format Telegram delivery would still need to generate somewhere, so this
  doesn't remove the narration step, it only relocates it.
* Bad, because System C's morning/midday/eod/weekly cadence and its
  OSINT+health+infra+platform content blend have no equivalent in System
  A/B today — building that would be new work disguised as consolidation,
  not a real simplification of what exists.

### Formally document as one layered architecture, no code change (chosen)

See Decision Outcome above.

* Good, because it matches the real, already-correct reuse pattern the
  code shows (`captain_brief_evolution.py` and `daily_digest.py` both
  `import` and call System A rather than reimplementing it) instead of
  forcing a merge the code's own module boundaries argue against.
* Good, because it closes the Registry's open action without introducing
  new regression risk to a live, scheduled, 10-minute-cadence production
  path.
* Neutral, because it leaves the three-cadence reality (10-min / 4x-day /
  cron) exactly as complex as it already was — documented, not simplified.
* Bad, because it is easy to mistake "these should stay separate" for "no
  further work is needed here" — the guardrail-coverage gap and the
  double-`evaluate_batch()`-call inefficiency named in Decision Drivers
  are real and still open; this ADR records them as disclosed, tracked
  gaps, not as closed.

## More Information

Primary sources read for this ADR: `core/platform/captain_brief_
orchestrator.py`, `core/platform/attention_engine.py`,
`core/platform/priority_engine.py`, `core/platform/captain_brief_
contract.py`, `core/platform/captain_brief_evolution.py`,
`core/platform/understanding_engine.py`, `core/platform/insight_engine.py`,
`core/platform/reasoning_engine.py`, `intelligence/captains_brief.py`,
`intelligence/brief/daily_digest.py`, `intelligence/brief/llm_provider.py`,
`core/llm/provider_chain.py`, `core/context-assembly/context_service.py`
(`/brief/evolved` route), `intelligence/scheduler.py`
(`_evolved_insight_generation_job`, `_attention_evaluation_job`,
`send_brief`/`check_midday_signals` registration),
`lcars-portal/src/app/api/captain-intelligence/generate/route.ts`,
`core/model-router/app.py` (`TASK_POLICY` entries for
`captain-insight-synthesis`, `captain-reasoning-synthesis`,
`intelligence-brief`).

Related decisions: builds on ADR-024 (Resilience Intelligence
Convergence — the shared `core/llm/provider_chain.py` this ADR's
guardrail-coverage finding concerns) and ADR-032 (LLM Application Security
Baseline — the guardrails layer that wraps System B's Model Router calls
but does not confirm coverage of System C's `provider_chain.py` fallback
tier; that gap is named in this ADR's Decision Drivers/Consequences as a
disclosed follow-up, not fixed here).

Mission context: `BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md` (the UI-
consolidation half of this same Convergence Review, PRs #275-278,
#280, #284 — completed 2026-09-19, same day as this ADR) and
`knowledge/SUOC-Platform-Registry.md`'s "Continuous Captain Brief
Orchestration" record, which this ADR's filename is cited from going
forward.
