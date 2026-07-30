-- Migration 0038: Wellness content sources
-- Adds RSS sources specifically for the wellness_sustainable_performance content pillar.
-- These feed the comms content pipeline only (content_source = true) and are tagged
-- category = 'wellness' so the content classifier can allow wellness-pillar scoring
-- exclusively for events from these sources.

INSERT INTO intelligence_source_registry (
  source_name, category, priority_rank, url, rss_url,
  source_type, jurisdiction, confidence_weight, active,
  notes, terms_reviewed, content_source, useful_life_days
) VALUES
(
  'Greater Good Magazine',
  'wellness',
  50,
  'https://greatergood.berkeley.edu',
  'https://greatergood.berkeley.edu/feed',
  'rss',
  'global',
  0.75,
  true,
  'Berkeley Science Center — evidence-based wellbeing, resilience, and performance science',
  true,
  true,
  28
),
(
  'Mindful.org',
  'wellness',
  51,
  'https://www.mindful.org',
  'https://www.mindful.org/feed/',
  'rss',
  'global',
  0.65,
  true,
  'Mindfulness and performance for leaders and professionals',
  true,
  true,
  28
),
(
  'Gallup Workplace',
  'wellness',
  52,
  'https://www.gallup.com/workplace/236927/home.aspx',
  'https://news.gallup.com/rss.aspx',
  'rss',
  'global',
  0.80,
  true,
  'Gallup research on employee well-being, engagement, and performance',
  true,
  true,
  21
),
(
  'Harvard Business Review — Managing Yourself',
  'wellness',
  53,
  'https://hbr.org/topic/managing-yourself',
  'https://feeds.hbr.org/harvardbusiness',
  'rss',
  'global',
  0.85,
  true,
  'HBR on personal effectiveness, leadership wellbeing, and sustainable high performance',
  true,
  true,
  21
),
(
  'Psychology Today — Work',
  'wellness',
  54,
  'https://www.psychologytoday.com/intl/basics/work',
  'https://www.psychologytoday.com/intl/feed',
  'rss',
  'global',
  0.70,
  true,
  'Psychology Today workplace, burnout, performance, and leadership psychology',
  true,
  true,
  21
)
ON CONFLICT DO NOTHING;
