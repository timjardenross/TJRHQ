-- =============================================================================
-- Migration: 0036b_content_source_seed.sql
-- Mission:   USS-TJR-MSN-0202 — Content Intelligence Sources
-- Purpose:   Seed 10 content-oriented RSS sources into intelligence_source_registry
--            for thought leadership signal discovery across the 8 content pillars.
-- Pillars:   operational_resilience | business_continuity | human_performance |
--            wellness_sustainable_performance | ai_augmented_leadership |
--            personal_operating_systems | future_of_work | decision_quality_governance
-- Governance:
--   - All sources are publicly available RSS feeds (no commercial licence required)
--   - Store title/summary/url only — not for content republication
--   - terms_reviewed = true for all rows
--   - content_source = true for all rows
--   - priority_rank starts at 100 (ORI sources occupy 1–50)
--   - Idempotent: ON CONFLICT (source_id) DO UPDATE
-- Created:   2026-06-28
-- =============================================================================

INSERT INTO intelligence_source_registry (
    source_id,
    source_name,
    category,
    priority_rank,
    url,
    rss_url,
    source_type,
    source_type_label,
    jurisdiction,
    confidence_weight,
    active,
    useful_life_days,
    terms_reviewed,
    content_source,
    notes
) VALUES

-- 1. MIT Sloan Management Review
-- Pillars: ai_augmented_leadership, future_of_work, decision_quality_governance
-- Licence: MIT open access; RSS publicly available, no commercial aggregation restriction
(
    'CONTENT-MIT-SLOAN-001',
    'MIT Sloan Management Review',
    'thought_leadership',
    100,
    'https://sloanreview.mit.edu',
    'https://sloanreview.mit.edu/feed/',
    'rss',
    'hbr_article',
    'GLOBAL',
    0.85,
    true,
    365,
    true,
    true,
    'MIT open access RSS. Covers management, leadership, AI strategy. Signal discovery only — title/summary/url. No commercial licence required for aggregation.'
),

-- 2. Harvard Business Review
-- Pillars: decision_quality_governance, ai_augmented_leadership, human_performance
-- Licence: HBR RSS is publicly available; individual article access may be paywalled but RSS metadata is open
(
    'CONTENT-HBR-001',
    'Harvard Business Review — Ideas',
    'thought_leadership',
    101,
    'https://hbr.org',
    'https://hbr.org/subscribe?tpcc=rss',
    'rss',
    'hbr_article',
    'GLOBAL',
    0.90,
    true,
    365,
    true,
    true,
    'HBR public RSS feed. Metadata (title/summary/url) freely available. Full articles may require subscription — aggregation for signal discovery only. No commercial licence required for RSS metadata.'
),

-- 3. McKinsey Insights
-- Pillars: operational_resilience, future_of_work, business_continuity
-- Licence: McKinsey publishes a public RSS feed for its Insights; no commercial aggregation restriction on metadata
(
    'CONTENT-MCKINSEY-001',
    'McKinsey & Company — Insights',
    'thought_leadership',
    102,
    'https://www.mckinsey.com/insights',
    'https://www.mckinsey.com/insights/rss',
    'rss',
    'industry_report',
    'GLOBAL',
    0.88,
    true,
    60,
    true,
    true,
    'McKinsey Insights public RSS. Signal discovery only — title/summary/url. Content is freely readable on site; RSS metadata unrestricted. Industry report cadence.'
),

-- 4. Gartner Blog Network
-- Pillars: ai_augmented_leadership, decision_quality_governance, future_of_work
-- Licence: Gartner Blog Network is publicly accessible; RSS metadata is open
(
    'CONTENT-GARTNER-BLOG-001',
    'Gartner Blog Network',
    'thought_leadership',
    103,
    'https://blogs.gartner.com',
    'https://blogs.gartner.com/feed/',
    'rss',
    'industry_report',
    'GLOBAL',
    0.82,
    true,
    60,
    true,
    true,
    'Gartner Blog Network public RSS. Analyst commentary and emerging tech signals. Metadata-only aggregation; full research requires licence. Signal discovery use only.'
),

-- 5. APRA — Speeches and Publications
-- Pillars: operational_resilience, business_continuity, decision_quality_governance
-- Licence: Australian Government open licence (CC BY 4.0); public regulator RSS
(
    'CONTENT-APRA-001',
    'APRA — Speeches and Publications',
    'regulatory',
    104,
    'https://www.apra.gov.au',
    'https://www.apra.gov.au/news-and-publications/rss',
    'rss',
    'industry_report',
    'AU',
    0.92,
    true,
    60,
    true,
    true,
    'Australian Prudential Regulation Authority. Australian Government open licence (CC BY 4.0). Covers CPS230, operational resilience, business continuity regulation. Full content freely available.'
),

-- 6. World Economic Forum
-- Pillars: future_of_work, operational_resilience, wellness_sustainable_performance
-- Licence: WEF RSS publicly available; content under WEF terms permitting non-commercial aggregation
(
    'CONTENT-WEF-001',
    'World Economic Forum — Agenda',
    'thought_leadership',
    105,
    'https://www.weforum.org',
    'https://www.weforum.org/agenda/feed/',
    'rss',
    'industry_report',
    'GLOBAL',
    0.84,
    true,
    60,
    true,
    true,
    'WEF Agenda public RSS. Covers future of work, resilience, sustainability, AI governance. Freely available metadata; signal discovery only. WEF terms permit non-commercial aggregation of RSS metadata.'
),

-- 7. MIT Technology Review
-- Pillars: ai_augmented_leadership, future_of_work, personal_operating_systems
-- Licence: MIT Technology Review RSS publicly available; metadata not restricted
(
    'CONTENT-MIT-TECHREVIEW-001',
    'MIT Technology Review',
    'thought_leadership',
    106,
    'https://www.technologyreview.com',
    'https://www.technologyreview.com/feed/',
    'rss',
    'hbr_article',
    'GLOBAL',
    0.86,
    true,
    365,
    true,
    true,
    'MIT Technology Review public RSS. AI, emerging tech, societal impact. Metadata freely available; full articles may require subscription. Signal discovery only.'
),

-- 8. Stanford Social Innovation Review
-- Pillars: wellness_sustainable_performance, human_performance, future_of_work
-- Licence: SSIR publishes open-access content; RSS publicly available under Creative Commons
(
    'CONTENT-SSIR-001',
    'Stanford Social Innovation Review',
    'thought_leadership',
    107,
    'https://ssir.org',
    'https://ssir.org/site/rss',
    'rss',
    'research_paper',
    'GLOBAL',
    0.80,
    true,
    180,
    true,
    true,
    'Stanford Social Innovation Review public RSS. Open-access journal; RSS and article metadata freely available. Covers sustainable performance, human-centred leadership. CC-licensed content.'
),

-- 9. Deloitte Insights
-- Pillars: operational_resilience, business_continuity, decision_quality_governance
-- Licence: Deloitte Insights RSS publicly available; metadata unrestricted for non-commercial signal discovery
(
    'CONTENT-DELOITTE-INSIGHTS-001',
    'Deloitte Insights',
    'thought_leadership',
    108,
    'https://www2.deloitte.com/us/en/insights.html',
    'https://www2.deloitte.com/us/en/insights/rss.xml',
    'rss',
    'industry_report',
    'GLOBAL',
    0.83,
    true,
    60,
    true,
    true,
    'Deloitte Insights public RSS. Covers risk, resilience, workforce, technology. Metadata-only aggregation; full articles freely available on site. Signal discovery use only.'
),

-- 10. Strategy+Business (PwC)
-- Pillars: decision_quality_governance, personal_operating_systems, ai_augmented_leadership
-- Licence: PwC Strategy+Business RSS publicly available; content open access
(
    'CONTENT-PWC-STRATEGY-001',
    'PwC Strategy+Business',
    'thought_leadership',
    109,
    'https://www.strategy-business.com',
    'https://www.strategy-business.com/rss/rss.xml',
    'rss',
    'hbr_article',
    'GLOBAL',
    0.82,
    true,
    365,
    true,
    true,
    'PwC Strategy+Business public RSS. Open-access management journal covering strategy, leadership, operating models. Freely available content and RSS metadata. Signal discovery only.'
)

ON CONFLICT (source_id) DO UPDATE SET
    source_name        = EXCLUDED.source_name,
    category           = EXCLUDED.category,
    priority_rank      = EXCLUDED.priority_rank,
    url                = EXCLUDED.url,
    rss_url            = EXCLUDED.rss_url,
    source_type        = EXCLUDED.source_type,
    source_type_label  = EXCLUDED.source_type_label,
    jurisdiction       = EXCLUDED.jurisdiction,
    confidence_weight  = EXCLUDED.confidence_weight,
    active             = EXCLUDED.active,
    useful_life_days   = EXCLUDED.useful_life_days,
    terms_reviewed     = EXCLUDED.terms_reviewed,
    content_source     = EXCLUDED.content_source,
    notes              = EXCLUDED.notes;

-- =============================================================================
-- Verification query (run manually after applying):
-- SELECT source_id, source_name, priority_rank, source_type_label, useful_life_days,
--        terms_reviewed, content_source, jurisdiction
-- FROM intelligence_source_registry
-- WHERE content_source = true
-- ORDER BY priority_rank;
-- Expected: 10 rows, priority_rank 100–109
-- =============================================================================
