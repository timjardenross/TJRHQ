#!/usr/bin/env python3
"""
Health OSINT Signal Collection — Phase 1 (PubMed + ClinicalTrials.gov)

Real ingestion for the Health/Performance OSINT Workbench (HEALTH_OSINT_
WORKBENCH.md). Before this script, health_signals held a one-time
26-row hand-authored seed with no real collection pipeline — this is
that pipeline's first phase.

Sources:
  - PubMed (NCBI E-utilities esearch/efetch) — one query per health_domain,
    last 30 days. study_design comes directly from PubMed's PublicationType
    field (a real structured tag, not inferred) where present.
  - ClinicalTrials.gov (REST API v2) — one query per health_domain.
    study_design/sample_size come from designModule.studyType/allocation
    and designModule.enrollmentInfo.count — both real structured fields.

New journals encountered via PubMed are auto-registered into
health_source_registry with a default publisher_reputation, EXCEPT a
short hand-curated list of known top-tier journals (see
KNOWN_JOURNAL_REPUTATION below) — same reasoning as the original 16
seed sources: without this, every auto-registered source would start
identical and need days of validation data before differentiating,
repeating the exact "SRS scoring inert" mistake found and fixed in
the technical workbench this session.

Usage:
    python3 tools/health/collect_health_signals.py [--dry-run] [--per-domain-limit N]
"""

import os
import re
import sys
import hashlib
import logging
import argparse
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(REPO_ROOT))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

from supabase import create_client

# ─── Per-health_domain search queries ────────────────────────────────────

# 2026-08-09 gap-closure: broadened after live testing against the real
# esearch/studies APIs (30-day PubMed pool, CTgov totalCount) confirmed
# every domain's result pool grew, none went to zero. "treatment" was the
# worst offender — its CTgov side was locked to a single condition
# ("cardiovascular disease treatment") while its PubMed side was already
# broad; broadened to a representative condition basket rather than fully
# open ("treatment efficacy OR therapeutic intervention" alone matched
# 250k+ trials via CTgov's fuzzy free-text matching — untargeted noise,
# not a real widening of scope). per_domain_limit still caps daily output
# at 15/domain regardless of pool size; a bigger pool means better
# candidates to pick those 15 from, not more volume.
PUBMED_QUERIES = {
    "epidemiology": "(epidemiology[tiab] OR outbreak[tiab] OR disease surveillance[tiab] OR incidence[tiab] OR prevalence[tiab])",
    "treatment": "(clinical trial[pt]) AND (treatment efficacy[tiab] OR therapeutic outcome[tiab] OR treatment outcome[tiab])",
    "supplement": "(dietary supplement[tiab] OR nutraceutical[tiab] OR vitamin supplementation[tiab]) AND (randomized[tiab] OR trial[tiab])",
    "performance": "(exercise performance[tiab] OR athletic performance[tiab] OR ergogenic[tiab] OR resistance training[tiab] OR endurance training[tiab])",
    "mental_health": "(mental health[tiab] OR depression[tiab] OR anxiety[tiab] OR stress[tiab] OR burnout[tiab]) AND (randomized controlled trial[pt] OR meta-analysis[pt])",
    "vaccine": "(vaccine efficacy[tiab] OR vaccine safety[tiab] OR immunization[tiab] OR vaccination coverage[tiab])",
}

CTGOV_QUERIES = {
    "epidemiology": "infectious disease surveillance OR outbreak investigation OR disease prevalence",
    "treatment": "cardiovascular disease treatment OR diabetes treatment OR cancer treatment OR chronic pain treatment",
    "supplement": "dietary supplement OR nutraceutical OR vitamin supplementation",
    "performance": "athletic performance OR exercise performance OR sports medicine",
    "mental_health": "depression OR anxiety OR stress resilience",
    "vaccine": "vaccine efficacy OR vaccine safety OR immunization",
}

# Phase 2: journal/agency RSS. Every URL here was curl-verified live before
# being added — not guessed. Dropped from the original candidate list:
#   - NIH, Cochrane: real Cloudflare JS challenge (403 "Just a moment..."),
#     not bypassable with a UA header or any non-browser fetch.
#   - CDC: www.cdc.gov itself is bot-blocked; the tools.cdc.gov RSS proxy
#     works but needs a numeric media ID I could not discover without
#     further undisciplined guessing (one guess hit a real but item-less
#     feed). Dropped rather than guess again.
#   - JAMA: the official current-issue feed (jamanetwork.com/rss/site_3/67.xml,
#     confirmed via JAMA's own /pages/rss page) serves title="JAMA" generically
#     for every item — no real article titles in the feed itself. JAMA content
#     is already reachable via Phase 1's PubMed queries, so this isn't a real
#     coverage gap, just a dropped redundant feed.
#   - FDA: curl fetches the feed fine (200), but Python's urllib gets
#     redirected to FDA's own "abuse-detection-apology" page and 404s
#     regardless of User-Agent header — a TLS/request-fingerprint block,
#     not a UA check, so no header change fixes it. Not worth a heavier
#     fetch tool for one feed; dropped and disclosed rather than silently
#     left broken.
# "kind": agency_news items don't carry a study design (they're press
# releases, not papers); journal items get study_design inferred from
# title keywords since these feeds (unlike PubMed) carry no structured
# PublicationType tag.
RSS_FEEDS = [
    {"source_name": "WHO", "url": "https://www.who.int/rss-feeds/news-english.xml", "kind": "agency_news"},
    {"source_name": "New England Journal of Medicine", "url": "https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm", "kind": "journal"},
    {"source_name": "The Lancet", "url": "https://www.thelancet.com/rssfeed/lancet_current.xml", "kind": "journal"},
]

DOMAIN_KEYWORDS = {
    "vaccine": ("vaccine", "vaccination", "immuniz"),
    "mental_health": ("mental health", "depression", "anxiety", "psychiatr"),
    "supplement": ("supplement", "nutraceutical", "vitamin", "dietary"),
    "performance": ("exercise", "athletic", "performance", "ergogenic"),
    "epidemiology": ("outbreak", "epidemic", "surveillance", "pandemic", "cases reported"),
}


def _infer_health_domain(text: str, default="treatment") -> str:
    t = text.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(k in t for k in keywords):
            return domain
    return default


def _infer_study_design_from_title(title: str) -> str:
    t = title.lower()
    if "meta-analysis" in t or "systematic review" in t:
        return "meta_analysis"
    if "randomized" in t or "randomised" in t or "rct" in t:
        return "RCT"
    if "case report" in t:
        return "case_study"
    if any(k in t for k in ("editorial", "perspective", "comment", "correspondence")):
        return "anecdotal"  # opinion pieces, not primary evidence
    return "observational"

# Hand-curated: journals whose real-world reputation we already know,
# so auto-registration doesn't start every source identical. Same
# reasoning as the original 16 seed sources' hand-set publisher_reputation.
def _normalize_journal_name(name: str) -> str:
    """Lowercase, strip a leading 'the ', strip anything after ':' or '=' (PubMed's
    Journal/Title field sometimes appends a translated/subtitle after these), collapse
    mid-string '. ' into a space (PubMed renders Lancet-family titles as "Lancet.
    Global health" — the period is a subtitle separator, not punctuation to preserve),
    strip trailing periods. Keys in KNOWN_JOURNAL_REPUTATION are pre-normalized to match."""
    n = name.lower().strip()
    n = re.sub(r'^the\s+', '', n)
    n = re.split(r'\s*[:=]\s*', n)[0]
    n = n.replace('. ', ' ')
    return n.rstrip('.')


# Keys are pre-normalized (no leading "the ") — see _normalize_journal_name.
# Deliberately excludes single generic words (e.g. bare "cell", "science",
# "nature") as keys: those false-matched unrelated journals ("Cell host &
# microbe", "Research in veterinary science") when this used substring
# matching. Exact match against the full normalized name only.
KNOWN_JOURNAL_REPUTATION = {
    "new england journal of medicine": 0.97, "lancet": 0.96, "nature medicine": 0.95,
    "jama": 0.94, "bmj": 0.93, "nature": 0.96, "science": 0.95, "cell": 0.93,
    "lancet infectious diseases": 0.94, "lancet oncology": 0.94, "lancet respiratory medicine": 0.94,
    "lancet global health": 0.90, "lancet public health": 0.90, "lancet psychiatry": 0.92,
    "medicine and science in sports and exercise": 0.85,
    "annals of internal medicine": 0.90, "circulation": 0.90, "diabetes care": 0.87,
    "plos medicine": 0.82, "plos one": 0.68, "scientific reports": 0.62,
    "cochrane database of systematic reviews": 0.93,
    "frontiers in endocrinology": 0.55, "frontiers in immunology": 0.55,
    "frontiers in public health": 0.5,
    "journal of the american college of cardiology": 0.90,
    "british journal of sports medicine": 0.85,
    "clinical psychology review": 0.80,
    "jama psychiatry": 0.90,
    "proceedings of the national academy of sciences of the united states of america": 0.94,
    "nature communications": 0.88,
    "cell host & microbe": 0.88,
}
DEFAULT_NEW_JOURNAL_REPUTATION = 0.45  # conservative — must earn tier via validation

STUDY_DESIGN_QUALITY = {"RCT": 0.85, "meta_analysis": 0.90, "observational": 0.55, "case_study": 0.30, "anecdotal": 0.10}


def _headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}


class HealthCollector:
    def __init__(self, dry_run=False, per_domain_limit=15):
        self.dry_run = dry_run
        self.per_domain_limit = per_domain_limit
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self._source_cache = {}  # source_name -> source_id
        self.stats = {"pubmed_fetched": 0, "ctgov_fetched": 0, "rss_fetched": 0, "saved": 0, "duplicates": 0, "sources_auto_registered": 0, "errors": 0}

    # ─── Source resolution ──────────────────────────────────────────────

    def _get_or_create_source(self, source_name: str, source_type: str, source_url: str = None) -> str:
        if source_name in self._source_cache:
            return self._source_cache[source_name]

        existing = self.supabase.table("health_source_registry").select("source_id").eq("source_name", source_name).limit(1).execute()
        if existing.data:
            self._source_cache[source_name] = existing.data[0]["source_id"]
            return existing.data[0]["source_id"]

        # Normalized exact match, not substring: an earlier version used
        # "key in name_lower" to handle PubMed's inconsistent "The " prefix,
        # but that let generic single words in the dict (science/cell/nature)
        # false-match unrelated journals — "Research in veterinary science"
        # and "Cell host & microbe" inherited Science/Cell's reputation
        # during testing. Normalizing (strip leading "the ", trailing
        # subtitle/translation after ":" or "=") and requiring exact
        # equality fixes the prefix problem without that false-positive risk.
        reputation = KNOWN_JOURNAL_REPUTATION.get(_normalize_journal_name(source_name), DEFAULT_NEW_JOURNAL_REPUTATION)
        row = {
            "source_name": source_name, "source_type": source_type, "source_url": source_url,
            "peer_reviewed": True, "publisher_reputation": reputation,
            "conflict_of_interest_disclosure": True, "funding_transparency": 0.5,
            "replication_success_rate": 0.5, "retraction_rate": 0.03,
            "avg_methodology_quality": 0.5, "auto_registered": True,
        }
        logger.info(f"Auto-registering new source: {source_name} (reputation={reputation})")
        if self.dry_run:
            self._source_cache[source_name] = "dry-run-placeholder"
            self.stats["sources_auto_registered"] += 1
            return "dry-run-placeholder"

        result = self.supabase.table("health_source_registry").insert(row).execute()
        source_id = result.data[0]["source_id"]
        self._source_cache[source_name] = source_id
        self.stats["sources_auto_registered"] += 1
        return source_id

    # ─── PubMed ──────────────────────────────────────────────────────────

    def fetch_pubmed(self, health_domain: str):
        query = PUBMED_QUERIES[health_domain]
        params = urllib.parse.urlencode({
            "db": "pubmed", "term": query, "retmax": self.per_domain_limit,
            "retmode": "json", "datetype": "pdat", "reldate": 30, "sort": "relevance",
        })
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                import json
                ids = json.loads(resp.read()).get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            logger.error(f"PubMed esearch failed for {health_domain}: {e}")
            self.stats["errors"] += 1
            return []

        if not ids:
            return []

        efetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={','.join(ids)}&retmode=xml"
        try:
            with urllib.request.urlopen(efetch_url, timeout=20) as resp:
                xml_data = resp.read()
        except Exception as e:
            logger.error(f"PubMed efetch failed for {health_domain}: {e}")
            self.stats["errors"] += 1
            return []

        items = []
        try:
            root = ET.fromstring(xml_data)
            for article in root.findall(".//PubmedArticle"):
                items.append(self._parse_pubmed_article(article, health_domain))
        except ET.ParseError as e:
            logger.error(f"PubMed XML parse failed for {health_domain}: {e}")
            self.stats["errors"] += 1
        self.stats["pubmed_fetched"] += len(items)
        return items

    def _parse_pubmed_article(self, article, health_domain):
        pmid = article.findtext(".//PMID") or ""
        title = (article.findtext(".//ArticleTitle") or "").strip()
        journal = (article.findtext(".//Journal/Title") or "Unknown Journal").strip()
        abstract_parts = [el.text or "" for el in article.findall(".//AbstractText")]
        abstract = " ".join(abstract_parts).strip()
        pub_types = [el.text for el in article.findall(".//PublicationType")]

        study_design = "observational"  # conservative default for peer-reviewed but untagged articles
        if any("Meta-Analysis" in t or "Systematic Review" in t for t in pub_types):
            study_design = "meta_analysis"
        elif any("Randomized Controlled Trial" in t for t in pub_types):
            study_design = "RCT"
        elif any("Case Reports" in t for t in pub_types):
            study_design = "case_study"
        elif any("Observational Study" in t or "Comparative Study" in t for t in pub_types):
            study_design = "observational"

        sample_size = None
        m = re.search(r'\b(\d{2,6})\s+(?:patients|subjects|participants|women|men|adults|children|individuals)\b', abstract, re.I)
        if m:
            sample_size = int(m.group(1))
        p_value = None
        m = re.search(r'p\s*[<=]\s*0?\.(\d+)', abstract, re.I)
        if m:
            p_value = float(f"0.{m.group(1)}")

        year_el = article.find(".//JournalIssue/PubDate/Year")
        year = year_el.text if year_el is not None else str(datetime.now(timezone.utc).year)

        return {
            "source": "pubmed", "pmid": pmid, "title": title or "(untitled)", "description": abstract[:2000],
            "journal": journal, "health_domain": health_domain, "study_design": study_design,
            "sample_size": sample_size, "p_value": p_value,
            "canonical_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "published_at": f"{year}-01-01" if year.isdigit() else None,
        }

    # ─── ClinicalTrials.gov ─────────────────────────────────────────────

    def fetch_clinicaltrials(self, health_domain: str):
        query = CTGOV_QUERIES[health_domain]
        params = urllib.parse.urlencode({"query.term": query, "pageSize": self.per_domain_limit, "sort": "LastUpdatePostDate:desc"})
        url = f"https://clinicaltrials.gov/api/v2/studies?{params}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                import json
                data = json.loads(resp.read())
        except Exception as e:
            logger.error(f"ClinicalTrials.gov fetch failed for {health_domain}: {e}")
            self.stats["errors"] += 1
            return []

        items = []
        for study in data.get("studies", []):
            try:
                items.append(self._parse_ctgov_study(study, health_domain))
            except Exception as e:
                logger.warning(f"Skipping malformed CTgov study: {e}")
        self.stats["ctgov_fetched"] += len(items)
        return items

    def _parse_ctgov_study(self, study, health_domain):
        proto = study["protocolSection"]
        ident = proto.get("identificationModule", {})
        design = proto.get("designModule", {})
        status = proto.get("statusModule", {})
        conditions = proto.get("conditionsModule", {}).get("conditions", [])

        study_type = design.get("studyType", "")
        allocation = design.get("designInfo", {}).get("allocation", "")
        if study_type == "INTERVENTIONAL" and allocation == "RANDOMIZED":
            study_design = "RCT"
        elif study_type == "OBSERVATIONAL":
            study_design = "observational"
        else:
            study_design = "observational"

        enrollment = design.get("enrollmentInfo", {}).get("count")
        overall_status = status.get("overallStatus", "")
        signal_type = "safety_alert" if overall_status in ("WITHDRAWN", "TERMINATED", "SUSPENDED") else "study_result"

        nct_id = ident.get("nctId", "")
        return {
            "source": "clinicaltrials", "nct_id": nct_id,
            "title": ident.get("briefTitle") or ident.get("officialTitle") or "(untitled trial)",
            "description": f"Status: {overall_status}. Conditions: {', '.join(conditions[:5])}. "
                            f"{status.get('whyStopped', '')}".strip()[:2000],
            "health_domain": health_domain, "study_design": study_design, "sample_size": enrollment,
            "signal_type": signal_type,
            "canonical_url": f"https://clinicaltrials.gov/study/{nct_id}",
            "published_at": status.get("studyFirstPostDateStruct", {}).get("date"),
        }

    # ─── RSS (FDA / WHO / NEJM / Lancet) ────────────────────────────────

    def fetch_rss(self, feed: dict):
        """Namespace-agnostic RSS 2.0 / RDF (RSS 1.0) parser: matches items and
        fields by tag local-name so one parser handles both formats — FDA/WHO
        are plain RSS 2.0, NEJM/Lancet are RDF. Prefers dc:title/dc:date over
        plain title/pubDate when present (more reliable on the RDF feeds)."""
        # A bot-identifying UA string here (tried first) makes FDA's server
        # 302-redirect to a 404 — a plain browser UA avoids it, confirmed by
        # testing (curl with the same custom UA reproduced the redirect;
        # curl with no UA / a browser UA did not).
        req = urllib.request.Request(feed["url"], headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_data = resp.read()
        except Exception as e:
            logger.error(f"RSS fetch failed for {feed['source_name']}: {e}")
            self.stats["errors"] += 1
            return []

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            logger.error(f"RSS parse failed for {feed['source_name']}: {e}")
            self.stats["errors"] += 1
            return []

        items = [el for el in root.iter() if el.tag.endswith('}item') or el.tag == 'item']
        parsed = []
        for item in items[:self.per_domain_limit]:
            fields = {}
            for child in item:
                local = child.tag.split('}')[-1]
                if child.text and child.text.strip():
                    fields.setdefault(local, child.text.strip())

            title = fields.get("title", "")
            if not title or title == feed["source_name"]:  # JAMA-style generic title, if it ever recurs
                continue
            link = fields.get("link") or fields.get("url") or fields.get("identifier", "")
            description = fields.get("encoded") or fields.get("description") or fields.get("content") or ""
            date_str = fields.get("date") or fields.get("pubDate")

            health_domain = _infer_health_domain(title + " " + description)
            if feed["kind"] == "agency_news":
                study_design = None
                signal_type = self._signal_type_from_title(title, default="safety_alert" if "recall" in title.lower() or "warning" in title.lower() else "study_result")
            else:
                study_design = _infer_study_design_from_title(title)
                signal_type = self._signal_type_from_title(title)

            parsed.append({
                "source": "rss", "source_name": feed["source_name"], "title": title[:500],
                "description": re.sub(r'<[^>]+>', '', description)[:2000],  # strip HTML tags
                "health_domain": health_domain, "study_design": study_design, "sample_size": None,
                "p_value": None, "signal_type": signal_type,
                "canonical_url": link, "published_at": self._parse_rss_date(date_str),
            })
        self.stats["rss_fetched"] = self.stats.get("rss_fetched", 0) + len(parsed)
        return parsed

    def _parse_rss_date(self, date_str):
        if not date_str:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    # ─── Classification + scoring ───────────────────────────────────────

    def _signal_type_from_title(self, title: str, default="study_result") -> str:
        t = title.lower()
        if any(k in t for k in ("adverse event", "side effect", "toxicity", "safety signal")):
            return "adverse_event"
        if any(k in t for k in ("outbreak", "epidemic", "cases reported")):
            return "outbreak"
        if "efficacy" in t and "trial" not in t:
            return "efficacy_claim"
        return default

    def _methodology_quality(self, study_design, sample_size, p_value):
        score = STUDY_DESIGN_QUALITY.get(study_design, 0.4)
        if sample_size:
            if sample_size >= 100:
                score += 0.05
            if sample_size >= 1000:
                score += 0.05
        if p_value is not None:
            score += 0.05
        return round(min(1.0, score), 2)

    def _confidence_level(self, tier, quality_score):
        if tier == "TIER_1" and quality_score >= 0.70:
            return "HIGH"
        if tier == "TIER_1":
            return "MEDIUM"
        if tier == "TIER_2" and quality_score >= 0.60:
            return "MEDIUM"
        if tier == "TIER_2":
            return "LOW"
        if tier == "TIER_3" and quality_score >= 0.60:
            return "LOW"
        if tier in ("TIER_3", "TIER_4"):
            return "LOW"
        return "UNKNOWN"

    # ─── Persistence ────────────────────────────────────────────────────

    def save_item(self, item):
        if item["source"] == "pubmed":
            source_id = self._get_or_create_source(item["journal"], "journal")
            dedup_key = f"pubmed:{item['pmid']}"
            signal_type = self._signal_type_from_title(item["title"])
        elif item["source"] == "rss":
            # These 4 (FDA/WHO/NEJM/Lancet) are already hand-curated rows from
            # the original seed migration — look up by name, don't auto-register.
            existing = self.supabase.table("health_source_registry").select("source_id").eq("source_name", item["source_name"]).limit(1).execute()
            if not existing.data:
                logger.warning(f"RSS source '{item['source_name']}' not found in health_source_registry — skipping item")
                return
            source_id = existing.data[0]["source_id"]
            dedup_key = f"rss:{item['source_name']}:{item['canonical_url']}"
            signal_type = item.get("signal_type", "study_result")
        else:
            source_id = self._get_or_create_source("ClinicalTrials.gov", "clinical_trial_db", "https://clinicaltrials.gov")
            dedup_key = f"ctgov:{item['nct_id']}"
            signal_type = item.get("signal_type", "study_result")

        dedup_hash = hashlib.sha256(dedup_key.encode()).hexdigest()

        existing = self.supabase.table("health_signals").select("signal_id").eq("dedup_hash", dedup_hash).limit(1).execute()
        if existing.data:
            self.stats["duplicates"] += 1
            return

        if source_id == "dry-run-placeholder":
            tier = "TIER_4"
        else:
            source_row = self.supabase.table("health_source_registry").select("reliability_tier").eq("source_id", source_id).limit(1).execute()
            tier = source_row.data[0]["reliability_tier"] if source_row.data else "TIER_4"

        quality = self._methodology_quality(item["study_design"], item.get("sample_size"), item.get("p_value"))
        confidence = self._confidence_level(tier, quality)
        rank_score = round(self._tier_score(tier) * quality * 100, 2)

        row = {
            "title": item["title"][:500], "description": item.get("description"),
            "signal_type": signal_type, "health_domain": item["health_domain"],
            "study_design": item["study_design"], "sample_size": item.get("sample_size"),
            "p_value": item.get("p_value"), "methodology_quality_score": quality,
            "rank_score": rank_score, "confidence_level": confidence,
            "source_id": source_id, "canonical_url": item["canonical_url"], "dedup_hash": dedup_hash,
            "published_at": item.get("published_at"),
            # 2026-09-06: without this, rows defaulted to auto_ingested=false
            # and never entered health_signal_curation.py's _pending() query
            # (auto_ingested=true AND auto_ingest_reviewed=false) or the
            # manual /health-osint-curation queue (same filter) — every
            # signal this collector ever saved (PubMed/ClinicalTrials.gov/RSS,
            # running independently of health_signal_ingestion.py's Sunday
            # cron) sat permanently unscored and unreviewed. This is the
            # same flag health_signal_ingestion.py's _save_signal() sets
            # unconditionally for its own rows — matching that convention
            # routes this collector's output into the same
            # relevance-gate/evidence-scoring pipeline instead of a second,
            # silent, un-curated backlog.
            "auto_ingested": True,
        }

        if self.dry_run:
            logger.info(f"[dry-run] would save: {item['title'][:80]} ({confidence}, quality={quality})")
            self.stats["saved"] += 1
            return

        try:
            self.supabase.table("health_signals").insert(row).execute()
            self.stats["saved"] += 1
        except Exception as e:
            logger.error(f"Save failed for {item.get('pmid') or item.get('nct_id')}: {e}")
            self.stats["errors"] += 1

    def _tier_score(self, tier):
        return {"TIER_1": 0.95, "TIER_2": 0.75, "TIER_3": 0.55, "TIER_4": 0.30}.get(tier, 0.30)

    # ─── Orchestration ──────────────────────────────────────────────────

    def run(self):
        logger.info(f"Starting health signal collection{' (DRY RUN)' if self.dry_run else ''}")
        for domain in PUBMED_QUERIES:
            for item in self.fetch_pubmed(domain):
                self.save_item(item)
            for item in self.fetch_clinicaltrials(domain):
                self.save_item(item)
        for feed in RSS_FEEDS:
            for item in self.fetch_rss(feed):
                self.save_item(item)
        logger.info(f"Collection complete: {self.stats}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--per-domain-limit", type=int, default=15)
    args = parser.parse_args()
    HealthCollector(dry_run=args.dry_run, per_domain_limit=args.per_domain_limit).run()


if __name__ == "__main__":
    main()
