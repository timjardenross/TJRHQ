-- STARSHIP-REDESIGN.md §5: minimal Decide ledger. No existing table cleanly
-- fits: `decisions` is mission-execution-outcome specific (mission_id,
-- artifacts, error_message), `decision_records` requires NOT NULL
-- mission_id + recommendation_id (assumes every decision is an AI
-- recommendation inside a mission - doesn't generalize to engineering
-- items), `commander_decisions` is the Slack bot's own routing log
-- (channel_id/thread_ts/confidence). This table is source-agnostic by
-- design, matching Decide's own "one place for judgement, whatever the
-- source" premise.

create table if not exists decide_ledger (
  id              uuid primary key default gen_random_uuid(),
  question        text not null,
  source          text not null check (source in ('mission', 'engineering')),
  item_ref        text not null,
  action          text not null check (action in ('approve', 'hold', 'undo')),
  decided_at      timestamptz not null default now(),
  undo_available  boolean not null default false,
  prior_status    text,
  outcome         text
);

create index if not exists idx_decide_ledger_decided_at on decide_ledger(decided_at desc);
create index if not exists idx_decide_ledger_item_ref on decide_ledger(item_ref);

comment on table decide_ledger is
  'STARSHIP-REDESIGN.md §5: append-only log of every Decide action (approve/hold/undo), independent of which governed source (mission/engineering) the item came from. outcome is nullable - no outcome-tracking mechanism exists yet, "if known" per spec, always null today. prior_status is the item''s status immediately before the action, captured so undo can restore it exactly rather than guessing.';

alter table decide_ledger enable row level security;

drop policy if exists decide_ledger_auth_read on decide_ledger;
create policy decide_ledger_auth_read on decide_ledger
  for select to authenticated using (true);

drop policy if exists decide_ledger_auth_write on decide_ledger;
create policy decide_ledger_auth_write on decide_ledger
  for all to authenticated using (true) with check (true);
