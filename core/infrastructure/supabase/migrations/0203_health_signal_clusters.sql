-- 0203_health_signal_clusters.sql
--
-- Health OSINT — cross-source signal clustering + synthesis, see
-- tools/health-osint/health_signal_synthesis.py.
--
-- health_signals.dedup_hash (0097) and health_signal_curation.py's
-- _dedup_key() both already catch same-source re-publication (the same
-- bulletin mirrored under a different URL from the same source_id). Never
-- addressed until now: the same underlying finding covered independently
-- by DIFFERENT sources with different titles/wording — the far more
-- common and more valuable case for a reader trying to see "is this one
-- real signal or five people writing about it."
--
-- Additive only. A cluster links N existing health_signals rows (each
-- keeps every column it already has) rather than merging/deleting any of
-- them, so no existing reader of health_signals is affected until it
-- starts also reading cluster_id / joining health_signal_clusters.

create table if not exists public.health_signal_clusters (
  cluster_id uuid primary key default gen_random_uuid(),
  narrative text,
  narrative_key_sources text[],
  narrative_confidence_note text,
  narrative_provider text,
  member_count integer not null default 0,
  similarity_threshold numeric(3,2),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.health_signal_clusters is
  'Groups of health_signals rows judged semantically near-duplicate across '
  'DIFFERENT sources by tools/health-osint/health_signal_synthesis.py '
  '(SemHash embedding similarity, threshold recorded per row since it may '
  'be tuned over time). One row per cluster of 2+ published signals; '
  'singleton signals are never clustered.';
comment on column public.health_signal_clusters.narrative is
  'LLM-synthesized 2-3 sentence narrative citing each member source by '
  'name, generated once per cluster. Null until synthesis succeeds — a '
  'provider failure leaves this null rather than a guess, same posture as '
  'health_signal_curation.py''s ESCALATE default.';
comment on column public.health_signal_clusters.narrative_confidence_note is
  'One sentence: do the clustered sources agree, or is there a real '
  'discrepancy worth flagging? Never blended into the narrative sentence '
  'itself so a UI can style it distinctly (e.g. a caution badge).';

alter table public.health_signals
  add column if not exists cluster_id uuid references public.health_signal_clusters (cluster_id);

comment on column public.health_signals.cluster_id is
  'Set by health_signal_synthesis.py when this signal was grouped with '
  '2+ other signals from different sources covering the same underlying '
  'finding. Null for signals with no detected cross-source duplicate, or '
  'not yet processed by a synthesis run.';

create index if not exists idx_health_signals_cluster_id
  on public.health_signals (cluster_id) where cluster_id is not null;

alter table public.health_signal_clusters enable row level security;
grant select on public.health_signal_clusters to authenticated;
drop policy if exists authenticated_select on public.health_signal_clusters;
create policy authenticated_select on public.health_signal_clusters for select to authenticated using (true);
