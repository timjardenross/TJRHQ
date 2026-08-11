# Recovery Pulse Redesign — Part B Implementation

**Date:** 2026-08-10
**Authority:** Captain-approved (Part B of the Recovery Pulse redesign mission — see `recovery-pulse-redesign-proposal.md` in this directory; Part A, the 4→3 pulses/day frequency cut, was implemented separately, see `recovery-pulse-3x-implementation.md`).
**Status:** Implemented, verified, committed.

## What changed

The Telegram Recovery Pulse flow (`telegram-bots/xo/app.py`) went from one fixed 3-question sequence for every pulse type to a **time-of-day-asymmetric flow**:

| Pulse type | Taps | Questions | Change |
|---|---|---|---|
| **Morning** | 3 | energy → nervous_system → body_signals | Unchanged (per explicit scope: "no change here") |
| **Midday** | 2 | energy → nervous_system | body_signals question dropped |
| **Evening** | 3 | energy → nervous_system → **day_win (new)** | 3rd question replaced: "One thing that went okay today?" instead of a repeat of body_signals |

Daily tap count: 3+2+3 = 8 (down from the pre-redesign 3×3 = 9, and the original 4×3 = 12 before Part A).

The new evening reflection question — "One thing that went okay today?" / 🙂 Something did · 😐 Nothing much · 😞 Rough day — writes a new `day_win` column, closing the PERMA/Accomplishment gap identified in the proposal (§2.5): the old flow had zero evening-specific content.

**Scope note on wording:** the proposal's mock also suggested relabeling the energy question ("High/Moderate/Low" → "Plenty/Some/Little" etc.) and "Dysregulated" → "Shut down", varying per pulse type. The Captain's task instructions explicitly scoped this implementation to **question count and the new evening question only** ("Morning: ... no change here" was explicit; midday/evening bullets only discussed tap count and the new question). I did not apply the proposal's cosmetic relabeling — energy and nervous_system keep their exact existing question text and button labels across all three pulse types. This avoids scope creep beyond the exact authorized instruction; flagging here in case the wording changes are wanted as a follow-up decision.

## Files changed

**`telegram-bots/xo/app.py`:**
- New `_pulse_final_key(pt)` — single source of truth for which key ends each pulse type's flow: `'m'` for midday (2-tap, ends on nervous_system itself), `'s'` for morning (body_signals), `'w'` for evening (day_win). Unknown pulse types default to the morning-shaped 3-tap flow (safe fallback, consistent with `_PULSE_LABELS.get(pt, pt)`'s existing pattern).
- New `_kb_day_win(pt, e, m)` — the evening-only 3rd-step keyboard (🙂/😐/😞), callback data uses a new `w=` key.
- `_kb_stress` docstring updated to note it's morning-only now (unchanged in behavior).
- `_write_pulse()` signature changed: `body_signals` and `day_win` are now optional kwargs (default `None`). Only columns actually supplied are included in the upsert payload — so a slot re-submission never clobbers a previously-written value for a column that pulse type doesn't ask about.
- `handle_pulse_callback()` rewritten to branch on `_pulse_final_key(pt)` rather than a fixed `if e and m and s` check: determines terminal state per pulse type, shows the correct 3rd-step keyboard (body_signals for morning, day_win for evening, nothing for midday), and renders the correct summary line (`Body: ...` vs `Today: ...`) in the final confirmation message.
- `_DAY_WIN_LABELS` dict added for human-readable display (`something_did` → "Something did", etc.).
- Callback data format comment and `/help` text updated to describe the new variable-length flow.

**`telegram-bots/xo/voice_capture.py`:**
- `promote_recovery_pulse()` docstring extended (behavior unchanged) to explicitly document why it stays notes-only for all three (now-differing) pulse-type question sets: a one-line voice transcript has no reliable way to answer a specific multi-choice question the way a button tap does, so it never populated `energy`/`nervous_system`/`body_signals` from free text before, and now also never populates the new `day_win` — same reasoning, extended to the new field. No functional change; this was already correct pre-redesign and required no code fix, only clarifying why.

**Database (Supabase project `cjvrpjwewsrumnbdydgg`):**
- New migration `core/infrastructure/supabase/migrations/0119_recovery_pulses_add_day_win.sql`, applied live:
  ```sql
  ALTER TABLE public.recovery_pulses
    ADD COLUMN day_win text
      CHECK (day_win IN ('something_did', 'nothing_much', 'rough_day'));
  ```
  Nullable, no backfill. Verified live via `information_schema.columns` (column exists, type `text`, nullable) and `pg_constraint` (`recovery_pulses_day_win_check` present with the exact 3-value CHECK).
- Confirmed `recovery_confidence_today` and `recovery_pulse_adherence_7d` views select explicit column lists (not `SELECT *`) and don't reference `day_win` or the pre-existing `mood`/`stress` — adding the column required no view changes.

## Schema drift investigation (Task 3) — mood/stress NOT dropped, live readers found

The proposal (§3) flagged `recovery_pulses.mood`/`.stress` as apparently dead — "nothing in `app.py`'s `_write_pulse()` ever populates them." That's true for the **Telegram bot specifically**, but a fresh repo-wide grep (Python and TypeScript) before dropping anything found this is **not dead platform-wide**:

**Live writer:** `lcars-portal/src/app/human-systems-workbench/medical/pulse/page.tsx` — the LCARS Portal's own Medical Bay manual pulse-logging UI (session-gated, `requireSession()`) — POSTs to `lcars-portal/src/app/api/human-systems/pulse/route.ts`, which upserts its payload (including `mood`/`stress` for pulse types that collect them) directly into `recovery_pulses`. This is the same Portal manual-entry surface the Part A implementation note already identified as still 4-way (`end_of_day` included) and out of that mission's scope — confirmed here that it also actively writes `mood`/`stress`.

**Live readers:**
- `lcars-portal/src/app/api/wellness/route.ts` — selects `energy,mood,stress,readiness,pain_score,notes` from `recovery_pulses`, merges pulse `mood` into the day's wellness snapshot when fresher than the daily log.
- `lcars-portal/src/app/api/human-systems/route.ts` — selects `energy,mood,stress,readiness,pain_score` from `recovery_pulses`, includes a `stressToNs()` fallback heuristic explicitly for when `nervous_system` is null but `stress` isn't.
- `lcars-portal/src/components/RecoveryConfidencePanel.tsx` / `lcars-portal/src/lib/useRecoveryConfidence.ts` — display `latest_mood`.
- `lcars-portal/src/app/(app)/timeline/page.tsx`, `lcars-portal/src/app/(app)/operating-model/page.tsx` — select and display `mood` from pulse-derived data.
- `core/command-centre/backend/api/personal-health.js` — `POST /pulse` writes `mood`/`stress` to `recovery_pulses` directly (a second live writer, independent of the Portal route above); `GET /status` reads `latest_mood`/`latest_stress`.
- `core/command-centre/backend/api/timeline.js`, `connectors/supabase-connector.js` — read `mood` from `recovery_pulses`.

**Conclusion: `mood` and `stress` are NOT dropped.** Per the task's own instruction ("If you find even one live reader ... do NOT drop them"), and this investigation found multiple live readers plus two independent live writers (LCARS Portal manual pulse page, and Command Centre backend's `/pulse` POST) — dropping these columns would break the Portal's Medical Bay pulse logging and its wellness/human-systems/timeline/operating-model displays. Left untouched. No migration for this item.

This confirms the schema situation is genuinely split by surface: the **Telegram bot** (the flow this mission touches) uses `energy`/`nervous_system`/`body_signals`(+now `day_win`) and never reads or writes `mood`/`stress`; the **LCARS Portal + Command Centre backend** (a separate, still-4-way manual-entry stack, already flagged as out-of-scope reconciliation work in the Part A note) actively use `mood`/`stress` and don't yet know about `body_signals`/`day_win`. Both column sets are real, live, and currently serving different surfaces of the same table — a genuine reconciliation opportunity, not a defect to silently fix here. Flagging as follow-up, not actioned.

## Verification performed

1. **`python3 -m py_compile`** on `telegram-bots/xo/app.py` and `telegram-bots/xo/voice_capture.py` — clean.
2. **`python3 telegram-bots/xo/test_voice_capture.py`** — full suite, **173/173 passed** (unaffected by the docstring-only change to `promote_recovery_pulse`).
3. **Scripted trace** of `_parse_cb` + `_pulse_final_key` callback-state logic through all three pulse types' full tap sequences, confirming exact question order, correct terminal detection, and correct `energy`/`nervous_system`/`body_signals`/`day_win` values at each step:
   - Morning: `e=high` → ask nervous_system → `m=calm` → ask body_signals → `s=quiet` → **TERMINAL**, writes `energy=high ns=calm body_signals=quiet day_win=None`.
   - Midday: `e=moderate` → ask nervous_system → `m=activated` → **TERMINAL**, writes `energy=moderate ns=activated body_signals=None day_win=None`.
   - Evening: `e=low` → ask nervous_system → `m=dysregulated` → ask day_win → `w=something_did` → **TERMINAL**, writes `energy=low ns=dysregulated body_signals=None day_win=something_did`.
4. **Live Supabase verification** post-migration: `day_win` column exists (`text`, nullable) with constraint `recovery_pulses_day_win_check` = `CHECK ((day_win = ANY (ARRAY['something_did'::text, 'nothing_much'::text, 'rough_day'::text])))`.
5. **Schema drift investigation**: fresh `information_schema.columns` + `pg_constraint` query against the live table, plus a repo-wide grep across Python and TypeScript for `mood`/`stress` reads/writes (not just assumed from the proposal) — found live readers/writers, did not drop.
6. No existing tests cover `handle_pulse_callback`'s button-flow branching logic specifically (the module has no unit tests exercising Telegram callback handlers) — worth noting as a gap, not a blocker; verified via the scripted trace above instead.

## What I deliberately did not touch

- **Wording/relabeling** the proposal's mock applied to morning/midday/evening's energy and nervous_system questions ("Plenty/Some/Little", "Shut down", per-time-of-day question text variants) — out of the explicit authorized scope for this task (see "Scope note on wording" above).
- **The LCARS Portal + Command Centre backend's separate 4-way manual pulse flow** — untouched, same reasoning as Part A: different stack (Next.js/Express), not named in this task's scope, and reconciling it to the new asymmetric/day_win model is a real cross-stack decision that deserves its own sign-off, not a side effect of this mission.
- **`mood`/`stress` columns** — confirmed live, not dropped (see above).

## Deployment

`tg-xo.service` restarted after this change; see restart/journalctl confirmation in the mission close-out message.
