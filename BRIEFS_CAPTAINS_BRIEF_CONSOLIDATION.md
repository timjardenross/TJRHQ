# Briefs / Captain's Brief Consolidation — Dependency Map & Phased Plan

**Status:** Phase 0 (discovery) complete. Phase 1 (signal-leakage fix,
backend-only) shipped in [PR #275](https://github.com/timjardenross/TJRHQ/pull/275).
Phase 4 (attention-semantics rework, backend-only) shipped concurrently in
[PR #276](https://github.com/timjardenross/TJRHQ/pull/276) — pulled forward
out of its original Phase-1-dependency-only ordering (§6) since it needed
no UI/Domains-IA prerequisite of its own; see §11 for detail. Phases 2-3
(merged cross-domain assembly + the Briefs "Domains" tab UI) implemented
and tested in this pass — see §8 for what shipped. Phase 5 (Captain's
Brief retirement) is scoped below, **not implemented in this pass** — see
§5 for why. With Phases 1-4 all landed, Phase 5's own gate ("once
equivalent or superior capability exists in Briefs") is now within reach,
though not yet declared met — see §5.

This document is the dependency map the consolidation mission requires
before any UI removal or route change, plus the phased plan for the
remaining work. It supersedes nothing in `BRIEFS_CANONICAL_UPLIFT.md`
(2026-09), which already delivered a large share of the mission's OSINT-side
goals — read that first; this doc picks up where it stops and covers the
cross-domain (non-OSINT) half of the mission.

---

## 1. The real system landscape: five "Captain Brief" systems, not two

Discovery (three parallel architectural sweeps, cross-checked against
`knowledge/SUOC-Platform-Registry.md`) found the mission's "two workbenches"
framing understates the problem. Five distinct systems share the name:

| # | System | Canonical implementation | Data model | Live UI |
|---|---|---|---|---|
| **A** | **Continuous Captain Brief Orchestration** — the canonical, event-bus-based cross-domain pipeline | `core/platform/captain_brief_orchestrator.py` (+`attention_engine.py`, `priority_engine.py`, `captain_brief_contract.py`) | `core_events` (Event Bus) → Attention Engine → Priority Engine → domain-grouped document | **`/captains-brief-workbench`** via `/api/captain-brief` → Python `GET /brief/full` |
| B | Legacy mission-based assembler | `core/context-assembly/assembler.py::assemble_captain_brief_context()` | missions + `recommendation_engine.py` | None in `lcars-portal` (Slack only, via E) |
| C | Captain's Daily Brief (Telegram/cron digest) | `intelligence/captains_brief.py` | ORI OSINT brief + health capacity + content, LLM-narrated | `TodaysBriefPanel.tsx` on Captain's Chair, via `/api/captains-daily-brief` → `captains_daily_briefs` table |
| D | Research-mission brief generator | `platform-runtime/lib/captain_brief.py` | Research mission output → Slack | Unrelated feature; name collision only |
| E | Slack `/captain-brief` command | `platform-runtime/commands/captain_brief.py` | Wraps B via Command Centre API | Slack only |
| — | **Briefs (OSINT/geopolitical archive)** | `intelligence/brief/brief_generator.py` | `intelligence_briefs` table | **`/briefs`**, `/briefs/[id]` |

The platform's own registry already tracks this as **"Architectural Debt (3
unreconciled pipelines)"** (`knowledge/SUOC-Platform-Registry.md:73`) with an
open, named action — **"Formal Captain Brief Convergence review (MSN-0342/
0343) vs. `captains_brief.py`/`captain_brief_evolution.py`"** — so this
consolidation lands on ground the platform already expected to need
reconciling, not a new problem.

**In scope for "Briefs vs Captain's Brief" consolidation:** System A (the
live `/captains-brief-workbench` UI and its backend) and the Briefs OSINT
archive. **System C** already had its own leakage (a second, independent
LLM re-synthesis) fixed by `BRIEFS_CANONICAL_UPLIFT.md` §2.7 — it now
renders the canonical OSINT view deterministically and needs no further
work here. **Systems B, D, E** are out of scope: B/E are a legacy,
non-event-based pipeline exposed only to Slack with no live `lcars-portal`
caller (a separate deprecation candidate, not part of this mission); D is
an unrelated research-mission feature that only shares a name.

---

## 2. Data flow today (as-built)

```
core_events (Event Bus)                         intelligence_events / intelligence_briefs
        │  poll_events()                                    │  brief_generator.py pipeline
        ▼                                                    ▼
Attention Engine → Priority Engine                  classify → dedup → rank → LLM narrative
        │  captain_brief_contract.py                         │  render.py (no LLM, pure selection)
        ▼                                                    ▼
CaptainBriefDocument (System A)                     intelligence_briefs row (immutable, insert-only)
   domain sections: health / operational_intelligence /       │
   engineering / learning / opportunities                     ├─→ /briefs, /briefs/[id] (Latest/Timeline/Explore)
        │                                                      ├─→ Telegram /brief (build_morning_intelligence_view)
        ├─→ /captains-brief-workbench (KPIs, Brief tab, Domains tab)
        ├─→ interrupt_dispatcher.py → Telegram push (System A's own channel)
        └─→ Captain's Chair "Needs You" (interrupt_now count only, links out)

intelligence/captains_brief.py (System C)
   reads render.py's canonical OSINT view (no re-synthesis, fixed 2026-09) +
   platform core_events (health/engineering/learning/opportunities, separately)
        │
        └─→ captains_daily_briefs table → TodaysBriefPanel.tsx (Captain's Chair)
```

Two structurally different pipelines feed two different "Captain's Chair"
surfaces today: System A's `interrupt_now` count (raw Event Bus) and System
C's rendered text (OSINT-only + platform `core_events` digest). **Neither
currently reads the OSINT `intelligence_briefs` Domain Picture or vice
versa** — System A's domain sections (health/operational_intelligence/
engineering/learning/opportunities) and Briefs' `domain_picture` (OSINT
event-type buckets + Health OSINT + Emergency Alert Hub, per
`BRIEFS_CANONICAL_UPLIFT.md` §2.5/§2.9) are two independent domain
taxonomies over disjoint data. **This is the real gap the mission's
"Domains" IA has to close** — see §4.

---

## 3. What `BRIEFS_CANONICAL_UPLIFT.md` already delivered (do not redo)

Confirmed against code, not just the doc's own claims:

- Insert-only, auto-published `intelligence_briefs` (immutable history) —
  `intelligence/persistence/intelligence_store.py:1257`.
- Event-driven generation gated on a real collection-completion heartbeat,
  bounded degraded cutoff — `intelligence/brief/morning_cycle.py`,
  `intelligence/scheduler.py:181-224`.
- Content model: `morning_cycle_id`, `coverage`, `comparison`,
  `domain_picture`, `known_unknowns` — migration `0191`.
- `/briefs` rebuilt as **Latest / Timeline / Explore**, `/briefs/[id]`
  canonical detail route.
- Deterministic current-vs-prior comparison (`comparison.py`, no LLM).
- Cross-domain fusion of Health OSINT + Emergency Alert Hub into
  `domain_picture`/`coverage` via decoupled reads (`external_domains.py`) —
  **not** Engineering/Missions/Learning/Opportunities, which live only in
  System A's Event Bus, not in any OSINT-adjacent table.
- System C (Captain's Chair's `TodaysBriefPanel`) fixed to render the
  canonical view instead of re-synthesizing — no independent "second
  interpretation of the same morning."

**What it explicitly left as FUTURE** (still open, relevant to later
phases here): a "Not Material Today" section, deeper day-over-day history,
an arbitrary-pair Compare UI, a Self-Improvement evidence surface.

---

## 4. What remains: the actual gap to mission parity

1. **Domains IA — resolved this pass (§8).** Briefs' `domain_picture`
   covered OSINT + Health OSINT + Emergency Alert Hub; System A's domain
   sections covered health / operational_intelligence / engineering /
   learning / opportunities from the platform Event Bus. The mission's
   "Domains" tab (§3 of the mission) needed **both** in one place. Two
   candidate approaches were on the table: (a) Briefs' frontend also
   queries `/brief/full` (System A) and renders its domain sections
   alongside `domain_picture`, or (b) a new shared assembly step in Python
   that produces one merged cross-domain document Briefs renders. A
   concrete architecture pass (reading both pipelines' actual code, not
   just this doc's prior description of them) confirmed the two shapes are
   structurally incompatible — dynamic OSINT bucket keys with a
   `worst_risk` posture proxy vs. five fixed event-bus sections with no
   posture field at all, and a stored historical snapshot vs. an
   always-live computation — so (a) would have pushed that reconciliation
   into the frontend anyway. **(b) was implemented**: a new
   `intelligence/brief/domains_view.py::assemble_domains_document()`,
   exposed as `GET /brief/domains` alongside `/brief/full`, merges both
   into one list of normalised `DomainSummary` objects (posture/confidence/
   what-changed/what-matters/watch/evidence-count) — the mission's own
   schema — without recomputing either pipeline's own synthesis.

2. **Signal leakage in System A — root cause fixed in this pass** (§7
   below); the domain-grouping/attention-routing architecture itself
   (Attention Engine categories, Priority Engine risk floor,
   `_WARNING_RISK_THRESHOLD`) is sound and was not touched — only the
   upstream data contract violation that let raw text impersonate a
   recommendation.

3. **Attention semantics (mission §7, "Needs Attention" scarcity)** — System
   A's `interrupt_now` is a pure threshold cut (`importance >= 75 AND
   confidence >= 70`), with no materiality/novelty/persistence/dedup-against-
   existing-attention-item logic. Captain's Chair's "Needs You" widget
   already only shows a *count*, not the raw list (`commandState.ts:173-180`
   per discovery), which limits the blast radius today — but the underlying
   list a Captain reaches via that link is still an unfiltered threshold cut.
   Reworking this (materiality/novelty/persistence scoring) is a real,
   separate design task, not a rename.

4. **Captain's Brief workbench retirement (mission §11)** — gated
   explicitly by the mission itself on "once equivalent or superior
   capability exists in Briefs." That capability (merged Domains IA, #1
   above) does not exist yet. Retiring `/captains-brief-workbench` or its
   nav entries now would be pure information loss, not consolidation —
   explicitly what the mission's own §1 and §11 warn against. **Not done in
   this pass.**

5. **Naming collision**: Briefs' nav entry (`workbenches.ts:158-163`) is
   currently described as "The intelligence brief archive - every
   synthesized OSINT/world-news brief" — narrower than the mission's target
   "Briefs = KNOW" canonical capability. Once #1 lands, this description
   (and the Workbench's actual IA) needs to broaden to cover cross-domain
   content, not just OSINT.

6. **Platform Registry update (mission §14/§9)** — `knowledge/
   SUOC-Platform-Registry.md` already has two stale citations found during
   discovery: "Continuous Captain Brief Orchestration" (line 812) cites the
   pre-rename `/captains-brief` route, and "Captain Experience Component
   Library" (line 857) cites `ApprovalQueue`/`CaptainApprovalQueue` as wired
   onto Captain's Chair — that wiring was already removed when
   `captains-chair-workbench` replaced the retired `(app)/captains-chair`
   stub (2026-08-11). Both need correcting regardless of this mission's
   outcome; folding the consolidation's own registry update into the same
   pass is the efficient sequencing.

---

## 5. Why this pass stops after Phase 3 (Domains IA merged; retirement not attempted)

The mission's own §1 mandate ("do not remove or rewrite working
functionality until its consumers, data contracts and replacement path are
understood") and §11 migration gate ("once equivalent or superior capability
exists in Briefs") both explicitly block retiring `/captains-brief-workbench`
before the Domains IA reaches parity. Phase 3 (§8) gives Briefs a genuine
merged cross-domain view for the first time, but "equivalent or superior
capability" is a claim about real-world Captain usage, not something this
pass can self-certify by shipping code — the new tab has automated test
coverage (Python assembly logic + React component rendering, §8) across
normal/no-data/degraded states, but **could not be exercised end-to-end in a
live authenticated browser session** (see §8's own caveat) the way this
repo's own conventions ask for before calling a UI change fully done.
Declaring Phase 5's gate met on that basis alone would be exactly the kind
of unvalidated claim the mission's §1/§11/§15 warn against — so retirement
stays out of scope for this pass, pending either a live walkthrough or the
Captain's own sign-off that the Domains tab is a real replacement.

Attention-semantics rework (Phase 4, mission §7) was unrelated to the IA
question and never blocked Phase 2-3 — it landed concurrently, in a
separate session, as [PR #276](https://github.com/timjardenross/TJRHQ/pull/276)
(§11). Landing separately rather than bundled into this pass matches the
mission's own "do not trade validation for speed" instruction (§15): two
independently-reviewable changes, two diffs, not one.

What *was* done, across this pass and the three before it: Phase 1's
signal-leakage root-cause fix (§7, PR #275) — backend-only, additive,
backward-compatible. Phase 4's persistence/novelty gate (§11, PR #276) —
also backend-only, additive, opt-in via a defaulted kwarg. Phase 2's shared
cross-domain assembly step and Phase 3's Domains tab UI (§8) — both new,
additive surfaces (a new Python module
+ HTTP route, a new Next.js route + tab) that touch no existing route,
nav entry, or UI behaviour outside the new tab itself.

---

## 6. Phased plan (remaining work)

| Phase | Work | Depends on | Risk if skipped |
|---|---|---|---|
| **1 — done** (PR #275) | Signal-leakage root-cause fix (§7) | — | Domains IA would inherit fabricated recommendations |
| **2 — done, this pass** | Merged cross-domain assembly: new `intelligence/brief/domains_view.py` + `GET /brief/domains`, merging System A's domain sections (Engineering/Missions/Learning/Opportunities/Health/Operational Intelligence) with `domain_picture` (§8) | Phase 1 | Domains IA ships incomplete, mission's own domain list (§3.9) unmet |
| **3 — done, this pass** | Briefs "Domains" tab UI — per-domain synthesized picture (posture/changed/what-matters/watch/evidence), read-only with link-out drill-down (§8) | Phase 2 | Two competing domain views persist |
| **4 — done** (PR #276) | Attention-semantics rework — materiality/novelty/persistence/dedup on top of the existing threshold cut, feeding a genuinely scarce "Needs Attention" list (§11) | Phase 1 (clean data) | "Needs Attention" stays a raw threshold cut, contra mission §7 |
| **5** | Captain's Brief retirement — redirect `/captains-brief-workbench` → `/briefs`, remove nav/registry entries, update `interrupt_dispatcher.py`'s deep-link, update Platform Registry citations (§4.6) | Phase 3 validated live (§5, §8) | Premature deletion, information loss (mission §1/§11 explicitly prohibit this) |

Phases 2-5 are independent PRs/sessions by design — each has its own UI
validation surface, its own risk profile, and its own reviewable diff.
Bundling them would violate the mission's own "do not trade validation for
speed" instruction (§15). Phases 2 and 3 landed together in this pass
because the UI has nothing to render without the assembly step behind it —
they share one validation surface (the Domains tab), not two.

---

## 7. Phase 1 detail: signal-leakage root-cause fix (implemented this pass)

**Root cause found** (not a downstream mislabeling — an upstream data
contract violation): `core_events.recommended_action` had exactly one text
column shared between two incompatible uses — a genuine reasoned action
proposal (`captain_brief_contract.py::recommendation_from_event()`, already
documented as a "deliberately minimal" pass-through adapter) and, in three
emitters, raw signal content substituted in because there was no other field
to carry readable text into a push notification:

1. `intelligence/persistence/intelligence_store.py:1098` — a scraped news
   headline (`row["raw_title"]`) written as `recommended_action`.
2. `intelligence/persistence/intelligence_store.py:778` (pre-fix) — a
   source-collection failure's raw exception message
   (`health.error_message`) written as `recommended_action`.
3. `core/coordination/command_bus.py:425` — a bare systemd state transition
   (`f"{svc}: {state}"`, e.g. `"nginx: failed"`) written as
   `recommended_action`.

Each of these then flowed unchanged through
`recommendation_from_event()` → `CaptainBriefItem.recommendation` →
`_next_actions()` / the top-priority line in `_generate_summary()` /
`interrupt_dispatcher.py`'s push body — i.e. a headline or an HTTP 401 error
literally became a "recommendation," a "next action," or interrupt-now push
content, exactly as the mission's §5 described.

**Fix**: added `core_events.description` (migration `0218_core_events_
description.sql`, additive/nullable) as the home for "what happened, in
readable form," explicitly documented (both in the migration's column
comments and in `event_bus.py::publish_event()`'s docstring) as distinct
from `recommended_action`. Plumbed through:

- `core/platform/event_bus.py::publish_event()` — new `description`
  kwarg, stored alongside (not replacing) `recommended_action`.
- The three emitters above — now pass `description=`, not
  `recommended_action=`. `recommended_action` stays unset for these events,
  so `recommendation_from_event()` correctly returns `None` — no fabricated
  Recommendation.
- `core/platform/attention_engine.py::AttentionDecision` — new
  `description` field, carried through every branch of `evaluate_event()`.
- `core/platform/captain_brief_contract.py::CaptainBriefItem` — new
  `description` field, carried through `assemble_captain_brief()`.
- `core/platform/interrupt_dispatcher.py` — push body now prefers
  `item.recommendation.description`, then `item.description` (the real
  readable content), and only falls back to `item.reason` (the bare
  `"importance=X >= Y AND confidence=Z >= W"` scoring trace) when neither
  exists — previously it fell back straight from recommendation to `reason`,
  skipping the one field that actually had readable content once
  `recommended_action` stopped being misused.

**Explicitly not touched in this pass** (same pattern, lower-confidence
evidence, flagged for a follow-up rather than bundled in blind): a `grep -n
"recommended_action="` across the repo found ~20 more call sites; most are
genuine synthesized recommendations (e.g. `platform-runtime/lib/strategy/
delivery_constraints.py`'s "Urgently resource and mature threatening
capabilities"), but `platform-runtime/lib/notebook/notebook_route_executor.py:167`
and `platform-runtime/lib/comms/portfolio.py:78` both pass a bare `title` as
`recommended_action` — the same pattern as fix #1 above, not yet verified
against their actual event semantics. Queued as a follow-up (§8).

**Tests**: `tests/test_signal_leakage_fix.py` (new, 5 tests) — proves both
emitters now populate `description` and leave `recommended_action` unset,
proves a description-only event produces no fabricated `Recommendation`
while remaining a real, visible attention item, and proves the dispatcher's
three-tier fallback (recommendation → description → reason) in both
directions. All 33 pre-existing tests across
`test_attention_engine.py`, `test_captain_brief_contract.py`,
`test_captain_brief_orchestrator.py`, `test_interrupt_dispatcher.py`,
`test_daily_brief_interrupt_now.py`, `test_attention_evaluation_job.py`,
plus `test_downdetector_priority_cadence.py` and
`test_priority_engine_wiring.py` (25 tests, indirectly touched modules),
pass unchanged — additive change, no existing behaviour altered.

---

## 8. Phase 2-3 detail: merged Domains tab (implemented this pass)

**Backend (Phase 2)** — `intelligence/brief/domains_view.py`, a new pure
(no-I/O) module, same contract as `assemble_captain_brief_document()`:
takes already-fetched `core_events` and the already-fetched latest
`intelligence_briefs` row as arguments, so it's testable without a live DB
or event bus.

- `assemble_domains_document(events, latest_brief) -> DomainsDocument`
  reuses `assemble_captain_brief_document()` (System A, unchanged) for the
  five event-bus domains and the latest brief's stored `domain_picture`
  (System — Briefs, unchanged) for OSINT/Health/Emergency — normalising
  both into one `list[DomainSummary]` (`key`, `label`, `source`, `posture`,
  `confidence`, `what_changed`, `what_matters`, `watch_conditions`,
  `evidence_count`, `evidence`, `as_of`, `availability`, `detail_href`).
- Posture for event-bus domains is derived from the worst `risk_score`
  among that section's items (RED ≥60, AMBER ≥30, mirroring
  `captain_brief_orchestrator.py`'s own `_WARNING_RISK_THRESHOLD` for RED);
  OSINT domains reuse `domain_picture`'s own `worst_risk` verbatim — no
  posture is invented where neither pipeline already computed one.
  Confidence, `what_changed`, and `what_matters` are built only from real
  per-item fields (`recommendation.confidence`, `reason`, `category`) —
  nothing fabricated for a field neither pipeline expresses today (e.g.
  OSINT buckets carry no numeric confidence, so `confidence` stays `None`
  rather than a made-up number).
- **Honest unavailability, not silent gaps**: if no brief has ever been
  generated, `osint_available=False` and a warning explains why — no
  OSINT-sourced domains are fabricated for a taxonomy that was never
  computed. If the latest brief's collection cycle was degraded
  (`coverage.degraded`), every OSINT domain from it is marked
  `availability="degraded"` and a top-level warning is added. A
  present-but-empty event-bus domain is marked `availability="no_data"`
  and still appears — the mission needs a Captain to see all domains from
  one place, including quiet ones, not have them disappear.
- Exposed as `GET /brief/domains` on `core/context-assembly/
  context_service.py`, same pattern as `/brief/full` (dataclass →
  `jsonify(dataclasses.asdict(...))`, same error-boundary shape). Proxied
  by a new Next.js route, `GET /api/briefs/domains`
  (`lcars-portal/src/app/api/briefs/domains/route.ts`), mirroring
  `api/captain-brief/route.ts` verbatim (session check, rate limit,
  15s timeout, `{error, detail}` on failure).
- Tests: `tests/test_domains_view.py` (17 new tests) — pure per-domain
  helpers exercised against hand-built `CaptainBriefItem`/`Recommendation`
  instances (posture thresholds, confidence rollup, watch-condition
  filtering) plus end-to-end wiring tests (all five event-bus domains
  always present even when empty; OSINT buckets passed through faithfully;
  the no-brief-yet and degraded-coverage warning paths). All pre-existing
  related suites (`test_captain_brief_orchestrator.py`,
  `test_captain_brief_contract.py`, `test_signal_leakage_fix.py`,
  `test_external_domain_signals.py`, `test_intelligence_brief_generator.py`)
  pass unchanged.

**Frontend (Phase 3)** — a fourth tab (`Domains`, alongside the existing
Latest/Timeline/Explore) in `lcars-portal/src/app/briefs/page.tsx`,
rendered by a new `_components/DomainsView.tsx`. Fetches
`/api/briefs/domains` lazily (only once the Domains tab is first opened,
not on every Briefs page load — the endpoint does live work on every call).

- Each domain renders as a card (posture pill, availability badge when not
  `ok`, confidence, "what changed," "what matters," "watch," and an
  evidence count) — a synthesized picture, never a raw event dump.
  Evidence is one click away behind a collapsible, capped preview — stays
  progressive disclosure, not the primary view.
- Cards are grouped under "OSINT / World Intelligence" and "Platform
  Domains" subheadings so a Captain can tell which pipeline a given domain
  came from, without the two shapes needing to look identical.
- Read-only throughout, matching `captains-chair-workbench`'s own
  "display + link out" precedent (`NeedsYou.tsx`, `Intelligence.tsx`): no
  approve/reject/execute affordances, only a "View full detail →" link —
  to `/briefs/[id]` for OSINT domains, `/captains-brief-workbench?domain=…`
  for event-bus domains (Captain's Chair remains the command surface).
- Tests: `DomainsView.test.tsx` (7 new tests, React Testing Library)
  covering the three scenarios this phase's brief specifically asked for —
  a normal domain (posture/confidence/what-matters/watch/evidence/link all
  render), a domain with no data (card stays visible with an explicit
  empty message, not silently dropped), and a domain with degraded/stale
  coverage (degraded badge + top-level warning banner + relative-age
  display) — plus the no-brief-yet warning and OSINT/Platform grouping.
  `tsc --noEmit` and `eslint` both clean on every touched file.

**Verification caveat — read before treating Phase 5's gate as met.** This
repo's own convention asks for a real dev-server run in a browser before
calling a UI change done. The dev server was started and confirmed
compiling cleanly with no runtime errors, and the new `/api/briefs/domains`
route was confirmed to enforce auth identically to the existing
`/api/captain-brief` route (307 → `/login` when unauthenticated, matching
middleware behaviour). **The actual authenticated rendering — the three
required scenarios inside a real logged-in session — was not observed**,
because this instance is the Captain's own single-tenant, credential-gated
system with no test account or auth bypass available, and creating or
guessing credentials was out of scope for this pass. The component-test
coverage above exercises the same scenarios against the real component and
real assembly logic, but a live walkthrough (or the Captain's own look) is
still needed before this substitutes for the dev-server-in-a-browser check
this repo's conventions ask for — see §5.

- Follow-up spotted in passing, not fixed here (separate, out-of-scope
  task): `lcars-portal/src/app/briefs/[id]/page.tsx`'s domain_picture
  caption still says "Health OSINT and Emergency Alert Hub are separate
  systems not yet fused into this synthesis" — stale relative to
  `brief_generator.py`'s actual behaviour (it already fuses both in, per
  `BRIEFS_CANONICAL_UPLIFT.md` §2.9/§2.5, confirmed in this pass's own
  architecture sweep). Worth fixing next time that page is touched.

---

## 8a. Post-Phase-3 production bug: same signal-leakage class, new field

A live production screenshot (Domains tab, event-bus "Platform Domains"
cards) showed `AttentionDecision.reason` — the Attention Engine's internal
audit trail, never meant to be read by a Captain — surfacing verbatim as
"What Matters" bullets:

1. A raw aggregation trace: *"9 events sharing domain=health-intelligence/
   event_type=health.readiness.scored ... — aggregate as a count/trend."*
2. A persistence-gate suppression narrative (Phase 4, §7 above): *"recurrence
   of already-acknowledged event [uuid] within 24h ... — not re-interrupting
   a stable, already-surfaced condition."*

**Root cause**: §8's own summary above already names the field this pass
used — `reason` — as one of the "real per-item fields" `what_matters`/
`watch_conditions` are "built only from," alongside `recommendation.
confidence` and `category`. That was wrong: `reason` is exactly the
diagnostic trace PR #275 (§7) had already established should never reach a
Captain-facing surface, and this module's own first pass reintroduced the
same class of leak in a field #275 didn't touch. Unlike #275's
`recommended_action` leak, this wasn't a domain emitter misusing a field —
`domains_view.py` itself picked the wrong field to read.

**Fix** (`intelligence/brief/domains_view.py`):

- `_readable_text(item)` — the only path `what_matters`/`watch_conditions`
  now use to get bullet text: `recommendation.description`, else
  `description`, else nothing (the item is simply excluded — no fallback to
  `reason`, unlike `interrupt_dispatcher.py`'s push body, which has no
  "may be empty" option and PR #275 deliberately gave a `reason` last
  resort). Since the persistence gate only ever rewrites `decision.reason`/
  `category` (never `decision.description` — confirmed by reading
  `_apply_recurrence_gate()`), this alone fixes leak #2 above: the item's
  own genuine `description` surfaces instead of the suppression narrative.
- `_aggregation_constraints()` + a new `DomainSummary.constraints: list[str]`
  field — a 3+-event aggregate (`evaluate_batch()`'s SHOULD_BE_AGGREGATED
  branch, `aggregation_key` set) is real information (a count/trend, and a
  large one — e.g. 109 `intelligence.source.failed` events — is worth a
  Captain's attention) but is not a synthesized finding about any single
  event. Aggregated items are now excluded from `what_matters`/
  `watch_conditions` entirely and instead produce one fresh, synthesized
  sentence per aggregation group ("N `<event_type>` event(s) aggregated as
  a count/trend this cycle — a coverage signal, not an individual
  finding..."), built only from the group's own size and `event_type` —
  never by reusing or parsing `item.reason`. This fixes leak #1 above and
  satisfies the "large failure-count aggregates must route to a per-domain
  coverage signal, not materiality bullets" requirement. `evidence` is
  unchanged and still shows `item.reason` verbatim — that drill-down is an
  explicit, one-click-away audit view, not a headline, and was never part
  of the leak.
- Frontend: `DomainSummary.constraints` plumbed through
  `lcars-portal/src/lib/domainsShared.ts` and rendered as a new "Coverage
  Notes" section in `DomainsView.tsx`, visually distinct (muted, italic)
  from "What Matters"/"Watch" and only shown when non-empty.

**Investigated, documented rather than fixed — a real blind spot in the
upstream posture calculation**: does `intelligence.source.failed` (the
event type behind the 109-event example above) get scored at all? Yes, but
not usefully. `intelligence_store.py::save_source_health()` publishes it via
`_publish_core_event(..., description=health.error_message)` with no
`importance`/`confidence` kwarg — both stay `None`. Every event still gets a
`PriorityScore` in `captain_brief_orchestrator.py::assemble_captain_brief_document()`
(no code path skips scoring for an unscored event), and
`priority_engine.py::_risk_from_importance_confidence()` treats a missing
importance/confidence as `0`, not "unknown": `risk = (0/100) * (1 -
0/100) * 100 = 0.0` — a real float, not `None`. `domains_view.py::
_posture_for_items()` only excludes a `None` risk_score from its rollup, so
this fabricated-by-omission `0.0` counts as a genuinely low-risk, fully-
scored event. A domain dominated by unscored source-failure events can
therefore post **GREEN** despite a large, real failure count — an
accidental blind spot, not a deliberate design choice by anyone who
reasoned about it.

**Not fixed in this pass, deliberately**: `_risk_from_importance_confidence()`'s
"absent -> 0" convention is `priority_engine.py`'s own documented choice
(module docstring: risk is "computed as the inverse relationship between
`importance` and `confidence`") and is shared by every consumer of
`PriorityScore`, not just this module — changing it is a scoring-semantics
change with a blast radius well beyond the Domains tab bug this pass set
out to fix (this pass's own scope explicitly excludes touching
`attention_engine.py`/`captain_brief_orchestrator.py`, and
`priority_engine.py` is the same category of shared, multi-consumer
engine). Mitigated at the display layer instead, honestly rather than
silently: the `constraints` coverage signal above surfaces a large
aggregated failure count regardless of what the (unreliable, for this event
shape) posture rollup says, and `_posture_for_items()` now carries an
explicit code comment naming this exact limitation so it isn't rediscovered
as a surprise later. A real fix — e.g. `PriorityInputs` distinguishing "no
signal supplied" from "supplied and low" — is queued as a follow-up (§9)
rather than bundled in blind here.

**Tests**: `tests/test_domains_view.py` — 7 new regression tests proving
`what_matters`/`watch_conditions` never contain raw `reason` text (a bare
scoring trace, the exact suppression-gate narrative from the screenshot, or
an aggregation trace), that the recommendation -> description fallback
order holds, and that a 109-event aggregate produces exactly one
`constraints` entry and zero `what_matters`/`watch_conditions` bullets.
`DomainsView.test.tsx` — 2 new tests proving "Coverage Notes" renders
separately from "What Matters" and is omitted entirely when empty. All
pre-existing `test_domains_view.py`/`DomainsView.test.tsx` cases pass
unchanged or were updated to set `description` (the field a real UI bullet
now requires) alongside the `reason` they already set for evidence-drilldown
coverage. `ruff check`, `tsc --noEmit`, and `eslint` all clean on every
touched file.

**Verification caveat, same as §8's**: no live-browser re-check against a
real authenticated session was performed for this fix, for the same reason
§8 already gives (no test account or auth bypass available in this
environment) — the component/pure-function test coverage above exercises
the same code paths, but a live look at the rendered Domains tab is still
worth doing before treating this as fully closed.

---

## 9. Follow-up work queued (not attempted in this pass)

Tracked as separate suggested tasks rather than bundled here, since each is
independently scoped, reviewable, and testable:

- ~~Verify and, if warranted, fix the same raw-text-as-recommended_action
  pattern in `notebook_route_executor.py:167` and `comms/portfolio.py:78`.~~
  **Done** — fixed in [PR #277](https://github.com/timjardenross/TJRHQ/pull/277).
- Live-browser validation of the Domains tab (§8's caveat) — a real
  authenticated walkthrough across the three scenarios, to actually clear
  Phase 5's "equivalent or superior capability" gate rather than assume it.
- Stale domain_picture caption on `/briefs/[id]` (§8, found in passing) —
  spun off as a separate background task, in progress as of this pass.
- ~~Phase 4: attention-semantics rework~~ **Done** — landed concurrently as
  [PR #276](https://github.com/timjardenross/TJRHQ/pull/276) (§11).
- ~~`priority_engine.py`'s posture blind spot (§8a, found in passing): an
  event that never sets `importance`/`confidence` (e.g.
  `intelligence.source.failed`) gets a real `risk_score` of `0.0`, not
  `None`, because `_risk_from_importance_confidence()` treats absent inputs
  as `0`.~~ **Done** — fixed in [PR #283](https://github.com/timjardenross/TJRHQ/pull/283):
  `_risk_from_importance_confidence()` now returns `None` when both
  `importance` and `confidence` are absent (a single missing input still
  scores as before). `PriorityScore.risk_score` is `float | None`;
  `captain_brief_orchestrator.py`'s warnings cut checks for `None`
  explicitly rather than comparing it against the threshold.
  `domains_view.py::_posture_for_items()` already filtered on
  `risk_score is not None`, so it inherited the fix with no code change.
  The `constraints` display-layer mitigation (§8a) stays — it solves a
  different problem (aggregated-group readability), not this one.
- Phase 5: Captain's Brief workbench retirement + nav/registry cleanup +
  Platform Registry correction (including the two already-stale citations
  found in this discovery, independent of this mission's outcome). Now the
  only phase left — blocked on the live-browser validation item above.

---

## 10. Final capability map (target state, once Phase 5 lands)

```
SOURCE SYSTEMS
  core_events (Event Bus)  |  intelligence_events (OSINT collection)  |  health_signals  |  alerts (Emergency)
        │                              │                                    │                  │
        ▼                              ▼                                    │                  │
DOMAIN ASSESSMENTS
  Attention Engine → Priority Engine   |  brief_generator.py (classify/dedup/rank/narrative)
  (health/operational_intelligence/       │
   engineering/learning/opportunities)    ▼
        │                              intelligence_briefs (immutable, per-morning-cycle)
        │                                    │
        └──────────────┬─────────────────────┘
                        ▼
              BRIEFING SYNTHESIS  (Phase 2, done: domains_view.py merges
                                    /brief/full's domains + the latest
                                    domain_picture into GET /brief/domains)
                        │
                        ▼
              BRIEFS WORKBENCH  (Latest / Domains [Phase 3, done] / Timeline / Explore)
                        │
        ┌───────────────┼────────────────────┐
        ▼               ▼                    ▼
  Captain's Chair   Telegram /brief    Other consumers (weekly-review,
  (read-only,       (canonical view)   investigations, daily ops cycle —
  link-out only —                      all read-only per discovery)
  no command
  affordances)
```

Captain's Chair remains the command surface (approve/reject/intervene/
execute) for anything Briefs flags as needing attention — discovery
confirmed it is *already* read-only + link-out for all brief-derived content
today (`NeedsYou.tsx`, `Remember.tsx`, `Intelligence.tsx`,
`TodaysBriefPanel.tsx` all link out rather than embedding actions;
`ApprovalQueue.tsx` is not wired into the current `-workbench` page). The
new Domains tab (§8) preserves this boundary explicitly — no
approve/reject/execute affordances, link-out only. That boundary is a
design decision worth preserving through Phase 5 too, not an accident to
fix.

---

## 11. Phase 4 detail: attention-semantics rework (PR #276, landed concurrently)

Implemented in a separate, concurrent session as
[PR #276](https://github.com/timjardenross/TJRHQ/pull/276) — included here
so this doc stays the single source of truth for the whole mission's
phased plan, not because it was built as part of this pass.

**Problem** (mission §7): `attention_engine.py::evaluate_event()` routed
every event into INTERRUPT_NOW on a pure `importance >= 75 AND confidence
>= 70` threshold cut, with no materiality, novelty, persistence, or
already-flagged dedup on top. Two concrete real-pipeline symptoms:

1. `intelligence/scheduler.py::_attention_evaluation_job()` calls
   `event_bus.poll_events()` with no `since` cursor every
   `ATTENTION_EVAL_INTERVAL_MINUTES` (default 10) — the same already-
   dispatched row (now `status="acknowledged"`) keeps reappearing in the
   poll and kept being re-classified as a fresh INTERRUPT_NOW on every
   cycle. `interrupt_dispatcher.py`'s own status check already prevented
   a *duplicate push*, but the classification itself (`doc.interrupt_now`,
   `doc.metadata.attention_category_counts.interrupt_now`) stayed noisy —
   the exact gap a future "Needs Attention" list reading that field
   directly (not just the dispatcher) would have inherited.
2. A domain that re-publishes a fresh row (new `event_id`, unchanged
   `importance`/`confidence`) every cycle for a still-true, already-
   acknowledged condition had no mechanism to be recognised as "the same
   thing again," since `core_events` rows are insert-only and each
   occurrence gets its own id.

**Fix**: a persistence/novelty gate added on top of the existing
threshold cut in `core/platform/attention_engine.py` — the threshold
logic itself (`_route_by_threshold()`, the pre-existing `evaluate_event()`
body, unchanged) still decides the base category first. Only a decision
that already resolved to INTERRUPT_NOW is then checked against an
optional `recent_surfaced` list of `core_events`-shaped rows:

- **Match key**: `(domain, event_type)` — `core_events` has no title
  column (unlike `intelligence_briefs.top_events`, which
  `intelligence/brief/comparison.py` matches by title similarity), so
  this is the table's own deterministic grouping key, the same pair
  `evaluate_batch()`'s SHOULD_BE_AGGREGATED branch already groups by. A
  row is allowed to match itself, which is what makes symptom #1 above
  self-correcting: the identical re-polled row naturally carries zero
  delta against itself.
- **Already-surfaced check**: the matched row's `status` must be
  `acknowledged`, `dismissed`, or `superseded` (`event_bus.py`'s own
  status vocabulary) — a still-`"new"` prior row is not "already
  surfaced" and is not dedup grounds.
- **Materiality check**: importance or confidence must have moved by
  `AttentionThresholds.material_change_delta` (default 15) or more since
  the matched prior row to count as a genuine change; either side missing
  a score is treated as a change (never silently suppress on incomplete
  data — the same "absent is not defaulted" convention the base threshold
  cut already applies).
- **Recency window**: `AttentionThresholds.recurrence_lookback_hours`
  (default 24), compared against `occurred_at` when both rows carry a
  parseable timestamp.
- **Downgrade target**: a prior `dismissed` row (a Captain explicitly
  said "not this") downgrades to `SHOULD_SIMPLY_BE_REMEMBERED`;
  `acknowledged`/`superseded` downgrade to `CAN_BE_DELAYED`. Never
  discarded outright — always a real category, never a black-box drop,
  per Blueprint Principle 3. `AttentionDecision.duplicate_of_event_id`
  is set to the matched prior row's `event_id` so the downgrade traces to
  a queryable row, same convention `related_event_ids` uses for
  SHOULD_BE_SUMMARISED.

**Wiring**: `evaluate_event()`/`evaluate_batch()` both take an optional
`recent_surfaced` kwarg (default `None` — omitting it is byte-for-byte
the pre-Phase-4 behaviour, so every existing caller and test is
unaffected). `captain_brief_orchestrator.py::assemble_captain_brief_document()`
defaults `recent_surfaced` to the `events` batch it was already given
(self-referential dedup, zero extra I/O) unless a caller passes its own
list or an explicit `[]` to opt out — this fixes symptom #1 for every
existing caller of `assemble_captain_brief_document()`
(`_attention_evaluation_job()`, `commands/brief.py`, `daily_digest.py`,
`captain_brief_cli.py`, `context_service.py`,
`captain_brief_evolution.py`) with no per-caller changes required.
`interrupt_dispatcher.py` is unchanged — it already reads
`doc.interrupt_now`, which now simply contains fewer stale repeats.

**Explicitly not done in this pass**: no wiring into a "Needs Attention"
Briefs UI section — Phases 2/3 (merged cross-domain assembly, Briefs
"Domains" tab) had not landed yet as of this PR (they landed shortly
after, concurrently, per §8), and this task was scoped backend-only
regardless. `recent_surfaced` beyond one poll's
own batch (a deliberately broader history query) is left to whichever of
Phase 2/3 or a future "Needs Attention" surface first needs it — the
parameter exists precisely so that can be added without another
`attention_engine.py` change.

**Tests**: `tests/test_attention_recurrence_gate.py` (new, 17 tests) —
covers no-`recent_surfaced`-passed backward compatibility, same-row
re-poll after acknowledgement, cross-event_id recurrence by
`(domain, event_type)`, dismissed-vs-acknowledged downgrade targets,
genuine escalation (importance and confidence, independently) still
interrupting, sub-threshold drift still suppressing, missing prior scores
never silently suppressing, no-match/still-"new"-prior not suppressing,
the gate never touching a non-INTERRUPT_NOW decision, the recency window
(default and widened), a custom `material_change_delta`, and determinism
across repeated calls. Plus 2 new tests in
`tests/test_captain_brief_orchestrator.py` covering the orchestrator's
default self-referential wiring and its explicit opt-out. All
pre-existing tests across `test_attention_engine.py`,
`test_captain_brief_orchestrator.py`, `test_interrupt_dispatcher.py`,
`test_daily_brief_interrupt_now.py`, `test_signal_leakage_fix.py`,
`test_attention_evaluation_job.py`, `test_captain_brief_contract.py`,
`test_cognitive_core_regression.py`, `test_approval_router.py`,
`test_priority_engine_wiring.py` and `test_downdetector_priority_cadence.py`
(97 tests total across this file's set, including the 19 new ones above)
pass unchanged — additive change, no existing behaviour altered.
