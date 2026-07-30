-- Migration 0039: Expand wellness content sources
-- Adds 10 more RSS sources for the wellness_sustainable_performance pillar,
-- covering professional leadership performance, burnout, recovery science,
-- and Australian workplace mental health.

INSERT INTO intelligence_source_registry (
  source_name, category, priority_rank, url, rss_url,
  source_type, jurisdiction, confidence_weight, active,
  notes, terms_reviewed, content_source, useful_life_days
) VALUES
(
  'Fast Company — Work Life', 'wellness', 55,
  'https://www.fastcompany.com/work-life', 'https://www.fastcompany.com/rss/work-life',
  'rss', 'GLOBAL', 0.72, true,
  'Professional wellbeing, burnout, sustainable careers, and high-performance habits',
  true, true, 21
),
(
  'MIT Sloan Management Review', 'wellness', 56,
  'https://sloanreview.mit.edu', 'https://sloanreview.mit.edu/feed/',
  'rss', 'GLOBAL', 0.85, true,
  'Leadership, organisational performance, and human capability — rigorous and practitioner-focused',
  true, true, 28
),
(
  'Thrive Global', 'wellness', 57,
  'https://thriveglobal.com', 'https://thriveglobal.com/feed/',
  'rss', 'GLOBAL', 0.68, true,
  'Sustainable high performance, burnout prevention, and leadership wellbeing',
  true, true, 21
),
(
  'Positive Psychology', 'wellness', 58,
  'https://positivepsychology.com', 'https://positivepsychology.com/blog/feed/',
  'rss', 'GLOBAL', 0.75, true,
  'Evidence-based positive psychology for performance, resilience, and leadership',
  true, true, 28
),
(
  'Harvard Health Publishing', 'wellness', 59,
  'https://www.health.harvard.edu', 'https://www.health.harvard.edu/blog/feed',
  'rss', 'GLOBAL', 0.80, true,
  'Harvard Medical School — stress, cognitive performance, recovery, and executive health',
  true, true, 28
),
(
  'World Economic Forum — Well-being', 'wellness', 60,
  'https://www.weforum.org/agenda/wellbeing', 'https://feeds.weforum.org/news/rss.xml',
  'rss', 'GLOBAL', 0.78, true,
  'WEF thought leadership on human capital, wellbeing at scale, and future of work',
  true, true, 21
),
(
  'CIPD — People Management', 'wellness', 61,
  'https://www.cipd.org', 'https://www.cipd.org/rss/articles/',
  'rss', 'GLOBAL', 0.80, true,
  'Chartered Institute of Personnel and Development — workplace wellbeing research and practice',
  true, true, 28
),
(
  'Inc. Magazine — Leadership', 'wellness', 62,
  'https://www.inc.com/leadership', 'https://www.inc.com/rss/',
  'rss', 'GLOBAL', 0.65, true,
  'Practical leadership performance, resilience, and sustainable high-output habits',
  true, true, 14
),
(
  'Heads Up — Beyond Blue Workplace', 'wellness', 63,
  'https://www.headsup.org.au', 'https://www.headsup.org.au/rss',
  'rss', 'AU', 0.78, true,
  'Australian workplace mental health — Beyond Blue initiative for leaders and organisations',
  true, true, 28
),
(
  'SuperFriend', 'wellness', 64,
  'https://superfriend.com.au', 'https://superfriend.com.au/feed/',
  'rss', 'AU', 0.75, true,
  'Australian workplace mental wellbeing — research and practice for the financial services sector',
  true, true, 28
)
ON CONFLICT DO NOTHING;
