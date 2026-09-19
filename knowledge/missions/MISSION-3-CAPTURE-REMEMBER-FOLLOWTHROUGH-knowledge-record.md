# Knowledge Record — Mission 3: Capture, Remember & Follow-Through

| Field | Value |
|---|---|
| Mission | Mission 3 — Capture, Remember & Follow-Through (TJR HQ accommodation-mission series, Mission 1 → Mission 2 → **Mission 3**) |
| Date | 2026-09-19 |
| Branch | `mission3-capture-remember-followthrough` |
| Status | Delivered — 0 new regressions, migrations applied live, cross-surface fixture proven |
| Depends on | Mission 1 (canonical architecture: Domain State → Number One → Attention State → Surfaces), Mission 2 (capacity contract: Green/Amber/Red/Unknown) |

## Verdict in one line

The confirmed gap — capture never became a task, and two competing capture
paths existed (portal/voice → captured_items, Telegram → personal_tasks
directly) — is closed. Actionability is now an independent, LLM-derived
judgement from classification; routing is idempotent at the database level;
personal tasks now flow into the same canonical Attention State Number One
uses; Remember is a derived view, not a new domain; capacity gating logic
that had drifted into two dialects (raw `orange`/`red` vs canonical
`Amber`/`Red`) is unified on one canonical mapper.

---

## A. Runtime Map — final canonical flow

```
CAPTURE CHANNELS
  Portal/voice (lcars-portal quick-capture, XO voice_capture.py)  ─┐
  Telegram plain text (XO app.py cmd_message, NL-trigger gate)    ─┼──▶ captured_items
  /note command (XO app.py)                                       ─┘      │
                                                                            ▼
                                              ENRICHMENT (core/capture/enrichment_worker.py,
                                              capture-enrichment.timer, every 15 min)
                                                    │
                                    classification ("what is this")
                                    + actionable / actionable_confidence ("does this need action")
                                    -- independent LLM judgements, one call
                                                    │
                          ┌─────────────────────────┼──────────────────────────┐
                          ▼                          ▼                          ▼
              actionable=yes, conf>=0.6   classification=personal,   classification in
              → personal_tasks             conf>=0.85 → captains_log  {mission,decision,
              (idempotent: unique idx      _entries (auto-route)      research,reference},
              on source_capture_id)                                   conf>=0.5 →
                          │                                            intelligence_notes
                          ▼                                            (officer triage)
              Personal Task Attention Adapter
              (core/coordination/personal_task_attention_adapter.py)
              deterministic: overdue/urgency/importance/blocked/stalled-deferral
                          │
                          ▼
              ATTENTION STATE (core/coordination/attention_state.py)
              additive merge into context_service.py's /brief/number-one
              attention_items -- Number One's own items unchanged, personal
              task items appended, single canonical capacity policy shared
                          │
              ┌───────────┼────────────────────────┐
              ▼           ▼                        ▼
      NUMBER ONE      REMEMBER                CHAIR / HUB
      (brief.top_    (GET /remember --      Chair: dedicated Remember panel
      priorities,     filtered view of      (captains-chair-workbench/
      escalations)    the same adapter      _components/Remember.tsx)
                       + unresolved          Hub: NO dedicated section --
                       captured_items,       NEEDS_NOW-tier items already
                       both capacity-aware)  surface via existing Needs You
                                             (documented in hub/page.tsx)
                          │
                          ▼
              FOLLOW-THROUGH (intelligence/adhd/follow_through_engine.py,
              intelligence-scheduler.service, _adhd_nudge_job)
              reads personal_tasks directly (same canonical table, not a
              shadow copy); capacity source now canonical
              (capacity_zone_from_checkin(), was raw "orange"/"red" strings)
                          │
                          ▼
              CANONICAL NOTIFICATION PATH (core/platform/notification_service.py)
              enrichment_worker.py's confirmations always went through this;
              follow_through_engine.py's own Telegram sender is a deliberate,
              documented exception (needs message_id notify() doesn't return) --
              not a Mission 3 violation, not touched.
```

## B. Ownership Map

| Concern | Owner |
|---|---|
| Capture (all channels) | `captured_items` table; writers: portal quick-capture, XO voice_capture.py, XO app.py's NL-capture branch, /note command |
| Classification ("what is this") | `core/capture/enrichment_worker.py`'s LLM call, `classification` column |
| Actionability ("does this need action") | Same LLM call, independent judgement, `actionable`/`actionable_confidence` columns (migration 0217) |
| Routing decision | `enrichment_worker.py`'s dispatch order (actionable-first, then classification-based) |
| Personal action truth | `personal_tasks` table (migration 0090), `work_state` enum |
| Resurfacing / "what deserves attention now" | `core/coordination/personal_task_attention_adapter.py` (personal tasks) + `core/coordination/attention_state.py` (missions) |
| Remember | `context_service.py`'s `_http_remember()` — derived, no new table |
| Capacity interpretation | `core/health/capacity_score.py`'s `capacity_zone_from_checkin()` — the ONE canonical Green/Amber/Red/Unknown mapper, now consumed by attention_state.py, personal_task_attention_adapter.py, AND follow_through_engine.py |
| Follow-through lifecycle/nudging | `intelligence/adhd/follow_through_engine.py` — mode-based scheduling, quiet hours, daily cap; consumes canonical `personal_tasks` and canonical capacity, does not own a second attention model |
| Interruption/notification | `core/platform/notification_service.py` (canonical); follow_through_engine.py's direct Telegram sender is a documented, pre-existing, scoped-out exception |
| Presentation | Chair (`captains-chair-workbench`), Hub (`/hub`) — both read canonical state via shared hooks in `captainsChairData.ts`, neither derives its own truth |
| Captain override | `work_state`/`follow_through_paused`/`snoozed_until` columns, XO Telegram callback handlers (`tk|done`, `tk|snooze`, `tk|drop`, etc.) — untouched by this mission |

## C. Capture Routing Contract

Classification taxonomy (unchanged from pre-Mission-3): `reference | mission |
personal | research | decision | unclassified`. `unclassified` never routes
anywhere (hard invariant, unchanged).

New, independent actionability taxonomy: `yes | no | ambiguous` +
`actionable_confidence`. Routing precedence in `enrich_item()`:

1. `unclassified` → inbox only (hard invariant, checked first, unconditionally).
2. `actionable == 'yes'` AND `actionable_confidence >= 0.6` → `personal_tasks`
   (idempotent, DB-enforced).
3. `classification == 'personal'` AND `confidence >= 0.85` → captains_log
   (pre-existing MSN-0200-P2B path, unchanged).
4. `classification` in `{mission, decision, research, reference}` AND
   `confidence >= 0.5` → `intelligence_notes` triage (pre-existing MSN-0336
   path, unchanged).
5. Otherwise → inbox only, `actionable`/`actionable_confidence` still persisted
   for observability.

## D. Capture → Task Integration

- **Idempotency**: DB-level unique index `personal_tasks_source_capture_uniq`
  on `(source_capture_id) WHERE source_capture_id IS NOT NULL` (migration
  0217, applied live). A retried/duplicate enrichment pass hits a unique
  violation, resolved by looking up the existing task — never a second row,
  never an exception escaping the routing function.
- **Provenance**: `personal_tasks.source_capture_id` → `captured_items.id`
  (pre-existing column, now populated); `captured_items.routed_to_table` /
  `routed_to_id` → `personal_tasks` row (previously-unused columns, now
  populated consistently across all three routing functions).
- **Async confirmation dedup**: the idempotent-retry branch explicitly skips
  re-sending the Telegram confirmation (`already_routed` flag) — proven by
  `test_idempotent_retry_does_not_resend_confirmation` and the cross-surface
  fixture's retry step.
- **Notification-failure isolation**: `_send_telegram_confirmation()` now
  wraps `notify()` in try/except — a notification failure can never roll back
  or appear to fail routing that already succeeded (data writes happen
  before the confirmation call in all three routing functions).

## E. Remember Model

`GET /remember` (`context_service.py`'s `_http_remember()`) — two derived
views, zero new persistence:

1. `resurfacing_tasks`: `attention_items_from_personal_tasks()` output,
   filtered to everything above `CAN_WAIT` — the same function
   `_http_number_one_brief()` calls, not a second computation.
2. `unresolved_captures`: `captured_items` still at `processing_status='pending'`
   — literally what failure-safety (§24) protects, made visible. Capped by
   capacity band (Red=3, Amber/Unknown=10, Green=30) — fewer, higher-value
   items under reduced capacity, no per-item scoring.

Capacity-awareness comes for free: Red demotes non-critical personal-task
items to `CAN_WAIT` inside the shared adapter, which this endpoint's filter
then naturally excludes. No second capacity rule exists in the Remember
endpoint.

## F. Personal Task Attention Adapter

`core/coordination/personal_task_attention_adapter.py` — deterministic rules
(mission §14's explicit preference over opaque scoring):

- `completed`/`abandoned` → never emitted.
- `follow_through_paused=True` → never emitted (Captain override wins).
- `work_state == 'blocked'` → `BLOCKED`.
- Overdue, or (urgency=5 AND importance>=4) → `NEEDS_NOW`.
- Due within 1 day, or importance>=4, or deferral_count>=3 (Follow-Through's
  own stalled-item signal) → `IMPORTANT_NOT_IMMEDIATE`.
- Otherwise → `CAN_WAIT`.

Wired additively into `_http_number_one_brief()` — Number One's own
`CoordinationBrief`/engine never queries `personal_tasks`; only the HTTP
response's `attention_items` array gains entries.

## G. Follow-Through Integration

Fold-in was scoped to the capacity source, not a rewrite of nudge scheduling
(explicitly approved: "Follow-Through may continue to own lifecycle/nudge-
specific behaviour, but it must consume the same underlying canonical
task/attention truth"):

- `follow_through_engine._fetch_todays_capacity_state()` now returns the
  canonical `Green`/`Amber`/`Red`/`Unknown` string via
  `capacity_zone_from_checkin()` (imported from `core/health/capacity_score.py`,
  zero heavy dependencies, safe in this cron-driven process) instead of
  reimplementing raw `"orange"`/`"red"` string handling.
- `_apply_capacity_gate()` signature/vocabulary updated to match; **behaviour
  proven identical** (30/30 existing + new tests pass, including
  `test_full_recovery_sequence_red_then_amber_then_green`).
- Follow-Through's own mode-based scheduling (`gentle`/`normal`/`persistent`/
  `deadline`/`waiting`), quiet hours, and daily cap are untouched.
- Follow-Through's direct Telegram sender (needs `message_id` back, which
  `notify()` doesn't return) is a deliberate, pre-existing, documented
  exception — not folded into the canonical notification path by this
  mission (explicitly out of scope: "do not broaden this into a Telegram
  consolidation project").

## H. Capacity Behaviour (Green/Amber/Red/Unknown)

Proven by `TestCapacityConsistency` in the cross-surface fixture and the
adapter's own unit tests:

- Capacity changes **presentation and category**, never mutates the
  underlying `personal_tasks` row (`task_row == task_row_before` asserted
  across all four capacity passes).
- Red demotes non-critical items to `CAN_WAIT`; critical (`NEEDS_NOW`) items
  proceed with a `"CRITICAL — proceed regardless of capacity"` note.
- Amber adds an advisory note only, no demotion.
- Green/Unknown: no per-item adjustment in this shared function (Mission 2's
  own established semantics, preserved verbatim) — Unknown is never MORE
  permissive than Amber at the list-filtering level
  (`follow_through_engine._apply_capacity_gate` still treats Unknown as
  Amber-equivalent for its own gating).

## I. Surface Changes

- **Chair**: new `Remember` panel (`captains-chair-workbench/_components/Remember.tsx`),
  thin presentation of `GET /remember` via `useRemember()` hook
  (`captainsChairData.ts`). Empty state enforced strictly, no manufactured content.
- **Hub**: no dedicated Remember section — documented decision in
  `hub/page.tsx` (NEEDS_NOW-tier personal tasks already surface via existing
  Needs You / `useNumberOneAttentionItems()`, which now additively includes
  personal-task items).
- **Ready Room**: untouched — UNSTICK ME still operates on `personal_tasks`
  directly, unchanged.
- **Telegram/XO**: `cmd_message`'s NL-capture branch now writes to
  `captured_items` (instant honest ack) instead of `personal_tasks` directly
  (async authoritative routing + confirmation). No Telegram-local
  actionability classifier added — the NL regex only gates "is this new
  information worth capturing" vs. ordinary chat, and extracts a
  title/temporal hint; it never sets `classification`.

## J. Failure & Recovery

Proven in `test_enrichment_worker.py` and `test_mission3_cross_surface_fixture.py`:

- LLM/enrichment failure → capture marked `ai_enrichment_status='failed'`,
  never deleted, `processing_status` untouched (no forced routing decision).
- Task-creation failure (insert exception) → capture stays `pending`, retried
  next pass, never lost.
- Notification-send failure → routing already committed, confirmation
  failure is a logged warning only (`_send_telegram_confirmation`'s new
  try/except).
- Worker restart / reprocessing the same pending row → idempotent (unique
  index), safe.
- Completed task reprocessed by the adapter → stays invisible (terminal
  `work_state` excluded), provenance fields untouched.
- Remember given malformed/incomplete source rows → degrades gracefully,
  still JSON-serialisable, never 500s the whole endpoint.
- Capacity resolver genuinely broken (raises) → propagates rather than
  silently defaulting to Green; the Flask boundary already returns a
  structured 500, not corrupted data.

## K. Test Evidence

- `core/capture/test_enrichment_worker.py` — 34 tests (actionability bridge,
  idempotency, notification-failure isolation, due-date hint preservation).
- `tests/test_follow_through_engine_capacity_gate.py` /
  `test_follow_through_capacity_recovery.py` — 30 tests (canonical capacity
  mapping, behaviour-preservation).
- `core/coordination/test_personal_task_attention_adapter.py` — 18 tests.
- `core/coordination/test_attention_state.py` / `test_attention_state_capacity.py`
  / `test_capacity_recovery.py` / `test_attention_state_ts_contract.py` — 35
  tests (generalised capacity policy, regression-free).
- `core/context-assembly/tests/test_number_one_brief.py` — 16 tests
  (personal-task merge, capacity pass-through, failure isolation).
- `core/context-assembly/tests/test_remember.py` — 7 tests.
- `telegram-bots/xo/test_nl_capture_ingress.py` — 10 tests (capture-ingress
  normalisation, honest ack, no local classifier).
- `tests/test_mission3_cross_surface_fixture.py` — 6 tests (full lifecycle,
  capacity consistency, failure/retry paths).
- **Full regression**: 1690 passed, 0 Mission-3-caused failures. 2 failures
  in `test_advisory_runtime.py`/`test_advisory_temporal.py` are a worktree
  environment gap (`logs/decisions/*.json` is gitignored runtime data present
  in the live checkout, absent from the git worktree) — confirmed passing on
  unmodified main with real data present; unrelated to any file this mission
  touched. 6 skipped (missing optional `semhash`/`llmsec` deps, pre-existing,
  unrelated). 12 deselected `TestLiveService` integration tests confirmed
  failing identically on unmodified main (require a running HTTP service).
- **TypeScript**: no `node_modules` installed in this environment (neither
  the live checkout nor the worktree) — `tsc --noEmit` / `next lint` could
  not be run. New/changed `.ts`/`.tsx` files were reviewed manually against
  existing, already-typed sibling components (`NeedsYou.tsx`,
  `useNumberOneAttentionItems`) for structural consistency. Recommend running
  `npm run typecheck` in `lcars-portal/` before merge.
- **Live migration verification**: 0217 and the pre-existing-gap 0204 applied
  to Supabase project `cjvrpjwewsrumnbdydgg`; columns/constraints/indexes
  confirmed present via direct schema queries; constraint enforcement (valid/
  invalid `actionable` values) verified inside a rolled-back transaction,
  confirmed zero residual rows afterward.

## L. Accommodation Coverage Matrix

Reconciled against the original accommodation list, scoped to items Mission 3
§26 named:

| Accommodation | Status |
|---|---|
| Bedside brain dump / writing instead of holding information mentally | **IMPLEMENTED** — capture is fast, unified, and failure-safe across portal/voice/Telegram |
| Notes / external brain | **IMPLEMENTED** — captured_items is the unified intake; nothing is silently lost |
| External task-starting support | **EXISTING / ALREADY PROVIDED** — Ready Room's UNSTICK ME, untouched, now reachable from Remember |
| One single actionable view | **PARTIALLY IMPLEMENTED** — Attention State now includes personal tasks alongside missions; a true single-pane view across all domains (decisions, calendar) is Mission 4/5 scope |
| Accountability / check-ins | **EXISTING / ALREADY PROVIDED** — Follow-Through engine, now capacity-source-unified but not rebuilt |
| External deadlines | **PARTIALLY IMPLEMENTED** — Telegram temporal-intent parsing preserved through the bridge; no NL date parsing added to the portal/TS side (deferred) |
| Point-of-action reminders | **EXISTING / ALREADY PROVIDED** — Follow-Through's mode-based resurfacing, untouched |
| Phone alarms/reminders | **HUMAN / NATIVE-DEVICE ACCOMMODATION** — not attempted, consistent with mission's own "do not build" list |
| Planning tomorrow | **MISSION 4** — executive-function/regulation support explicitly deferred |
| Reduced-capacity disclosure/context | **EXISTING / ALREADY PROVIDED** — Mission 2's capacity contract, now more consistently applied |
| Permission to design around the Captain's brain, not conventional productivity behaviour | **IMPLEMENTED** — deterministic categorisation, no gamification/scoring/streaks introduced anywhere in this mission |

## M. Deferred Register

- **Web voice capture**: not investigated/built this pass — Telegram voice
  remains the only voice channel. Owner: Mission 6 (per original spec §5) or
  a dedicated follow-up.
- **TS-side natural-language temporal parsing**: Ready Room's due-date field
  is still a raw HTML date input; the only NL date parser
  (`follow_through_nl.py`) is Python-only, Telegram-specific. A browser-side
  equivalent (or a shared API for it) is unbuilt. Owner: whichever mission
  next touches Ready Room's capture UX.
- **google-tasks/sync/route.ts**: a third, pre-existing direct-insert path
  into `personal_tasks` (external Google Tasks sync), unrelated to Mission
  3's own capture channels. Not investigated for competing-truth risk this
  pass. Owner: a future task-sync-specific audit if it ever needs one.
- **`intelligence/adhd/task_nudge_scheduler.py`**: confirmed dead (no live
  caller — `platform-runtime/adhd_task_scheduler.py`'s
  `start_adhd_task_scheduler()` has zero callers anywhere in the platform),
  kept in place for rollback per its own pre-existing documentation. Not
  Mission 3's to delete; flagged for a future dead-code sweep.
- **Decision Attention adapter, calendar Attention adapter, Evidence
  Library, autonomous execution**: explicitly out of scope per mission §27,
  untouched.
- **TypeScript typecheck**: not run this session (no `node_modules`
  available in either the live checkout or the worktree). Run
  `npm run typecheck` in `lcars-portal/` before merge.

---

## Final validation

> "I can give something to TJR HQ quickly, stop holding it in my head, and
> trust that HQ will bring it back when it matters."

Proven end-to-end by `tests/test_mission3_cross_surface_fixture.py`'s
`test_full_lifecycle`: a single Telegram capture ("send the specialist
referral on Friday") becomes exactly one canonical `personal_task`
(idempotent under retry), surfaces once in Attention State and once in
Remember (never duplicated), behaves consistently but differently under
Green/Amber/Red/Unknown capacity without ever mutating the underlying task
row, and disappears from active attention on completion while its
provenance back to the original capture remains intact.

No competing capture, task, capacity, notification, or attention
architecture was introduced. The one real duplication discovery found
(capacity-string handling, Green/Amber/Red vocabulary drift) was reconciled
onto the existing canonical mapper rather than papered over.
