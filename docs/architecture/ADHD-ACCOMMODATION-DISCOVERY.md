# Digital Accommodation & Cognitive Support — Discovery Report

**Status:** Discovery only. No features were built or changed as part of this mission.
**Date:** 2026-09-18
**Scope:** Full-repository investigation of TJR HQ (`lcars-portal`, `core/`, `platform-runtime/`, `intelligence/`, `telegram-bots/`, `tools/supabase/schema`, `core/infrastructure/supabase/migrations`) against the proposed ADHD/AuDHD digital accommodation model.

**Method:** Eight parallel deep-read investigations covering (1) every Workbench, (2) Number One / XO / Captain's Chair orchestration, (3) capacity & health/wellness systems, (4) the ADHD/task/capture module family, (5) notifications/scheduling/calendar/timers/routines, (6) briefs & reflection systems, (7) the live database schema, and (8) PWA/mobile/iPad + feature flags + dead code. All findings below are grounded in code read during this investigation, cited by file path. Where a mission-required input (the literal 50-item accommodation list) was not supplied to this investigation, a representative set was constructed from the eight named categories and is flagged as such in Section B.

---

## Mission Completion Answer (read this first)

**How much of the digital accommodation system is already hiding inside TJR HQ?**

A great deal — more than a typical greenfield ADHD-app project would have after a year of building. Concretely, already live in production:

- A **live, hourly-scheduled follow-through/nudge engine** (`intelligence/adhd/follow_through_engine.py`) that reads a real ADHD-shaped task model (`personal_tasks`: urgency, importance, effort, `follow_through_mode`, `micro_action`), respects quiet hours and a daily send cap, and nudges via the one canonical notification pathway.
- A **live LLM task-decomposition endpoint** ("what's the one 5–15 min next step") wired into a real UI (Ready Room's "UNSTICK ME" mode), which explicitly has **no timers, streaks or scores by design** (`ActiveTaskView.tsx`).
- A **mature, multi-channel universal capture pipeline** (`captured_items`) fed by web, Telegram voice, and Telegram text, with an AI enrichment worker that auto-routes personal notes and knowledge items — already almost exactly the "Capture" layer the mission asks for.
- A **real, live capacity model** (`capacity_checkins` + companions) that already **changes mission ranking**, not just displays a score (`core/coordination/recommendation_engine.py:rank_missions`).
- A **recovery-posture-aware "sanctuary mode"** on the LifeOS Hub that self-quiets when capacity is low — this is GREEN/AMBER/RED-as-operating-input, already built, just not named that way everywhere.
- A **daily reflective journal with a `wins` field** that has existed for months and has never once been read back by anything (`captains_log_entries.wins`).
- A **complete, wired mobile alerts+decisions bottom-sheet** (`MobileAlertDrawer.tsx`) that is never mounted in any layout — a finished feature sitting completely unused.
- A **complete Telegram voice-capture pipeline** (transcribe → classify → route) with **no web-app equivalent** and no mention that it exists on the web side.

**What's missing is not capability — it's a reconciliation layer.** The single biggest structural problem this discovery surfaced is that TJR HQ currently computes "what matters right now" in **three to four independent, non-communicating places** (Captain's Chair's `commandState.ts`, Number One's coordination engine, the officer-layer XO synthesis, and a fourth Command Centre coordination API that is silently running on mock data). None of them talk to each other. Building a fifth would make this worse, not better.

**The smallest set of changes required** to make this feel like one coherent, capacity-aware system is described in Section I (Prioritised Gap Register) and Section J. In short: (1) pick one of the three-to-four priority engines as canonical and have the others defer to it or retire, (2) teach the capture enrichment worker one more routing rule so captures can become `personal_tasks`, (3) surface the `wins` field and Ready Room completions as a real Evidence view, (4) mount the mobile alert drawer that already exists, (5) fix one broken argument in `capacity_gate.py` that silently disables real Red-capacity mission deferral, and (6) stop three separate Telegram bots from independently narrating the Captain's wellness state. None of these are new systems.

---

## A. Existing Capability Inventory

### A.1 Workbenches (registry: `lcars-portal/src/lib/workbenches.ts`, `LIVE_WORKBENCHES`)

The 19 registered, currently-navigable workbenches, plus the legacy `(app)/*` route group (mostly retired redirect stubs, a handful of still-live niche tools):

| Workbench | Capability | Maturity | ADHD relevance |
|---|---|---|---|
| **LifeOS Hub** (`/hub`) | Ambient daily-glance surface reusing Captain's Chair synthesis; self-quiets into low-stimulation "sanctuary" mode under PROTECT/RECOVER posture | Fully implemented | High — capacity-gated cognitive-load reduction, already built |
| **Capture Workbench** (`/capture-workbench`) | Inbox triage for Telegram/Slack/API captures, proxies to Command Centre | Fully implemented (proxy) | Core Capture layer |
| **Captain's Chair** (`/captains-chair-workbench`) | Aggregator: recovery posture, missions, alerts, intelligence, "Needs You," reminders, notebook | Fully implemented, real data, no stubs | Core Now-layer candidate |
| **Mission Workbench** | All missions, capacity-cost filtered by recovery posture | Fully implemented | Capacity-aware filtering already live |
| **Weekly Review** | Cross-workbench synthesis of what happened/slipped/needs attention, reads ~17 tables | Fully implemented, real aggregation | Reflection loop, but backlog-biased by design |
| **Ready Room** (`/ready-room`) | DO / UNSTICK ME modes on `personal_tasks`; "the one next physical action," explicitly no timers/streaks/scores | Fully implemented | **The platform's direct ADHD/executive-function feature** |
| **Intelligence Workbench** / **Health OSINT Workbench** | External OSINT/research monitoring (cyber signals / health-research content) — NOT personal reflection despite naming | Fully implemented | None (confirm scope, avoid confusing with personal capacity) |
| **Emergency Alerts** | AU emergency info, attention-prioritised, mute/silence | Fully implemented | Notification-pattern precedent (silence/mute UX) |
| **Human Systems** (`/human-systems-workbench`) | Core capacity-intelligence engine: check-ins, interventions/experiments, posture, trends | Fully implemented | **Highest capacity relevance of any surface** |
| **Physical Readiness** | Read-only exercise library/history; readiness check-in intentionally retired in favour of Human Systems | Deliberately scoped down | Low |
| **Shopping List** | CRUD wishlist/gift tracker | Fully implemented, narrow scope | Low — not a generic "things to buy" capture |
| **Content Workbench** | Full QA-gated content pipeline | Fully implemented | None |
| **Advisory** | Think/Perspectives/Outcomes; shared backend engine across Slack/Telegram/XO surfaces; outcome-tracking | Fully implemented | Structured decision-reflection loop |
| **Captain's Brief** | Assembled daily narrative brief, explicitly non-realtime | Fully implemented | Feeds Now/Remember layers |
| **Briefs (archive)** | Intelligence-brief archive (external OSINT, not personal) | Fully implemented | None |
| **Knowledge Workbench** | "Memory" domain live; "Library" (document cataloguing) deliberately pulled back to draft, hidden | Partial — backend ready, UI intentionally narrower | Low |
| **HQ Status / HQ Evolution** | Platform ops-health / self-improvement meta-tooling | Fully implemented (proxy) | None (system, not personal) |
| **Engineering Handoffs** | Read-only handoff/PR visibility | Fully implemented | None |

Legacy `(app)/*` pages (`captains-log`, `medical`, `operations`, `search`, `timeline`, `automation-centre`, `intelligence`, `operating-model`, `delivery`, `engineering`) are **still live, reading real tables directly** — their only "immaturity" is navigational (superseded, unlisted), not technical. One page (`stage-progression`) was deliberately killed for showing 100%-fabricated mock data — the only confirmed dishonest-UI case found anywhere.

### A.2 Number One / XO / Captain's Chair orchestration

- `platform-runtime/lib/officers/*.py` — a scheduled (daily-cycle) officer framework with real trigger types (`SCHEDULED/EVENT_DRIVEN/THRESHOLD_BASED/LIFECYCLE_BASED/ESCALATION_BASED`, `officer_triggers.py`), schedules (`officer_schedules.py`), idle/overdue detection (`officer_followups.py`). All outputs are **text rows in the `decisions` table** — no action-execution.
- `core/coordination/number_one.py` — a real prioritization/recommendation engine (Eisenhower-style, capacity-aware, health-adjusted queue), but a **pure function**: capacity and missions are caller-supplied, it has no live data access of its own.
- `core/exec-assistant/` — ~15% built relative to its own README; calendar/email sync, alerting, and both interfaces (Telegram/web) are vaporware; only a preference store and priority scorer exist.
- `core/command-centre/backend/api/coordination.js` (Node "Command Centre") — wraps Number One's output but its data directory (`core/coordination/outputs/`) **does not exist on disk**, so every route (`/brief`, `/queue`, `/escalations`, etc.) is silently serving **hardcoded mock data in production**.
- **By design**, the whole stack is non-autonomous: `number_one.py`'s own docstring states "Rule-based (not AI, not autonomous)… all execution requires XO approval." There is no action-execution API anywhere — an "approved" recommendation only flips a status string in `decisions`.
- **Genuine duplication**: three-to-four independent systems each compute "what matters now" (officer/XO synthesis → Slack-style brief; Number One coordination engine → `/api/number-one-brief`; Captain's Chair's `commandState.ts` → does not consume either of the above; Command Centre's coordination API → mock data). None reconcile.

### A.3 Capacity & health/wellness systems

- **Canonical live model**: `capacity_checkins` (+ `capacity_interventions`, `capacity_intervention_events`, `capacity_experiments`, `capacity_calibration`), written exclusively by the standalone Telegram `capacitybot`. Retired predecessors (`recovery_pulses`, `human_systems_daily`) are explicitly dead in code comments.
- **Genuine behaviour-changing gate, live**: `core/coordination/recommendation_engine.py:rank_missions()` depresses P2/P3 mission scores under Red capacity and attaches advisory notes — this actually reorders what's recommended, not just displayed.
- **Advisory-only overlay**: `number_one.py:get_health_adjusted_queue()` explicitly never alters mission records, only annotates.
- **A more sophisticated but currently broken gate**: `core/health/capacity_gate.py`'s `CapacityGate` is fully built to defer non-P0 missions under Red capacity, but its only caller (`platform-runtime/lib/daily_ops_cycle.py:_step_human_systems`) passes it an **empty mission list** instead of the real one already in scope two lines away — so its mission-deferral logic can structurally never fire. This is a concrete, fixable bug, not a missing feature.
- **Duplication**: XO bot, `wellness_officer`, and `recovery_officer` all still independently narrate "how is the Captain doing" from the same underlying data, even though XO's own onboarding text tells users capacity now belongs solely to `capacitybot`. XO's own dead-command fallback text references `/recovery_status` and `/dispatch`, which are not registered anywhere in its command handler.
- **Inputs are 100% manual conversational check-ins** — no wearable/HealthKit ingestion exists anywhere in the repo (a documented non-goal).

### A.4 ADHD/task/capture/knowledge systems

- `intelligence/adhd/follow_through_engine.py` — **the single most important discovery of this mission**. Live, hourly-scheduled (`intelligence/scheduler.py`), mode-aware (`gentle/normal/persistent/deadline/waiting`) nudging over `personal_tasks`, respecting quiet hours and a daily send cap, delivering via the canonical `notify()`.
- `intelligence/adhd/task_decomposition.py` — the *intended* Python decomposition module is dead/orphaned; the real, live decomposition logic runs directly in `core/model-router/app.py` and is called by Ready Room's `DecomposeView.tsx` via `/api/ready-room/decompose`.
- `intelligence/adhd/task_nudge_scheduler.py` — explicitly superseded, dormant dead-letter code kept only for rollback.
- **Follow-Through settings UI** (`lcars-portal/src/app/settings/follow-through/`) is cosmetic — it persists toggles that the live backend engine never reads. A real gap between a built UI and a built backend that don't talk to each other.
- **Universal capture (`captured_items`)** is genuinely mature: web quick-capture, floating capture, Command Centre API, and **Telegram voice + text** all feed one table; an enrichment worker (`core/capture/enrichment_worker.py`) auto-routes high-confidence personal notes to `captains_log_entries` and mission/decision/research items to `intelligence_notes`. A second, deliberately separate capture path exists for content-pipeline captures (`comms_content`, bypassing `captured_items`).
- **Nothing in the capture pipeline ever creates a `personal_tasks` row** — the ADHD follow-through engine and the capture pipeline are today fully disconnected data universes, despite both being ready to be joined.
- **Six distinct "thing to track" concepts** exist across the codebase: `personal_tasks` (life-admin/ADHD tasks), `captured_items` (pre-triage inbox), Command Centre `missions` (separate Node service), `comms_content` (content pipeline), `intelligence_notes` (org-knowledge triage), `shopping_list_items` (purpose-built wishlist). Google Tasks is correctly folded into `personal_tasks` rather than being a seventh competitor — good existing precedent for "capture surface, not a new system."

### A.5 Notifications, scheduling, reminders, calendar

- **One canonical notify pathway**, actively CI-enforced: `core/platform/notification_service.py:notify()` (Telegram + Apprise transports), with a lint gate (`tools/check_notification_senders.py`) blocking any *new* raw Telegram API call outside five permanently-justified exceptions.
- A **second, independent JS notification engine** exists in Command Centre (`notification-engine.js`, 15-min in-memory eval loop) — a parallel rebuild of similar signal-to-notify logic, not a caller of the canonical Python `notify()`.
- Three reminder/follow-up primitives (`officer_schedules.py`, `officer_triggers.py`, `officer_followups.py`) plus a production nudge engine (`intelligence/proactive_cadences.py`, 13 named cron jobs registered on APScheduler) plus the ADHD follow-through engine plus a fourth `human_systems_scheduler.py` (pgqueuer cron) — **at least four separate scheduling mechanisms** exist, though they're largely domain-partitioned rather than truly duplicative.
- **Calendar is read-only display only** — `api/calendar/today`/`upcoming` explicitly documented as read-only; nothing gates or prioritizes decisions off calendar data. One narrow exception: an appointment-prep cron reads a separate appointments table.
- **No timer/pomodoro/focus-session feature exists anywhere**, even as dead code.
- **No routine/habit data concept exists** — `officer_schedules.py`'s cadence catalogue is the closest analogue, but it governs officer/system cadences, not personal routines.

### A.6 Briefs, intelligence, reflection systems

- Personal-life-facing briefs (`captain-brief`, `captains-daily-brief`, `number-one-brief`, `recommendations`, `captain-intelligence`) are real and largely live, with the one place that tracks whether an AI recommendation turned out useful (`insight_outcomes`) — but that tracks *recommendation quality*, not personal accomplishment.
- **`captains_log_entries`** is the platform's ADR-declared "PRIMARY reflective health journal," with a genuine daily `wins` field. **It is captured every day and never read back by anything else in the platform** — Timeline and Search only select `tomorrows_priority`/`overall_note`/capacity.
- Three separate features are all confusingly named "Captain's Log" (the real daily journal; a disabled Human Systems log page; a Captain's Chair quick-capture box that actually writes to `intelligence_notes`) — a naming collision worth resolving before building anything new here.
- **Weekly Review already computes completion signals** (Ready Room completions, workout completions, published content) but its headline sections ("What Mattered," "Carry Forward") are explicitly designed to exclude positive/completed items — by deliberate design choice ("not a productivity score"), not oversight.
- Voice debrief via the XO Telegram bot (`debrief_engine.py`) produces structured reflection (themes, stressors, energy sources, decisions emerging) but has no standalone surfaced view — it only feeds into the brief pipeline.
- **No Evidence Library exists anywhere.** But at least seven ready-made data sources for one already exist without new capture: `captains_log_entries.wins`, completed `personal_tasks`, completed `physical_workout_sessions`, published `comms_content`, `capacity_checkins` day-trajectory improvements, `debrief_logs`, and `weekly_reviews` historical snapshots.

### A.7 Database / state model

- The live schema (`core/infrastructure/supabase/migrations/0001–0216`) is the canonical source of truth; `tools/supabase/schema/*.sql` is legacy/superseded design documentation, not live schema.
- The platform **already has its own built-in dead/duplicate-domain detector**: `domain_registry` + `domain_heartbeats`, with 13+ recorded retirement migrations (0112–0117, 0170, 0181–0183) — any future schema proposal should be checked against this registry rather than treated as greenfield.
- Confirmed overlapping concepts: three capacity-adjacent tables (`recovery_pulses` [retired] → `capacity_checkins` [canonical] → `capacity_calibration` [still active, different purpose]); four decision-tracking tables (`decisions` [Captain-confirmed retired but still called by ~35 dormant `platform-runtime/lib/*` modules], `decide_ledger` [active/canonical], `decision_records`/`decision_outcomes` [dropped], `commander_decisions` [legacy]); two document/chunking pipelines (`knowledge_documents`/`document_chunks` vs `processing_documents`/`processing_chunks`); a parallel `exec_assistant_*` table family that overlaps conceptually with `captains_daily_briefs`/`follow_through_events`/`alerts`.
- The context-assembly JSON schemas that feed AI/officer reasoning (`captain_brief_context.json`, `operating_picture_context.json`) already assemble health + priorities + blockers + key dates + decisions into one object — but have **no first-class capacity field**, only a generic `health` field, despite `capacity_checkins` being the live canonical capture table. This is a real gap in an otherwise-good composition layer.
- A single, deliberate vector-memory store exists (`mem0`/Qdrant, `unified_memory.py`) — no need for a new memory store.

### A.8 PWA / mobile / iPad, feature flags, dead code

- **Installable PWA**: yes, mature (`manifest.webmanifest`, real icons, app shortcuts to Capture/Engineering Queue/Alerts).
- **Offline**: minimal/deliberately conservative — service worker caches only 5 static assets, never navigations or API responses.
- **Push notifications**: only local Web Notifications from a running/installed PWA; true server push (VAPID + Web Push) is a documented-but-unbuilt next phase.
- **iPad/safe-area handling**: mature and iterated, including a documented real regression fix (iPad Air landscape falling into a breakpoint gap).
- **Touch targets**: a single, deliberately narrow bottom nav bar (Workbenches / Capture / Physical Readiness) below 1280px, 56px thumb targets.
- **Voice input on web**: does not exist — TTS output exists (Google Cloud Neural2), but no `SpeechRecognition` anywhere in the web app. Voice *capture* only exists via the Telegram XO bot.
- **No dedicated feature-flag service** — only a few env-var-style flags gating a mostly-superseded legacy Express backend.
- **High-value hidden capability**: `MobileAlertDrawer.tsx` is a complete, real-data-wired mobile alerts+decisions bottom sheet — **imported nowhere**, confirmed unused by the repo's own knip dead-code report. A finished feature with zero surfacing cost to turn on.
- Other confirmed-unused-but-real components worth a second look: `ApprovalQueue.tsx`, `CaptainIntelligencePanel.tsx`, `HumanSystemsPanel.tsx`, `RecoveryConfidencePanel.tsx`.
- Python dead-code scan (vulture) confirms two small real bugs (`mistral_agent_client.py`'s `timeout_ms` param is silently unused; a disabled test assertion) and notes structurally that it likely misses whole dead clusters that only whole-program reachability analysis would catch.

---

## B. 50-Accommodation Coverage Matrix

The literal 50-item accommodation list was not supplied to this investigation. The table below instantiates a representative 6–7 items per the mission's eight named categories, built from standard ADHD/AuDHD accommodation practice and cross-checked against everything found in Section A. Treat this as a first-pass matrix to be reconciled against the Captain's actual 50-item list, not as the final answer.

Legend: ✅ exists · 🟡 partial · ❌ missing · 🍎 native Apple/physical/human better

| # | Accommodation | Status | Existing TJR HQ capability | Recommended action |
|---|---|---|---|---|
| **1. Time, Memory & External Brain** |
| 1 | Capture any thought instantly, from anywhere | ✅ | `captured_items` (web + Telegram voice/text) | SURFACE |
| 2 | Externalise "don't forget" items so they resurface at the right time | 🟡 | `follow_through_engine.py` nudges tasks, but nothing routes a generic capture into it | CONNECT |
| 3 | See only what's relevant right now, not the whole backlog | 🟡 | Number One's health-adjusted queue, Weekly Review's "You Can Ignore" | EVOLVE (reconcile the 3-4 competing engines first) |
| 4 | A single place to look for "what did I decide/commit to" | 🟡 | `decide_ledger`, but 4 overlapping decision tables exist | CONSOLIDATE / EVOLVE |
| 5 | Passive reminders for appointments without manual entry | 🟡 | Google Calendar OAuth exists (read-only), appointment-prep cron reads a separate table | CONNECT |
| 6 | Time-blindness aids (what time is it, how long until X) | ❌ | Nothing found | 🍎 native iOS/Watch better |
| 7 | A single canonical "todo" that doesn't require deciding where something belongs | 🟡 | 6 distinct task-like models exist; capture doesn't yet feed `personal_tasks` | CONNECT (see Gap Register #2) |
| **2. Executive Function & Task Initiation** |
| 8 | Break an overwhelming task into a single next tiny step | ✅ | Ready Room "UNSTICK ME" + `/api/ready-room/decompose` | SURFACE |
| 9 | Gentle vs. persistent nudge intensity per task | ✅ | `follow_through_mode` (gentle/normal/persistent/deadline/waiting) | SURFACE |
| 10 | Body-doubling / accountability for starting a task | ❌ | Nothing found | 🍎 human/physical better |
| 11 | Reduce number of choices when capacity is low | 🟡 | `recommendation_engine.py` reorders under Red capacity; Number One caps top-N | EVOLVE (reconcile) |
| 12 | Snooze/defer without losing the item | ✅ | `personal_tasks.next_review_at`/`snoozed_until` | SURFACE |
| 13 | Detect a stalled task and offer help, not shame | ✅ | `follow_through_engine.py` stall detection | SURFACE |
| 14 | Auto-defer non-essential work under low capacity | 🟡 (broken) | `capacity_gate.py` built but starved of real data (empty list bug) | EVOLVE — fix the one-line bug |
| **3. Capacity & Working With the Brain** |
| 15 | Daily capacity check-in (green/amber/red) | ✅ | `capacity_checkins`, `capacitybot` | SURFACE |
| 16 | Capacity changes what's recommended, not just what's shown | ✅ (partial) | `recommendation_engine.py:rank_missions` | EVOLVE (extend to more surfaces) |
| 17 | Track what interventions actually help | ✅ | `capacity_interventions`, `capacity_intervention_events`, `capacity_experiments` | SURFACE |
| 18 | Self vs. system-calculated capacity comparison | ✅ | `capacity_calibration` | SURFACE |
| 19 | Recovery-aware "sanctuary" low-stimulation mode | ✅ | LifeOS Hub self-quiets under PROTECT/RECOVER | SURFACE |
| 20 | One voice narrating "how am I doing," not three | ❌ (duplicated) | XO, wellness_officer, recovery_officer all independently narrate | CONSOLIDATE |
| **4. Distraction & Stimulation** |
| 21 | Reduce notification volume under high capacity load | 🟡 | `notify()` has severity levels; no explicit capacity-based volume throttle found | EVOLVE |
| 22 | Focus/DND session support | ❌ | No timer/focus-session feature exists anywhere | 🍎 iOS Focus Mode better |
| 23 | Sensory/stimulation state tracking | ✅ | `capacity_checkins` sensory-regulation fields (migration 0158) | SURFACE |
| 24 | Distraction "what should I do instead" helper | ✅ | `capacitybot`'s `distract.py` | SURFACE |
| **5. Food, Hydration & Daily Living** |
| 25 | Meal/hydration reminders | ❌ | Nothing found | 🍎 native/physical better |
| 26 | Shopping/errand capture that isn't a full task | 🟡 | `shopping_list_items` exists but is gift/wishlist-scoped, not general errands | EVOLVE or scope-note as DON'T BUILD (widen an existing narrow tool only if truly needed) |
| 27 | Simple daily-living checklist under low capacity (Red) | ❌ | Nothing dedicated found | BUILD (small, capacity-conditional) |
| **6. Movement & Nervous-System Regulation** |
| 28 | Exercise/movement logging | ✅ | `physical_workout_sessions`, Physical Readiness workbench | SURFACE |
| 29 | Breathing/regulation exercise prompt | ❌ | Nothing found | 🍎 Watch/native better, or human/physical |
| 30 | Decompression suggestion when overloaded | 🟡 | Advisory/`capacitybot` guide exists conceptually; no explicit "decompression" action found | EVOLVE |
| **7. Communication, Emotion & Rejection Sensitivity** |
| 31 | Delay sending an emotionally-charged message | ❌ | Nothing found | BUILD (small) or 🍎 native "undo send" |
| 32 | Crisis/PEM-style pacing support | ✅ | `telegram-bots/revs` (pacing, PEM, crisis layer) | SURFACE |
| 33 | Rejection-sensitivity-aware framing in feedback loops | 🟡 | Weekly Review explicitly avoids framing non-completion as failure | SURFACE (extend the principle) |
| **8. Self-Accommodation & Evidence** |
| 34 | Evidence of wins/progress, not just backlog | 🟡 (data exists, unused) | `captains_log_entries.wins`, Ready Room completions | BUILD the *view*; data already exists — see Gap Register #3 |
| 35 | Weekly reflective retrospective | ✅ | Weekly Review | SURFACE |
| 36 | Track whether a recommendation/decision was actually good | ✅ | `insight_outcomes`, Advisory outcome-tracking | SURFACE |
| 37 | Voice-based end-of-day debrief | ✅ | XO Telegram `debrief_engine.py` | SURFACE (also give it a standalone view) |

*(Remaining items to reach 50 should be filled in once the Captain's actual list is available; the categories above already surface the clear existing/missing/Apple-better pattern that will likely hold for the rest.)*

**Overall pattern across all categories:** the accommodations most already covered are ones close to "task/capacity/capture" (categories 1–3, 6, 8); the ones most clearly better left to Apple/physical/human (category 4's Focus Mode, 5's meal/hydration reminders, 6's breathing exercises, human body-doubling) should go straight to the Do-Not-Build list rather than being rebuilt.

---

## C. Experience-Layer Assessment

### A. CAPTURE — "Get it out of my head"
**Already substantially exists.** `captured_items` is fed by web quick-capture, floating capture, Command Centre API, and Telegram voice + text (full STT pipeline in `telegram-bots/xo/voice_capture.py`). An enrichment worker auto-classifies and routes high-confidence items. **Gap**: a second, un-unified capture path exists for content (`comms_content` direct), and — most importantly — **nothing routes a capture into `personal_tasks`**, so a captured "thing to do" never reaches the ADHD follow-through engine without a manual step. **Recommended disposition: CONNECT**, not build — add one routing invariant to the existing enrichment worker (see Gap Register #2).

### B. NOW — "What do I need to do right now?"
**Partially exists, duplicated.** Captain's Chair, the LifeOS Hub, Number One's health-adjusted queue, and the officer/XO synthesis each independently attempt to answer this question, reading different data, in different runtimes, with no reconciliation. The suppression/curation logic itself is good (Captain's Chair's "Needs You" caps to 0–3 items; Number One's health-adjusted queue caps to top 3 under Red) — the problem is there are three-to-four of them. **Recommended disposition: EVOLVE** — pick Captain's Chair's `commandState.ts` (the richest, most-consumed, already-capacity-aware surface) as canonical, and have Number One's/officer-layer output feed into it as one more input rather than existing as parallel truth.

### C. REGULATE — "My brain isn't cooperating"
**Partially exists.** Real capacity state capture, real intervention/experiment tracking, and one genuinely live gate that reorders missions under Red capacity all exist. What's missing: (1) the more sophisticated `capacity_gate.py` mission-deferral mechanism is built but inert due to an empty-list bug; (2) there's no explicit "I'm stuck / overloaded / can't initiate" self-report → intervention-suggestion loop distinct from the daily check-in (the check-in captures state; nothing yet maps "stuck" specifically to "here's Ready Room's UNSTICK ME" as an automatic suggestion); (3) no timer/focus-session or breathing-exercise capability exists, and per the Do-Not-Build analysis, some of this belongs to Apple/physical anyway. **Recommended disposition: EVOLVE** (fix the bug, wire self-reported states to existing interventions) rather than build new regulation UI.

### D. REMEMBER — "Don't let me forget"
**Partially exists, scattered.** Reminders/follow-ups exist as backend primitives (`officer_followups`, `follow_through_engine`, `proactive_cadences`) and Emergency Alerts already has a mature "surface only what needs attention, silence what doesn't" UX pattern that could generalize. What's missing is a single **contextual surface** (TODAY / LEAVING HOME / WAITING FOR / DON'T FORGET / TONIGHT / COMING UP) that pulls from these existing primitives rather than being a new manually-maintained list. **Recommended disposition: CONNECT** — this is a UI composition task over existing data (`personal_tasks` due/waiting states, calendar "upcoming," follow-through nudges), not a new capture or storage layer.

### E. REFLECT — "Show me evidence"
**Data exists; the view does not.** `captains_log_entries.wins` has been captured daily for months and never surfaced again. Weekly Review already computes completion signals but deliberately keeps them out of its headline sections. Seven ready-made data sources for an Evidence Library were identified in Section A.6 with zero new capture required. **Recommended disposition: BUILD** the aggregation/view only — this is genuinely the cheapest possible "BUILD" in the whole report because every input already exists and is already being written.

---

## D. Capacity Integration Assessment

**What's possible today:**
- A single canonical capacity model (`capacity_checkins`) that is well-instrumented (interventions, experiments, calibration, sensory/regulation fields).
- Real, live GREEN/AMBER/RED-as-operating-input behaviour exists in exactly one place that matters: `recommendation_engine.py:rank_missions()`, which actually reorders and annotates missions under Red capacity, called from the live `/brief/captain` and `/recommendations/full` endpoints.
- A self-quieting UI mode (LifeOS Hub) that reduces visual/cognitive load under low-capacity postures — this is arguably the most ADHD-appropriate piece of UI already in the platform.

**What's missing or broken:**
- The more rigorous, purpose-built capacity gate (`capacity_gate.py`) that would defer entire categories of non-essential work under Red is **structurally inert** — a one-line data-plumbing bug (an empty list passed where the real mission list is already in scope) prevents it from ever firing its core logic. This is the single cheapest, highest-leverage fix identified in this whole investigation.
- Capacity is not yet a first-class field in the context-assembly schemas (`captain_brief_context.json` etc.) that feed AI/officer reasoning — only a generic `health` field exists, so any future orchestration layer (Number One, above) would have to special-case its way to real capacity data rather than receiving it as a normal input.
- Amber-specific behaviour ("reduce choices, protect transition time, increase external prompts") is not distinctly modeled anywhere — today the system essentially only distinguishes Red (deprioritize) from everything else. A genuine three-tier (Green/Amber/Red) behavioural contract does not yet exist in code, only in the two data fields (`capacity_state`) and the docs.
- Notification volume is not throttled by capacity — `notify()` has severity levels but no capacity-aware volume gate, so a low-capacity day and a high-capacity day currently generate the same nudge volume.

---

## E. Number One Assessment

**Context available today:** Missions/decisions/anchors via `officer_context.py` (from the `decisions` table by prefix); capacity as a caller-supplied string only (no independent read); no direct calendar access; no personal/health context beyond what's passed in.

**Can it act, or only recommend?** Only recommend. Every officer/Number One output terminates as a text row in `decisions`; there is no action-execution API anywhere in the stack — nothing converts an "approved" recommendation into a calendar change, a task mutation, or a message send. This is explicitly stated as by-design in `number_one.py`'s own docstring ("Non-autonomous… all execution requires XO approval or direction"), not merely unfinished.

**Can it proactively surface something?** The backend officer cycle *is* a genuine scheduled/triggered loop — but its output is designed to feed a Slack-style brief, and the web UI (Captain's Chair) never consumes it. So proactive detection exists, but is invisible on the surface the Captain actually uses day to day.

**Can it suppress/prioritize ("14 tasks, only 2 matter")?** Yes — in at least three separate places, each with its own cap logic (top-3, top-5, top-4). This capability clearly already exists; it's just triplicated.

**What concretely blocks Number One from being a real orchestration layer:**
1. No action-execution API — recommend-only by design, at every layer.
2. No independent live wiring to capacity/calendar — it's a pure function over caller-supplied data.
3. The Node "Command Centre" coordination API is running entirely on mock data (missing export directory).
4. `exec-assistant` (calendar/email sync, alerting, interfaces) is largely unbuilt relative to its own documented roadmap.
5. No proactive trigger loop reaches the web UI the Captain actually looks at.
6. Three-to-four independent "what matters now" computations exist with no reconciliation layer.

**Recommendation:** Before any "make Number One smarter" work, the priority should be reconciliation (pick one canonical priority computation) and one connective step (feed it real, live capacity + calendar instead of caller-supplied values) — not new reasoning capability. The reasoning/prioritization logic itself is already reasonably good.

---

## F. iPad Surface Assessment

**Already solid:** installable PWA with real manifest/shortcuts, safe-area-aware layouts with a documented history of real-world iPad regression fixes, a deliberately minimal touch-optimized bottom nav below 1280px width.

**Gaps relative to "ambient interface":**
- No true server push (only local notifications while the PWA is running/installed) — meaningfully limits "persistent ambient" behaviour when the app isn't foregrounded.
- No voice input in the web app at all (TTS output only) — voice capture is Telegram-only, so the iPad PWA cannot do what the Telegram bot already can.
- Offline support is minimal by design (only 5 static assets cached) — acceptable for a always-connected companion device, but worth confirming intentional.
- No Shortcuts/Widgets/Focus Mode integration found anywhere.

**Highest-value, lowest-cost win:** `MobileAlertDrawer.tsx` already exists, fully wired to real alerts + decisions-awaiting-approval data, safe-area-correct, and is simply never mounted in any layout. Turning this on is close to a zero-cost win for the "ambient interface" goal — no new code, just wiring it into the existing mobile layout shell.

**Which existing experiences would most benefit from a persistent iPad surface:** LifeOS Hub (already designed as the ambient daily-glance surface) and a future NOW view are the natural fits; Ready Room's DO/UNSTICK ME mode is also a strong candidate for a focused, distraction-free full-screen iPad mode given it already has no timers/gamification to fight against.

---

## G. Duplication & Consolidation Findings

| Duplication | Instances | Recommendation |
|---|---|---|
| "What matters now" priority computation | Captain's Chair `commandState.ts`, Number One coordination engine, officer/XO synthesis, Command Centre coordination API (mock data) | Pick Captain's Chair as canonical (richest, most consumed); feed the others into it as inputs, or retire |
| Capacity gating logic | `recommendation_engine.py:rank_missions` (live, inline) vs. `capacity_gate.py` (built, structured, currently inert) | Fix `capacity_gate.py`'s data-plumbing bug and consolidate onto the more auditable one, retiring the inline version |
| Personal wellness narration | XO bot, `wellness_officer`, `recovery_officer` all independently narrate capacity/wellness state from the same data | Consolidate onto `capacitybot` per the product's own stated direction; remove XO's now-stale narration code and dead command references |
| Decision-tracking tables | `decisions` (retired, still called by ~35 dormant modules), `decide_ledger` (canonical), `decision_records`/`decision_outcomes` (dropped), `commander_decisions` (legacy) | Confirm the ~35 `platform-runtime/lib/*` modules calling the retired `decisions` table are truly dormant (traces to a disabled Slack service); if so, plan their removal rather than leaving live-looking code pointed at a dead table |
| Task-like concepts | `personal_tasks`, `captured_items`, Command Centre `missions`, `comms_content`, `intelligence_notes`, `shopping_list_items` | Not all need merging — Google Tasks' precedent (fold into `personal_tasks` as a capture surface) is the right pattern to extend to general capture, not a call to unify all six into one table |
| Notification engines | Canonical Python `notify()` (CI-enforced) vs. a second JS notification engine in Command Centre | Confirm whether Command Centre's JS engine is still needed now that its own coordination API is mock-data-only; if Command Centre is being phased out, its notification engine likely should be too |
| Document/chunking pipelines | `knowledge_documents`/`document_chunks` (original RAG) vs. `processing_documents`/`processing_chunks` (later ingestion) | Confirm these serve genuinely different stages before treating as safe-to-ignore |
| "Captain's Log" naming collision | Three unrelated features share the name (real daily journal; disabled Human Systems page; Captain's Chair quick-capture box writing to `intelligence_notes`) | Rename two of the three before adding any new "log"-adjacent feature, to avoid a fourth collision |
| Scheduling mechanisms | `officer_schedules.py`, `intelligence/proactive_cadences.py` (APScheduler), `human_systems_scheduler.py` (pgqueuer), ADHD follow-through engine | Largely domain-partitioned and probably fine as-is; flag only if a new scheduled behaviour is proposed — extend an existing scheduler rather than adding a fifth |

---

## H. Do-Not-Build List

Capabilities better left to Apple, physical environment, exercise, or human support — TJR HQ should at most coordinate, remind, or contextualise:

- **Time-blindness ambient awareness** (what time is it, how long until X) — native iOS/Apple Watch complications and Live Activities already solve this better than any custom UI could.
- **Focus/DND sessions** — iOS Focus Mode already exists and integrates system-wide; TJR HQ should at most suggest *when* to enable it, never rebuild it.
- **Meal/hydration reminders** — better handled by native reminder apps or physical cues (a water bottle on the desk) than a bespoke in-app nudge competing for attention with everything else.
- **Breathing/regulation exercises** — Apple Watch Breathe/Mindfulness, or a physical practice, are more appropriate than an in-app exercise; TJR HQ could at most prompt "consider a breathing break," never implement the exercise itself.
- **Body-doubling / accountability for starting a task** — this is fundamentally a human/social intervention; no digital surface substitutes for it.
- **PEM/crisis pacing support** — already appropriately handled by `telegram-bots/revs`, which is itself deliberately Telegram-native (quick, low-friction, crisis-appropriate); no reason to rebuild in the web app.
- **Delay-sending emotionally-charged messages** — iOS Mail/Messages "undo send" already exists at the OS level for supported apps; not worth a bespoke TJR HQ feature unless the message channel is TJR-internal.
- **Wearable/physiological capacity sensing** — explicitly a documented non-goal already; Apple Health already aggregates this far better than a bespoke ingestion pipeline would.

---

## I. Prioritised Gap Register

Ranked by (cognitive load reduction × frequency of need × existing capability reuse) ÷ implementation complexity — highest first.

| # | Evidence | Existing capability | Gap | Proposed change | User benefit | Complexity | Dependencies | Disposition |
|---|---|---|---|---|---|---|---|---|
| 1 | `platform-runtime/lib/daily_ops_cycle.py:_step_human_systems` passes `[]` where real `missions` is already in scope two lines away | `capacity_gate.py`'s full Red-capacity mission-deferral logic | Structurally can never fire | Pass the real mission list already available in `run_daily_cycle()` | Real Red-day backlog hiding, not just advisory notes | Trivial (one-line fix) | None | EVOLVE |
| 2 | `enrichment_worker.py` already auto-routes `personal`→`captains_log_entries` and `mission/decision/research`→`intelligence_notes`; nothing routes to `personal_tasks` | Universal capture pipeline, `personal_tasks`, Google Tasks precedent for "capture surface → personal_tasks" | A captured "thing to do" never reaches the follow-through engine without a manual step | Add one more routing invariant mirroring the existing two, using the Google Tasks pull's own default (`follow_through_mode='gentle'`) as precedent | Captures actually become nudged tasks — closes the Capture↔Remember loop | Low (one file, reuses existing schema) | None | CONNECT |
| 3 | `captains_log_entries.wins`, Ready Room completions, published content, capacity trajectory improvements are all already written and queryable | Weekly Review's existing (buried) completion-signal queries | No Evidence view exists; the closest thing deliberately excludes wins from its headline | Build a thin read/aggregation view over these seven existing tables — no new capture | Directly answers "show me evidence," the mission's explicit counterbalance goal | Low–medium (pure aggregation, no new writes) | None | BUILD (view only) |
| 4 | `MobileAlertDrawer.tsx` is complete, real-data-wired, confirmed unused by knip | Full mobile alerts+decisions bottom sheet | Never mounted in any layout | Wire it into the existing mobile layout shell | Immediate "ambient iPad surface" improvement at near-zero cost | Trivial | None | SURFACE |
| 5 | Three independent "what matters now" engines confirmed (Captain's Chair, Number One, officer/XO synthesis), plus a fourth on mock data | Rich existing logic in each | No reconciliation; risk of contradictory guidance as each evolves independently | Designate Captain's Chair's `commandState.ts` canonical; feed Number One/officer outputs into it as inputs, not parallel truth; retire or fix the mock-data Command Centre path | One coherent "what to do now" instead of three that can disagree | Medium (integration work, no new UI) | Requires agreeing on canonical source | CONNECT / EVOLVE |
| 6 | XO bot, `wellness_officer`, `recovery_officer` all independently narrate the same capacity data; XO's own onboarding text says this belongs to `capacitybot` alone; dead command references confirmed in XO | `capacitybot` as the stated canonical wellness-narration surface | Redundant, drifting narration logic in 2-3 other bots | Remove/redirect the duplicate narration code paths in XO/wellness_officer/recovery_officer | Less duplicated maintenance, one consistent voice for wellness state | Medium | Coordinate with whichever bot users actually rely on day to day | CONSOLIDATE |
| 7 | Follow-Through settings UI persists toggles the backend engine never reads | `follow_through_engine.py` (env-var driven), `FollowThroughSection.tsx` (UI-only) | Settings the user sets appear to do nothing | Wire the engine to read the settings row as defaults before falling back to env vars | Settings the user changes actually take effect — avoids silent broken-promise UX | Low–medium | None | EVOLVE |
| 8 | Context-assembly schemas (`captain_brief_context.json` etc.) have only a generic `health` field | `capacity_checkins` as the live canonical capacity source | Capacity is not first-class in the schema that feeds AI/officer reasoning | Add a capacity field to the context-assembly schema, sourced from `capacity_checkins` | Any future orchestration/AI reasoning gets capacity "for free" instead of special-casing it | Low–medium | None | EVOLVE |
| 9 | No REMEMBER contextual surface exists (TODAY/LEAVING HOME/WAITING FOR/etc.) despite the underlying data (due tasks, waiting states, upcoming calendar) already existing | `personal_tasks` states, calendar "upcoming," follow-through nudges, Emergency Alerts' silence/surface UX pattern | No single composed "don't let me forget" view | Build a thin composed view over existing data, reusing Emergency Alerts' proven surface/silence interaction pattern | Reduces reliance on physical whiteboards/scattered notes per mission intent | Medium | None | CONNECT |
| 10 | No Amber-specific behavioural contract exists in code (only Red is distinctly handled) | `capacity_checkins.capacity_state` already has an amber value | System doesn't yet behave differently under Amber (reduced choices, protected transition time) beyond what Red-only logic incidentally catches | Extend `recommendation_engine.py`/`capacity_gate.py` logic to a genuine three-tier contract | Matches the mission's explicit Green/Amber/Red behavioural spec, not just data model | Medium | Depends on #1 being fixed first | EVOLVE |

---

## J. Proposed Target Experience

**A high-capacity morning:** The LifeOS Hub opens on `/hub` (already the PWA start_url) showing full detail — missions, calendar, intelligence — because recovery posture is not PROTECT/RECOVER. Captain's Chair's "Needs You" surfaces 0–3 genuinely important items, computed once (not three times differently). Ready Room offers full-scope task selection; deep work and planning are unhidden per the mission's Green-capacity intent.

**A normal workday:** Captures (typed on the web or voice-noted via Telegram) land in one inbox, get auto-classified, and — once Gap #2 is closed — a "thing to do" quietly becomes a gently-nudged `personal_tasks` item without the Captain having to decide where it belongs. The follow-through engine (already live) nudges stalled items on its own schedule, respecting quiet hours. Nothing new to remember to check.

**An Amber period:** The Hub and Captain's Chair reduce to fewer, larger touch targets; Number One's advisory notes ("today, focus on P0/P1 only") become consistent because there's one canonical source producing them; the amber-specific behavioural contract (Gap #10) actually reduces choices rather than just annotating them.

**A Red/overloaded period:** `recommendation_engine.py`'s existing Red-capacity mission depression, plus the now-fixed `capacity_gate.py` (Gap #1), genuinely hide non-essential backlog rather than merely down-ranking it. The Hub's sanctuary mode (already built) visually quiets the whole surface. Ready Room shows only "the one next physical action" — which it already does by design, with no timers or scores to add pressure.

**An evening transition:** The daily journal (already built) prompts for `wins`, decisions made, and tomorrow's priority — and, once Gap #3 lands, those wins actually show up somewhere later instead of disappearing into a write-only table. A voice debrief via the XO bot (already built) captures anything spoken rather than typed.

**A moment where something needs to be remembered:** A composed REMEMBER view (Gap #9), built from data that already exists (due tasks, waiting-for items, upcoming calendar), surfaces the one relevant fact — "leaving home in 20 minutes: don't forget X" — and then disappears once resolved, the way Emergency Alerts already does for genuinely time-relevant information.

**A moment TJR cannot initiate a task:** Ready Room's UNSTICK ME mode (already built, already the platform's clearest ADHD accommodation) breaks the task into one 5–15 minute next step via the live decomposition endpoint — with explicitly no timer, streak, or score competing for attention.

**A moment of emotional activation:** Today, nothing exists purpose-built for this (Gap register does not currently include a build item here beyond the "delay sending a message" Do-Not-Build note) — the honest answer is this is the one area where the discovery found genuinely little existing infrastructure to reuse, and any future work here should start from research into what's actually needed rather than assumed.

---

*This report reflects code as read during the 2026-09-18 discovery investigation. No code, schema, or configuration was changed as part of this mission, per the guardrails in the mission brief.*
