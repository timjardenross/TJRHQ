# HQ V1 Integration Contracts

**Mission:** HQ V1 Integration QA & Contract Validation
**Audited commit (frozen baseline):** `6c655cdc7568fd997c81fce904b5197ff71957cb`
**Production deployment at audit start:** `dpl_E6BrRsFuMHsKJYDS7RMRzzKZXpGL` — READY

This document is implementation-grounded: every claim cites the real merged
code at the frozen commit, not mission/PR descriptions. It exists to answer
one question before Captain's Chair/LifeOS are built: *do the underlying
systems have canonical owners, stable read boundaries, honest
freshness/unknown semantics, and a coherent "needs attention" meaning —
enough that a command layer can consume them without repairing upstream
architecture?*

---

## 1. Canonical Ownership Map

| Domain | Canonical data owner | Canonical interpretation owner | Notes |
|---|---|---|---|
| Human Systems (capacity/context) | `capacity_checkins` | `assessed-context.ts` (`buildAssessedContext`) | Exposed via `GET /api/human-systems/context` |
| Ready Room (execution) | `personal_tasks` | `lib/personalTasks.ts` (`rankToday`, `getReadyRoomContext`) | Google Tasks sync is a second write surface on the same table, not a second store |
| Weekly Review (retrospective) | `weekly_reviews` (accepted state only) | `api/weekly-review/route.ts` + `weeklyReview.ts`/`synthesis.ts` | Reads other domains read-only; owns none of their data |
| HQ Evolution (improvement learning) | opportunity/outcome store (`scripts/self_improvement/opportunity_store.py`) | `outcome_evaluation.py`, `evolution_orchestrator.py` | PolicyEngine/remediation engine unmodified; `outcome_evaluation.py` has zero imports of `policy` |
| HQ Status (machinery health) | `domain_heartbeats`/`domain_heartbeats_latest` (pre-existing, unowned by this mission) | `lib/hqStatusInterpreter.ts` (pure, DB-free) | Interpretation-only; owns no telemetry itself |
| Briefs (canonical OSINT intelligence assessment) | `intelligence_briefs` | `intelligence/brief/brief_generator.py` | Only synthesizes OSINT/world-news sources; its own tagline's cross-domain claim corrected to match this scope (I1, resolved) |
| Captain's Daily Brief (the artifact TJR actually reads each morning) | `captains_daily_briefs` | `intelligence/captains_brief.py` | A **separate entity** from the OSINT Brief above, sharing the word "brief" — real naming-collision risk |
| Technical OSINT | intelligence_events + source-health views | `intelligence-workbench` API routes | Domain scoring owned here, reused (not recomputed) by Brief/weekly-report consumers |
| Health OSINT | `health_signals` + source-health views | `health-osint` API routes + `tools/health-osint/health_signal_curation.py` (Captain-authorized auto-triage) | |
| Emergency Alert Hub | `alerts` | `intelligence/emergency_alerts.py` | Confirmed **not** wired into the canonical Brief — audited, no defect: the Brief never claims Emergency coverage, so there is no false-currency risk (I2, resolved as ACCEPTABLE, no code change) |
| Calendar | `google_calendar_tokens` (tokens) / live Google Calendar (events) | `lib/google-calendar.ts` | Production-quality but isolated — not wired into Brief/Ready Room/command-surface layer yet |
| Google Tasks / Ready Room integration | `personal_tasks.google_task_id` etc. (migration 0184) | `api/google-tasks/sync/route.ts` | Confirmed: single canonical task store, no shadow store |
| Model Router (shared dependency) | n/a (pure dispatch) | `core/model-router/app.py` | One caller (`intelligence/config.py`) had a wrong port default — fixed this mission |
| Knowledge Library (shared dependency) | `processing_documents` | `core/infrastructure/vm-processing/worker.py` | Best-behaved Model Router citizen platform-wide (zero cloud bypass) |
| Captain's Chair | *(owns nothing — by design)* | | |
| LifeOS | *(owns nothing — by design)* | | |

---

## 2. Cross-Workbench Contract Inventory

### Human Systems assessed context
Owner: `assessed-context.ts`. Purpose: small, freshness-aware capacity/posture/trajectory object. Read: `GET /api/human-systems/context`. Write: Human Systems only. Freshness: `fresh`/`stale`/`none` + a separate `has_checkin_today` (today-by-date, deliberately distinct from fresh-by-age). Unknown: no today-row → `UNKNOWN` posture, `low` confidence, never a guessed constrained posture. Consumers: Ready Room, Weekly Review — both through this contract, never raw `capacity_checkins` queries for posture (a distinct raw-evidence read for a different purpose in Weekly Review is legitimate, not a violation — see §8).

### Ready Room attention/execution summary
Owner: `personalTasks.ts`. Purpose: `ReadyRoomContext` (posture + capacityLimit) informs, never vetoes. Fails safe to `UNKNOWN`/cap-3 on any Human Systems read error. Write: Ready Room + Google Tasks sync (same table). Consumers: Weekly Review reads raw `personal_tasks` execution evidence directly (read-only, never mutates).

### Weekly Review accepted weekly context
Owner: `weekly-review/route.ts` + `weeklyReview.ts`. Persists accepted next-week posture/carry-forward/reflection (`weekly_reviews`, upsert by `week_start`). Fresh Human Systems evidence always outranks `priorWeek`'s planned posture for current-day decisions — explicit precedence, structurally separated.

### HQ Status summary (Captain's-Chair-ready)
Owner: `hqStatusInterpreter.ts`. `CaptainChairSummary` — posture, material degradations, needs-attention/unknown counts, freshness. Pure interpretation, no write authority. UNKNOWN/missing critical telemetry never resolves to NORMAL. **This mission's repairs:** (1) a confirmed-isolated single critical-job failure now holds at DEGRADED for one cycle instead of immediately escalating to ATTENTION; (2) a job that reported `ok` once and then silently stopped running is no longer trusted forever — `fetchStaleOkDomainKeys` reuses the pre-existing, already-mature `domain_heartbeat_latest` (singular) view's cadence-aware `is_stale` column to downgrade a stale `ok` to `unknown` (I4, resolved without writing any new cadence math — an existing, already-deployed signal source was wired in instead) (see §10).

### HQ Evolution opportunity/outcome summary
Owner: `scripts/self_improvement/opportunity_store.py` / `outcome_contract.py` / `outcome_evaluation.py`. Implementation success and improvement success are permanently distinct facts. Observation windows hard-gate evaluation timing (a `not_yet_ready`/`skip` result, never an early guess). Concurrent-change detection forces `inconclusive`. Zero import path from outcome code to `PolicyEngine`.

### Canonical Brief (OSINT) vs. Captain's Daily Brief
Two genuinely separate pipelines share the word "brief": the OSINT `intelligence_briefs`/`ResilienceBrief` (fortnightly-ish, cross-domain in name only — collects only OSINT/world-news sources) and the daily-consumed `captains_daily_briefs`/`CaptainBriefDocument` (deterministic, template-based, no LLM call in its core assembly). Telegram's manual `/brief` command renders the OSINT Brief verbatim; the scheduled 07:00 Telegram morning message goes through a **second LLM synthesis** (`daily_digest.py`) that re-narrates the Brief's own content — this is real, pre-existing architecture, not introduced by the three merged missions, and is flagged as a deferred consolidation candidate, not repaired here. The OSINT Brief's own overclaiming tagline ("across every domain") was corrected to its actual OSINT/world-news scope this mission (I1, resolved — `briefs/page.tsx`, `api/briefs/route.ts`, `workbenches.ts`).

### Emergency current posture
Owner: `alerts` table / `intelligence/emergency_alerts.py`. Per-alert `lastSeenAt`/`issuedAt`/`expiry` always shown, not just an `is_active` boolean. **This mission's repair:** Captain's Chair and LifeOS Hub's `useEmergencyAlerts()` now cross-checks the same collection-heartbeat freshness the Emergency Alert Hub workbench's own `CoveragePanel` already used, so "Clear" can never mean "we stopped checking a while ago" on those two surfaces (see §10). Confirmed this pipeline is deliberately not wired into either Brief — audited, not a defect, since neither Brief claims Emergency coverage (I2, resolved as ACCEPTABLE — see §9).

### Calendar upcoming commitments
Owner: `lib/google-calendar.ts`. Read: `/api/calendar/today`, `/api/calendar/upcoming`. 5-minute server-side cache; explicit `disconnected` state (HTTP 409), never a silently-empty/stale panel. **Not yet wired** into Brief/Ready Room/command-surface consumption — production-quality but isolated (kiosk + Content Workbench only today). Not one of this mission's 10 deferred items; noted here as a pre-existing observation, unchanged.

### Google Tasks / Ready Room state
Owner: `api/google-tasks/sync/route.ts`. `personal_tasks` remains the single canonical store; Google Tasks is explicitly "another capture surface," never a shadow store. Deletion-detection correctly distinguishes "removed on Google" (`abandoned`) from "completed." **This mission's repair:** the Ready Room page itself now shows an in-page sync-health indicator (`GET /api/ready-room/sync-status`, reusing `fetchAgentStatusEntries`) — the distinction already existed in the backend and in HQ Status, and is now surfaced on the page where a Captain would look for it in the moment (I6, resolved).

---

## 3. Freshness Semantics — cross-domain summary

| Domain | Can stale data silently look current? | Evidence |
|---|---|---|
| Human Systems | No | `has_checkin_today` distinct from age-based freshness; explicitly guarded with a code comment against exactly this bug |
| Ready Room | No | Surfaces Human Systems freshness into its own status sentence |
| Weekly Review | No | `priorWeek` explicitly labeled prior/historical; live posture always recomputed fresh |
| HQ Status (capability tone) | No | UNKNOWN/missing telemetry never resolves to NORMAL; a job that stopped heartbeating after one `ok` write is now caught too — downgraded to `unknown` via the pre-existing cadence-aware `is_stale` view (§9 I4, resolved) |
| HQ Evolution | No | Observation windows gate evaluation timing; concurrent-change detection forces INCONCLUSIVE |
| Emergency (Hub workbench) | No | `CoveragePanel` derives an explicit stale/degraded/unknown state from real collection heartbeats |
| Emergency (Captain's Chair / LifeOS Hub) | No — fixed this mission | Previously yes (no staleness check at all); now cross-checks the same heartbeat contract the Hub workbench uses |
| Canonical OSINT Brief | No — fixed this mission | `sources_failed`/`sources_stale` are computed and now surfaced to the one human-approval screen |
| Captain's Daily Brief | No — fixed this mission | Pipeline now computes and persists `evidence_window_hours` + `collection_caveat` per brief (migration 0194); a genuinely quiet collection period and a silently-failed one are no longer indistinguishable (I7, resolved) |
| Calendar | No | Explicit `disconnected` state, never silently stale |

## 4. Unknown/Unavailable Semantics — cross-domain summary

Every domain audited (8 distinct domains: Human Systems freshness/confidence,
HQ Status capability/posture, source health, Emergency source coverage,
Weekly Review evidence, Evolution outcome evaluation) maps a genuinely
unknown/no-data state to `unknown`/`inconclusive`/a conservative default —
**never** to `healthy`/`normal`/`no_change`. Confirmed via the actual code
branch that fires in each case, not by assertion.

One adjacent (but distinct) weakness, now fixed: the Captain's weekly
Telegram health report previously rendered a genuinely-quiet week and a
week where the Sunday 02:00 health-OSINT collector silently failed
identically ("No signals collected this week."). This was a
**failure-propagation** gap (I3), not an unknown-mapped-to-healthy defect —
no code path there ever asserted "healthy" — but the reader couldn't tell
the two states apart. `captains_brief.py`'s `_health_osint_collector_caveat()`
now checks the collector's own heartbeat and appends an explicit caveat
when the empty week coincides with a collection failure, distinguishing it
from an honestly quiet week (I3, resolved).

## 5. Attention Semantics — cross-domain summary

Platform-level definition, confirmed consistently applied: **"a material
issue, commitment or decision that genuinely requires TJR's involvement"**
— explicitly not every failed job, open task, unread intelligence item,
Evolution finding, waiting item, source failure, or calendar event.

- HQ Status: `needsAttentionCount` counts only critical+unavailable capabilities, never raw failure volume — and (this mission) never a single unconfirmed-isolated failure either.
- Intelligence/Health OSINT: a curated single top signal, explicitly rejecting a raw count ("reads as noise, not a curated signal").
- Attention Engine: a dual-threshold gate (importance≥75 AND confidence≥70 simultaneously) — deliberately conservative.
- One conflated, non-compliant mapping was found (`/api/home/needs-attention`, which counts stale source health as "needs attention") but it is **dead code** — the only page that called it was retired in a 2026-08 UX pass, zero live callers confirmed. Recommend deletion in a future pass to prevent silent re-conflation if ever revived; not touched this mission (out of scope, no live risk).

## 6. Authority Boundaries

Platform-wide Authority Firewall audit result: **no live, reachable P0
found.** Every AI/LLM touchpoint traced either (a) only ever feeds a human
decision or a separately-gated deterministic step, or (b) has a
Captain-documented, conservative safety valve.

- **HQ Evolution:** confirmed no path from `outcome_evaluation.py` to `PolicyEngine`; `REGRESSED` never triggers rollback; a prior `IMPROVED` outcome never changes a new candidate's automation eligibility.
- **Mission creation / publishing:** a real, historical P0 (MSN-0352 — an LLM action executing the instant it appeared in a streamed response) was already found and repaired with a propose→approve gate before this mission began. Both paths are now PASS.
- **Health signal curation** (`tools/health-osint/health_signal_curation.py`): the LLM's PUBLISH/REJECT/ESCALATE judgment directly flips `suppressed`/`auto_ingest_reviewed` with no separate deterministic gate — on first read this looks like exactly the pattern §14 warns about. On closer inspection (this session's own judgment call, going beyond the sub-audit's initial flag): this is a Captain-directly-requested automation (documented in the file's own header — a 141-signal manual-review backlog that was never actually happening), the writes are reversible metadata flags on rows that still exist (not deletion), and ESCALATE — the default for anything the model isn't confident about — leaves the row exactly as ingestion left it, still in the human queue. Reclassified **PASS/ACCEPTABLE**, not a repair item: it matches the ALLOWED "evaluate bounded qualitative evidence" pattern, not the forbidden "declare uncertain safety safe" pattern. It did bypass Model Router entirely (calls `provider_chain` directly) — **fixed this mission**: `_classify()` now tries Model Router first (`health-signal-curation` task added to `TASK_POLICY`/`route_map`), falling back to the existing direct-provider chain only if the router itself is unreachable, matching the platform's Tier-0 local-first pattern (I9, resolved).
- **Ready Room "Unstick Me" (task decomposition):** Model Router output is always an editable suggestion, only written after an explicit human "Start here" click.
- **Emergency severity:** official tiers come verbatim from jurisdictional feeds; routing/urgency decisions are computed from the official field, never the LLM's prose. **This mission's repair:** the hourly digest email's LLM summary is not required to preserve exact official wording — now followed by a verbatim official-wording section for any urgent-tier alert, so official wording survives regardless of paraphrase (§10).
- **Weekly Review posture:** reference-quality implementation of "never turn correlation into causal fact" — cited as the pattern other domains should be measured against.
- `scripts/self_improvement/policy.py`'s `automation_eligibility` takes the LLM's own self-reported `confidence` as an input to a separately-gated deterministic threshold. Re-audited this mission (I8): the logic is a downgrade-only ratchet — a category's deterministic ceiling can only ever be lowered by low confidence/weak evidence, never raised above it, so the LLM cannot inflate its own authority. No behavior change was needed; added a clarifying docstring and two regression tests (`test_policy_confidence_cannot_raise_eligibility`, `test_policy_low_confidence_downgrades_an_auto_eligible_category`) locking this invariant in, on top of the pre-existing mandatory human-approval gate (I8, resolved — confirmed safe, hardened with tests).

## 7. Morning Operating Sequence (actual runtime order, Australia/Melbourne)

| Time | Job |
|---|---|
| 02:00 | Brief QA pre-screen |
| 03:00 | HQ Evolution self-improvement cycle (deploy timer) |
| 04:30 | `self-improving-system.timer` (legacy self-improvement daemon) — **moved this mission from 07:00** (I5, resolved) |
| 05:00 | Downdetector threshold recompute |
| 06:00 | Daily source collection (Technical intelligence) + GitHub sync |
| 06:40 | Intelligence suppression audit |
| 06:45 | Mission registry sync, source fidelity audit |
| 07:00 | Morning Brief generation + Telegram delivery — sole occupant of this slot again, per §9 I5 |
| 07:00 | Fortnightly ORI brief (separate product) |
| 07:30 | Health-mission correlation |
| 12:30 / 18:00 | Midday / EOD brief |
| Continuous (15 min) | Emergency Alert Hub ingestion, all jurisdictions, 24/7 no pause |
| Continuous (hourly) | Emergency Alert Hub hourly summary email |
| Mon 04:00 | Weekly health synthesis (`weekly_health_synthesis` — cadence label corrected this mission, was wrongly "Sat 08:00") |
| Sun 02:00 | Health OSINT weekly fetch + auto-curation |
| Sun 03:00 | Episodic memory decay (added to HQ Status registry this mission) |

**I5 resolved:** `self-improving-system.timer` previously fired at 07:00, a
documented, acknowledged collision with `captains_morning_brief` (also
07:00) — two independent OS processes competing for CPU/DB/API headroom at
the single most safety-critical moment of the day. Moved to 04:30
Melbourne local: 1h clear of `hq-evolution.timer`'s own worst-case end,
30min clear of `health-intelligence-weekly.timer`'s Monday 04:00 slot, and
30min clear of the 05:00 downdetector recompute. `deploy/self-improving-system.timer`,
`deploy/hq-evolution.timer`'s header comment, and the `docs/self-improvement/`
docs were all updated to match.

No explicit dependency/readiness gate exists between the 06:00 collection
job and the 07:00 Morning Brief — an implicit ordering assumption, not
positively verified, but no evidence of it actually failing in practice was
found. Deferred (ACCEPTABLE, low confirmed risk) — not one of the 10
tracked deferred items.

## 8. Dependency Map / Data Access Efficiency

Single canonical owner confirmed for: tasks (`personal_tasks`), Human
Systems check-ins (`capacity_checkins`), heartbeats (`domain_heartbeats`,
one shared writer function), Evolution findings/outcomes, Weekly Review
records, Google Tasks sync state. Mission creation has two call sites
(human-gated route + AI-proposed/Captain-approved action) but both funnel
through the same table/ID-minting/registry conventions — a deliberate
dual-entry-point design, not a shadow store.

One documentation/architecture mismatch found and fixed this mission:
`assessed-context.ts`'s docstring absolutely claimed Weekly Review "is not
allowed to query capacity_checkins directly," while
`reviewHumanSystems()` legitimately does so for a distinct raw-evidence
rollup (never re-deriving posture). Scoped the docstring's claim precisely
rather than changing the (correct) code.

Knowledge Library's `processing_documents` status enum is independently
re-declared in both TypeScript and Python rather than sourced from one
shared contract — low risk today (small table, matches a DB CHECK
constraint on both sides), flagged as a gap to close before more Knowledge
Library consumers accrete. Not fixed this mission.

## 9. Deferred Gaps — All 10 Resolved This Mission

Originally logged as audit findings the mission's AUDIT FIRST rule required
classifying before touching any code. All 10 were subsequently worked
through the mission's PASS / REPAIR REQUIRED / ACCEPTABLE DEFERRED GAP
framework and closed out — 8 with an actual code/config/doc repair, 1
(I8) confirmed already-safe and hardened with tests rather than changed,
and 1 (I2) confirmed a deliberate design choice with no defect. None
remain outstanding.

| ID | Gap | Domain | Resolution |
|---|---|---|---|
| I1 | Canonical Brief's own tagline claimed cross-domain synthesis; `brief_generator.py` only ever collects OSINT/world-news sources | Briefs | **Fixed.** Tagline/description corrected to the Brief's actual OSINT/world-news scope in `briefs/page.tsx`, `api/briefs/route.ts`, `workbenches.ts`. |
| I2 | Emergency Alert Hub is not wired into the canonical Brief at all | Emergency / Briefs | **Audited, no defect (ACCEPTABLE).** Confirmed the Brief never claims Emergency coverage anywhere in its UI or API surface, so there is no false-currency risk. Emergency has its own dedicated, freshness-guarded surfaces (Hub workbench, and now Captain's Chair/LifeOS per this mission's I2-adjacent fix). No code change made. |
| I3 | The Captain's weekly Telegram health report couldn't distinguish a genuinely quiet health-OSINT week from a week the Sunday collector silently failed for all 7 days | Health OSINT / Briefs | **Fixed.** `captains_brief.py`'s `_health_osint_collector_caveat()` checks the collector's own heartbeat and appends an explicit caveat when an empty week coincides with a collection failure. |
| I4 | HQ Status: a job that heartbeats `ok` once and then silently stops running was never re-flagged — `domain_heartbeats_latest` returned that stale `ok` row forever | HQ Status | **Fixed.** `fetchStaleOkDomainKeys` reuses the pre-existing, already-mature `domain_heartbeat_latest` (singular) view's cadence-aware `is_stale` column to downgrade a stale `ok` to `unknown` — no new cadence math was written, an already-deployed signal source was wired in instead. |
| I5 | A documented, unresolved 07:00 scheduling collision between the Morning Brief job and the separate `self-improving-system.timer` systemd unit | Platform / scheduling | **Fixed.** `self-improving-system.timer` moved to 04:30 Melbourne local, clear of `hq-evolution.timer`, `health-intelligence-weekly.timer`, and the 05:00 downdetector recompute. |
| I6 | Ready Room had no in-page indicator that Google Tasks sync was currently degraded | Ready Room | **Fixed.** New `GET /api/ready-room/sync-status` route (reusing `fetchAgentStatusEntries`) + `TodayStream.tsx` caveat surfacing the existing backend signal on the page itself. |
| I7 | Captain's Daily Brief pipeline computed no coverage/evidence-cutoff metadata at all | Briefs | **Fixed.** New `evidence_window_hours`/`collection_caveat` columns (migration 0194) computed and persisted per brief in `captains_brief.py`. |
| I8 | `scripts/self_improvement/policy.py`'s automation_eligibility takes the LLM's own self-reported confidence as an input | HQ Evolution | **Audited, confirmed safe, hardened (no behavior change).** The logic is a downgrade-only ratchet — confidence can only lower a category's deterministic ceiling, never raise it. Added a clarifying docstring and two regression tests locking the invariant in. |
| I9 | `tools/health-osint/health_signal_curation.py` bypassed Model Router (called `provider_chain` directly) | Health OSINT / Model Router | **Fixed.** `_classify()` now tries Model Router first (new `health-signal-curation` task in `TASK_POLICY`/`route_map`), falling back to the direct-provider chain only if the router is unreachable — the platform's standard Tier-0 local-first pattern. |
| I10 | Duplicate migration-number prefixes pre-existing on main (0095, 0096, 0145, 0189) | Platform hygiene | **Fixed.** All 4 groups resolved: 2 (0095, 0096) turned out to be leftover byte-identical duplicates of files a prior renumbering pass had already renamed (deleted); the other 2 (0145, 0189) renumbered to 0195/0196 by real chronological order (git/Supabase `list_migrations` timestamps), with the one live cross-reference updated. Confirmed cosmetic-only: Supabase tracks applied migrations by an independent timestamped version, never by this filename. |

## 10. Repairs Made This Mission

1. **HQ Status ATTENTION false-escalation (P1):** a confirmed-isolated single critical-job failure (immediately preceding heartbeat was `ok`) now holds at DEGRADED for one cycle instead of escalating straight to ATTENTION. Ambiguous/persistent failures still escalate exactly as before — fail-safe by default.
2. **Captain's Chair / LifeOS Hub emergency alert staleness (P0/P1):** `useEmergencyAlerts()` now cross-checks per-source collection heartbeats (reusing the Emergency Alert Hub workbench's own contract) so "Clear" can never mean "we stopped checking a while ago."
3. **Scheduler/registry drift (3 items):** `hq_evolution_cycle` added to `SCHEDULER_JOBS`; `google_tasks_sync` and `episodic_memory_decay` seeded into `domain_registry` (migration 0193); `episodic_memory_decay` also added to `SCHEDULER_JOBS`; `weekly_health_synthesis`'s cadence label corrected from a nonexistent "Sat 08:00" to its real Monday 04:00 trigger.
4. **Stale labels / broken link / doc drift:** 3 user-facing "Agent & Job Status" strings updated to "HQ Status"; a dead `/comms-studio` link removed from Mission detail; `docs/LIVE-WORKBENCHES.md` resynced to the actual 14-entry registry (was missing 2 rows, had 2 stale titles).
5. **Official emergency wording preservation (P1):** the hourly digest email now appends a verbatim official-wording section for any urgent-tier alert, regardless of how the LLM's summary paraphrases it.
6. **Model Router URL default (P2):** `intelligence/config.py` was the only caller defaulting to the wrong port (8080 vs. the router's real 8891) — fixed.
7. **Brief coverage/freshness visibility (P2):** `sources_failed`/`sources_stale` — already computed, never surfaced — now shown on the one screen with a human approval gate.
8. **HQ Status recovery propagation (P2):** the Status tab now polls every 30s (matching this workbench's own existing Jobs-tab convention) instead of fetching once on mount, so recovery is reflected without a manual reload.
9. **Documentation accuracy (P3):** scoped an overclaiming docstring in `assessed-context.ts` to match the actual, correct code rather than changing the code to match an overstated claim.
10. **Canonical Brief tagline overclaim (I1):** corrected "across every domain"-style wording to the Brief's actual OSINT/world-news scope in `briefs/page.tsx`, `api/briefs/route.ts`, and `workbenches.ts`.
11. **Health-OSINT weekly-digest silent-failure conflation (I3):** `captains_brief.py`'s new `_health_osint_collector_caveat()` distinguishes a genuinely quiet week from a week the Sunday collector silently failed, appending an explicit caveat to the Telegram digest and to `_collection_coverage_caveat()`'s Captain's Daily Brief equivalent.
12. **HQ Status stale-`ok`-forever gap (I4):** `fetchStaleOkDomainKeys` downgrades a job's stale-but-still-`ok` heartbeat to `unknown` by reusing the pre-existing `domain_heartbeat_latest` (singular) view's cadence-aware `is_stale` column — no new cadence math introduced.
13. **07:00 scheduling collision (I5):** `self-improving-system.timer` moved to 04:30 Melbourne local; `hq-evolution.timer`'s header comment and the `docs/self-improvement/` docs updated to match.
14. **Ready Room Google Tasks sync-health indicator (I6):** new `GET /api/ready-room/sync-status` route + `TodayStream.tsx` caveat.
15. **Captain's Daily Brief coverage/evidence-cutoff metadata (I7):** new `evidence_window_hours`/`collection_caveat` columns (migration 0194), computed and persisted per brief.
16. **PolicyEngine confidence-coupling hardening (I8):** confirmed the existing downgrade-only ratchet is already safe; added a clarifying docstring and 2 regression tests, no behavior change.
17. **Health signal curation Model Router bypass (I9):** `_classify()` now tries Model Router first, falling back to the direct-provider chain only if the router itself is unreachable.
18. **Migration renumbering (I10):** deleted 2 leftover byte-identical duplicate files from a prior renumbering pass (0095, 0096); renumbered the other 2 duplicate-prefix files (0145→0195, 0189→0196) by real chronological order, with the one live cross-reference updated.

Confirmed as audited-with-no-defect, no code change: Emergency Alert Hub's
deliberate non-integration with the canonical Brief (I2) — see §9.

All repairs are additive/backward-compatible; full test suites (Python + Vitest), typecheck, lint, and the 3 CI gate scripts remain green after every change (see final validation in the closeout report).

## 11. Captain's Chair Readiness Matrix

| Domain | Classification | Canonical owner | Read boundary | Freshness | Unknown behaviour | Attention meaning | Write authority |
|---|---|---|---|---|---|---|---|
| Human Systems | READY TO CONSUME | `capacity_checkins` via `assessed-context.ts` | `GET /api/human-systems/context` | fresh/stale/none + has_checkin_today | UNKNOWN posture, low confidence | n/a (informs, doesn't gate) | Human Systems only |
| Ready Room | READY TO CONSUME | `personal_tasks` via `personalTasks.ts` | in-process `getReadyRoomContext()` | inherits Human Systems freshness | fails safe to UNKNOWN/cap-3 | pinned items = explicit human attention already acted on | Ready Room + Google Tasks sync |
| Weekly Review | READY TO CONSUME | `weekly_reviews` via `route.ts` | `GET/POST /api/weekly-review` | priorWeek explicitly historical; live posture always fresh | unavailable signals return null, never false-zero | n/a | Weekly Review only |
| HQ Status | READY TO CONSUME | `domain_heartbeats*` via `hqStatusInterpreter.ts` | `GET /api/agent-status-workbench/overview` → `captainSummary` | isolated-failure repair + stale-`ok` downgrade both in place (§9 I4) | UNKNOWN never resolves to NORMAL | `needsAttentionCount` = critical+unavailable, confirmed-isolated failures excluded | none (read-only interpreter) |
| HQ Evolution | READY TO CONSUME | opportunity/outcome store | `/api/self-improvement/evolution-summary` | observation windows gate evaluation | weak/confounded evidence → INCONCLUSIVE | n/a (not a user-attention queue) | existing PolicyEngine pipeline only |
| Canonical OSINT Brief | READY TO CONSUME | `intelligence_briefs` via `brief_generator.py` | `/api/intelligence-workbench/brief` | coverage now surfaced to reviewers (§10) | n/a | n/a | Brief pipeline only, human approval gate before publish |
| Captain's Daily Brief | READY TO CONSUME | `captains_daily_briefs` via `captains_brief.py` | `/api/captains-daily-brief` | `evidence_window_hours`/`collection_caveat` now computed and persisted per brief (§9 I7) | n/a | n/a | Brief generation job only |
| Emergency | READY TO CONSUME | `alerts` via `emergency_alerts.py` | `/api/emergency-alerts`, `/api/emergency-alerts/sources` | Hub workbench always had staleness detection; Captain's Chair/LifeOS Hub fixed this mission | per-alert `lastSeenAt` always shown; freshness never silently "current" | n/a (severity-driven, not attention-count-driven) | ingestion job only |
| Calendar | READY WITH CAVEAT (not yet wired) | `google_calendar_tokens` via `google-calendar.ts` | `/api/calendar/today`, `/api/calendar/upcoming` | explicit `disconnected` state, 5-min cache | n/a | n/a | kiosk/Content Workbench write paths only |
| Google Tasks / execution integration | READY TO CONSUME (as part of Ready Room) | see Ready Room row | | | | Ready Room page now shows its own sync-health indicator (§9 I6) | |

## 12. LifeOS Readiness Notes

Upstream inputs LifeOS will need are honestly available:
- **Day/date/time, current command posture:** derivable from Human Systems + HQ Status contracts above, both READY.
- **Next important commitments:** Calendar's data layer is production-quality but not yet wired into any cross-domain command surface — LifeOS Hub's own `useEmergencyAlerts`/`useAgentHealth`/etc. hooks already consume some of these independently (confirmed working in this mission's fix), but a genuine "next commitments" feed spanning Calendar + Ready Room + Weekly Review does not exist yet and is explicitly LifeOS/Captain's Chair's own future synthesis work, not something this mission was asked to build.
- **Small Needs You count/list:** HQ Status and Emergency both now have honest, non-inflated attention semantics (§5, §10) suitable for this. Ready Room's "needs attention" mapping (pinned/urgent tasks) was confirmed correctly scoped in the Human Execution Loop audit.
- **Intelligence headline/posture:** both the Canonical OSINT Brief and the Captain's Daily Brief (the artifact actually read each morning) are READY TO CONSUME — both now carry coverage/freshness metadata (§9 I7) LifeOS can surface alongside the headline itself rather than assume.
- **HQ health:** READY TO CONSUME (§9 I4).
- **Small Evolution opportunity signal:** READY TO CONSUME.

This mission does not build LifeOS's synthesis — it confirms the upstream
inputs can support it honestly. All 10 deferred gaps named during this
audit (§9) are now resolved; no outstanding caveat blocks LifeOS from
consuming any of the contracts above.
