-- DRAFT, NOT APPLIED. Lives outside core/infrastructure/supabase/migrations on purpose so no deploy path picks it up.
-- NUMBERING: provisional (0262 belongs to another change; production migration versions are timestamps). See the Batch 1 durable-state engineering report.
-- Production status + attempt-level delivery records for briefs (flags BRIEF_STATUS_V1 / BRIEF_DELIVERY_RECORD_V1, default OFF).
--
-- PREREQUISITES: captains_daily_briefs and intelligence_briefs exist (they do). Independent of 0263.
-- Design: production_status / reasons are intrinsic to one brief row, so they are additive nullable columns on the brief tables.
--  Delivery is 1:N (attempts, chunks, a marked recovery resend) so it gets its own table, the source of truth. telegram_status /
--  telegram_at / delivery_disclosure on the brief row are a denormalised ROLLUP for cheap reads; telegram message ids live only in
--  the attempts table. Authoritative vocabulary = the code (intelligence/delivery_record.py):
--    outcome  CONFIRMED | PARTIAL | FAILED | UNKNOWN | UNCONFIRMED      kind  PRIMARY | AUTHORISED_RECOVERY_RESEND
--  (NOT the earlier planning vocabulary PENDING/SENT/SUPPRESSED/NOT_CONFIGURED; email is not written by any code and is deferred.)
-- Expand-only for existing tables: nothing here changes or drops an existing column; old writers are unaffected.
--
-- Transactional and re-runnable: one transaction, lock_timeout so it never queues behind a long transaction and blocks the brief
-- writers (SQLSTATE 55P03 means: retry later; nothing was applied). Every object is created idempotently.

begin;
set local lock_timeout = '3s';
set local statement_timeout = '60s';

-- 1. Additive brief-row columns (nullable; no default, so no table rewrite) -------------------------------------
alter table public.captains_daily_briefs
    add column if not exists production_status         text,
    add column if not exists production_status_reasons jsonb,
    add column if not exists telegram_status           text,
    add column if not exists telegram_at               timestamptz,
    add column if not exists delivery_disclosure       text;
alter table public.intelligence_briefs
    add column if not exists production_status         text,
    add column if not exists production_status_reasons jsonb,
    add column if not exists telegram_status           text,
    add column if not exists telegram_at               timestamptz,
    add column if not exists delivery_disclosure       text;

do $$
declare
    t text;
    pfx text;
begin
    foreach t in array array['captains_daily_briefs', 'intelligence_briefs'] loop
        pfx := case t when 'captains_daily_briefs' then 'captains_briefs' else 'intel_briefs' end;
        if not exists (select 1 from pg_constraint where conname = pfx || '_production_status_chk') then
            execute format('alter table public.%I add constraint %I check (production_status is null or production_status in (''NORMAL'',''DEGRADED'',''FAILED'')) not valid', t, pfx || '_production_status_chk');
        end if;
        if not exists (select 1 from pg_constraint where conname = pfx || '_telegram_status_chk') then
            execute format('alter table public.%I add constraint %I check (telegram_status is null or telegram_status in (''CONFIRMED'',''PARTIAL'',''FAILED'',''UNKNOWN'',''UNCONFIRMED'')) not valid', t, pfx || '_telegram_status_chk');
        end if;
        -- Rollup columns are written together by the code; a timestamp or disclosure without a status is a corrupt rollup.
        if not exists (select 1 from pg_constraint where conname = pfx || '_rollup_chk') then
            execute format('alter table public.%I add constraint %I check (telegram_status is not null or (telegram_at is null and delivery_disclosure is null)) not valid', t, pfx || '_rollup_chk');
        end if;
        execute format('alter table public.%I validate constraint %I', t, pfx || '_production_status_chk');
        execute format('alter table public.%I validate constraint %I', t, pfx || '_telegram_status_chk');
        execute format('alter table public.%I validate constraint %I', t, pfx || '_rollup_chk');
    end loop;
end $$;

-- 2. Attempt-level delivery record ---------------------------------------------------------------------------
create table if not exists public.intelligence_delivery_attempts (
    attempt_id             uuid        primary key,
    brief_table            text        not null check (brief_table in ('captains_daily_briefs','intelligence_briefs','ref')),
    brief_id               text        not null,   -- row id, or a derived key (type:date:hash) when the row id is unavailable (no FK by design)
    channel                text        not null check (channel = 'telegram'),
    content_hash           text        not null,   -- sha256 of the delivered text: a new text is a new version
    kind                   text        not null check (kind in ('PRIMARY','AUTHORISED_RECOVERY_RESEND')),
    attempt_no             integer     not null check (attempt_no >= 1),
    chunks_total           integer     not null default 0 check (chunks_total >= 0),
    planned_chunks         jsonb       not null default '[]'::jsonb check (jsonb_typeof(planned_chunks) = 'array'),
    chunks                 jsonb       not null default '[]'::jsonb check (jsonb_typeof(chunks) = 'array'),   -- [{index,state,message_id,error,attempts,chunk_hash,at}]
    state                  text        not null default 'sending' check (state in ('sending','finished')),
    outcome                text        check (outcome is null or outcome in ('CONFIRMED','PARTIAL','FAILED','UNKNOWN','UNCONFIRMED')),
    supersedes_attempt_id  uuid        references public.intelligence_delivery_attempts(attempt_id),
    authorised_by          text,
    reason                 text,
    started_at             timestamptz not null default now(),
    finished_at            timestamptz,
    check ((state = 'sending' and outcome is null) or (state = 'finished' and outcome is not null)),
    check (kind = 'PRIMARY' or (supersedes_attempt_id is not null and authorised_by is not null))
);

-- Concurrency guard: two senders that both compute "the next attempt" cannot both claim it.
-- (Prevents preventable duplicates; it does NOT make delivery exactly-once.)
create unique index if not exists intel_delivery_attempt_no_uq
    on public.intelligence_delivery_attempts (brief_table, brief_id, channel, content_hash, attempt_no);
-- At most one authorised recovery resend per brief version and channel (approved policy: one marked resend).
create unique index if not exists intel_delivery_one_resend_uq
    on public.intelligence_delivery_attempts (brief_table, brief_id, channel, content_hash) where kind = 'AUTHORISED_RECOVERY_RESEND';
-- At most one CONFIRMED full-brief primary per brief version and channel (a second would be a preventable duplicate; continuation
-- attempts of a PARTIAL send carry planned_chunks and are not covered).
create unique index if not exists intel_delivery_one_confirmed_primary_uq
    on public.intelligence_delivery_attempts (brief_table, brief_id, channel, content_hash)
    where kind = 'PRIMARY' and outcome = 'CONFIRMED' and planned_chunks = '[]'::jsonb;
-- Restart recovery looks for interrupted attempts.
create index if not exists intel_delivery_interrupted_ix
    on public.intelligence_delivery_attempts (started_at) where state = 'sending';
create index if not exists intel_delivery_brief_ix
    on public.intelligence_delivery_attempts (brief_table, brief_id, channel);

-- Append-only outcome history (M4). Applies to every role including service_role (not the table owner's superuser DDL).
--   * DELETE and TRUNCATE are refused.
--   * Identity columns never change after the claim.
--   * A finished attempt stays finished; its outcome may only move FORWARD: UNKNOWN -> UNCONFIRMED | PARTIAL | CONFIRMED,
--     UNCONFIRMED -> PARTIAL | CONFIRMED, PARTIAL -> CONFIRMED. CONFIRMED and FAILED never change.
--   * A chunk recorded as CONFIRMED (index, message id) can never be altered or removed; chunks only grow.
create or replace function public.intelligence_delivery_attempts_guard() returns trigger language plpgsql as $$
declare
    oc jsonb;
    nc jsonb;
begin
    if tg_op = 'DELETE' then
        raise exception 'intelligence_delivery_attempts is append-only (DELETE refused)' using errcode = 'integrity_constraint_violation';
    end if;
    if (new.attempt_id, new.brief_table, new.brief_id, new.channel, new.content_hash, new.kind, new.attempt_no, new.chunks_total,
        new.planned_chunks, new.supersedes_attempt_id, new.authorised_by, new.started_at)
       is distinct from
       (old.attempt_id, old.brief_table, old.brief_id, old.channel, old.content_hash, old.kind, old.attempt_no, old.chunks_total,
        old.planned_chunks, old.supersedes_attempt_id, old.authorised_by, old.started_at) then
        raise exception 'intelligence_delivery_attempts: identity columns are immutable' using errcode = 'integrity_constraint_violation';
    end if;
    if old.state = 'finished' then
        if new.state <> 'finished' or new.finished_at is distinct from old.finished_at then
            raise exception 'intelligence_delivery_attempts: a finished attempt cannot be reopened' using errcode = 'integrity_constraint_violation';
        end if;
        if new.outcome is distinct from old.outcome and not (
               (old.outcome = 'UNKNOWN'     and new.outcome in ('UNCONFIRMED', 'PARTIAL', 'CONFIRMED'))
            or (old.outcome = 'UNCONFIRMED' and new.outcome in ('PARTIAL', 'CONFIRMED'))
            or (old.outcome = 'PARTIAL'     and new.outcome = 'CONFIRMED')) then
            raise exception 'intelligence_delivery_attempts: outcome % -> % is not a permitted forward transition', old.outcome, new.outcome
                using errcode = 'integrity_constraint_violation';
        end if;
    end if;
    -- The reason of a finished attempt is audit text: it may only be EXTENDED (reconcile / recovery append ';note'), never edited.
    if old.state = 'finished' and new.reason is distinct from old.reason
       and (old.reason is not null and (new.reason is null or left(new.reason, length(old.reason)) <> old.reason)) then
        raise exception 'intelligence_delivery_attempts: the reason of a finished attempt can only be appended to' using errcode = 'integrity_constraint_violation';
    end if;
    if jsonb_array_length(new.chunks) < jsonb_array_length(old.chunks) then
        raise exception 'intelligence_delivery_attempts: chunk history cannot shrink' using errcode = 'integrity_constraint_violation';
    end if;
    for oc in select e from jsonb_array_elements(old.chunks) e where e ->> 'state' = 'CONFIRMED' loop
        select e into nc from jsonb_array_elements(new.chunks) e
         where (e ->> 'index') = (oc ->> 'index') and e ->> 'state' = 'CONFIRMED'
           and (e ->> 'message_id') is not distinct from (oc ->> 'message_id') limit 1;
        if nc is null then
            raise exception 'intelligence_delivery_attempts: a CONFIRMED chunk cannot be altered or removed' using errcode = 'integrity_constraint_violation';
        end if;
    end loop;
    return new;
end $$;

create or replace function public.intelligence_delivery_attempts_no_truncate() returns trigger language plpgsql as $$
begin
    raise exception 'intelligence_delivery_attempts is append-only (TRUNCATE refused)' using errcode = 'integrity_constraint_violation';
end $$;

drop trigger if exists intelligence_delivery_attempts_guard_trg on public.intelligence_delivery_attempts;
create trigger intelligence_delivery_attempts_guard_trg before update or delete on public.intelligence_delivery_attempts
    for each row execute function public.intelligence_delivery_attempts_guard();
drop trigger if exists intelligence_delivery_attempts_no_truncate_trg on public.intelligence_delivery_attempts;
create trigger intelligence_delivery_attempts_no_truncate_trg before truncate on public.intelligence_delivery_attempts
    for each statement execute function public.intelligence_delivery_attempts_no_truncate();

-- Privileges (N2): minimum role = service_role only. Hosted default ACLs give new tables to anon/authenticated and production has
-- several signed-in users, so NO signed-in role may read delivery records (no portal reader exists; the recovery job and the sender
-- use the service role). TRUNCATE is also removed from the service role (the statement trigger above refuses it for everyone).
revoke all on table public.intelligence_delivery_attempts from public, anon, authenticated;
revoke truncate on table public.intelligence_delivery_attempts from service_role;

alter table public.intelligence_delivery_attempts enable row level security;
drop policy if exists intel_delivery_attempts_read on public.intelligence_delivery_attempts;
-- RLS enabled with NO policy: anon/authenticated see nothing even if a grant is added by mistake. Only the service role (BYPASSRLS) works.

commit;

-- Rollback (exact; separate decision, delivery audit data: export the attempts table first):
--   begin;
--   drop table public.intelligence_delivery_attempts;           -- also removes its triggers and indexes
--   drop function public.intelligence_delivery_attempts_guard(), public.intelligence_delivery_attempts_no_truncate();
--   alter table public.captains_daily_briefs drop column production_status, drop column production_status_reasons,
--       drop column telegram_status, drop column telegram_at, drop column delivery_disclosure;
--   alter table public.intelligence_briefs   drop column production_status, drop column production_status_reasons,
--       drop column telegram_status, drop column telegram_at, drop column delivery_disclosure;
--   commit;
