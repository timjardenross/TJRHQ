-- tools/intelligence/recompute_signal_scores.py (daily, 01:00 UTC) wrote
-- osint_confidence_level/criticality_score and then rank_score back to
-- intelligence_events one PATCH per row — ~31k PostgREST requests a night
-- for ~16k non-suppressed events, about half of all API traffic and so
-- half of the project's log ingestion (Free plan: 1 GB/month, was at
-- 11 GB — Supabase usage review 2026-09-27). This takes a chunk of rows as
-- jsonb and applies them in one UPDATE, so a pass is ~33 calls instead of
-- ~16k. Null fields in a row are left untouched, so the confidence pass and
-- the rank pass can each send only their own columns. The IS DISTINCT FROM
-- guard skips rows whose values haven't changed (no dead tuples/WAL for a
-- no-op rewrite).
create or replace function bulk_update_signal_scores(p_rows jsonb)
returns integer
language plpgsql
security invoker
as $$
declare
  updated integer;
begin
  update intelligence_events ie
  set osint_confidence_level = coalesce(r.osint_confidence_level, ie.osint_confidence_level),
      criticality_score      = coalesce(r.criticality_score, ie.criticality_score),
      rank_score             = coalesce(r.rank_score, ie.rank_score)
  from jsonb_to_recordset(p_rows) as r(
    event_id uuid,
    osint_confidence_level text,
    criticality_score numeric,
    rank_score numeric
  )
  where ie.event_id = r.event_id
    and (ie.osint_confidence_level, ie.criticality_score, ie.rank_score)
        is distinct from (
          coalesce(r.osint_confidence_level, ie.osint_confidence_level),
          coalesce(r.criticality_score, ie.criticality_score),
          coalesce(r.rank_score, ie.rank_score)
        );
  get diagnostics updated = row_count;
  return updated;
end;
$$;

-- Batch job only (service-role key). Per 0214/0210: REVOKE FROM PUBLIC is
-- not enough on this project — default privileges auto-grant EXECUTE to
-- anon/authenticated — so revoke from those explicitly.
revoke all on function bulk_update_signal_scores(jsonb) from public, anon, authenticated;
grant execute on function bulk_update_signal_scores(jsonb) to service_role;
