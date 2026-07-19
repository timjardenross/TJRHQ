-- Migration 0040: Extended wellness content sources
-- Adds 10 more RSS sources for wellness_sustainable_performance pillar,
-- covering Australian government workplace health, global leadership research,
-- academic wellbeing science, and executive coaching bodies.

INSERT INTO intelligence_source_registry (
  source_name, category, priority_rank, url, rss_url,
  source_type, jurisdiction, confidence_weight, active,
  notes, terms_reviewed, content_source, useful_life_days
) VALUES
(
  'AHRI — HR Institute',
  'wellness', 65,
  'https://www.ahri.com.au',
  'https://www.ahri.com.au/feed',
  'rss', 'AU', 0.82, true,
  'Australian HR Institute — employee wellbeing, resilience, sustainable performance in Australian workplaces',
  true, true, 21
),
(
  'Safe Work Australia',
  'wellness', 66,
  'https://www.safeworkaustralia.gov.au',
  'https://www.safeworkaustralia.gov.au/rss.xml',
  'rss', 'AU', 0.79, true,
  'National workplace health and safety regulator — psychosocial hazards, mental health at work, evidence-based interventions',
  true, true, 28
),
(
  'Black Dog Institute',
  'wellness', 67,
  'https://www.blackdoginstitute.org.au',
  'https://www.blackdoginstitute.org.au/news-and-resources/news/feed/',
  'rss', 'AU', 0.83, true,
  'Leading Australian mental health research — workplace depression, burnout, resilience and psychological wellbeing',
  true, true, 28
),
(
  'The Conversation — Health',
  'wellness', 68,
  'https://theconversation.com/au',
  'https://theconversation.com/au/health/articles.atom',
  'rss', 'AU', 0.80, true,
  'Academic experts writing for practitioners — evidence-based occupational health, mental wellbeing, and performance science',
  true, true, 21
),
(
  'McKinsey Quarterly — People & Organisation',
  'wellness', 69,
  'https://www.mckinsey.com/capabilities/people-and-organizational-performance/our-insights',
  'https://www.mckinsey.com/rss.xml',
  'rss', 'GLOBAL', 0.88, true,
  'McKinsey research on workforce wellbeing, human capital, leadership performance, and organisational health',
  true, true, 21
),
(
  'Deloitte Insights — Human Capital',
  'wellness', 70,
  'https://www2.deloitte.com/us/en/insights/topics/human-capital-trends.html',
  'https://www2.deloitte.com/us/en/insights.rss.html',
  'rss', 'GLOBAL', 0.84, true,
  'Deloitte research on workforce trends, wellbeing at scale, leader effectiveness and sustainable work design',
  true, true, 21
),
(
  'International Coach Federation',
  'wellness', 71,
  'https://coachingfederation.org',
  'https://coachingfederation.org/blog/feed/',
  'rss', 'GLOBAL', 0.78, true,
  'ICF — coaching research, practitioner insights, wellbeing in coaching practice and leadership development',
  true, true, 28
),
(
  'Center for Creative Leadership',
  'wellness', 72,
  'https://www.ccl.org',
  'https://www.ccl.org/feed/',
  'rss', 'GLOBAL', 0.80, true,
  'CCL research on leadership development, resilience, executive wellbeing, and sustainable high performance',
  true, true, 21
),
(
  'Stanford Social Innovation Review',
  'wellness', 73,
  'https://ssir.org',
  'https://ssir.org/rss/articles.xml',
  'rss', 'GLOBAL', 0.78, true,
  'Evidence-based research on human potential, wellbeing at scale, and purposeful high-impact leadership',
  true, true, 28
),
(
  'Cambridge Wellbeing Institute',
  'wellness', 74,
  'https://www.wellbeing.cam.ac.uk',
  'https://www.wellbeing.cam.ac.uk/feed',
  'rss', 'GLOBAL', 0.85, true,
  'University of Cambridge — rigorous wellbeing science, sustainable performance research, and leadership psychology',
  true, true, 28
)
ON CONFLICT DO NOTHING;
