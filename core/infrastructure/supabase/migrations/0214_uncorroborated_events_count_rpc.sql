-- Weekly-review's OSINT section counted "needs corroboration" by fetching
-- up to 500 intelligence_events ids into Node, then a second query for
-- signal_corroboration rows matching those ids, then filtering in
-- JavaScript. Replace both round trips + the 500-row payload with one
-- exact DB-side count.
create or replace function count_uncorroborated_events(p_since timestamptz)
returns bigint
language sql
stable
security invoker
as $$
  select count(*)
  from intelligence_events ie
  where ie.suppressed = false
    and ie.collected_at >= p_since
    and not exists (
      select 1 from signal_corroboration sc where sc.signal_id = ie.event_id
    );
$$;

-- REVOKE FROM PUBLIC alone is not sufficient on this project -- Supabase's
-- default privileges auto-grant EXECUTE to anon/authenticated on new
-- functions regardless (see migration 0210's correction, a4b430318, where
-- this exact gap left a function anon-callable). Revoke from anon
-- explicitly, only then grant to authenticated.
revoke all on function count_uncorroborated_events(timestamptz) from public, anon, authenticated;
grant execute on function count_uncorroborated_events(timestamptz) to authenticated;
