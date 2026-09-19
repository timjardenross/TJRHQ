# Mission 5 — 50-Accommodation Reconciliation (Provisional)

**Status: OPEN ITEM, not a closed reconciliation.** The literal "original 50
accommodations" list does not exist anywhere in this repository's reachable
git history (confirmed by repository discovery). The closest artifact is a
37-item draft matrix at `docs/architecture/ADHD-ACCOMMODATION-DISCOVERY.md`
on the orphaned, never-merged branch `origin/claude/tjr-adhd-accommodation-discovery-aike59`
(commit `7dc1f0a59`), whose own author states it is incomplete: *"remaining
items to reach 50 should be filled in once the Captain's actual list is
available."* A second, narrower 11-item matrix exists in
`knowledge/missions/MISSION-3-CAPTURE-REMEMBER-FOLLOWTHROUGH-knowledge-record.md`
(§L), scoped only to items Mission 3 explicitly named — it does not add new
titles beyond the 37-item draft, only independent status confirmations for a
subset, folded in below.

Per Captain-approved decision: the programme baseline **stays 50**, not 37.
Rows 1–37 below are the draft's content, carried in as real repository-evidence
and re-verified against current code where the task called for it (see
"Verification" column). Rows 38–50 are **explicitly unresolved** — no titles
are invented for them; they are placeholders awaiting the Captain's
authoritative source list. Closing that 13-item gap is an open item for the
Mission 5 knowledge record, not something this document resolves.

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
| 38 | UNKNOWN — item 38 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 39 | UNKNOWN — item 39 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 40 | UNKNOWN — item 40 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 41 | UNKNOWN — item 41 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 42 | UNKNOWN — item 42 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 43 | UNKNOWN — item 43 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 44 | UNKNOWN — item 44 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 45 | UNKNOWN — item 45 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 46 | UNKNOWN — item 46 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 47 | UNKNOWN — item 47 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 48 | UNKNOWN — item 48 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 49 | UNKNOWN — item 49 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |
| 50 | UNKNOWN — item 50 of 50, awaiting Captain's list | programme-spec-only | NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST | n/a | none | no repository evidence located, awaiting Captain's authoritative 50-item source list |

## Notes on cross-check against the Mission 3 11-item matrix

The Mission 3 knowledge record's own 11-item matrix (§L) does not name any
accommodation not already present in the 37-item draft above; it independently
confirms IMPLEMENTED/PARTIALLY IMPLEMENTED status for capture (#1/#2/#7),
task-starting support (#8), accountability/follow-through (#9/#13), and
explicitly defers "planning tomorrow" and "reduced-capacity disclosure" framing
to Mission 4/prior missions. No new rows were added from it; it was used only
to corroborate rows above (particularly #1, #2, #7, #13).

## Summary counts (rows 1–37 only; rows 38–50 are the open gap, counted separately)

- IMPLEMENTED: 19 (#1, 2, 8, 9, 12, 13, 14, 15, 17, 18, 19, 23, 24, 28, 32, 34, 35, 36, 37)
- PARTIALLY IMPLEMENTED: 11 (#3, 4, 5, 7, 11, 16, 20, 21, 26, 30, 33)
- NATIVE PLATFORM: 2 (#6, 22)
- EXTERNAL/HUMAN: 4 (#10, 25, 29, 31)
- DEFERRED: 1 (#27)
- Total rows 1–37: 19+11+2+4+1 = 37 ✓
- Rows 38–50 (13 rows): NO REPOSITORY EVIDENCE — AWAITING CAPTAIN LIST
- **Of the 19 IMPLEMENTED, 2 were upgraded this session from the source doc's PARTIAL/broken classification after independent re-verification (#14, #34), and 1 (#2) plus 1 partial-improvement (#7) were upgraded per Mission 3's own confirmed fix.**

## The single most important open question for the Captain

**Where is the actual 50-item list, and does it supersede or extend the
37-item draft?** Everything in this document downstream of that question is
provisional. Until the Captain supplies the authoritative list, rows 38–50
cannot be given real titles without either (a) fabricating plausible-sounding
accommodations that were never actually specified, which this document
deliberately refuses to do, or (b) the programme silently re-baselining to 37
and quietly dropping 13 items nobody has re-derived — which the Captain's own
decision explicitly rejected. This reconciliation should be treated as
**interim** and re-run in full once the source list surfaces.
