-- 0219_number_one_context.sql
--
-- Mission 6B (Final CoS Convergence, §4-9) — Number One's chat persona
-- (lcars-portal/src/app/api/ai/chat/route.ts) is a stateless LLM proxy: it
-- takes only whatever `messages[]` the browser tab resends, so pronoun/
-- referent resolution ("I'm stuck" meaning the referral just surfaced by
-- "what am I forgetting?") only works within one browser tab's lifetime and
-- never across surfaces (Telegram, a second tab, a page reload).
--
-- Single-user app (personal_tasks convention, migration 0090) — one row is
-- enough; no per-session key. This is NOT a chat-turn log (that's
-- conversation_turns, migration 0208, XO/Telegram-specific) — it holds only
-- the single "last canonical object Number One's dispatcher acted on or
-- surfaced", so a short chain of intents ("what am I forgetting?" -> "I'm
-- stuck" -> "still can't start" -> "not now" -> "where was I?" -> "done")
-- can resolve "this"/"it" without the Captain repeating the task.
--
-- Short-lived by design (brief's own language): read side treats a row
-- older than NUMBER_ONE_CONTEXT_TTL_MINUTES (see intent-router.ts) as
-- expired rather than deleting it here — keeps the write path a single
-- upsert with no cron/cleanup job needed.
create table if not exists number_one_context (
  id            text primary key default 'default',
  object_type   text not null check (object_type in ('personal_task', 'captured_item')),
  object_id     uuid not null,
  object_title  text,
  last_intent   text not null,
  updated_at    timestamptz not null default now()
);

comment on table number_one_context is
  'Mission 6B: single-row pointer to the last canonical object Number One''s intent dispatcher surfaced/acted on, for referent resolution across turns. Not a chat log — see conversation_turns (0208) for that. Row is treated as expired (not deleted) past a short TTL enforced in application code.';

alter table number_one_context enable row level security;

drop policy if exists number_one_context_authenticated_all on number_one_context;
create policy number_one_context_authenticated_all on number_one_context
  for all to authenticated using (true) with check (true);
