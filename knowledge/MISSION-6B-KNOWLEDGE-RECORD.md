# Mission 6B — Knowledge Record

TJR HQ Mission 6B: Final Chief-of-Staff Convergence & Programme Closure.

## Baseline

- Mission 5 merge SHA: `807671fdd883f3de341b722ee12c96cccaf51be5`
- Mission 6A merge SHA: `7d14c5072`
- Mission 6B baseline (authoritative main at start): `807671fdd`
- Branch: `mission6b-final-cos-convergence`, dedicated worktree, no reuse of prior mission worktrees.

## Convergence register — final dispositions

See `knowledge/MISSION-6B-CONVERGENCE-REGISTER.md` for full reasoning. Summary:

| Item | Disposition |
|---|---|
| 8.1 XO/Capacity Bot Telegram | NO CHANGE REQUIRED — justified, tested, signposted two-process design |
| 8.2 Command Centre notification path | RECONCILE — implemented (orphaned decorative store retired) |
| 8.3 Capacity-aware delivery | NO CHANGE REQUIRED — initial "posture vocabulary defect" finding was wrong; `commandState.ts`'s `CommandPosture` is a documented, deliberate third vocabulary, not a collision |
| 8.4 Hub → Ready Room continuity | IMPLEMENT — implemented (`?task=<id>` deep link) |
| 8.5 Voice → Canonical Capture | DEFER WITH JUSTIFICATION — Telegram voice capture already satisfies the canonical-ingress requirement |
| 8.6 PickUpBanner evidence continuity | IMPLEMENT — implemented (clickable resume, no fabricated evidence) |
| 8.7/8.9 Evidence-aware Number One / explainability | IMPLEMENT — implemented via Number One dispatcher |
| 8.8 Captain preference propagation | IMPLEMENT — implemented via `isDoNotSuggest()` gate |
| 8.10 Decision-quality evidence | DEFER WITH JUSTIFICATION — two G-008 signals from genuinely different evidence sources; reconciling risks silently dropping fields from the live report |

## Number One orchestration — what was built

**Before:** "Number One" was only an LLM system-prompt persona (`lcars-portal/src/lib/ai-roles.ts:89-91`) on a stateless proxy (`lcars-portal/src/app/api/ai/chat/route.ts`). No conversation state, no canonical-capability dispatch, no preference gate. A separate, unrelated `core/coordination/number_one.py` (rule-based engineering-coordination brief generator) shares the name but is not the Captain-facing CoS.

**After:** `lcars-portal/src/lib/number-one/`:
- `intent-router.ts` — `classifyIntent()` deterministically matches the 9 canonical phrasings (regex, not LLM inference — traceability matters more than flexibility for a Captain-facing state mutation). `dispatchIntent()` routes each to its real owning capability:
  - `remember` → `captureNote()` → `captured_items` insert (mirrors `lib/capture.ts`)
  - `what_forgetting` → context_service.py's `/remember` (Mission 3's canonical Remember capability)
  - `what_matters` → context_service.py's `/brief/number-one` (canonical Attention State via `attention_items_from_brief`)
  - `stuck`/`cant_start`/`too_much` → Model Router's `/api/model/adhd-decompose` (Mission 4 execution support), gated by `evidenceAwareNote()` (§8.7/§8.9, quiet/explainable, never scored language) and `isDoNotSuggest()` (§8.8)
  - `not_now` → `deferTask()` → `personal_tasks.snoozed_until` (canonical non-lossy defer)
  - `where_was_i` → `fetchPickUpCandidate()` (same paused/restart_cue logic as `pickUpItems()`)
  - `done` → `completeTask()` → `personal_tasks.work_state='completed'` (canonical completion, never a Number One-local marker)
- `context-store.ts` — `number_one_context` (migration 0219), single-row, 120-minute TTL, holds the last canonical object referenced, for pronoun/referent resolution across turns ("I'm stuck" after "what am I forgetting?" resolves to the same referral without the Captain repeating themselves).
- `canonical-actions.ts` — server-side ports of `lib/capture.ts`/`lib/personalTasks.ts`'s mutations (same tables/columns, only the Supabase client differs — a Next.js API route has no browser client available). No new schema beyond the context table.

Wired into `route.ts`: only for `role === 'number_one'`, before the LLM call. A matched intent short-circuits with a deterministic reply in the same SSE contract the client already parses (`sseFromText()`); anything unmatched falls through to the existing LLM persona unchanged. Every other role (Chief Engineer, XO, Advisory Board, ...) is untouched.

## Tests

- `lcars-portal/src/lib/number-one/__tests__/intent-router.test.ts` — 10 new tests covering all 9 canonical intents, argument extraction, and negative cases (freeform text, keyword-adjacent-but-not-matching phrasing like "the printer is stuck").
- Full existing suite: 688/688 passing (65 files) after all changes, no regressions.
- `npx tsc --noEmit`: clean.

## Adversarial review

Ran against the full diff (base `807671fdd`). No critical/high defects found. Two residual notes (not defects, no fix needed):
1. `evidenceAwareNote()` can restate what `decompose()` just did when both fire in the same reply (phrasing overlap, not incorrect).
2. `too_much` and `cant_start` intents currently share the same `decompose(mode: 'smaller')` call — Model Router's endpoint has no dedicated overload-specific mode. Reasonable given the real endpoint contract; a future enhancement, not a Mission 6B gap.

## Retired paths

- Command Centre's in-app notification read-state: `_store`/`getUnread`/`getHistory`/`markRead`/`markAllRead` (`core/command-centre/backend/services/notification-engine.js`) and their 4 HTTP routes (`/unread`, `/history`, `/:id/read`, `/read-all` in `api/notifications.js`). Confirmed zero live consumer repo-wide before removal. The real signal-evaluation + Telegram delivery engine is untouched.

## Preserved paths (explicitly, not by omission)

- XO/Capacity Bot two-process Telegram architecture (8.1).
- `commandState.ts`'s `CommandPosture` vocabulary (8.3) — distinct, documented, intentional.
- `decision_effectiveness.py` and `get_decision_quality_stats()` both remain (8.10) — not reconciled, residual debt below.
- Telegram voice capture as the sole voice-to-Capture ingress (8.5) — browser/PWA voice deferred.

## Closure pass (post-PR-#281 review, 2026-09-19)

The Captain reviewed PR #281 and required one bounded final pass before merge: an explicit Hub assessment, an executable cross-surface proof (not just architectural reasoning), a capacity/posture representative matrix, adversarial dispatcher testing, and a live-schema check on migration 0219 before any application decision. Results:

### LifeOS Hub assessment
Dedicated read-only review (`lcars-portal/src/app/hub/page.tsx` + `Sidebar.tsx`/`MobileCommandBar.tsx`) against ORIENT→SHOW WHAT MATTERS→HELP ME CONTINUE→GET ME TO THE RIGHT CAPABILITY. 5 of 7 criteria already satisfied (canonical context via shared `deriveCommandStatus`/`buildNeedsYouItems`, no duplication of Chair/Attention-State, no mobile-specific defect). **2 real, bounded gaps found and fixed:**
- Number One had zero discoverability from Hub or global nav — reachable only via Workbenches → Advisory → Think → Advanced disclosure → Number One, the exact topology-knowledge friction the mission targets. **Fixed**: `?advisor=number_one` deep-link support threaded through `advisory-workbench/page.tsx` → `ThinkView` → `ConsultView` (auto-expands the Advanced disclosure, pre-selects Number One), plus a direct "Ask Number One" link on Hub itself.
- Hub had no "where I left off" signal at all (only Ready Room showed paused/restart-cued tasks). **Fixed**: one capped, single-item "Pick up where you left off" card on Hub, reusing `pickUpItems()` verbatim — explicitly NOT a second Remember panel (see `hub/page.tsx`'s own addendum comment on why this is a different concept from Remember's broader resurfacing).

Both fixes are link/data-source additions to the existing Hub pattern, not new UI patterns or a redesign.

### Deterministic cross-surface proof (executable, not reasoned)
New test: `lcars-portal/src/lib/number-one/__tests__/dispatch-scenario.test.ts` (14 tests, all passing) runs the exact canonical scenario — remember → what_forgetting → stuck → cant_start → too_much → not_now → where_was_i → done — against a fake in-memory Supabase client + mocked context_service/Model Router fetches. Proves: one canonical object throughout (no duplicate `personal_tasks`/`captured_items` rows across the whole chain), context survives every turn, "still can't start" continues the same object rather than restarting, "not now" is a non-lossy UPDATE (task never abandoned), "where was I?" recovers the same object via the context-store fallback path, "done" completes canonical state, DO_NOT_SUGGEST suppresses an otherwise-qualifying suggestion, stale (>120min) context is treated as expired rather than acted on, and zero-context intents ask rather than guess.

**Boundary identified, not glossed over**: `context_service.py`'s own `/remember` logic and Model Router's real decompose model call are proven live elsewhere (`core/context-assembly/tests/test_remember.py`; Model Router's own test suite) — this test proves the JS dispatcher's continuity/idempotency contract against those interfaces, not the full multi-repo live call chain in one process.

**Idempotency gap found by this proof — FIXED (Captain-mandated blocking defect, not residual debt)**: `remember` had no idempotency key, so a retried "remember that X" created a duplicate `captured_items` row. Fixed via migration `0220_captured_items_idempotency_key.sql` — a nullable `idempotency_key` column on `captured_items` (Mission 3's canonical table, not a Number-One-specific mechanism) with a partial unique index. `captureNote()` now accepts an optional idempotency key, threaded from the calling chat message's own `id` (`route.ts`'s `ChatMessage.id` → `ConsultView.tsx`). Safety comes from the database's unique constraint, not application-level check-then-insert: a second insert with the same key fails atomically under a real concurrent race, and the caller reads back whichever row won. Exact-identity match only, never fuzzy content dedup (a Captain repeating the same words later with a different request id is two legitimate captures). 5 new tests prove: same-request retry → one row; concurrent race → one row; legitimate repetition (different ids) → two rows; failure/retry-after-lost-response → one row; no key supplied → pre-existing behaviour unaffected.

### Capacity × posture representative matrix
No new test needed — two already-passing suites already constitute this proof:
- **Posture axis (JS, `lcars-portal/src/lib/__tests__/personalTasks.readyRoomContext.test.ts`, part of the 702 passing)**: confirms all 6 states (`ENGAGE/STEADY/PROTECT/RECOVER/RESET/UNKNOWN`) are live in `capacityLimitForPosture` (not regressed to 3), proves canonical task list is never mutated by posture (only the admitted-count changes), and proves explicit Captain override (`pinned_today` / `in_progress`) survives a shrinking cap even at `capacityLimit: 1` (the RECOVER-equivalent constrained case).
- **Capacity axis (Python, `tests/test_follow_through_engine_capacity_gate.py` + `test_daily_ops_cycle_capacity_gate.py` + `test_follow_through_capacity_recovery.py`, run live this pass: 27/27 passing)**: proves Green emits no gate actions, Amber limits without mutating missions, Red defers non-P0 while explicitly protecting P0 (the override-equivalent case), and — critically — `test_no_mission_is_mutated_by_the_gate` proves canonical truth stays constant while gate behaviour varies.

**Why no single joint "Red+PROTECT" test exists**: Capacity (Green/Amber/Red/Unknown, `capacity_checkins`-derived) and execution posture (`ENGAGE/STEADY/PROTECT/RECOVER/RESET/UNKNOWN`, Human-Systems-derived) are architecturally separate inputs feeding separate gates (Follow-Through's Python capacity gate; Ready Room's JS posture-driven cap) per the brief's own §2 distinction — there is no live code path that combines them into one joint decision to test as a matrix. Testing each axis independently, which both proofs above do, is the architecturally correct proof; inventing a combined test would test something that doesn't exist in the running system.

### Number One adversarial routing
Covered in `dispatch-scenario.test.ts`'s second describe block: all 7 adversarial phrases ("No, the other task.", "Not that.", "Don't suggest that again.", "Just show me the task.", "Don't open Ready Room.", "Stop.", ordinary conversation) correctly fail to match any canonical intent pattern and fall through to the existing LLM persona — **no wrong canonical mutation is ever risked** by the deterministic layer for ambiguous/correction/conversational input, by construction (a pattern must match specifically, or nothing happens deterministically).

**Documented limitation, not silently assumed handled**: the context-store holds exactly one object at a time, so "completion with multiple plausible objects" cannot structurally occur in the deterministic dispatcher — only the zero-context case ("which task?") is handled by asking. True multi-candidate disambiguation would require tracking more than one candidate, which is out of this mission's bounded scope; it's only reachable today at the LLM-freeform layer.

### Migration 0219 — live-schema assessment (read-only, not applied)
Investigated via Supabase MCP tools against the live project: no numbering or table-name collision (confirmed `number_one_context` does not exist live, and 0219 is not already applied), migration SQL is syntactically valid and matches this project's own RLS conventions, rollback is a trivial `drop table` (new, isolated, zero FKs). **One incidental finding, unrelated to 0219 itself**: `user_settings` — the table cited as precedent for the single-row `authenticated ... using(true)` RLS pattern — actually has RLS enabled with **zero policies** live (fail-closed, likely broken), so the precedent comparison was to a misconfigured table; 0219 itself is written correctly (it includes an explicit policy) and doesn't inherit this problem, but `user_settings`'s state is a separate pre-existing bug worth flagging. **0219 has NOT been applied to live Supabase** — application requires the Captain's explicit approval per this session's production/shared-state boundary; this is a recommendation (GO), not an action taken.

## Final residual technical debt register (explicit, not hidden, not manufactured)

1. **Two G-008-readiness signals** (`decision_effectiveness.py` jsonl-backed live; `get_decision_quality_stats()` `outcome_records`-backed orphaned) — different evidence sources computing the same threshold. Unreconciled by design (8.10 disposition); needs a real migration decision, not attempted here.
2. `evidenceAwareNote()` can restate what a just-completed decompose call already did — cosmetic phrasing overlap, not incorrect.
3. `too_much`/`cant_start` share one decompose mode (`smaller`) — correct given the Model Router endpoint's real contract; no dedicated overload mode exists to differentiate with.
4. Multi-candidate disambiguation ("which of these two tasks") is not implemented in the deterministic dispatcher — structurally out of scope for a single-slot context store; falls through to the LLM layer today.
5. Pre-existing, separately-owned: `user_settings` has RLS enabled with zero policies live (found incidentally during the 0219 live-schema check) — fail-closed, likely broken, unrelated to Mission 6B's own security posture. Not expanded into this mission's scope.

(The `remember` idempotency gap previously listed here was fixed, not left as debt — see above.)

## PR / merge

Pushed as PR #281. Idempotency fix, migration 0219 + 0220 applied to live Supabase, final CI, and merge status recorded in the programme closure record.
