# Mission 5 — 50-Accommodation Reconciliation

**Status: rows 1–50 now identified.** The literal "original 50
accommodations" list did not exist anywhere in this repository's reachable
git history at the time of initial discovery. The closest repository
artifact was a 37-item draft matrix at
`docs/architecture/ADHD-ACCOMMODATION-DISCOVERY.md` on the orphaned,
never-merged branch `origin/claude/tjr-adhd-accommodation-discovery-aike59`
(commit `7dc1f0a59`), whose own author stated it was incomplete. A second,
narrower 11-item matrix exists in
`knowledge/missions/MISSION-3-CAPTURE-REMEMBER-FOLLOWTHROUGH-knowledge-record.md`
(§L), scoped only to items Mission 3 explicitly named — it does not add new
titles beyond the 37-item draft, only independent status confirmations for a
subset, folded in below.

Items 38–50 were subsequently supplied directly by the Captain as the
programme's authoritative list for this range (final closure directive,
2026-09-19). They are recorded here as **programme-spec-only** — classified
honestly against current repository state, with no implementation evidence
invented for them. This mission did not build anything new to make items
38–50 appear more complete than they are; several are correctly classified
as outside HQ's remit entirely.

Rows 1–37 are the 37-item draft's content, carried in as real
repository-evidence and re-verified against current code where the task
called for it (see "Verification" column). Rows 38–50 are the Captain-supplied
titles, classified using the same taxonomy.

| # | Accommodation | Source | Status | Evidence-aware? | Citation | Verification |
|---|---|---|---|---|---|---|
| 1 | Capture any thought instantly, from anywhere | repo-evidence-37 | IMPLEMENTED | n/a | `core/capture/enrichment_worker.py`; `captured_items` (Telegram voice/text + web) | relied on source doc, unverified this session |
| 2 | Externalise "don't forget" items so they resurface at the right time | repo-evidence-37 | IMPLEMENTED | yes — Mission 3 closed the capture→`personal_tasks` gap the source doc flagged as PARTIAL; routed items reach `follow_through_engine.py`'s nudge cycle | `core/capture/enrichment_worker.py:323-408` (`_route_actionable_capture`, unique index via migration 0217) | personally re-checked: upgraded from source doc's PARTIAL |
| 3 | See only what's relevant right now, not the whole backlog | repo-evidence-37 | PARTIALLY IMPLEMENTED | no | Number One health-adjusted queue; Weekly Review "You Can Ignore"; Captain's Chair `commandState.ts` | relied on source doc, unverified this session |
| 4 | A single place to look for "what did I decide/commit to" | repo-evidence-37 | PARTIALLY IMPLEMENTED | no | `decide_ledger` canonical; `decisions`/`decision_records`/`commander_decisions` still overlapping | relied on source doc, unverified this session |
| 5 | Passive reminders for appointments without manual entry | repo-evidence-37 | PARTIALLY IMPLEMENTED | no | Google Calendar OAuth (read-only); separate appointment-prep cron table | relied on source doc, unverified this session |
| 6 | Time-blindness aids (what time is it, how long until X) | repo-evidence-37 | NATIVE PLATFORM | n/a | none — native iOS/Watch better | relied on source doc, unverified this session |
| 7 | A single canonical "todo" that doesn't require deciding where something belongs | repo-evidence-37 | PARTIALLY IMPLEMENTED | yes — same Mission 3 routing fix as #2 narrows this, but 6 distinct task-like models (`personal_tasks`, `captured_items`, Command Centre `missions`, `comms_content`, `intelligence_notes`, `shopping_list_items`) still exist unconsolidated | `core/capture/enrichment_worker.py:323-408` | personally re-checked: routing gap closed, model consolidation gap remains |
| 8 | Break an overwhelming task into a single next tiny step | repo-evidence-37 | IMPLEMENTED | yes — now has an evidence-tracked intervention identity | Ready Room "UNSTICK ME" / `DecomposeView.tsx` via `/api/ready-room/decompose`; `capacity_interventions` row `rr_unstick_me` / `rr_decompose_one_action`, domain='ready_room' (migration `0218_mission5_evidence_domain_generalisation.sql:145-148`) | personally re-checked this session |
| 9 | Gentle vs. persistent nudge intensity per task | repo-evidence-37 | IMPLEMENTED | no | `personal_tasks.follow_through_mode` (gentle/normal/persistent/deadline/waiting) | relied on source doc, unverified this session |
| 10 | Body-doubling / accountability for starting a task | repo-evidence-37 | EXTERNAL/HUMAN | n/a | none found — human/physical better | relied on source doc, unverified this session |
| 11 | Reduce number of choices when capacity is low | repo-evidence-37 | PARTIALLY IMPLEMENTED | no | `core/coordination/recommendation_engine.py:rank_missions`; Number One top-N cap | relied on source doc, unverified this session |
| 12 | Snooze/defer without losing the item | repo-evidence-37 | IMPLEMENTED | n/a | `personal_tasks.next_review_at`/`snoozed_until` | relied on source doc, unverified this session |
| 13 | Detect a stalled task and offer help, not shame | repo-evidence-37 | IMPLEMENTED | yes — Mission 4's "Pick Up Banner" interruption-recovery flow is now an evidence-tracked intervention | `intelligence/adhd/follow_through_engine.py` stall detection; `capacity_interventions` row `rr_interruption_recovery`, domain='ready_room' (migration 0218:151-152) | personally re-checked this session |
| 14 | Auto-defer non-essential work under low capacity | repo-evidence-37 | IMPLEMENTED | yes | `platform-runtime/lib/daily_ops_cycle.py:_step_human_systems` now passes the real `missions` list into `CapacityGate.evaluate()` (was a hardcoded `[]`) | `platform-runtime/lib/daily_ops_cycle.py:164-184,1589`; fixed by commit `b742816e1` ("fix(mission1): confirmed foundation defects — capacity gate...") | **DRIFT FOUND** — source doc (8 days old) says "🟡 broken / empty-list bug"; personally re-checked and confirmed FIXED, but by Mission 1, not Mission 5, on 2026-09-19 |
| 15 | Daily capacity check-in (green/amber/red) | repo-evidence-37 | IMPLEMENTED | n/a | `capacity_checkins`, `capacitybot` | relied on source doc, unverified this session |
| 16 | Capacity changes what's recommended, not just what's shown | repo-evidence-37 | PARTIALLY IMPLEMENTED | n/a | `recommendation_engine.py:rank_missions` (live in one place, not all surfaces) | relied on source doc, unverified this session |
| 17 | Track what interventions actually help | repo-evidence-37 | IMPLEMENTED | yes | `capacity_interventions` / `capacity_intervention_events` (migrations 0151, 0157, 0202), now domain-generalised to also cover `ready_room` (migration `0218_mission5_evidence_domain_generalisation.sql:23-40`) — this is Mission 5's own delivered work this session, currently uncommitted in the worktree | personally re-checked this session |
| 18 | Self vs. system-calculated capacity comparison | repo-evidence-37 | IMPLEMENTED | n/a | `capacity_calibration` | relied on source doc, unverified this session |
| 19 | Recovery-aware "sanctuary" low-stimulation mode | repo-evidence-37 | IMPLEMENTED | n/a | LifeOS Hub self-quiets under PROTECT/RECOVER | relied on source doc, unverified this session |
| 20 | One voice narrating "how am I doing," not three | repo-evidence-37 | PARTIALLY IMPLEMENTED | no | XO bot, `wellness_officer`, `recovery_officer` still independently narrate the same data (duplication, not a missing capability) | relied on source doc, unverified this session |
| 21 | Reduce notification volume under high capacity load | repo-evidence-37 | PARTIALLY IMPLEMENTED | no | `notify()` has severity levels; no capacity-based volume throttle found | relied on source doc, unverified this session |
| 22 | Focus/DND session support | repo-evidence-37 | NATIVE PLATFORM | n/a | none — iOS Focus Mode better | relied on source doc, unverified this session |
| 23 | Sensory/stimulation state tracking | repo-evidence-37 | IMPLEMENTED | no | `capacity_checkins` sensory-regulation fields (migration 0158) | relied on source doc, unverified this session |
| 24 | Distraction "what should I do instead" helper | repo-evidence-37 | IMPLEMENTED | no | `telegram-bots/capacitybot/distract.py` | relied on source doc, unverified this session |
| 25 | Meal/hydration reminders | repo-evidence-37 | EXTERNAL/HUMAN | n/a | none — native/physical better | relied on source doc, unverified this session |
| 26 | Shopping/errand capture that isn't a full task | repo-evidence-37 | PARTIALLY IMPLEMENTED | n/a | `shopping_list_items` (gift/wishlist-scoped only) | relied on source doc, unverified this session |
| 27 | Simple daily-living checklist under low capacity (Red) | repo-evidence-37 | DEFERRED | n/a | nothing dedicated found; recommended as a small future build | relied on source doc, unverified this session |
| 28 | Exercise/movement logging | repo-evidence-37 | IMPLEMENTED | n/a | `physical_workout_sessions`, Physical Readiness workbench | relied on source doc, unverified this session |
| 29 | Breathing/regulation exercise prompt | repo-evidence-37 | EXTERNAL/HUMAN | n/a | none — Watch/native or human/physical better | relied on source doc, unverified this session |
| 30 | Decompression suggestion when overloaded | repo-evidence-37 | PARTIALLY IMPLEMENTED | yes — Ready Room's overload-reduction sequence is now a named, evidence-tracked intervention, but it is scoped to Ready Room task-overload, not a general "I feel overloaded" surface | `capacity_interventions` row `rr_overload_reduction` ("This feels like too much"), domain='ready_room' (migration 0218:149-150) | personally re-checked this session: upgraded citation, status unchanged (still partial — general/non-task-specific decompression still absent) |
| 31 | Delay sending an emotionally-charged message | repo-evidence-37 | EXTERNAL/HUMAN | n/a | none found; native OS "undo send" is the better fit | relied on source doc, unverified this session |
| 32 | Crisis/PEM-style pacing support | repo-evidence-37 | IMPLEMENTED | no | `telegram-bots/revs` (pacing, PEM, crisis layer) | relied on source doc, unverified this session |
| 33 | Rejection-sensitivity-aware framing in feedback loops | repo-evidence-37 | PARTIALLY IMPLEMENTED | no | Weekly Review avoids framing non-completion as failure (principle exists, not generalised) | relied on source doc, unverified this session |
| 34 | Evidence of wins/progress, not just backlog | repo-evidence-37 | IMPLEMENTED | check against Mission 5's other implementation streams, not independently verified here | `lcars-portal/src/app/human-systems-workbench/_components/RecoveryView.tsx:442-451` now renders `data.wellness.wins` (sourced from `health_insights.wins_this_week`) | **DRIFT FOUND** — source doc says "🟡 partial, data exists but no view"; personally re-checked and found `captains_log_entries.wins`-derived data IS now surfaced in Human Systems Workbench's Recovery view. Could not establish from this pass alone which mission shipped it (file predates this worktree's own commits, i.e. it was already on the baseline branch) |
| 35 | Weekly reflective retrospective | repo-evidence-37 | IMPLEMENTED | n/a | Weekly Review workbench | relied on source doc, unverified this session |
| 36 | Track whether a recommendation/decision was actually good | repo-evidence-37 | IMPLEMENTED | yes | `insight_outcomes` (migrations 0062, 0137, 0215); Advisory outcome-tracking | relied on source doc for the Advisory-side claim; `insight_outcomes` table lineage personally re-checked this session |
| 37 | Voice-based end-of-day debrief | repo-evidence-37 | IMPLEMENTED | no | XO Telegram `debrief_engine.py` | relied on source doc, unverified this session |
| 38 | Boredom / unstructured space | programme-spec-only | NATIVE PLATFORM | n/a | none — unstructured downtime is an absence of a task, not a software feature; better served by not prescribing anything | classified honestly, no implementation evidence invented |
| 39 | Contextual outfits | programme-spec-only | EXTERNAL/HUMAN | n/a | none — physical/wardrobe, outside any digital platform's remit | classified honestly, no implementation evidence invented |
| 40 | Write instead of talk when activated | programme-spec-only | NATIVE PLATFORM | n/a | the whole platform is text-first (Telegram/Ready Room capture) by default design, not a dedicated accommodation feature — same "capture anytime" infrastructure as #1, but this item is about a communication *preference*, not a capture mechanism | classified honestly, no new feature invented; not double-counted as IMPLEMENTED since nothing was built specifically for this |
| 41 | Let others process differently | programme-spec-only | EXTERNAL/HUMAN | n/a | none — interpersonal/relational, not a platform concern | classified honestly, no implementation evidence invented |
| 42 | Delay emotional responses | programme-spec-only | EXTERNAL/HUMAN | n/a | none found; same category as #31 (delay-send) — native OS "undo send" is the better fit, not a TJR HQ feature | classified honestly, no implementation evidence invented |
| 43 | "Feedback not failure" framing | programme-spec-only | PARTIALLY IMPLEMENTED | no | same partial evidence as #33 — Weekly Review avoids framing non-completion as failure as a general principle, not yet generalised across every surface | reused #33's existing citation, not fabricated new evidence |
| 44 | Understand rejection response | programme-spec-only | PARTIALLY IMPLEMENTED | no | same as #33 — RSD-aware framing exists as a stated principle in Weekly Review, not a dedicated "understand my rejection response" capability | reused #33's existing citation, not fabricated new evidence |
| 45 | Notes instead of interrupting | programme-spec-only | IMPLEMENTED | no | same capture infrastructure as #1 — async note capture (Telegram voice/text, `captured_items`) already lets the Captain leave a note without interrupting a task | reused #1's existing citation; not a dedicated new feature, an existing capability applied to this use case |
| 46 | Disclose ADHD where useful | programme-spec-only | EXTERNAL/HUMAN | n/a | none — a Captain-to-other-people disclosure decision, not appropriate for HQ to automate or template | classified honestly, no implementation evidence invented |
| 47 | Disclose reduced capacity / emotional state | programme-spec-only | EXTERNAL/HUMAN | n/a | none — same as #46, a disclosure to other people, not a platform feature; HQ tracks the Captain's own capacity internally but does not manage external disclosure of it | classified honestly, no implementation evidence invented |
| 48 | Evidence library | programme-spec-only | IMPLEMENTED | yes | this is the one item in 38–50 with genuine, direct repository evidence: Human Systems Workbench's `WhatHelpsMeCard.tsx`/`WhatHelpsView.tsx` + `intervention-effectiveness.ts`, now extended this mission to cover `domain='ready_room'` via `support-effectiveness/route.ts` | personally verified this session — this is exactly what Mission 5 built/extended, not a coincidental prior match |
| 49 | Avoid rigid diet systems | programme-spec-only | NOT APPROPRIATE FOR HQ | n/a | none, deliberately — this reads as a guardrail against building something (a rigid tracking/compliance system), consistent with Mission 5 §27's own "no productivity/compliance scoring" principle, not a capability gap to fill | classified honestly, no implementation evidence invented |
| 50 | Permission to stop chasing normal / design around the brain | programme-spec-only | NATIVE PLATFORM | n/a | this is the whole platform's founding design philosophy (accommodation-first, "past effectiveness is evidence not command," never turning adaptation into control — Mission 5's own §2/§29) rather than a discrete feature; it is embodied throughout, not owned by any one component | classified honestly — a principle already structurally present, not something to build as a standalone feature |

## Notes on cross-check against the Mission 3 11-item matrix

The Mission 3 knowledge record's own 11-item matrix (§L) does not name any
accommodation not already present in the 37-item draft above; it independently
confirms IMPLEMENTED/PARTIALLY IMPLEMENTED status for capture (#1/#2/#7),
task-starting support (#8), accountability/follow-through (#9/#13), and
explicitly defers "planning tomorrow" and "reduced-capacity disclosure" framing
to Mission 4/prior missions. No new rows were added from it; it was used only
to corroborate rows above (particularly #1, #2, #7, #13).

## Summary counts — all 50 items

Rows 1–37 (repository-evidence draft):
- IMPLEMENTED: 19 (#1, 2, 8, 9, 12, 13, 14, 15, 17, 18, 19, 23, 24, 28, 32, 34, 35, 36, 37)
- PARTIALLY IMPLEMENTED: 11 (#3, 4, 5, 7, 11, 16, 20, 21, 26, 30, 33)
- NATIVE PLATFORM: 2 (#6, 22)
- EXTERNAL/HUMAN: 4 (#10, 25, 29, 31)
- DEFERRED: 1 (#27)
- Total: 37 ✓

Rows 38–50 (Captain-supplied, programme-spec-only):
- IMPLEMENTED: 2 (#45, #48)
- PARTIALLY IMPLEMENTED: 2 (#43, #44)
- NATIVE PLATFORM: 3 (#38, #40, #50)
- EXTERNAL/HUMAN: 5 (#39, #41, #42, #46, #47)
- NOT APPROPRIATE FOR HQ: 1 (#49)
- Total: 2+2+3+5+1 = 13 ✓

**All 50 items now classified.** Of the 13 Captain-supplied items, only 2
(#45, #48) map onto genuine existing/extended repository capability; 3 are
foundational design principles rather than discrete features (#38, #40,
#50); 5 are correctly out of scope for HQ entirely (interpersonal/physical
disclosure or preference, not a software gap); 1 is explicitly a guardrail
against building something (#49), consistent with Mission 5's own
no-compliance-scoring principle. Nothing was invented or retrofitted to make
this range look more complete than it is.

- **Of the 19 IMPLEMENTED in rows 1–37, 2 were upgraded this session from the
  source doc's PARTIAL/broken classification after independent
  re-verification (#14, #34), and 1 (#2) plus 1 partial-improvement (#7) were
  upgraded per Mission 3's own confirmed fix.**

## Closure note

The open question this document previously carried — "where is the actual
50-item list" — is resolved: the Captain supplied items 38–50 directly as
part of the Mission 5 final closure directive (2026-09-19). This
reconciliation is complete for all 50 items. Reconciliation completion does
not imply every accommodation belongs inside TJR HQ, and does not convert
this matrix into an automatic feature backlog — several items above are
correctly EXTERNAL/HUMAN, NATIVE PLATFORM, or NOT APPROPRIATE FOR HQ by
design, not by omission.
