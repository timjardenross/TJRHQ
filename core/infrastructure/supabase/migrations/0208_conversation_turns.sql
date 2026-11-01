-- 0208_conversation_turns.sql
--
-- USS-TJR-MSN-0378 Stream 2 ("Living Memory Across the Ship" — Play B,
-- TJR HQ Capability Brief 2026-09-14, MEM-1/XO-1). Pre-flight for that
-- mission confirmed `grep -n "conversation_turns|chat_history|
-- conversation_history" telegram-bots/xo/app.py` had zero matches — XO's
-- live reply path (cmd_message, generate_async(text,
-- _xo_system_prompt(...))) has no turn-replay mechanism at all today; each
-- reply is generated with zero knowledge of what was said a message ago.
--
-- One row per turn (not a JSON array column, unlike debrief_sessions.turns
-- in migration 0206) because this table is read as a sliding time/count
-- window ("last N turns" or "last N minutes") across an open-ended,
-- long-lived chat — not as one whole unit per short-lived session — so a
-- row-per-turn shape with an index on (chat_id, created_at) is the natural
-- fit for that query pattern.
create table if not exists conversation_turns (
  id          uuid primary key default gen_random_uuid(),
  chat_id     bigint not null,
  role        text not null check (role in ('captain', 'xo')),
  text        text not null,
  created_at  timestamptz not null default now()
);

create index if not exists idx_conversation_turns_chat_recent
  on conversation_turns(chat_id, created_at desc);

-- Stream 5 (nightly consolidation job, not built in this migration) will
-- read rows older than its distillation cutoff and write facts into
-- Graphiti via unified_memory.py's remember() — this flag lets that job
-- mark what it has already processed without deleting raw turns (mission's
-- Explicitly-Not-In-Scope: no destructive deletes as a side effect of this
-- work).
alter table conversation_turns
  add column if not exists consolidated_at timestamptz;

create index if not exists idx_conversation_turns_unconsolidated
  on conversation_turns(chat_id, created_at) where consolidated_at is null;

comment on table conversation_turns is
  'Raw per-turn Telegram chat history for XO (telegram-bots/xo/app.py). Written on both the Captain''s message and XO''s reply, synchronously, on the reply hot path (cheap insert only — no LLM extraction there). Read back as a recent-turns window to give XO short-term conversational memory. consolidated_at is set by the Stream 5 nightly job once a turn has been distilled into Graphiti via unified_memory.py remember(); NULL means not yet processed. USS-TJR-MSN-0378 Stream 2.';

alter table conversation_turns enable row level security;

-- Same convention as debrief_sessions/debrief_logs (migration 0206) and
-- alerts/alert_silences (0174/0205): service_role (XO bot's own client)
-- does all reads/writes; authenticated (future LCARS Portal read-only
-- view, out of scope for this mission but kept consistent) gets select.
drop policy if exists conversation_turns_service_write on conversation_turns;
create policy conversation_turns_service_write on conversation_turns
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
drop policy if exists conversation_turns_authenticated_read on conversation_turns;
create policy conversation_turns_authenticated_read on conversation_turns
  for select to authenticated using (true);
