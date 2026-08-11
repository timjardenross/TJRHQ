# Wellness-coaching automation — de-duplicated /dispatch check goes live

**Date:** 2026-08-10
**Author:** Chief Engineer (Advisory, USS-TJR-003), implementing on Captain directive
**Source finding:** `.claude/skills/bot-reviews/fixes-2026-08-09/final-4-domains.md` §4
("wellness-coaching: left as wired-but-quiet" — the open question left there was
exactly this: is automating `/dispatch` safe, and what does it need first).

## Summary

`telegram-bots/recovery_officer/engagement_dispatcher.py::run_dispatch_check()`
is now running proactively on `intelligence-scheduler.service`, every 45
minutes between 06:00–23:00 Brisbane time, instead of being reachable only via
the XO bot's manual `/dispatch` command. The blocker that stopped this from
being a five-minute timer wiring — `run_dispatch_check()` has no
de-duplication and is a pure function of current pulse state, so a naive
timer would re-send an identical reminder every tick for as long as a pulse
window stayed open and unlogged — is fixed with a persisted Supabase
de-dup ledger, not an in-memory flag.

Live-verified at deploy time: the automation's first-ever run sent one real,
accurate Telegram message (an L2 "confidence low" escalation, reflecting the
Captain's genuine unlogged state at the time — 1/3 pulses done, 33%
confidence) and correctly wrote its own de-dup marker so it will not repeat
for that window.

## Design decisions

### 1. De-duplication: `wellness_reminder_log` table (migration 0118)

One row per `(window_date, pulse_window, action)` actually dispatched:

```sql
create table wellness_reminder_log (
  id                  uuid primary key default gen_random_uuid(),
  window_date         date not null,
  pulse_window        text not null check (pulse_window in ('morning', 'midday', 'evening')),
  action              text not null,
  confidence_at_send  integer,
  sent_at             timestamptz not null default now(),
  created_at          timestamptz not null default now(),
  unique (window_date, pulse_window, action)
);
```

- `window_date` — Brisbane calendar date (matches `recovery_pulses.log_date`'s
  own Brisbane-anchored semantics; `recovery_confidence_today` already uses
  `AT TIME ZONE 'Australia/Brisbane'` for the same reason).
- `pulse_window` — the canonical morning/midday/evening bucket **at the
  moment of the check**, computed via `telegram_bots.xo.pulse_time.pulse_type_for_hour()`
  — the single source of truth for the 3x/day schedule (Captain directive
  2026-08-10, migration 0115), not a second copy of the split.
- `action` — the exact dispatch decision string `run_dispatch_check()` already
  produces internally (`reminder_morning`, `reminder_midday`,
  `reminder_evening`, `escalation_l2`, `escalation_l3`, `daily_summary`).
  Keying on `(window, action)` rather than just `(window)` means a
  *different, still-accurate* signal (e.g. an escalation about the other two
  still-missing pulses) is allowed to fire once even after the window's L1
  reminder already went out — see Case C below for why that's the right
  call, not a dedup gap.

Checked via `_reminder_already_sent()` before every send, recorded via
`_record_reminder_sent()` immediately after a real send —
`run_dispatch_check()`'s own new `_dispatch()` helper wraps this so every
branch (L1 reminder, L2/L3 escalation, daily summary) goes through the same
gate; nothing bypasses it.

**Fail-closed on error**: if the dedup check itself throws (network error,
missing client, RLS denial), it is treated as "already sent" and the caller
skips — same contract as `intelligence/adhd/task_nudge_scheduler.py`'s
`NudgeRateLimiter.should_nudge()` ("don't nudge if we can't check"). A missed
reminder recovers next window; a Telegram message that already went out
cannot be un-sent, so an uncertain check must never resolve to "send".

**Why Supabase, not the existing SQLite `NudgeRateLimiter` pattern**: the
mission's explicit safety requirement is that the guarantee survive
scheduler restarts. `NudgeRateLimiter`'s SQLite file lives at
`/tmp/adhd_nudges.db` by default — durable across a *process* restart but not
guaranteed across a host reboot or a different deployment target, and this
module already has an established Supabase-write convention elsewhere in the
platform (`captains_daily_briefs`, `domain_heartbeats`) that RLS and the
Telegram bot's own client already know how to talk to. Supabase was the
better fit for this specific table, not a rejection of the SQLite pattern in
general.

**RLS**: mirrors `recovery_pulses`' own dual-role pattern (migration
0110/0115) — `service_role` gets `ALL`, `authenticated` gets `SELECT`+`INSERT`.
This covers both credential shapes actually in use: the scheduler daemon's
explicit `SUPABASE_SERVICE_ROLE_KEY` client, and whatever role the live XO
bot's own `SUPABASE_KEY` resolves to (not inspected directly — the value
wasn't read, only confirmed to exist as an env var name, per the "never
distribute/inspect secrets you don't need to" discipline).

### 2. A real bug found and fixed along the way: naive local time

`run_dispatch_check()`'s `should_remind` hour-of-day gating used
`datetime.now().hour` — **naive local server time**, not Brisbane time. This
is the exact class of drift risk MSN-0305 already fixed once in
`wellness_officer/intelligence.py::escalation_level()` ("the Slack copy used
naive local system time instead of Brisbane time... 'afternoon' would
resolve differently depending on which copy ran and where") — the fix just
never reached this second, independent copy of a Brisbane-hour read in the
same file. Given this mission was explicitly asked to ground the automation
in the *real* current pulse windows, leaving a known-bad time source in place
while building de-dup logic on top of it would have been building on sand.
Fixed via a new `_brisbane_now()` helper with the same
try `zoneinfo` / except fall back to naive `datetime.now()` contract already
used by the module's own `_brisbane_today()`.

One thing this did **not** fix, deliberately out of scope: escalation_l2's
own hour-gating (`wellness_officer/intelligence.py::escalation_level()`) has
no hour floor at all once `pulses_completed <= 1` — it can return level 2 at
any hour of the day, independent of whether it's 3am or 3pm. That's
pre-existing behaviour, unrelated to my changes, and already reachable today
via manual `/dispatch`. I did not touch it. Instead the scheduled **job**
itself gates to 06:00–23:00 Brisbane before it ever calls
`run_dispatch_check()` at all (see Cadence below) — belt-and-braces on top of
the pre-existing gap rather than a fix to it.

### 3. Cadence: 45 minutes, 06:00–23:00 Brisbane, on `intelligence-scheduler.service`

- **Where**: `intelligence/scheduler.py`'s `_start_scheduler()` — the same
  live `BlockingScheduler` daemon that already runs
  `_intraday_status_collection_job` (`IntervalTrigger`, 180 min),
  `_attention_evaluation_job` (`IntervalTrigger`, 10 min), and
  `_adhd_nudge_job` (`IntervalTrigger`, 60 min, also Telegram-bound). New job
  `_wellness_reminder_job`, registered exactly the same way
  (`IntervalTrigger` + `next_run_time=datetime.now(tz)` to fire immediately on
  service start rather than waiting a full interval, same as the intraday and
  attention jobs). No new standalone service stood up — this repo already
  has more schedulers running than it needs (per the platform registry's own
  "two uncoordinated schedulers" flag), so reusing the live one was the
  composition-first call, not a new fourth process.
- **Interval — 45 minutes**: the mission brief suggested 30–60 min "fine-grained
  enough to nudge reasonably promptly within a window without being naggy."
  Checked against the actual window widths in `pulse_time.py`: morning is
  7 hours (5–12h), midday is 8 hours (12–20h), evening is 9 hours (20–5h
  wrapping past midnight) — all comfortably wider than even the top of the
  suggested range, so the choice is about promptness-vs-noise within a
  window, not about missing a window entirely. 45 min lands in the middle of
  the suggested range: a reminder lands within 45 min of a window opening
  (and of the Captain not having logged anything), without checking so often
  that a`45-minute cadence produces meaningfully more Telegram traffic than a
  60-minute one for the same de-duplicated outcome. Configurable via
  `WELLNESS_REMINDER_INTERVAL_MINUTES` env var (matches the
  `*_INTERVAL_MINUTES` convention already used for the other three interval
  jobs) if the Captain wants it tighter or looser later — no code change
  needed.
- **Hour gate — 06:00–23:00 Brisbane**: job-level, checked before
  `run_dispatch_check()` is even called. Belt-and-braces specifically because
  `escalation_l2`'s own internal hour floor is weaker than the L1 branch's
  (see §2 above) — this closes that gap for the automated path without
  touching the pre-existing function. Configurable via
  `WELLNESS_REMINDER_ENABLED` (default `true`) for a fast kill-switch without
  a redeploy, matching `ADHD_NUDGE_ENABLED`'s existing convention.

### 4. Bot adapter: `_StandaloneTelegramBot`

`run_dispatch_check()`'s `_send()` calls `bot.send_message(chat_id=, text=,
parse_mode=)` synchronously. The live `/dispatch` command handler
(`telegram-bots/xo/app.py::cmd_dispatch`) passes a `_BotAdapter` wrapping a
real `python-telegram-bot` `Bot` instance and fires it via
`asyncio.get_event_loop().create_task(...)` — that only works inside an
already-running asyncio event loop (the bot's own). `intelligence/scheduler.py`
runs a synchronous `BlockingScheduler` with no event loop at all, so reusing
`_BotAdapter` directly would have silently done nothing (a coroutine created
and never awaited).

Added `_StandaloneTelegramBot` to `engagement_dispatcher.py` — a minimal
synchronous adapter doing a raw `urllib` HTTP POST to the Bot API, same idiom
already established in `core/platform/notification_service.py::_send_telegram()`
and `core/coordination/command_bus.py`'s private senders (both already proven
patterns for sending Telegram from a non-async process). This satisfies the
module's own docstring, which already promised a "Standalone (cron /
APScheduler)" mode and listed `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` as
required env vars — the promise existed in the docstring before this
mission; the code to back it up did not.

### 5. A second real gap found while wiring the scheduler job: env var mismatch

`intelligence-scheduler.service`'s `EnvironmentFile=` is
`platform-runtime/.env`, which defines `SUPABASE_SERVICE_ROLE_KEY` but **not**
`SUPABASE_KEY` (confirmed by name only, not value). `engagement_dispatcher.py`'s
own `_get_supabase_client()` reads `SUPABASE_KEY` — a name that only exists in
`telegram-bots/xo/.env` (loaded by `tg-xo.service`, not the scheduler daemon).
Had the scheduler job called `run_dispatch_check()` without an explicit
`supabase_client=`, it would have silently gotten `client=None` inside the
dispatcher, `get_recovery_status()` would have returned the all-zero
`_STATUS_DEFAULTS`, and the automation would have run forever against fake
"no telemetry" data — the exact wrong-data risk this kind of cross-process
wiring invites. `_wellness_reminder_job()` builds its own client explicitly
from `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` and passes it in, closing
this before it ever ran live.

## Verification

### Static checks

- `python3 -m py_compile` clean on both changed files, under both the
  `platform-runtime/.venv` and `telegram-bots/xo/.venv` interpreters.
- No existing test file specifically covers `engagement_dispatcher.py`
  (confirmed via repo-wide search). Ran the adjacent `pulse_time.py`-covering
  suite (`telegram-bots/xo/test_voice_capture.py`, 173 tests) as a regression
  check on the shared `pulse_type_for_hour()` dependency — unaffected, all
  173 pass.

### The 4 required trace-through cases — verified twice, against the real
`wellness_reminder_log` table, RLS included, with isolated fake test dates
(`2099-01-15`, `2099-02-20`) so no real dedup rows were touched, and a
`DummyBot` in place of the real Telegram API so no test message was sent.
Cleaned up after each run (confirmed 0 leftover rows). Run once against
whichever branch the real live `escalation_level()` (real-clock, unmocked)
happened to select, and once more with `escalation_level` forced to `1` to
specifically exercise the L1 `reminder_<pulse_type>` branch called out in the
mission brief.

| Case | L2/L3 branch result | L1 `reminder_X` branch result |
|---|---|---|
| **(a)** window just opened, nothing logged — should send once | `action=escalation_l2`, `deduped=false`, `message_sent=true`, 1 real call to `bot.send_message` | `action=reminder_morning`, `deduped=false`, `message_sent=true`, 1 call |
| **(b)** same window, rechecked 30 min later, still nothing logged — should NOT re-send | `deduped=true`, `message_sent=false`, 0 calls | `deduped=true`, `message_sent=false`, 0 calls |
| **(c)** Captain logs a pulse mid-window — should NOT send for that window anymore | morning now logged → action becomes `escalation_l2` again (a *different*, still-accurate signal about the 2 remaining pulses) but this too dedupes on a repeat check 10 min later; critically, `reminder_morning` never re-appears once `morning_done=True` | `action=none` — `next_suggested_pulse` skips to midday, but midday's `should_remind` window (`hour>=12`) isn't open yet at 09:45, so genuinely nothing to send |
| **(d)** window rolls over to the next pulse type — should be eligible to send again | new `pulse_window=midday` → `deduped=false`, sends fresh | `action=reminder_midday`, `pulse_window=midday`, `deduped=false`, sends fresh |

Full assertion output for both runs is in the commit; both scripts printed
`ALL 4 CASES PASS` / `ALL 4 L1-BRANCH CASES PASS` and confirmed 0 leftover
rows in `wellness_reminder_log` for their fake test dates afterward.

**Note on Case (c) semantics**: "should NOT send for that window anymore"
is interpreted as *the reminder that's now been satisfied should never
re-appear* — verified directly (`reminder_morning` never re-selected once
`morning_done=True`, because `next_suggested_pulse` itself skips a logged
pulse type; this is pre-existing behaviour in `run_dispatch_check()`, not
something this mission added). It is **not** interpreted as "go silent about
everything for the rest of the window" — an escalation about the other two
still-missing pulses is a genuinely different, accurate signal, and it gets
its own independent dedup key so it fires once, not repeatedly.

### Live verification (real deploy, real data, real Telegram send)

`intelligence-scheduler.service` was restarted to pick up the code
(`systemctl restart`), confirmed `active`, and its startup log shows
`_wellness_reminder_job` registered and firing immediately
(`next_run_time` trick, same as the intraday/attention jobs):

```
Added job "_wellness_reminder_job" to job store "default"
Wellness reminder check triggered
GET .../wellness_reminder_log?...window_date=eq.2026-08-10&pulse_window=eq.morning&action=eq.escalation_l2&limit=1  -> 200 OK, no match
[recovery-dispatcher] Sent message to chat_id=643108092
POST .../wellness_reminder_log -> 201 Created
Wellness reminder check complete: action=escalation_l2 sent=True deduped=False window=2026-08-10/morning conf=33
```

This was the automation's genuine first run against the Captain's real,
unlogged state at the time (1/3 pulses logged today, 33% confidence,
midday+evening still missing) — an accurate, warranted L2 escalation, not a
test artifact. Confirmed via Supabase MCP immediately after: exactly one row
in `wellness_reminder_log` for today
(`window_date=2026-08-10, pulse_window=morning, action=escalation_l2,
confidence_at_send=33`). The next scheduled tick (and any manual `/dispatch`
in between) will see this row and correctly skip re-sending for the same
window/action.

## What wasn't touched

- `escalation_level()`'s own hour-floor gap for the `pulses_completed <= 1`
  branch (§2) — pre-existing, out of this mission's scope, mitigated at the
  job level via the 06:00–23:00 gate rather than modified directly.
- `force_summary` parameter on `run_dispatch_check()` — still present,
  unused by any live caller (only `cmd_dispatch` calls this function, with
  default `force_summary=False`), now also subject to the same de-dup gate
  as everything else for consistency. Not exercised by this mission's
  verification since nothing calls it live.
- Manual `/dispatch` in `telegram-bots/xo/app.py::cmd_dispatch` — unchanged.
  It now goes through the same de-dup gate as the scheduled job (no
  special-casing by caller identity), so if the Captain runs `/dispatch`
  manually right after an automated check already sent something for the
  current window, they'll correctly see `sent=no` rather than a duplicate.

## Mission status

Implemented, live-deployed, and verified — not just designed. Migration 0118
applied directly via Supabase MCP and confirmed present in the repo's
migration history. `intelligence-scheduler.service` restarted and confirmed
running the new job. Commit `2800f4eb`, pushed to `origin/main`.
