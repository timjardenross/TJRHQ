-- 0014_research_memory.sql
-- Research reuse memory: stores completed /xo research missions so future
-- queries can be reused/refreshed instead of re-run.
--
-- Columns mirror exactly the contract already in code (no new shape invented):
--   write: slack-bot/commands/research_command.py :: _persist_research_memory
--   read : slack-bot/lib/research_memory_retrieval.py :: ResearchMemoryEntry
--          core/coordination/number_one_memory_adapter.py (research_memory query)
-- Retrieval is keyword-overlap over rows with created_at within ~180 days, so a
-- descending created_at index is the only index the read path needs; query_hash
-- is indexed for dedup lookups by the writer.

create table if not exists public.research_memory (
  id                    uuid primary key default gen_random_uuid(),
  mission_id            text,
  original_question     text not null,
  consolidated_findings text,
  recommendation        text,
  confidence_level      double precision default 0,
  tags                  text[]     default '{}',
  reuse_count           integer    default 0,
  provider_path         jsonb      default '[]'::jsonb,
  tasks_completed       integer    default 0,
  task_count            integer    default 0,
  query_hash            text,
  researcher_id         text,
  execution_status      text,
  created_at            timestamptz default now(),
  stored_at             timestamptz not null default now()
);

create index if not exists research_memory_created_at_idx
  on public.research_memory (created_at desc);

create index if not exists research_memory_query_hash_idx
  on public.research_memory (query_hash);

comment on table public.research_memory is
  'Completed research missions retained for reuse/refresh decisions (MSN-0057 research memory).';
comment on column public.research_memory.query_hash is
  'Hash of the normalised research question, used by the writer for dedup lookups.';
comment on column public.research_memory.reuse_count is
  'Incremented each time this entry is reused to answer a later query.';
