-- Migration 0178: Health OSINT chronic pain source (#27)
--
-- Captain named 7 priority research areas (Mental Health, ADHD, Autism,
-- AUDHD, Chronic Pain, Supplement, Performance) — see
-- tools/health-osint/priority_domains.py. Chronic Pain was the one with
-- zero coverage anywhere in this platform, confirmed live 2026-08-27: no
-- existing source or health_domain tag touches it at all.
--
-- Reuses Europe PMC, the same real, already-proven source the 4
-- neurodivergence sources use (migration 0160) — same endpoint shape,
-- only the query and domain classifier differ. See
-- tools/health-osint/parsers/parse_europepmc_chronic_pain.py's module
-- docstring for the confirmed-live query and result count (110,091 hits,
-- current 2026 results, verified by real parse test before this
-- migration was written).
--
-- Additive only — no existing health_source_registry/health_signals rows
-- touched. health_domain is free-text (migration 0141), so the new
-- chronic_pain_* codes need no schema change.

INSERT INTO health_source_registry
  (source_name, source_type, source_url, peer_reviewed, publisher_reputation,
   conflict_of_interest_disclosure, funding_transparency, avg_methodology_quality,
   auto_registered)
VALUES
  -- Same reputation figures as the 'Europe PMC' row added in migration
  -- 0160 for the neurodivergence source — same real source, same mixed
  -- preprint/published quality profile, different query.
  ('Europe PMC (Chronic Pain)', 'database', 'https://www.ebi.ac.uk/europepmc/',
   false, 0.65, true, 0.75, 0.55, true)
ON CONFLICT DO NOTHING;

INSERT INTO health_source_fetch_config
  (source_id, fetch_tool, fetch_url, cadence, parser_function,
   monthly_budget, dedup_field, auto_publish, default_confidence_level)
SELECT hsr.source_id, v.fetch_tool, v.fetch_url, v.cadence, v.parser,
       v.budget, 'dedup_hash', false, 'MEDIUM'
FROM health_source_registry hsr
JOIN (VALUES
  -- Field-restricted (TITLE:/ABSTRACT:) query, same discipline as
  -- migration 0160's neurodivergence query — confirmed live 2026-08-27
  -- to return overwhelmingly on-topic results.
  ('Europe PMC (Chronic Pain)', 'direct',
   'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=%28TITLE%3A%22chronic+pain%22+OR+ABSTRACT%3A%22chronic+pain%22+OR+TITLE%3Afibromyalgia+OR+ABSTRACT%3Afibromyalgia+OR+TITLE%3A%22central+sensitization%22+OR+ABSTRACT%3A%22central+sensitization%22+OR+TITLE%3A%22neuropathic+pain%22+OR+ABSTRACT%3A%22neuropathic+pain%22%29&format=json&resultType=core&pageSize=25&sort=P_PDATE_D+desc',
   'weekly', 'parse_europepmc_chronic_pain', 0)
) v(source_name, fetch_tool, fetch_url, cadence, parser, budget)
  ON hsr.source_name = v.source_name
ON CONFLICT DO NOTHING;
