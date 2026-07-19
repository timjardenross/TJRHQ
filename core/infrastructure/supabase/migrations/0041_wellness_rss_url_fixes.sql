-- Migration 0041: Fix dead wellness RSS feed URLs
-- Updates 8 corrected feed URLs, deactivates 5 confirmed-dead sources,
-- fixes domain changes, and replaces CIPD (no feed) with People Management.

-- ── Fix correctable URLs ──────────────────────────────────────────────────────

UPDATE intelligence_source_registry
SET rss_url = 'https://feeds.hbr.org/harvardbusiness'
WHERE source_name = 'Harvard Business Review — Managing Yourself';

UPDATE intelligence_source_registry
SET rss_url = 'https://www.mckinsey.com/insights/rss'
WHERE source_name = 'McKinsey Quarterly — People & Organisation';

UPDATE intelligence_source_registry
SET rss_url = 'https://ssir.org/site/rss_2.0'
WHERE source_name = 'Stanford Social Innovation Review';

UPDATE intelligence_source_registry
SET rss_url = 'https://www.fastcompany.com/work-life/rss'
WHERE source_name = 'Fast Company — Work Life';

UPDATE intelligence_source_registry
SET rss_url = 'https://www.psychologytoday.com/us/front/feed'
WHERE source_name = 'Psychology Today — Work';

UPDATE intelligence_source_registry
SET rss_url = 'https://agenda.weforum.org/news/feed/'
WHERE source_name = 'World Economic Forum — Well-being';

UPDATE intelligence_source_registry
SET rss_url = 'https://news.gallup.com/poll/rss'
WHERE source_name = 'Gallup Workplace';

UPDATE intelligence_source_registry
SET rss_url = 'https://www.inc.com/rss'
WHERE source_name = 'Inc. Magazine — Leadership';

-- Try improved paths for uncertain sources
UPDATE intelligence_source_registry
SET rss_url = 'https://www.blackdoginstitute.org.au/feed/'
WHERE source_name = 'Black Dog Institute';

UPDATE intelligence_source_registry
SET rss_url = 'https://www.cambridgewellbeing.org/feed'
WHERE source_name = 'Cambridge Wellbeing Institute';

UPDATE intelligence_source_registry
SET rss_url = 'https://coachingfederation.org/resources/blog/feed/'
WHERE source_name = 'International Coach Federation';

UPDATE intelligence_source_registry
SET rss_url = 'https://www.ccl.org/articles/feed/'
WHERE source_name = 'Center for Creative Leadership';

UPDATE intelligence_source_registry
SET rss_url = 'https://www.health.harvard.edu/rss/feed'
WHERE source_name = 'Harvard Health Publishing';

-- ── Deactivate confirmed dead sources (no public RSS) ────────────────────────

UPDATE intelligence_source_registry
SET active = false, notes = notes || ' [DEACTIVATED: no public RSS feed]'
WHERE source_name IN (
  'Thrive Global',
  'Heads Up — Beyond Blue Workplace',
  'SuperFriend',
  'AHRI — HR Institute',
  'Safe Work Australia'
);

-- CIPD has no feed but their magazine (People Management) does — swap it
UPDATE intelligence_source_registry
SET active = false, notes = notes || ' [DEACTIVATED: no public RSS — replaced by People Management]'
WHERE source_name = 'CIPD — People Management';

-- Deloitte Insights — corporate RSS not confirmed, deactivate pending verification
UPDATE intelligence_source_registry
SET active = false, notes = notes || ' [DEACTIVATED: RSS feed unconfirmed]'
WHERE source_name = 'Deloitte Insights — Human Capital';

-- ── Add People Management (CIPD magazine) as replacement ─────────────────────

INSERT INTO intelligence_source_registry (
  source_name, category, priority_rank, url, rss_url,
  source_type, jurisdiction, confidence_weight, active,
  notes, terms_reviewed, content_source, useful_life_days
) VALUES (
  'People Management',
  'wellness', 75,
  'https://www.peoplemanagement.co.uk',
  'https://www.peoplemanagement.co.uk/rss',
  'rss', 'GLOBAL', 0.80, true,
  'CIPD''s flagship magazine — HR practice, workplace wellbeing, leadership development, and people strategy',
  true, true, 21
)
ON CONFLICT DO NOTHING;
