-- Migration 0160: Health OSINT neurodivergence sources (#23-26)
--
-- TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md §16
-- "Evidence Metadata" needs real research evidence to fill
-- capacity_interventions.evidence_strength, which has sat at 'unknown' for
-- all 30 seeded interventions since migration 0157 (that migration
-- explicitly left it that way pending human curation — nothing was
-- feeding it). Health OSINT's existing 6 health_domain categories
-- (epidemiology, treatment, supplement, performance, mental_health,
-- vaccine / the richer performance_*/mental_health_*/factor_* taxonomy in
-- HEALTH_OSINT_IMPLEMENTATION.md §3) have zero coverage of autism/ADHD/
-- sensory-regulation research — most of the 30 seeded interventions
-- (sensory reduction, pacing, masking-reduction, movement, timers) are
-- exactly that literature and had nowhere to land.
--
-- Adds 4 new sources, all direct-fetch (no Firecrawl/Bright Data budget
-- spent), all confirmed live 2026-08-22 by real curl testing before this
-- migration was written — see each parser's own docstring
-- (tools/health-osint/parsers/parse_{europepmc,crossref,sciencedaily,
-- medicalxpress}_neurodivergence.py) for the exact confirmed request/
-- response shape. See HEALTH_OSINT_IMPLEMENTATION.md §4a for the full
-- disposition of the ~30 other candidate sources considered and not
-- wired (Google Scholar has no API; individual journals are already
-- covered via Europe PMC/Crossref; several AU-org sites are real but
-- HTML-only and need a Firecrawl-budgeted parser built against their
-- actual fetched markup, not guessed here).
--
-- Additive only — no existing health_source_registry/health_signals rows
-- touched. health_domain is free-text (no CHECK constraint, confirmed in
-- migration 0141), so the new neuro_* codes need no schema change.

INSERT INTO health_source_registry
  (source_name, source_type, source_url, peer_reviewed, publisher_reputation,
   conflict_of_interest_disclosure, funding_transparency, avg_methodology_quality,
   auto_registered)
VALUES
  -- Aggregator of peer-reviewed literature + preprints (PubMed, bioRxiv/
  -- medRxiv/PsyArXiv, Crossref-registered DOIs) — mixed quality by design,
  -- same category as the existing 'bioRxiv/medRxiv Recent' source but
  -- broader coverage and richer per-item metadata (abstracts, journal,
  -- affiliation in one call). peer_reviewed=false at the SOURCE level
  -- because individual items vary (published paper vs. preprint) — see
  -- the parser's per-item known_unknowns.peer_reviewed for the real
  -- per-record flag; reputation set slightly above the pure-preprint
  -- bioRxiv source (0.55) since most Europe PMC hits are journal-
  -- published, not preprint-only.
  ('Europe PMC', 'database', 'https://www.ebi.ac.uk/europepmc/',
   false, 0.65, true, 0.75, 0.55, true),
  -- DOI registration agency, not a curated index — metadata-only,
  -- abstract not guaranteed (confirmed live: present on ~4/5 real
  -- records). Lower reputation than Europe PMC since Crossref itself
  -- makes no quality/peer-review claim about what it registers.
  ('Crossref', 'database', 'https://www.crossref.org',
   false, 0.50, true, 0.70, 0.40, true),
  -- Research journalism (secondary reporting), not primary literature —
  -- reputation set in line with the existing 'medRxiv (preprint)' static
  -- source (0.40), reflecting editorial review without peer review.
  ('ScienceDaily', 'institution', 'https://www.sciencedaily.com',
   false, 0.45, false, 0.50, 0.35, true),
  ('Medical Xpress', 'institution', 'https://medicalxpress.com',
   false, 0.45, false, 0.50, 0.35, true)
ON CONFLICT DO NOTHING;

INSERT INTO health_source_fetch_config
  (source_id, fetch_tool, fetch_url, cadence, parser_function,
   monthly_budget, dedup_field, auto_publish, default_confidence_level)
SELECT hsr.source_id, v.fetch_tool, v.fetch_url, v.cadence, v.parser,
       v.budget, 'dedup_hash', false, 'MEDIUM'
FROM health_source_registry hsr
JOIN (VALUES
  -- Field-restricted (TITLE:/ABSTRACT:) query — confirmed live 2026-08-22
  -- to return only genuinely on-topic results; an earlier free-text OR
  -- query (no field restriction) let Europe PMC's own synonym expansion
  -- pull in unrelated hits (PTSD trauma treatment, folic acid
  -- supplementation) with no autism/ADHD/AuDHD term anywhere in the
  -- record — this exact query was re-tested after that discovery.
  ('Europe PMC', 'direct',
   'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=%28TITLE%3A%22autism%22+OR+ABSTRACT%3A%22autism%22+OR+TITLE%3A%22autistic%22+OR+ABSTRACT%3A%22autistic%22+OR+TITLE%3A%22ADHD%22+OR+ABSTRACT%3A%22ADHD%22+OR+TITLE%3A%22AuDHD%22+OR+ABSTRACT%3A%22AuDHD%22%29&format=json&resultType=core&pageSize=25&sort=P_PDATE_D+desc',
   'weekly', 'parse_europepmc_neurodivergence', 0),
  ('Crossref', 'direct',
   'https://api.crossref.org/works?query.bibliographic=autistic+burnout+masking+sensory+processing+ADHD&filter=from-pub-date:2025-01-01&rows=25&select=DOI,title,abstract,published,container-title,author',
   'weekly', 'parse_crossref_neurodivergence', 0),
  ('ScienceDaily', 'direct',
   'https://www.sciencedaily.com/rss/mind_brain/autism.xml',
   'weekly', 'parse_sciencedaily_neurodivergence', 0),
  -- Needs the pipeline's real User-Agent (health_signal_ingestion.py's
  -- _direct_get already sends one) — a UA-less request 400s, confirmed
  -- live 2026-08-22. No config change needed here; documented in the
  -- parser's own docstring since this is a genuine gotcha for this one
  -- source, not something the fetch_config row itself can express.
  ('Medical Xpress', 'direct',
   'https://medicalxpress.com/rss-feed/search/?search=autism+OR+adhd+OR+neurodivergent',
   'weekly', 'parse_medicalxpress_neurodivergence', 0)
) v(source_name, fetch_tool, fetch_url, cadence, parser, budget)
  ON hsr.source_name = v.source_name
WHERE NOT EXISTS (
  SELECT 1 FROM health_source_fetch_config cfg WHERE cfg.source_id = hsr.source_id
);

-- Verify after applying:
-- SELECT source_name, reliability_tier, reliability_score FROM health_source_registry WHERE source_name IN ('Europe PMC','Crossref','ScienceDaily','Medical Xpress');
-- SELECT hsr.source_name, cfg.fetch_tool, cfg.parser_function, cfg.active FROM health_source_fetch_config cfg JOIN health_source_registry hsr USING (source_id) WHERE hsr.source_name IN ('Europe PMC','Crossref','ScienceDaily','Medical Xpress');
