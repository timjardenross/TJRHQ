-- Chief Engineer implementation (.claude/skills/bot-reviews/fixes-2026-08-09/
-- wellness-coaching-automation.md) — automating
-- telegram-bots/recovery_officer/engagement_dispatcher.py::run_dispatch_check()
-- onto intelligence-scheduler.service (Captain directive 2026-08-10, per
-- final-4-domains.md §4 "wellness-coaching: left as wired-but-quiet").
--
-- run_dispatch_check() is a pure function of *current* pulse state — it has
-- never had its own de-duplication, only reachable manually via the XO bot's
-- /dispatch command where a human decides when to re-run it. Putting it on
-- any timer without a persisted "already sent for this window" marker would
-- re-send the identical Telegram reminder every single scheduler tick for as
-- long as a pulse window (morning/midday/evening — recovery_pulses_3x_daily,
-- migration 0115) stays open and unlogged.
--
-- wellness_reminder_log is the dedup ledger: one row per
-- (Brisbane calendar day, pulse window, dispatch action) that was actually
-- sent. run_dispatch_check() checks this table before sending and records a
-- row after a real send; a duplicate check for the same (day, window,
-- action) short-circuits to a no-op. Persisted to Supabase (not in-memory,
-- not SQLite like intelligence/adhd/task_nudge_scheduler.py's
-- NudgeRateLimiter) specifically so the guarantee survives scheduler
-- restarts, per this mission's explicit safety requirement.
--
-- RLS mirrors recovery_pulses' own dual-role pattern (migration 0110/0115):
-- service_role (the scheduler daemon's explicit SUPABASE_SERVICE_ROLE_KEY
-- client — platform-runtime/.env has no SUPABASE_KEY, only
-- SUPABASE_SERVICE_ROLE_KEY) and authenticated (whatever role the live XO
-- bot's own SUPABASE_KEY resolves to) both need read+write.

create table if not exists wellness_reminder_log (
  id                  uuid primary key default gen_random_uuid(),
  window_date         date not null,
  pulse_window        text not null check (pulse_window in ('morning', 'midday', 'evening')),
  action              text not null,
  confidence_at_send  integer,
  sent_at             timestamptz not null default now(),
  created_at          timestamptz not null default now(),
  unique (window_date, pulse_window, action)
);

comment on table wellness_reminder_log is
  'De-dup ledger for engagement_dispatcher.py::run_dispatch_check(). One row per (Brisbane day, pulse window, dispatch action) actually sent via Telegram — checked before every send so a scheduled/interval check never re-sends an identical reminder within the same open pulse window, and the guarantee survives process restarts. See migration 0118.';

create index if not exists wellness_reminder_log_window_idx
  on wellness_reminder_log (window_date, pulse_window);

alter table wellness_reminder_log enable row level security;

create policy service_all
  on wellness_reminder_log
  for all
  to service_role
  using (true)
  with check (true);

create policy auth_read
  on wellness_reminder_log
  for select
  to authenticated
  using (true);

create policy auth_write
  on wellness_reminder_log
  for insert
  to authenticated
  with check (true);
