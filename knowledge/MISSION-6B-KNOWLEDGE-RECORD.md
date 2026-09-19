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

## Residual technical debt (explicit, not hidden)

1. **Two G-008-readiness signals** (`core/intelligence/decision_effectiveness.py`, jsonl-backed, live; `core/coordination/mission_knowledge_store.py`'s `get_decision_quality_stats()`, `outcome_records`-backed, orphaned) compute the same 10-decision threshold from different evidence sources. A future migration mission should either migrate `logs/decisions/*.json` history into `outcome_records` or extend `get_decision_quality_stats()` to match the full report shape before reconciling — not attempted here per this mission's own "do not guess architectural authority" boundary.
2. `evidenceAwareNote()` / decompose-mode overlap noted above — cosmetic, not incorrect.
3. Browser/PWA voice capture remains undeferred-but-unbuilt (8.5) — Telegram voice covers the canonical requirement; revisit only if real Captain demand for a second voice surface emerges.
4. Full capacity × posture matrix (brief §20) and cross-surface Telegram→Capture→Number One→Hub→Ready Room→notification→completion→evidence live-system walkthrough (brief §21) were reasoned through architecturally (every step routes through canonical tables/services already verified live) but not executed as a live end-to-end manual run in this pass — the deterministic unit-level scenario (classifyIntent's 9 intents + argument extraction) is tested; a full live walkthrough is recommended before the next mission builds on this surface.

## PR / merge

Not yet pushed — awaiting explicit Captain go-ahead per repo git discipline (push/PR is a shared-state, visible-to-others action). See programme closure record for final status once merged.
