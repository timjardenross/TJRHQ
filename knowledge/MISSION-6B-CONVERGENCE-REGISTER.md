# Mission 6B — Convergence Register Dispositions

Baseline: Mission5 merge `807671fdd883f3de341b722ee12c96cccaf51be5`, Mission6A merge `7d14c5072`, Mission6B baseline main `807671fdd`.

## 8.1 XO Bot / Capacity Bot Telegram Convergence
**Disposition: NO CHANGE REQUIRED**
Two independent systemd services (`tg-xo.service`, `tg-capacitybot.service`), both live. Zero command collision — XO hard-redirects capacity asks to Capacity Bot (`telegram-bots/xo/app.py:346,367-368`), regression-tested (`telegram-bots/xo/test_capacity_dedup.py`). Evidence engine (`capacitybot/evidence_engine.py:272`, table `capacity_intervention_events`) is owned solely by Capacity Bot — XO does not import/duplicate it. This matches the brief's own allowance: "two runtime processes can legitimately remain while presenting one coherent interaction model." Signposted seam, not a defect.

## 8.2 Command Centre Notification Path
**Disposition: RECONCILE**
`core/command-centre/backend/services/notification-engine.js` has two halves:
- Orphaned in-memory `_store` (line ~24) + `/unread /history /:id/read /read-all` routes (`api/notifications.js`) — no live UI consumer, `markRead()` mutates only the in-memory array (decorative). **Retire this half.**
- Real metrics/escalation proxy (`/metrics`, `/risk`, `/escalations/*`) into `slack-bot`'s SQLite-backed services — legitimate, keep, but point its dismiss/ack semantics at canonical `intelligence/adhd/follow_through_engine.py` (`personal_tasks`: `next_review_at`, `snoozed_until`, `nudge_count`, `deferral_count`) rather than parallel `notifications.db`.

## 8.3 Capacity-Aware Delivery
**Disposition: RECONCILE**
Only `follow_through_engine.py` gates on capacity (`_fetch_todays_capacity_state`, `_apply_capacity_gate`). Command Centre's Critical/High severity notifications bypass capacity entirely — acceptable per spec ("CRITICAL safety-relevant behaviour must remain appropriately interruptive") but undocumented; document it as deliberate.
Execution posture (ENGAGE/STEADY/PROTECT/RECOVER/RESET/UNKNOWN) is not consulted by any delivery path — out of scope to add (capacity already covers interruption/timing per spec §8.3; posture governs presentation elsewhere).
**Investigated, not a defect:** `lcars-portal/src/lib/commandState.ts:1-27` defines `CommandPosture` (`RESPOND/RECOVER/PROTECT/FOCUS/STEADY/UNKNOWN`) — the file's own header explains this is a deliberate, documented composition-layer vocabulary distinct from Human Systems' execution posture: it reuses `PROTECT`/`RECOVER` verbatim where meaning aligns, and introduces `FOCUS`/`RESPOND`/`STEADY` only for command-level concepts execution posture has no equivalent for (citing prior mission §6/§17). This matches the brief's own §2 distinction ("capacity and execution posture are related but distinct concepts") — CommandPosture is a third, intentionally separate concept (command-level "what kind of day"), not a collision. **No change required** — initial discovery fork flagged this without reading the file's documented rationale; correcting the register here.

## 8.4 Hub → Ready Room Continuity
**Disposition: IMPLEMENT**
Zero Hub hrefs point to `/ready-room`; `needs_now`-tier personal-task items land on `/mission-workbench` instead (`commandState.ts:169-257`). Ready Room has no `?task=<id>` param to deep-link a specific task. Fix: add task-id param handling to Ready Room page/TodayStream; change `commandState.ts:256` href to `/ready-room?task=<ref>` for `needs_now`-tier personal-task items only (leave `decision_required` on mission-workbench — that's a decision surface, not execution).

## 8.5 Voice → Canonical Capture
**Disposition: DEFER WITH JUSTIFICATION**
Telegram voice capture already exists and is live (`voice-capture-pipeline` — Telegram → faster-whisper → `captured_items`, same canonical ingress the brief requires). Browser/PWA voice capture would duplicate this ingress for marginal reach gain (desktop/mobile web voice input) against real added complexity (permissions, transcript confirmation UI, accessibility, failure recovery). No captain-facing evidence of demand beyond existing channel. Defer; canonical single ingress already satisfied via Telegram.

## 8.6 PickUpBanner Evidence Continuity
**Disposition: IMPLEMENT**
`PickUpBanner.tsx` is passive display, not even clickable. Canonical evidence write path already exists (`SupportFeedback.tsx`'s `recordSupportCompletion()`/`recordSupportEvent()` → `/api/ready-room/support-events` → `capacity_intervention_events`). Fix: make banner's "Switch to Do to continue" actionable; call `recordSupportCompletion()` when Captain resumes via the banner (completion-as-outcome-signal, not an extra feedback prompt — avoids friction per spec's own guidance).

## 8.7 / 8.9 Evidence-Aware Number One + Explainability
**Disposition: IMPLEMENT** (as part of Number One orchestration build, §4-9)
No orchestration layer exists today — see below. Evidence surfacing will use the existing `ready-room/support-effectiveness` read route, phrased per spec §8.9 wording ("previously helpful," never scored/causal language).

## 8.8 Captain Preference Propagation (DO_NOT_SUGGEST)
**Disposition: IMPLEMENT** (as part of Number One orchestration build)
DO_NOT_SUGGEST lives in Capacity Bot's `intervention_engine.py`/evidence tables (migration `0218_mission5_evidence_domain_generalisation.sql`), Postgres-backed (Supabase) — reachable from lcars-portal's Next.js server routes via the same Supabase client already used elsewhere. Number One's chat route currently never queries it. Fix: gate any suggestion Number One would surface through this table before including it.

## 8.10 Decision-Quality Evidence
**Disposition: DEFER WITH JUSTIFICATION**
`get_decision_quality_stats()` (`core/coordination/mission_knowledge_store.py:475`, `outcome_records`-backed, Captain 1-5 confidence ratings) and `decision_effectiveness.py:184` (`with_held >= 10`, jsonl-backed, `logs/decisions/*.json` success/failure/partial outcomes) compute the **same G-008-readiness threshold (10 decisions)** from genuinely different evidence — automated outcome tracking vs Captain-assigned quality rating — not identical data through two pipes. `decision_effectiveness.py`'s live report also carries mode-distribution/category/success-rate fields `get_decision_quality_stats()` does not compute; a straight swap in `intelligence_reporter.py:70-73,220,266` would silently drop those fields from the live report. True reconciliation needs either migrating `logs/decisions/*.json` history into `outcome_records` or extending `get_decision_quality_stats()` to match the full report shape — out of scope for this targeted convergence item without further discovery. **Leave both in place; recorded as residual technical debt** (two G-008 signals, same threshold, different sources — a future migration mission should unify them, not this one guessing which is authoritative).

---

## Number One Orchestration (Sections 4-9) — the mission centerpiece
**Current state:** "Number One" is only an LLM system-prompt persona (`lcars-portal/src/lib/ai-roles.ts:89-91`) served by a stateless proxy (`lcars-portal/src/app/api/ai/chat/route.ts`). No server-side conversation state, no canonical-capability dispatch, no DO_NOT_SUGGEST gate. `core/coordination/number_one.py` is an unrelated rule-based engineering-coordination brief generator — not the Captain-facing CoS.

**Gap to close:** build a deterministic intent classifier + dispatcher in front of/alongside the LLM call; short-lived server-side conversational context (last active canonical object) so pronoun/referent resolution works across turns without the client replaying full history; wire each of the 8 canonical intents (Remember this / What matters / What am I forgetting / I'm stuck / Still can't start / Too much / Not now / Where was I / Done) to its real owning canonical route; gate suggestions through DO_NOT_SUGGEST before they reach the LLM prompt or action-proposal path.

Exact route map for dispatch targets pending final discovery pass (in progress).
