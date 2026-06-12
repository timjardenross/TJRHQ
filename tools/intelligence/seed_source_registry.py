"""
WP-ORI-2: Source Registry Seed Script
Populates intelligence_source_registry with all approved sources.

Run:
    python tools/intelligence/seed_source_registry.py
    python tools/intelligence/seed_source_registry.py --dry-run
    python tools/intelligence/seed_source_registry.py --wipe  # clears existing then reseeds

No SafeLinks. All URLs are canonical verified sources.
The registry is treated as a governed platform capability.

Future sources (approved but not required for MVP) are included as inactive=False
entries so they appear in the registry and can be activated without code changes.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ── Bootstrap .env ─────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# ─── Source Registry ───────────────────────────────────────────────────────────
# Fields: source_name, category, priority_rank, url, rss_url, api_endpoint,
#         source_type, jurisdiction, confidence_weight, active, notes
#
# source_type: rss | api | scrape | manual
# priority_rank: 1 (highest) to 5 (lowest)
# confidence_weight: 0.00–1.00 (higher = more authoritative)

SOURCES = [

    # ─── Category 1: Australian Government & Regulatory ──────────────────────
    {
        "source_name":        "APRA Media Releases",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.apra.gov.au/news-and-publications",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "Primary APRA regulatory announcements. No RSS. Scrape news listing.",
    },
    {
        "source_name":        "APRA Publications",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.apra.gov.au/publications",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "Consultation papers, information papers, prudential standards. CPS 230 primary source.",
    },
    {
        "source_name":        "ASIC News Centre",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://asic.gov.au/about-asic/news-centre/",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "Regulatory actions, enforcement, market integrity notices.",
    },
    {
        "source_name":        "RBA Media Releases",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.rba.gov.au/media-releases/",
        "rss_url":            "https://www.rba.gov.au/rss/rss-cb-media-releases.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "Monetary policy, financial stability, payment system notices.",
    },
    {
        "source_name":        "ACSC Alerts & Advisories",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.cyber.gov.au/about-us/view-all-content/alerts-and-advisories",
        "rss_url":            "https://www.cyber.gov.au/rss/alerts",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "ASD/ACSC critical cyber security alerts. Scrape times out but official RSS feed at /rss/alerts is live.",
    },
    {
        "source_name":        "ACSC Advisories",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.cyber.gov.au/about-us/view-all-content/advisories",
        "rss_url":            "https://www.cyber.gov.au/rss/advisories",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             True,
        "notes":              "ASD/ACSC cyber security advisories (broader than alerts). Official RSS feed confirmed live.",
    },
    {
        "source_name":        "NCSC UK Advisories",
        "category":           "regulatory",
        "priority_rank":      2,
        "url":                "https://www.ncsc.gov.uk/section/keep-up-to-date/alerts-advisories",
        "rss_url":            "https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             True,
        "notes":              "UK NCSC advisories — Five Eyes partner, co-authored with ASD/ACSC on global threats. Confirmed live.",
    },
    {
        "source_name":        "CISA Known Exploited Vulnerabilities",
        "category":           "regulatory",
        "priority_rank":      2,
        "url":                "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
        "rss_url":            None,
        "api_endpoint":       "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        "source_type":        "api",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.92,
        "active":             True,
        "notes":              "CISA KEV catalog — authoritative list of actively-exploited CVEs. ACSC advisories frequently reference this. Confirmed live JSON API.",
    },

    # ─── Category 2: Emergency Management & Hazard Intelligence ──────────────
    {
        "source_name":        "Bureau of Meteorology Warnings",
        "category":           "emergency_management",
        "priority_rank":      1,
        "url":                "https://www.bom.gov.au/australia/warnings/",
        "rss_url":            "https://www.bom.gov.au/fwo/IDZ00059.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             False,
        "notes":              "Severe weather warnings. All BOM feed/page URLs return 403 (bot detection active) — deactivated.",
    },
    {
        "source_name":        "Weatherzone Warnings",
        "category":           "emergency_management",
        "priority_rank":      1,
        "url":                "https://www.weatherzone.com.au/warnings",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.88,
        "active":             True,
        "notes":              "BOM replacement — Weatherzone aggregates official BOM-issued warning texts for all states. No auth, HTTP 200 confirmed.",
    },
    {
        "source_name":        "VicEmergency",
        "category":           "emergency_management",
        "priority_rank":      1,
        "url":                "https://www.emergency.vic.gov.au/",
        "rss_url":            None,
        "api_endpoint":       "https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON",
        "source_type":        "api",
        "jurisdiction":       "AU",
        "confidence_weight":  0.93,
        "active":             True,
        "notes":              "Victoria emergency incidents. Original OSOM API 404 — replaced with EMV data.emergency.vic.gov.au JSON feed. Confirmed live with real incidents.",
    },
    {
        "source_name":        "NSW SES",
        "category":           "emergency_management",
        "priority_rank":      1,
        "url":                "https://www.ses.nsw.gov.au/news/",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.93,
        "active":             True,
        "notes":              "NSW floods, storms, rescues. RSS feed returns malformed XML — switched to scrape.",
    },
    {
        "source_name":        "CFA Warnings & Incidents",
        "category":           "emergency_management",
        "priority_rank":      2,
        "url":                "https://www.cfa.vic.gov.au/warnings-restrictions",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.92,
        "active":             True,
        "notes":              "Victorian bushfire and grassfire warnings. RSS feed returns malformed XML — switched to scrape.",
    },
    {
        "source_name":        "Geoscience Australia Earthquakes",
        "category":           "emergency_management",
        "priority_rank":      2,
        "url":                "https://earthquakes.ga.gov.au/",
        "rss_url":            None,
        "api_endpoint":       "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
        "source_type":        "api",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             True,
        "notes":              "Seismic events M2.5+. GA API returned empty responses — switched to USGS GeoJSON feed (covers Australia, globally authoritative).",
    },

    # ─── Category 3: Critical Infrastructure & Utilities ─────────────────────
    {
        "source_name":        "AEMO Market Notices",
        "category":           "critical_infrastructure",
        "priority_rank":      1,
        "url":                "https://www.aemo.com.au/market-notices",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             False,
        "notes":              "National Electricity Market operational notices. Scrape page returns 403 (bot detection) — deactivated.",
    },
    {
        "source_name":        "AEMO NEMweb Market Notices",
        "category":           "critical_infrastructure",
        "priority_rank":      1,
        "url":                "https://www.nemweb.com.au/REPORTS/CURRENT/Market_Notice/",
        "rss_url":            None,
        "api_endpoint":       "https://www.nemweb.com.au/REPORTS/CURRENT/Market_Notice/",
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "AEMO replacement — NEMweb public directory of NEM market notice files. Official AEMO data dissemination path. HTTP 200 confirmed, real notices visible.",
    },
    {
        "source_name":        "TPG Telecom Service Status",
        "category":           "critical_infrastructure",
        "priority_rank":      2,
        "url":                "https://status.messaging.tpgtelecom.com.au/",
        "rss_url":            "https://status.messaging.tpgtelecom.com.au/history.rss",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.82,
        "active":             True,
        "notes":              "TPG/Vodafone/iiNet replacement — official TPG Telecom status page with working RSS feed. Confirmed live.",
    },
    {
        "source_name":        "NBN Network Status",
        "category":           "critical_infrastructure",
        "priority_rank":      2,
        "url":                "https://www.nbnco.com.au/support/network-status",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.85,
        "active":             True,
        "notes":              "NBN outage and degradation notices. No RSS or public API.",
    },
    {
        "source_name":        "Telstra Service Alerts",
        "category":           "critical_infrastructure",
        "priority_rank":      2,
        "url":                "https://crowdsupport.telstra.com.au/t5/service-alerts/tkb-p/service-alerts",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.85,
        "active":             True,
        "notes":              "Telstra public outage announcements via community support portal.",
    },
    {
        "source_name":        "Optus Network Status",
        "category":           "critical_infrastructure",
        "priority_rank":      2,
        "url":                "https://www.optus.com.au/support/network",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.85,
        "active":             False,
        "notes":              "Optus outage notifications. Consistently times out (>15s) — deactivated. Monitor for status page URL change.",
    },
    {
        "source_name":        "TPG Service Status",
        "category":           "critical_infrastructure",
        "priority_rank":      3,
        "url":                "https://status.tpg.com.au/",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.82,
        "active":             False,
        "notes":              "TPG/Vodafone/iiNet service status. DNS resolution failing — domain may have moved. Deactivated pending verification.",
    },

    # ─── Category 4: Cloud & Technology Dependency ────────────────────────────
    {
        "source_name":        "Microsoft Azure Status",
        "category":           "cloud_technology",
        "priority_rank":      2,
        "url":                "https://status.azure.com/en-us/status",
        "rss_url":            "https://status.azure.com/en-us/status/feed/",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             True,
        "notes":              "Microsoft Azure / M365 / Teams service health RSS feed.",
    },
    {
        "source_name":        "AWS Service Health Dashboard",
        "category":           "cloud_technology",
        "priority_rank":      2,
        "url":                "https://status.aws.amazon.com/",
        "rss_url":            "https://status.aws.amazon.com/rss/all.rss",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             True,
        "notes":              "AWS global + ap-southeast-2 (Sydney) health events.",
    },
    {
        "source_name":        "Google Cloud Status",
        "category":           "cloud_technology",
        "priority_rank":      2,
        "url":                "https://status.cloud.google.com/",
        "rss_url":            "https://status.cloud.google.com/en/feed.atom",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             True,
        "notes":              "Google Cloud Platform and Workspace status Atom feed.",
    },
    {
        "source_name":        "Salesforce Trust Status",
        "category":           "cloud_technology",
        "priority_rank":      2,
        "url":                "https://status.salesforce.com/",
        "rss_url":            None,
        "api_endpoint":       "https://api.status.salesforce.com/v1/incidents/active",
        "source_type":        "api",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             True,
        "notes":              "Salesforce CRM/Service Cloud incidents. /api/v1/incidents returns 403 — updated to api.status.salesforce.com/v1/incidents/active (public API endpoint).",
    },
    {
        "source_name":        "ServiceNow Status",
        "category":           "cloud_technology",
        "priority_rank":      2,
        "url":                "https://status.servicenow.com/",
        "rss_url":            None,
        "api_endpoint":       "https://status.servicenow.com/api/v2/status.json",
        "source_type":        "api",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             False,
        "notes":              "ServiceNow ITSM platform status. DNS resolution failing from this network — deactivated. Re-enable when network access confirmed.",
    },

    # ─── Category 5: Banking & Payments Infrastructure ─────────────────────────
    {
        "source_name":        "AusPayNet",
        "category":           "banking_payments",
        "priority_rank":      1,
        "url":                "https://www.auspaynet.com.au/resources/news-and-events",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             False,
        "notes":              "Australian Payments Network. All URL variants return 404 or timeout — deactivated pending site restructure.",
    },
    {
        "source_name":        "AusPayNet Insights",
        "category":           "banking_payments",
        "priority_rank":      1,
        "url":                "https://auspaynet.com.au/insights",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.90,
        "active":             True,
        "notes":              "AusPayNet replacement — /insights page is scrapeable (HTTP 200). Covers payments policy, fraud stats, and industry developments. Note: no-www URL required.",
    },
    {
        "source_name":        "SWIFT Newsroom",
        "category":           "banking_payments",
        "priority_rank":      2,
        "url":                "https://www.swift.com/news-events/news",
        "rss_url":            "https://www.swift.com/rss/news",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.93,
        "active":             False,
        "notes":              "SWIFT messaging network news. RSS feed consistently times out (>15s) — deactivated. Likely geo-blocked or rate-limited.",
    },
    {
        "source_name":        "RBA Payments & Infrastructure",
        "category":           "banking_payments",
        "priority_rank":      1,
        "url":                "https://www.rba.gov.au/payments-and-infrastructure/",
        "rss_url":            "https://www.rba.gov.au/rss/rss-cb-media-releases.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "RBA payments system oversight and operational notices.",
    },

    # ─── Category 6: Transport & Workforce Mobility ───────────────────────────
    {
        "source_name":        "PTV Disruptions",
        "category":           "transport",
        "priority_rank":      3,
        "url":                "https://www.ptv.vic.gov.au/disruptions/",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.80,
        "active":             False,
        "notes":              "Public Transport Victoria service disruptions. Returns HTTP 403 — bot detection active. Deactivated.",
    },
    {
        "source_name":        "Sydney Trains Alerts",
        "category":           "transport",
        "priority_rank":      3,
        "url":                "https://transportnsw.info/alerts",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.80,
        "active":             True,
        "notes":              "Transport for NSW service alerts.",
    },
    {
        "source_name":        "Transurban Traffic Updates",
        "category":           "transport",
        "priority_rank":      3,
        "url":                "https://www.transurban.com/network",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.80,
        "active":             False,
        "notes":              "Major toll road incidents. All URL variants return 404 — site restructured. Deactivated.",
    },
    {
        "source_name":        "Melbourne Airport",
        "category":           "transport",
        "priority_rank":      3,
        "url":                "https://www.melbourneairport.com.au/arrivals",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.78,
        "active":             True,
        "notes":              "Flight arrivals page. /passengers/flights and /flight-information both 404 — updated to /arrivals (HTTP 200).",
    },

    # ─── Category 7: Trusted Media & Intelligence Sources ─────────────────────
    {
        "source_name":        "ABC News",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.abc.net.au/news/",
        "rss_url":            "https://www.abc.net.au/news/feed/51120/rss.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.78,
        "active":             True,
        "notes":              "ABC News Australia — business and technology section.",
    },
    {
        "source_name":        "Reuters",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.reuters.com/",
        "rss_url":            "https://feeds.reuters.com/reuters/businessNews",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.80,
        "active":             False,
        "notes":              "Reuters business news. feeds.reuters.com DNS no longer resolves — Reuters removed public RSS feeds. Deactivated.",
    },
    {
        "source_name":        "AP News Business",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://apnews.com/business",
        "rss_url":            "https://feeds.apnews.com/rss/apf-business",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.80,
        "active":             True,
        "notes":              "Reuters replacement — AP News wire service, authoritative global financial/business news, no paywall. RSS confirmed live.",
    },
    {
        "source_name":        "Guardian Australia",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.theguardian.com/australia-news",
        "rss_url":            "https://www.theguardian.com/australia-news/rss",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.78,
        "active":             True,
        "notes":              "Guardian Australia — no paywall, strong Australian political/regulatory/business coverage. RSS confirmed live.",
    },
    {
        "source_name":        "Bloomberg",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.bloomberg.com/",
        "rss_url":            "https://feeds.bloomberg.com/markets/news.rss",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.82,
        "active":             True,
        "notes":              "Bloomberg markets feed. Good for financial system stress signals.",
    },
    {
        "source_name":        "BBC News",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.bbc.com/news/",
        "rss_url":            "http://feeds.bbci.co.uk/news/world/rss.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.78,
        "active":             True,
        "notes":              "BBC World News. Geopolitical context and global disruption events.",
    },
    {
        "source_name":        "Financial Times",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.ft.com/",
        "rss_url":            "https://www.ft.com/rss/home/uk",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.83,
        "active":             True,
        "notes":              "Financial Times. Banking regulation and systemic risk reporting.",
    },
    {
        "source_name":        "Australian Financial Review",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.afr.com/",
        "rss_url":            "https://www.afr.com/rss",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.82,
        "active":             False,
        "notes":              "AFR — Australian financial and business news. RSS feed returns malformed XML (paywall redirect). Deactivated.",
    },
    {
        "source_name":        "ABC News Business",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://www.abc.net.au/news/business/",
        "rss_url":            "https://www.abc.net.au/news/feed/104217374/rss.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.80,
        "active":             True,
        "notes":              "AFR replacement — ABC News Business section. Authoritative Australian business/banking/regulatory coverage. No paywall. RSS confirmed live.",
    },
    {
        "source_name":        "Financial Newswire",
        "category":           "media",
        "priority_rank":      4,
        "url":                "https://financialnewswire.com.au/",
        "rss_url":            "https://financialnewswire.com.au/feed/",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.78,
        "active":             True,
        "notes":              "Australian financial services industry news. Covers banking, super, regulation. Free RSS feed confirmed live.",
    },

    # ─── Future Sources (inactive at MVP — activate without code change) ──────
    {
        "source_name":        "APRA Speeches",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.apra.gov.au/speeches",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             False,
        "notes":              "FUTURE: APRA Board Member speeches. Forward-looking regulatory signals.",
    },
    {
        "source_name":        "APRA Consultations",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.apra.gov.au/consultations",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             False,
        "notes":              "FUTURE: Open consultation papers. Leading indicator for regulatory change.",
    },
    {
        "source_name":        "ASIC Enforcement Activity",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://asic.gov.au/about-asic/news-centre/find-a-media-release/?query=&filter=enforcement",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             False,
        "notes":              "FUTURE: ASIC enforcement actions. Peer bank exposure signal.",
    },
    {
        "source_name":        "OAIC Breach Notifications",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.oaic.gov.au/privacy/notifiable-data-breaches",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             False,
        "notes":              "FUTURE: Office of the Australian Information Commissioner. Data breach reports.",
    },
    {
        "source_name":        "ASD Publications",
        "category":           "regulatory",
        "priority_rank":      1,
        "url":                "https://www.asd.gov.au/publications",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             False,
        "notes":              "FUTURE: Australian Signals Directorate publications and threat reports.",
    },
    {
        "source_name":        "CISA Alerts",
        "category":           "regulatory",
        "priority_rank":      2,
        "url":                "https://www.cisa.gov/news-events/cybersecurity-advisories",
        "rss_url":            "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.95,
        "active":             False,
        "notes":              "FUTURE: US CISA advisories. Often precedes ACSC advisories on global threats.",
    },
    {
        "source_name":        "ENISA Advisories",
        "category":           "regulatory",
        "priority_rank":      2,
        "url":                "https://www.enisa.europa.eu/publications",
        "rss_url":            "https://www.enisa.europa.eu/news/rss/",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             False,
        "notes":              "FUTURE: EU Agency for Cybersecurity publications.",
    },
    {
        "source_name":        "ASX Operational Notices",
        "category":           "banking_payments",
        "priority_rank":      1,
        "url":                "https://www.asx.com.au/markets/trade-our-cash-market/operating-our-market.htm",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             False,
        "notes":              "FUTURE: ASX market operational notices and trading halts.",
    },
]


# ─── Seed logic ───────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _fetch_existing_ids() -> dict:
    """Fetch {source_name: source_id} for all rows already in the table."""
    url = f"{SUPABASE_URL}/rest/v1/intelligence_source_registry?select=source_id,source_name"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read())
            # Keep only the first occurrence per name (oldest record)
            seen = {}
            for r in rows:
                if r["source_name"] not in seen:
                    seen[r["source_name"]] = r["source_id"]
            return seen
    except Exception:
        return {}


def _upsert(rows: list[dict]) -> tuple[int, int]:
    """Upsert rows into intelligence_source_registry. Returns (inserted, failed).

    Looks up existing source_ids by name so merge-duplicates works on the
    primary key rather than always inserting new rows.
    """
    existing = _fetch_existing_ids()

    # Inject source_id for rows that already exist in the DB
    enriched = []
    for row in rows:
        r = dict(row)
        if r["source_name"] in existing:
            r["source_id"] = existing[r["source_name"]]
        enriched.append(r)

    url = f"{SUPABASE_URL}/rest/v1/intelligence_source_registry"
    headers = {
        **_headers(),
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    body = json.dumps(enriched).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return len(result) if isinstance(result, list) else 1, 0
    except urllib.error.HTTPError as exc:
        body_err = exc.read().decode()
        print(f"  ✗ Supabase HTTP {exc.code}: {body_err[:200]}", file=sys.stderr)
        return 0, len(rows)
    except Exception as exc:
        print(f"  ✗ Error: {exc}", file=sys.stderr)
        return 0, len(rows)


def _delete_all() -> None:
    url = f"{SUPABASE_URL}/rest/v1/intelligence_source_registry?source_id=neq.00000000-0000-0000-0000-000000000000"
    headers = {**_headers(), "Prefer": "return=minimal"}
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    with urllib.request.urlopen(req, timeout=10):
        pass


def seed(dry_run: bool = False, wipe: bool = False) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("✗ SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set", file=sys.stderr)
        sys.exit(1)

    active   = [s for s in SOURCES if s["active"]]
    inactive = [s for s in SOURCES if not s["active"]]
    total    = len(SOURCES)

    print(f"OR Intelligence — Source Registry Seed")
    print(f"  Total sources:   {total}")
    print(f"  Active (MVP):    {len(active)}")
    print(f"  Future/inactive: {len(inactive)}")

    if dry_run:
        print("\nDry run — no changes made. Sources that would be seeded:")
        for s in SOURCES:
            flag = "✓" if s["active"] else "○"
            print(f"  {flag} [{s['category']:<24}] P{s['priority_rank']} {s['source_name']}")
        return

    if wipe:
        print("\nWiping existing source registry...")
        _delete_all()
        print("  Registry cleared")

    print(f"\nSeeding {total} sources...")
    inserted, failed = _upsert(SOURCES)
    print(f"\n{'✓' if failed == 0 else '!'} Seed complete: {inserted} upserted, {failed} failed")
    print(f"  Active sources ready: {len(active)}")
    print(f"  Future sources staged: {len(inactive)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OR Intelligence — Source Registry Seed")
    parser.add_argument("--dry-run", action="store_true", help="Print sources without writing")
    parser.add_argument("--wipe",    action="store_true", help="Clear registry before seeding")
    args = parser.parse_args()
    seed(dry_run=args.dry_run, wipe=args.wipe)
