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
        "rss_url":            "https://www.cyber.gov.au/rss.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "ACSC/ASD critical cyber security advisories. Highest cyber source priority.",
    },

    # ─── Category 2: Emergency Management & Hazard Intelligence ──────────────
    {
        "source_name":        "Bureau of Meteorology Warnings",
        "category":           "emergency_management",
        "priority_rank":      1,
        "url":                "http://www.bom.gov.au/australia/warnings/",
        "rss_url":            "http://www.bom.gov.au/fwo/warnings_national.xml",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             True,
        "notes":              "Severe weather, flood, fire, storm warnings. National coverage.",
    },
    {
        "source_name":        "VicEmergency",
        "category":           "emergency_management",
        "priority_rank":      1,
        "url":                "https://www.emergency.vic.gov.au/",
        "rss_url":            None,
        "api_endpoint":       "https://www.emergency.vic.gov.au/public/osom-public-common/public/events-feed",
        "source_type":        "api",
        "jurisdiction":       "AU",
        "confidence_weight":  0.93,
        "active":             True,
        "notes":              "Victoria emergency incidents. API feed of active events.",
    },
    {
        "source_name":        "NSW SES",
        "category":           "emergency_management",
        "priority_rank":      1,
        "url":                "https://www.ses.nsw.gov.au/news/",
        "rss_url":            "https://www.ses.nsw.gov.au/news/rss/",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.93,
        "active":             True,
        "notes":              "NSW floods, storms, rescues.",
    },
    {
        "source_name":        "CFA Warnings & Incidents",
        "category":           "emergency_management",
        "priority_rank":      2,
        "url":                "https://www.cfa.vic.gov.au/warnings-restrictions",
        "rss_url":            "https://www.cfa.vic.gov.au/wlebrss/",
        "api_endpoint":       None,
        "source_type":        "rss",
        "jurisdiction":       "AU",
        "confidence_weight":  0.92,
        "active":             True,
        "notes":              "Victorian bushfire and grassfire warnings.",
    },
    {
        "source_name":        "Geoscience Australia Earthquakes",
        "category":           "emergency_management",
        "priority_rank":      2,
        "url":                "https://earthquakes.ga.gov.au/",
        "rss_url":            None,
        "api_endpoint":       "https://earthquakes.ga.gov.au/geojson/query?minmagnitude=3.0&orderby=time",
        "source_type":        "api",
        "jurisdiction":       "AU",
        "confidence_weight":  0.95,
        "active":             True,
        "notes":              "Seismic events M3.0+. API returns GeoJSON FeatureCollection.",
    },

    # ─── Category 3: Critical Infrastructure & Utilities ─────────────────────
    {
        "source_name":        "AEMO Market Notices",
        "category":           "critical_infrastructure",
        "priority_rank":      1,
        "url":                "https://www.aemo.com.au/market-notices",
        "rss_url":            None,
        "api_endpoint":       "https://www.aemo.com.au/aemo/apps/api/report/MARKET_NOTICE",
        "source_type":        "api",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "National Electricity Market operational notices. API returns JSON list.",
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
        "active":             True,
        "notes":              "Optus outage notifications.",
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
        "active":             True,
        "notes":              "TPG/Vodafone/iiNet service status page.",
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
        "api_endpoint":       "https://status.salesforce.com/api/v1/incidents",
        "source_type":        "api",
        "jurisdiction":       "GLOBAL",
        "confidence_weight":  0.90,
        "active":             True,
        "notes":              "Salesforce CRM/Service Cloud incidents JSON API.",
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
        "active":             True,
        "notes":              "ServiceNow ITSM platform status API.",
    },

    # ─── Category 5: Banking & Payments Infrastructure ─────────────────────────
    {
        "source_name":        "AusPayNet",
        "category":           "banking_payments",
        "priority_rank":      1,
        "url":                "https://www.auspaynet.com.au/news",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.97,
        "active":             True,
        "notes":              "Australian Payments Network — payment system governance and incidents.",
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
        "active":             True,
        "notes":              "SWIFT messaging network news and operational notices.",
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
        "active":             True,
        "notes":              "Public Transport Victoria service disruptions.",
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
        "url":                "https://www.transurban.com/traffic-and-disruptions",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.80,
        "active":             True,
        "notes":              "Major toll road incidents affecting workforce mobility.",
    },
    {
        "source_name":        "Melbourne Airport",
        "category":           "transport",
        "priority_rank":      3,
        "url":                "https://www.melbourneairport.com.au/flight-information",
        "rss_url":            None,
        "api_endpoint":       None,
        "source_type":        "scrape",
        "jurisdiction":       "AU",
        "confidence_weight":  0.78,
        "active":             True,
        "notes":              "Flight disruptions at Melbourne Airport.",
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
        "active":             True,
        "notes":              "Reuters business news. Secondary verification source.",
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
        "active":             True,
        "notes":              "AFR — Australian financial and business news.",
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


def _upsert(rows: list[dict]) -> tuple[int, int]:
    """Upsert rows into intelligence_source_registry. Returns (inserted, failed)."""
    url = f"{SUPABASE_URL}/rest/v1/intelligence_source_registry"
    headers = {
        **_headers(),
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    body = json.dumps(rows).encode()
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
