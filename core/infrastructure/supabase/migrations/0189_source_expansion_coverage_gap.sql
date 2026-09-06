-- 0189_source_expansion_coverage_gap.sql
-- OSINT Ingestion Quality & Relevance Mission — source expansion to close
-- the real coverage gap found 2026-09-06 via a user-requested spot-check
-- (Telstra outage review, Origin breach followup never reached
-- intelligence_events at all; Reuters — also referenced — has a dead RSS
-- endpoint, HTTP 000, not a config toggle away from working).
--
-- Live-verified before insert (2026-09-06):
--   - iTnews real RSS path is /rss/rss.ashx (its /rss path serves an HTML
--     wrapper, not feed XML — a plain guess at the URL would have been wrong).
--   - ARN's /rss/ 301-redirects to /feed/, which is real RSS.
--   - 4 targeted Google News RSS search queries (Telstra, Origin Energy,
--     APRA/ASIC operational resilience, critical-infra/energy cyberattack
--     Australia) all return real, current items — the Telstra query
--     directly surfaced "Telstra outage caused by failure to address
--     well-known network issues - ABC News" (ABC's OWN direct feed missed
--     this story; Google's index did not).
--   - Google News RSS item <link> is a Google redirect wrapper
--     (news.google.com/rss/articles/<opaque>), not the real publisher URL.
--     Confirmed this does NOT need special handling:
--     intelligence/classification/source_tier.py's own docstring already
--     documents the deliberate design that a signal is tiered by "whatever
--     URL the signal actually carries" (Tier 4 default for unrecognised
--     domains) — an aggregator-mediated link getting a conservative Tier 4
--     is the existing intended behaviour, not a bug to route around.
--     Each wrapped link is unique per article, so exact-URL dedup is
--     unaffected.
--   - AFR's RSS was tried at several guessed paths (/rss, /feed, /rss.xml,
--     /arc/outboundfeeds/rss/) — all either 404 or redirect to a JS-
--     rendered HTML page, not feed XML. Genuinely dead, like Reuters;
--     not addressed here (would need either a working AFR feed URL TJR
--     may know of, or continued reliance on Google News search for AFR-
--     originated stories, which the queries above already partially cover
--     since Google indexes AFR content).

insert into intelligence_source_registry
  (source_name, category, priority_rank, url, rss_url, source_type, jurisdiction, active, notes)
values
  ('iTnews', 'cybersecurity', 2, 'https://www.itnews.com.au', 'https://www.itnews.com.au/rss/rss.ashx', 'rss', 'AU', true,
   '2026-09-06: real RSS path verified live (homepage rel=alternate link), /rss alone serves an HTML wrapper not feed XML. AU tech/IT/cyber trade press — added to close a coverage gap general media sources miss.'),

  ('ARN — Australian IT Channel', 'media', 4, 'https://www.arnnet.com.au', 'https://www.arnnet.com.au/feed/', 'rss', 'AU', true,
   '2026-09-06: /rss/ 301-redirects here, verified live real RSS content. Voice of the AU IT channel — lower priority, general coverage supplement.'),

  ('Google News — Telstra', 'critical_infrastructure', 2,
   'https://news.google.com/search?q=Telstra+(outage+OR+network+OR+review)+when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'https://news.google.com/rss/search?q=Telstra%20(outage%20OR%20network%20OR%20review)%20when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'rss', 'AU', true,
   '2026-09-06 gap-closure: added specifically because ABC News''s own direct RSS feed (25-item window) missed a real Telstra outage-review story that this query caught immediately. Item links are Google redirect wrappers by design — see migration header note on source_tier.py''s existing conservative-tiering behaviour for aggregator links, not a bug.'),

  ('Google News — Origin Energy', 'critical_infrastructure', 2,
   'https://news.google.com/search?q=%22Origin+Energy%22+(breach+OR+cyber+OR+data)+when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'https://news.google.com/rss/search?q=%22Origin%20Energy%22%20(breach%20OR%20cyber%20OR%20data)%20when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'rss', 'AU', true,
   '2026-09-06 gap-closure: same rationale as Google News — Telstra, for the Origin Energy breach-followup coverage gap found the same session.'),

  ('Google News — APRA/ASIC Operational Resilience', 'regulatory', 1,
   'https://news.google.com/search?q=(APRA+OR+ASIC)+(operational+resilience+OR+frontier+AI+OR+CPS+230)+when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'https://news.google.com/rss/search?q=(APRA%20OR%20ASIC)%20(operational%20resilience%20OR%20frontier%20AI%20OR%20CPS%20230)%20when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'rss', 'AU', true,
   '2026-09-06: supplements the existing direct APRA/ASIC regulatory sources with press coverage of the same topics — catches media analysis/commentary the direct regulator feeds do not carry themselves.'),

  ('Google News — Critical Infrastructure/Energy Cyberattack AU', 'cybersecurity', 2,
   'https://news.google.com/search?q=(critical+infrastructure+OR+energy+sector)+cyberattack+Australia+when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'https://news.google.com/rss/search?q=(critical%20infrastructure%20OR%20energy%20sector)%20cyberattack%20Australia%20when:14d&hl=en-AU&gl=AU&ceid=AU:en',
   'rss', 'AU', true,
   '2026-09-06 gap-closure: closes the coverage gap for the AI-enhanced energy/OT attack story found the same session (originally Reuters-sourced, whose direct feed is dead).');
