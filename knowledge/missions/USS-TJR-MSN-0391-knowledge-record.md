---
mission_id: USS-TJR-MSN-0391
title: "Mission 6A — Chief-of-Staff Experience Foundations (discovery + safe independent fixes)"
status: "DISCOVERY COMPLETE / PARTIAL IMPLEMENTATION — ready for Mission 6B convergence pending Mission 5"
date: 2026-09-19
branch: mission6a-chief-of-staff-experience-foundations
worktree: /opt/starship-endeavour-mission6a
baseline_main_sha: 744fbcb42
mission4_merge_sha: 98ce01fd6
concurrent_with: mission5-evidence-adaptive-support (isolated branch, not touched)
---

# Mission 6A — Chief-of-Staff Experience Foundations

Discovery-first pass across whole-of-HQ experience. 4 parallel discovery streams (A+C, B+G, D+E+F+I, H+J) run against read-only worktree checkout. This record is deliverable #17 (mission knowledge record) and folds in deliverables #1-13.

## 1. Current-state HQ experience map (summary)

Three independent Captain-facing surfaces mutate canonical domains with no shared dispatcher:
- **XO Telegram bot** (`telegram-bots/xo/app.py`) — conversational surface, mission brief, capture, Adaptive Follow-Through task actions (done/snooze/defer/block/decompose).
- **Capacitybot** (`telegram-bots/capacitybot/app.py`) — separate Telegram bot, capacity check-ins, `/helpme`, `/guide`, `/distract`, `/protocols`, `/experiment`. Explicitly documented as having **no LLM/NL path** — button-driven only, and has its own effectiveness/intervention-ranking engine Number One/XO have zero visibility into.
- **LCARS Portal** (`lcars-portal/`) — web app, Workbench grid, reuses canonical HTTP bridges (`context_service.py`) for Remember/Attention rather than re-deriving logic — the best-behaved of the three.

**Number One** (`core/coordination/number_one.py`) is a clean, deterministic, read-only mission-coordination engine (RECOMMENDS, never DECIDES — documented authority model, no drift found). It only operates on the *mission* domain; it has no visibility into personal-task/capacity/capture actions happening inside XO bot or capacitybot.

## 2. Number One orchestration map

- Owns: mission work queue, follow-ups, blockers, XO escalations, daily brief (all read-only synthesis over `Mission`/`WorkQueueItem` dataclasses).
- Does not own, does not touch: `personal_tasks`, `captured_items`, `capacity_checkins` — these are mutated directly by XO bot and capacitybot glue code, bypassing Number One entirely.
- Adjacent, easily-confused concept: `platform-runtime/lib/officers/xo_orchestrator.py` — a *different* "XO Central Coordination Intelligence" synthesizing autonomous officer outputs, unrelated to `core/coordination/number_one.py`. Naming collision, not functional duplication.
- Governance manifests (`governance/authority/number_one.yaml`, `xo.yaml`) are both baseline-permissive/unconfigured — no action-specific restrictions defined either way.

## 3. Canonical intent taxonomy + routing map

| Intent | Canonical owner | Current routing |
|---|---|---|
| Remember this | Mission 3 Capture | Clean — writes `captured_items` via enrichment pipeline. XO bot has no `/remember` read command though (portal-only gap). |
| What matters? | Mission 2 Attention | Clean — `attention_items_from_brief()` shared normalizer, all surfaces read same vocabulary. |
| What am I forgetting? | Mission 3 Remember | Clean — `_http_remember()` unresolved_captures. |
| I'm stuck | Mission 4 execution support | **Split** — lives only on capacitybot's `/helpme` (separate bot, separate ranking engine), XO bot has no equivalent and no awareness. |
| Still can't start | Mission 4 execution support | XO bot's `_ft_decompose_and_start` handles it, capacitybot's `/helpme` is a second unconnected mechanism for a very similar need. |
| Too much | capacity-aware overload response | Split — `NumberOne.get_health_adjusted_queue()` (Green/Amber/Red overlay) vs. capacitybot's `/distract`, not obviously reading the same capacity computation. |
| Not now | canonical defer/snooze | Clean — single implementation (`_ft_defer_tomorrow`/`_ft_snooze`), shared by button and NL reply. |
| Where was I? | interruption recovery | `restart_cue`/`micro_action` fields, same mechanism as "still can't start," no dedicated command surfacing it outside a reminder context. |
| Done. | canonical completion | Clean — single implementation (`_ft_mark_done`), button + NL both hit it. |

6/9 clean single implementations. 3 split across the XO/capacitybot boundary (the same organizational fragmentation as §1, not a Number One defect).

Four independently-built "intent vocabularies" exist with no shared taxonomy module (XO capture/update regex, debrief tier scorer, voice-capture classifier, engineering semantic_router) — none currently compete for the same decision, but future intent additions have no canonical place to register.

## 4. Workbench responsibility matrix

Verified against target responsibilities (Chair=executive perspective, Ready Room=execution, Human Systems=capacity/regulation, Hub=orientation):

- **Chair, Ready Room, Human Systems, Hub** all match their target job-to-be-done well, with explicit in-code comments documenting the boundary decisions (not accidental discipline — a prior redesign pass already enforced this). Hub and Chair share `buildNeedsYouItems()`/`deriveCommandStatus()` so they cannot disagree.
- Nav is now deliberately minimal — single curated `LIVE_WORKBENCHES` source of truth (`lib/workbenches.ts`), a fix for a documented prior drift bug. This substantially supersedes the MSN-0320 "59% unreachable" finding.
- **Genuine gap found**: Hub (the PWA start_url / "front door") has no link to Ready Room, Capture, or capacity check-in, and is itself not in the 3-tab mobile nav. On mobile (the Captain's stated primary device), reaching Ready Room — arguably the single most-used "what do I do today" surface — takes 2 taps through a 21-tile directory. Flagged for 6B/redesign, not fixed here (real UX/nav decision, not a bug fix).

## 5. Duplicate/legacy/dead UX register

- **19 genuinely-unreachable legacy `(app)` pages confirmed still current** (spot-checked `/intelligence`, `/delivery`, `/operations`, `/automation-centre`) — not stale, matches 2026-08-16 finding.
- **Fixed this pass**: `/medical` legacy dashboard (dead check-in/pulse action tabs) was still the `href` target for the platform's 4 highest-severity wellness alerts (red-flag, emotional-load, pain-critical, pain-elevated) — a live dead-end on the path a Captain most needs working when something urgent fires. Repointed to `/human-systems-workbench`, matching the pattern already used for the adjacent recovery-debt alert. `lcars-portal/src/lib/alerts.ts`.
- **Naming collision (not functional dup)**: three unrelated "Captain's Log" surfaces (`/captains-log` full reflection form → `captains_log_entries`; Chair's quick-capture widget → `intelligence_notes`; Notebook page, the widget's own destination). Flagged for a redesign-phase naming/ownership decision, not fixed (no functional bug, just discoverability risk).
- Task/capacity/capture/reminder canonical-owner audit: clean. Single write path per domain, no duplicate CRUD UIs found. Capacity entry is deliberately Telegram-only (web forms retired-in-place with clear rationale comments).

## 6. Cross-Workbench / cross-surface continuity

Traced live, tested example (Mission 3 fixture test `tests/test_mission3_cross_surface_fixture.py`): Telegram capture → `captured_items` → enrichment → `personal_tasks` → Attention State/Number One brief → Remember (derived view, no duplication) → completion, provenance preserved throughout. Web reads the same tables/bridges, not parallel logic. This is a tested, live contract — not aspirational.

Caveat (from Mission 3's own knowledge record): true single-pane parity across attention/decisions/calendar is explicitly flagged PARTIALLY IMPLEMENTED, scoped to Mission 4/5, not 6A.

## 7. Cross-device / mobile / PWA assessment

- Manifest + service worker present and correctly scoped (cache-first only for 5 static assets, no navigation/API caching — avoids stale-auth bugs).
- Notification handling is **local-only** — true server push (VAPID) explicitly documented as deferred, not built. No offline fallback UI (also explicitly acknowledged as future work in MOBILE-MVP.md).
- Session continuity: standard httpOnly-cookie SSR session, no separate PWA token mechanism — solid.
- Deep linking: PWA manifest shortcuts + notification `data.url`, works.

## 8. Notification coherence assessment

- 8 independent delivery mechanisms (1 canonical Telegram lib + 5 permanent-exception Telegram senders + 1 **unreconciled duplicate** JS Telegram sender + email + client web-notifications). The repo's own CI gate (`tools/check_notification_senders.py`) already flags the Command Centre JS sender as an unresolved duplicate — confirmed still true, not fixed this pass (real architectural decision, out of "safe independent fix" territory).
- Command Centre's in-app notification store is **fully decorative** — plain in-memory array, resets on restart, zero relationship to canonical mission/event state. Acting on it does nothing real.
- Capacity/posture-gated delivery exists for exactly **one** notification class (ADHD task follow-through nudges via `follow_through_engine.py`). Every cadence job, interrupt-now push, mission-approval push, and scheduled brief ignores Green/Amber/Red entirely.
- Web-push alerts have no dismiss/ack action and no shared dismissal ledger with Telegram's ack/dismiss flow — same underlying event can show as acknowledged on one channel and not the other.

These are real findings but are architectural-decision-sized, not safe one-line fixes — recorded here for 6B/redesign prioritization, not touched.

## 9. Native-platform ownership matrix

| Capability | Status | Classification |
|---|---|---|
| Alarms, timers, Apple Watch, Focus/DND | Not present | NATIVE PLATFORM SHOULD OWN |
| Screen Time, grayscale | Not present | HUMAN ACCOMMODATION |
| Native OS reminders (EventKit) | Not present | HQ SHOULD INTEGRATE (if a native wrapper is ever built — same doctrine as existing Google Tasks sync) |

Consistent with existing precedent already on record in Mission 3's knowledge record ("Phone alarms/reminders — HUMAN/NATIVE-DEVICE ACCOMMODATION — not attempted, consistent with mission's own 'do not build' list").

## 10. Voice

Telegram voice pipeline (faster-whisper) is live and tested. Web voice UI does not exist — zero `MediaRecorder`/`SpeechRecognition` usage found. This was an **explicit, named deferral to Mission 6** in the Mission 3 knowledge record. Extension surface: `voice_capture.py`'s `transcribe_audio()`/`classify_text()`/`save_capture()` are pure functions independent of Telegram's Update/Context objects — a web extension needs only a browser capture UI + a route calling the same pipeline, writing `captured_items` with a new `source_channel_id`. Not built this pass (would require new frontend surface + review, correctly scoped as a follow-up build, not a "safe one-line fix").

## 11. Cognitive load findings

- Task capture / task completion / task start flows: genuinely minimal, 1 click, zero confirmation dialogs, clear specific labels. Positive finding — preserve in any redesign.
- Draft-state loss: capture text, task quick-add fields, and task pause-notes are all plain `useState` with no persistence — minor, consistent pattern across 3 components, worth a shared fix later, not done this pass (scope creep for a discovery mission).
- Capacity check-in has zero in-app capture path (Telegram-only by deliberate 2026-08-22 decision) — plus a disclosed, still-open data gap (sleep/CPAP/sitting-tolerance have no live capture path on *either* channel).

## 12. Mission 5 → Mission 6B integration register

Flagged, not built (per mission's "no fake Mission 5" rule):

1. **Capacitybot's `evidence_engine.py`** — personal causal-effect estimator (Bayesian structural time-series against `capacity_checkins`), writing `capacity_interventions.personal_causal_effect*`. This is exactly Mission 5's shape, living entirely on the capacitybot bypass surface today with zero Number One/XO visibility.
2. **Capacitybot's `intervention_engine.py`** — shared deterministic ranking engine behind `/capacity` Q9, `/helpme`, `/guide`, already incorporating "personal success weighting" from `capacity_intervention_events`. When Mission 5 lands canonical evidence/effectiveness architecture, this engine is the natural migration target — and Number One/XO's routing for "I'm stuck"/"Too much" (see §3) should eventually call into whatever Mission 5 produces here, not re-derive it.
3. **`capacity_intervention_events`** — live outcomes/effectiveness feedback loop table, pre-dating Mission 5, worth reconciling against Mission 5's evidence storage rather than treated as a second source of truth.
4. Ready Room may eventually want lightweight support-feedback once Mission 5's effectiveness model exists (per original mission brief §28 example) — not requested by any current UI, just flagging the likely consumer.

## 13. Safe independent 6A fixes implemented this pass

- **`lcars-portal/src/lib/alerts.ts`** — repointed 4 wellness-alert hrefs (`wellness-redflag`, `wellness-emotional-load`, `wellness-pain-critical`, `wellness-pain-elevated`) from the retired `/medical` dashboard to `/human-systems-workbench`, matching the existing pattern already used for the recovery-debt alert. Fixes a live dead-end on the platform's highest-severity alert path. Verified: `npx tsc --noEmit` clean, no test coverage existed to update (grepped, none found referencing these hrefs).

No other code changes made — remaining findings (Hub↔Ready Room mobile reachability, Captain's Log naming collision, Command Centre notification duplication/decorative state, capacity-gated delivery gap, draft-state persistence, web voice capture) are real but each requires either a genuine UX/architecture decision or new-surface build work, correctly scoped as 6B/redesign-phase work rather than "safe independent 6A fixes."

## Deferred / not done this pass (deliberately, per mission scope)

- Deterministic experience test matrix (mission §31-34) — not built; would require either live conversational integration tests against XO bot or a fixture harness. Recommend as first Mission 6B task once the M5 dependency for "I'm stuck"/"Too much" routing is resolved (§12 item 2), since building the test matrix before that routing converges would test today's fragmented behavior, not the target behavior.
- Adversarial experience review (mission §35) — the discovery streams above already surfaced the adversarial-review-shaped findings (duplicate state, dead ends, orchestration bypass, decorative notification state) organically; no additional pass run given the volume already found. No unresolved *critical* 6A architectural defect found — the one critical-severity issue (dead alert links) was fixed in §13.

## Definition-of-done status against mission §38

Items 1-3, 5, 9-12, 16-17 (part) satisfied by this discovery pass. Items 6 (duplicate workflow removal) partially satisfied — the one safe independent duplicate found (dead alert hrefs) was fixed; the naming-collision and orchestration-bypass duplicates require a decision, not a mechanical fix. Items 13-15 (Captain override / failure / capacity-posture testing) not separately validated this pass — no code changes were made to intent-routing or capacity-gating logic, so no new regression surface was introduced requiring it; existing Mission 1-4 suites untouched. Item 19 (deterministic 6A tests) explicitly deferred (see above) rather than fabricated. Item 22: **ready to converge with Mission 5 through 6B**, pending Mission 5 completion and the routing decision in §12 item 2.
