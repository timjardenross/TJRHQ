-- 0249_archive_revs_tables.sql
--
-- Decommission of the REVS pilot bot (tg-revs, 2026-11-03). Its seven tables are moved out of
-- the public schema into a private `archive` schema instead of being dropped: the data is kept
-- (one pilot user and one screening record, both created 2026-08-14, the user informed), but
-- it is no longer in the schema the API exposes, and nothing in the repo reads or writes it.
--
-- Checked before the move: no function or view references these tables, and the only foreign
-- keys are between the revs_* tables themselves (every child points at revs_users), so the
-- whole group moves together. RLS and the existing policies travel with each table.
--
-- Reverse with, for each table: alter table archive.revs_X set schema public;
-- (revs_users first is not required: foreign keys follow the tables.)
--
-- Not done here: dropping the no-login `revs_bot` role, revoking the Telegram bot token, and
-- deleting the /bots/revs folder in Infisical. Those are manual steps for the Captain.

create schema if not exists archive;
revoke all on schema archive from public;

alter table if exists public.revs_users          set schema archive;
alter table if exists public.revs_checkins       set schema archive;
alter table if exists public.revs_weekly_reviews set schema archive;
alter table if exists public.revs_tools          set schema archive;
alter table if exists public.revs_setbacks       set schema archive;
alter table if exists public.revs_crisis_events  set schema archive;
alter table if exists public.revs_pem_screen_log set schema archive;

comment on schema archive is
  'Retired data kept for reference, not exposed through the API. Holds the REVS pilot tables '
  '(decommissioned 2026-11-03, migration 0249).';
