# Recovery Pulse: 4/day → 3/day — Implementation Note

**Date:** 2026-08-10
**Authority:** Captain directive (Part A of the Recovery Pulse redesign mission — authorized to implement; Part B is research/proposal only, see `recovery-pulse-redesign-proposal.md` in this directory).
**Status:** Implemented, verified, committed.

## What changed

The Recovery Pulse check-in went from 4 pulses/day (morning · midday · end_of_day · evening) to 3 (morning · midday · evening). The dropped bucket was **`end_of_day`** (16:00–20:00 Brisbane), folded into **`midday`**, which now spans 12:00–20:00.

Morning (5:00–12:00) and evening (20:00–5:00) are unchanged.

## Why `end_of_day` and not another bucket

Three independent signals all pointed the same direction:

1. **Domain reasoning.** Morning (start-of-day baseline) and evening (end-of-day reflection/closure) are the two structurally distinct anchor points in daily self-report practice — see Part B's proposal for the sourcing. `midday` and `end_of_day` were always the least distinct pair: both are "how's capacity holding through the workday" checks, ~4 hours apart, with no structural reason (like a sleep cycle or a work/rest transition) separating them the way morning and evening are separated.

2. **Live usage data.** Queried `recovery_pulses` in Supabase (project `cjvrpjwewsrumnbdydgg`) on 2026-08-10 for all-time counts by `pulse_type`:

   | pulse_type | all-time | last 30d | last 14d |
   |---|---|---|---|
   | morning | 25 | 8 | 2 |
   | midday | 17 | 3 | 0 |
   | end_of_day | 14 | 3 | 0 |
   | evening | 10 | 2 | 0 |

   `end_of_day` is the second-least-logged bucket, behind only `evening`. Between the two least-used buckets, `evening` is the one worth *keeping deliberately* — closing-the-day reflection is high-value even when (especially when) it's the one people are too tired to do, whereas `end_of_day` has no distinct value proposition of its own once `midday` exists. Dropping `end_of_day` specifically, not `evening`, was the correct read of this data.

3. **Prior design intent already in the codebase.** `platform-runtime/recovery_scheduler.py` (D-055, Slack dispatcher, now retired) fires at exactly 3 windows — 07:00, 12:30, 20:00 — with no fourth `end_of_day`-specific window, and its own docstring says "Fires at 3 windows per day (matching Telegram)." That comment was aspirational/inaccurate at the time it was written (Telegram was still 4-way), but it shows a 3-window day was already the implicit target elsewhere in the platform before this change made Telegram consistent with it.

## Files changed

**Canonical bucketing (single source of truth):**
- `telegram-bots/xo/pulse_time.py` — `pulse_type_for_hour()` now returns only `morning`/`midday`/`evening`. Full rationale is in the module docstring. Every other Python surface below reads pulse data that ultimately came from this function (or the DB view built on top of rows it produced).

**Telegram UI (the flow the Captain actually taps):**
- `telegram-bots/xo/app.py` — `_PULSE_LABELS` dropped `end_of_day`; `/help` text, the XO system-prompt capacity line, `cmd_db_status`, and both checkmark-ledger renders in `handle_pulse_callback` now say `/3` and show 3 dots (`AM · Mid · PM` instead of `AM · Mid · EOD · PM`).

**Ledger / scoring math (the pieces the Captain's daily brief and dispatch logic depend on):**
- `intelligence/captains_brief.py` — `generate_eod_summary()`'s recovery-pulse block now renders 3 checkmarks and `AM · Mid · PM`.
- `telegram-bots/recovery_officer/engagement_dispatcher.py` — `RecoveryStatus` dropped the `end_of_day_done` field; `next_suggested_pulse`, `build_pulse_reminder`, `build_escalation_message`, `build_daily_summary` all updated to 3-way; `run_dispatch_check`'s "all pulses done" check is now `== 3`; the L1 reminder time-windows collapsed from 4 to 3 (`midday` reminder window now 12:00–19:00, absorbing the old `end_of_day` window).
- `telegram-bots/wellness_officer/intelligence.py` — `WellnessSnapshot` dropped `end_of_day_done`, `pulses_missing` default 4→3. **`escalation_level()`'s thresholds were rewritten**, not just relabeled: the old thresholds (`confidence <= 25` → L2, `<= 50` → L1) were calibrated to a 4-pulse percentage scale (25/50/75/100). Re-applying those same numbers against a 3-pulse scale (33/67/100) would have silently shifted what each escalation level means (1 pulse logged would read as 33%, landing in the *old* L1 band instead of L2). Switched to comparing `pulses_completed` directly (`<=1` → L2, `==2` → L1, `>=3` → clear) — scale-independent, and preserves the exact prior qualitative meaning regardless of how many pulses make up "all".
- `telegram-bots/wellness_officer/brief.py` — both `/4` pulse-count strings → `/3`.
- `telegram-bots/xo/test_voice_capture.py` — the two `pulse_type_for_hour` boundary assertions for 16:00/19:59 updated from expecting `end_of_day` to expecting `midday`.

**Database (Supabase project `cjvrpjwewsrumnbdydgg`):**
- New migration `core/infrastructure/supabase/migrations/0115_recovery_pulses_3x_daily.sql`, applied live. Rebuilds `recovery_confidence_today` and `recovery_pulse_adherence_7d` so `pulses_completed` / `pulses_missing` / `recovery_confidence` are computed from `COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening'))` rather than a bare `COUNT(*)`, with `LEAST`/`GREATEST` capping instead of a hard `CASE` lookup. This is deliberately defensive — see "What I deliberately did not touch" below for why a bare `COUNT(*)` would have been a live landmine.

## What I deliberately did not touch, and why

The `recovery_pulses` table's `pulse_type` CHECK constraint still allows `'end_of_day'` as a legal value. Two other live surfaces still reference it:

- **LCARS Portal Medical Bay** (`lcars-portal/src/app/human-systems-workbench/medical/pulse/page.tsx`, `RecoveryConfidencePanel.tsx`, `useRecoveryConfidence.ts`) — a Next.js pulse-logging UI that still offers a 4-way choice including `end_of_day`, and reads `end_of_day_done` from the view by name.
- **Command Centre backend** (`core/command-centre/backend/api/personal-health.js`) — its `/pulse` POST endpoint's `VALID_PULSE_TYPES` still includes `'end_of_day'`, and its `/status` response still surfaces `end_of_day_done`.
- **The Slack `/recovery-pulse` modal** (`platform-runtime/commands/recovery_pulse.py`) — also still 4-way. Confirmed via `systemctl is-active starfleet-slack-bot.service` → **inactive** (disabled), so this specific surface poses zero live risk right now, but the code itself wasn't touched.

None of these were named in the Captain's directive (which scoped to `pulse_time.py`, `app.py`, the recovery_pulses/recovery_confidence scoring, and the `captains_brief.py` ledger — i.e., the Telegram experience the Captain uses daily), and the LCARS Portal + Command Centre backend are a materially different stack (Next.js/Express) outside a same-session, same-review scope. I left them alone rather than expanding scope unilaterally.

To make sure leaving them alone couldn't silently corrupt anything: the new view SQL keeps `end_of_day_done` as a column (still `bool_or(pulse_type = 'end_of_day')`, so the Portal keeps reading a real, if usually-false, value instead of an undefined field) and filters the Telegram-facing scoring math to only count `morning`/`midday`/`evening`. Concretely: if the Portal is ever used to log a 4th, `end_of_day`-typed pulse on a day that already has all 3 canonical pulses, `recovery_confidence` still correctly reads 100% (capped, not silently zeroed) — a bare `COUNT(*)`-based CASE statement (the pre-existing pattern) would have hit a count of 4, matched no `WHEN` branch, and fallen through to `ELSE 0`, i.e. "no telemetry" despite full telemetry being logged. This was a real design flaw already latent in the CASE-based approach before this migration, not something my change introduced — I fixed it defensively while I was in there.

**Follow-up work this surfaces, not done here:** the LCARS Portal and Command Centre backend should eventually be reconciled to the 3-pulse model too, or an explicit decision made that the Portal intentionally supports a richer 4-way manual-entry mode than the fast Telegram flow. That's a cross-stack decision outside this mission's authorized scope — flagging it rather than hiding it, per Chief Engineer discipline.

## Verification performed

1. **`py_compile`** on all 7 changed Python files — clean.
2. **`python3 telegram-bots/xo/test_voice_capture.py`** — full suite, **173/173 passed**, including the updated `pulse_type_for_hour` boundary tests.
3. **Manual trace** of the ledger-rendering and scoring code paths with synthetic `RecoveryStatus` objects at 0/1/2/3 pulses completed, confirming: correct 3-dot ledgers, correct `next_suggested_pulse` sequencing (morning → midday → evening → None), correct escalation levels (0 pulses/morning window → L1 friendly reminder; 1 pulse → L2; 2 pulses → L1; 3 pulses → L0 clear), and correct `captains_brief.generate_eod_summary()` output (3 checkmarks, `AM · Mid · PM`).
4. **Live Supabase query** against `recovery_confidence_today` post-migration: today's actual data (1 real morning pulse logged) returned `pulses_completed: 1, pulses_missing: 2, recovery_confidence: 33, confidence_label: "Multiple pulses missing", midday_done: false, evening_done: false` — confirmed the live view is producing correct 3-way output against real rows, not just synthetic ones.

## Git note

`intelligence/captains_brief.py` had an unrelated, concurrently-landing change (a weekly OSINT exec-summary feature) sitting unstaged in the working tree when this was committed. Only the recovery-pulse hunk in that file was staged and committed here (via a hand-built patch applied with `git apply --cached`, verified with `git diff --cached` to contain exactly the intended 2-line change) — the other session's in-progress work was left in the working tree, untouched, for that session to commit itself.
