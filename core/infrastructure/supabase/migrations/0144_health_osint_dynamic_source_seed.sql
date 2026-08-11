-- Health OSINT Phase 2/3 seed: register the 6 dynamic-fetch sources and
-- their fetch config. Real URLs confirmed live 2026-08-11 while building
-- each parser (tools/health-osint/parsers/) — NOT the doc's original
-- guesses, several of which were dead/stale (see each parser's own
-- docstring for the confirmed-vs-doc discrepancy). ClinicalTrials.gov is
-- NOT inserted here — it already exists as a hand-curated TIER_2 static
-- source (migration 0093/0094); this migration only adds a fetch_config
-- row referencing its existing source_id, upgrading it to also be
-- auto-fetched.

INSERT INTO health_source_registry
  (source_name, source_type, source_url, peer_reviewed, publisher_reputation,
   conflict_of_interest_disclosure, funding_transparency, avg_methodology_quality,
   auto_registered)
VALUES
  ('FDA MedWatch', 'health_agency', 'https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts',
   false, 0.90, true, 0.90, 0.70, true),
  ('CDC Epidemic Tracking', 'health_agency', 'https://www.cdc.gov/outbreaks/index.html',
   false, 0.90, true, 0.90, 0.70, true),
  ('bioRxiv/medRxiv Recent', 'preprint', 'https://api.biorxiv.org/details/biorxiv',
   false, 0.55, true, 0.70, 0.45, true),
  ('WHO Outbreak Alerts', 'health_agency', 'https://www.who.int/emergencies/disease-outbreak-news',
   false, 0.92, true, 0.90, 0.70, true),
  ('NIH Research Alerts', 'health_agency', 'https://reporter.nih.gov',
   false, 0.92, true, 0.90, 0.65, true)
ON CONFLICT DO NOTHING;

INSERT INTO health_source_fetch_config
  (source_id, fetch_tool, fetch_url, cadence, parser_function,
   monthly_budget, dedup_field, auto_publish, default_confidence_level)
SELECT hsr.source_id, v.fetch_tool, v.fetch_url, v.cadence, v.parser,
       v.budget, 'dedup_hash', false, 'MEDIUM'
FROM health_source_registry hsr
JOIN (VALUES
  ('FDA MedWatch', 'firecrawl', 'https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts', 'weekly', 'parse_fda_medwatch', 8),
  ('CDC Epidemic Tracking', 'firecrawl', 'https://www.cdc.gov/outbreaks/index.html', 'weekly', 'parse_cdc_epidemic', 8),
  ('ClinicalTrials.gov', 'direct', 'https://clinicaltrials.gov/api/v2/studies?query.cond=exercise+OR+sleep&filter.overallStatus=RECRUITING%7CNOT_YET_RECRUITING&pageSize=20&sort=StudyFirstPostDate:desc', 'weekly', 'parse_clinicaltrials_new', 0),
  ('bioRxiv/medRxiv Recent', 'direct', 'https://api.biorxiv.org/details/biorxiv/2026-08-01/2026-08-01/0', 'weekly', 'parse_biorxiv_trending', 0),
  ('WHO Outbreak Alerts', 'direct', 'https://www.who.int/api/news/diseaseoutbreaknews?$orderby=PublicationDate%20desc&$top=10', 'weekly', 'parse_who_alerts', 0),
  ('NIH Research Alerts', 'direct', 'https://api.reporter.nih.gov/v2/projects/search', 'weekly', 'parse_nih_alerts', 0)
) v(source_name, fetch_tool, fetch_url, cadence, parser, budget)
  ON hsr.source_name = v.source_name
WHERE NOT EXISTS (
  SELECT 1 FROM health_source_fetch_config cfg WHERE cfg.source_id = hsr.source_id
);
