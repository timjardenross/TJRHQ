# Cognitive Support & Chief-of-Staff Programme — Closure Record

Missions 1 through 6B. Written so a future engineering session can understand the final architecture without reconstructing it from git history.

## What did we build?

A Chief-of-Staff layer (Number One) that lets the Captain express intent in plain language — "remember this," "what am I forgetting," "I'm stuck," "too much," "not now," "where was I," "done" — and have HQ route that intent to the one canonical system that already owns it, rather than the Captain needing to know which Workbench, table, or service is responsible.

## What canonical architecture now exists?

- **Attention State** (Mission 1): `needs_now / important_not_immediate / can_wait / blocked / decision_required`. Computed once (`core/coordination/attention_state.py`), consumed everywhere (Hub's Needs You, Number One's brief, Remember).
- **Capacity** (Mission 2): `Green / Amber / Red / Unknown`. Modifies presentation/interruption/deferment; never mutates domain truth.
- **Execution Posture** (Human Systems, live runtime vocabulary): `ENGAGE / STEADY / PROTECT / RECOVER / RESET / UNKNOWN`. Distinct from Capacity and from `commandState.ts`'s separate `CommandPosture` (a third, intentionally distinct command-level "what kind of day" concept documented in that file — not a collision to fix).
- **Capture → Remember → Follow-Through** (Mission 3): one ingress (`captured_items`), one resurfacing view (Remember, `context_service.py`'s `/remember`), one canonical notification/defer/complete path (`personal_tasks` via `follow_through_engine.py`).
- **Execution support** (Mission 4): One-Action / UNSTICK ME / decomposition (`/api/ready-room/decompose` → Model Router), overload reduction, interruption recovery (PickUpBanner).
- **Evidence & Adaptive Support** (Mission 5): `capacity_intervention_events`, `capacity_preferences` (with `do_not_suggest`/`preferred` states), `HELPFUL/NOT_HELPFUL/NOT_NOW` feedback semantics. Explicit preference always outranks historical evidence.
- **Number One orchestration** (Mission 6B, new): deterministic intent classifier + dispatcher + short-lived cross-turn context (`number_one_context`), sitting in front of the existing LLM persona, calling the above capabilities directly rather than reimplementing any of them.

## How does Number One operate as Chief of Staff?

It intercepts 9 canonical Captain intents before any LLM call and routes each to its real owning capability (see knowledge record for the full map). Anything that doesn't match a canonical intent falls through unchanged to the existing free-form LLM persona. A short-lived server-side context row remembers the last canonical object referenced, so a chain like "what am I forgetting?" → "I'm stuck" → "still can't start" → "not now" → "where was I?" → "done" resolves as one continuous conversation about one object, not eight unrelated commands. Number One never stores its own copy of tasks, evidence, or preferences — it reads and writes the same canonical tables every other surface uses.

## How do the Workbenches divide responsibility?

Unchanged from Mission 6A, validated again in this mission: Chair (executive perspective), Hub (orientation, "where do I go next"), Ready Room (execution — "what am I doing, how do I start"), Human Systems (capacity/regulation/support patterns). Hub now has a real, low-friction path into Ready Room for a specific task (`?task=<id>`) instead of forcing a detour through the mission-review surface.

## LifeOS Hub — does it work as the orientation layer?

Assessed explicitly against ORIENT→SHOW WHAT MATTERS→HELP ME CONTINUE→GET ME TO THE RIGHT CAPABILITY (Captain-requested closure-pass check, not assumed satisfied by the `?task=` deep link alone). 5 of 7 criteria already held (canonical context via shared synthesis functions, no duplication of Chair/Attention-State, no mobile-specific defect). 2 real, bounded gaps found and fixed: Number One was undiscoverable from Hub or global nav (fixed with a direct "Ask Number One" link + `?advisor=` deep link into the existing advisor console); Hub had no "where I left off" signal at all (fixed with one capped, single-item pick-up-task card, explicitly not a second Remember panel — see knowledge record for the reasoning boundary). Both fixes are link/data-source additions to the existing pattern, not a redesign.

## How does capacity change behaviour?

Green/Amber/Red/Unknown gates Follow-Through's notification delivery (`_apply_capacity_gate`) and Ready Room's daily task cap (`capacityLimitForPosture`). It never changes what's true — only what's shown, when, and how insistently. Critical/safety-relevant signals (Command Centre's mission-staleness/health-decline evaluator) remain interruptive regardless of capacity, by design.

## How does execution support work?

Mission 4's decompose endpoint (`first`/`smaller`/`another` modes) now has a second entry point: Number One's `stuck`/`cant_start`/`too_much` intents call the same Model Router endpoint directly, so the Captain gets identical execution support whether they open Ready Room or just type "I'm stuck" to Number One.

## How does HQ remember and follow through?

Capture writes one row to `captured_items`. Remember is a filtered, capacity-aware view over `personal_tasks` + unresolved captures — not a second table. Follow-Through owns notification/defer/complete semantics against `personal_tasks`. Number One's `remember`/`what_forgetting`/`not_now`/`done` intents call exactly these paths.

## How does HQ learn what helps?

Mission 5's evidence engine (`capacity_intervention_events`, domain-scoped to `ready_room`/`capacity`) tracks attempts/better/worse per intervention, gated by a minimum sample size before it's trusted. Number One's execution-support replies now quietly reference this ("we've had better results before...") only when the evidence clears that bar and the Captain hasn't excluded it.

## How does Captain preference override adaptation?

`capacity_preferences` (`do_not_suggest` / `preferred`) is checked by `isDoNotSuggest()` before Number One includes any evidence-based suggestion, and by the existing `support-effectiveness` route for Ready Room's own ranking. One preference store, checked from both surfaces — never a surface-local exclusion list.

## How does the experience work across surfaces?

Telegram (XO bot, Capacity bot — two processes, one coherent interaction model, no shared evidence duplication), the LCARS Portal web console (Number One's chat persona, now dispatch-aware), Ready Room, Hub, and notifications all read/write the same canonical tables (`personal_tasks`, `captured_items`, `capacity_intervention_events`, `capacity_preferences`). No surface computes its own competing version of task state, evidence, or preference.

## What remains native-platform responsibility?

Not re-litigated in this mission (no new capability register item required it) — the existing boundary (device alarms/timers/DND/accessibility features are native-owned, HQ doesn't rebuild OS functionality) stands unchanged.

## What technical debt remains?

1. Two G-008-readiness signals (`decision_effectiveness.py` live/jsonl, `get_decision_quality_stats()` orphaned/`outcome_records`) compute the same threshold from different sources — needs a real migration decision, not a guess.
2. `remember` has no idempotency key — a retried capture command can create a duplicate `captured_items` row (found by the closure pass's executable dispatch-scenario proof; every other canonical mutation in the dispatcher is naturally idempotent, this one is not).
3. `evidenceAwareNote()` can restate what a just-completed decompose call already did (cosmetic).
4. `too_much` and `cant_start` share one decompose mode (`smaller`) — no dedicated overload mode exists on the Model Router endpoint yet.
5. Multi-candidate disambiguation ("which of two plausible tasks") is not implemented in the deterministic dispatcher — the context-store is single-slot by design; falls through to the LLM layer today.

## What was deliberately not built?

- A second Telegram bot merging XO and Capacity Bot — the two-process design is justified and tested (`test_capacity_dedup.py`).
- Browser/PWA voice capture — Telegram voice already satisfies the canonical single-ingress requirement; building a second surface wasn't justified by demand.
- A "fix" to `commandState.ts`'s `CommandPosture` vocabulary — it's a documented, intentional third concept, not a collision.
- Any behavioural scoring, productivity grading, or exposed confidence/posterior numbers in Number One's replies.

## What evidence proves the programme works?

- 706/706 tests pass (66 files) at final merge, including 10 intent-classification tests, 14 dispatch-scenario tests (executable cross-surface proof), and 5 idempotency tests (same-request retry, concurrent race, legitimate repetition, failure/retry, no-key-supplied). `npx tsc --noEmit` clean.
- Existing, already-passing suites constitute the capacity/posture representative matrix: `personalTasks.readyRoomContext.test.ts` (6-state posture vocab, canonical-truth stability, Captain override) and 27/27 live-run Python capacity-gate tests (Green/Amber/Red, canonical-truth stability, P0-protection override).
- Adversarial review of the full diff found no critical/high-severity defects; the one genuine gap it enabled discovery of (remember's missing idempotency key) was classified as a blocking defect and fixed before merge, not filed as debt.
- Convergence register: all 10 items from Missions 6A/5 carry an explicit disposition (2 corrected mid-mission from an initial discovery fork's mistaken "defect" call, after reading the actual documented rationale in the code).
- LifeOS Hub: explicitly assessed against ORIENT→SHOW WHAT MATTERS→HELP ME CONTINUE→GET ME TO THE RIGHT CAPABILITY; 2 real gaps found and fixed (Number One discoverability, interruption-recovery signal).
- All 19 CI checks green on final head, including merge-gate.

## Production verification — migrations 0219 + 0220 (applied, Captain-approved, verified)

Both applied to live Supabase (project `cjvrpjwewsrumnbdydgg`) after Captain authorisation, verified post-apply via Supabase MCP tools:
- `number_one_context`: exists, `relrowsecurity = true`, policy `number_one_context_authenticated_all` present (`authenticated`, `ALL`, `using(true)`/`with_check(true)`), 0 rows (clean).
- `captured_items.idempotency_key`: column exists, nullable text.
- `captured_items_idempotency_key_uidx`: unique partial index confirmed exactly as written (`WHERE idempotency_key IS NOT NULL`).
- `get_advisors(security)`: no new finding attributable to either migration. Pre-existing `user_settings` RLS-enabled-zero-policies finding (36 tables total) confirmed present and unrelated — separate, pre-existing debt, not expanded into this mission.

## Final PR / merge status — PROGRAMME COMPLETE

- PR #281, branch `mission6b-final-cos-convergence`.
- Merge SHA: `e93523951b30eff923b4b731727164dd6324639d` (merge commit "Merge pull request #281 from timjardenross/mission6b-final-cos-convergence").
- Authoritative post-merge `main` SHA (fast-forwarded, `/opt/starship-endeavour`): `e93523951b30eff923b4b731727164dd6324639d`.
- All 19 required CI checks (LCARS Portal CI, Python CI, Vercel, merge-gate) green at merge time; no bypass.
- Working tree clean post-fast-forward; all Mission 6B artifacts (Number One dispatcher, migrations 0219/0220, Hub uplift, PickUpBanner repair, Command Centre notification retirement, knowledge/convergence/closure records) verified present on `main`.

## Final residual technical debt register (post-idempotency-fix)

1. Two G-008-readiness signals (`decision_effectiveness.py` jsonl-backed live; `get_decision_quality_stats()` `outcome_records`-backed orphaned) — different evidence sources computing the same threshold. Unreconciled by design; needs a real migration decision.
2. `evidenceAwareNote()` can restate what a just-completed decompose call already did — cosmetic phrasing overlap, not incorrect.
3. `too_much`/`cant_start` share one decompose mode (`smaller`) — correct given the Model Router endpoint's real contract.
4. Multi-candidate disambiguation ("which of two plausible tasks") is not implemented in the deterministic dispatcher — the context-store is single-slot by design; falls through to the LLM layer today.
5. Pre-existing, separately-owned: `user_settings` has RLS enabled with zero policies live (found incidentally during the 0219 live-schema check) — fail-closed, likely broken, unrelated to Mission 6B's own security posture.

No fixes were manufactured merely to produce a zero-item register.
