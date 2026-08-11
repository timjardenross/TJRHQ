"""
Parses bioRxiv/medRxiv's real public API for recently-posted preprints —
HEALTH_OSINT_IMPLEMENTATION.md section 4 dynamic source #20 ("bioRxiv/
medRxiv Trending").

Built + confirmed live 2026-08-11. Real API, not scraping:

    GET https://api.biorxiv.org/details/biorxiv/{start}/{end}/{cursor}
    GET https://api.biorxiv.org/details/medrxiv/{start}/{end}/{cursor}

    e.g. https://api.biorxiv.org/details/biorxiv/2026-08-04/2026-08-11/0

No API key, plain `urllib.request` GET, HTTP 200 on both bioRxiv and
medRxiv, no bot-block encountered — so, per this build's instructions, the
Firecrawl fallback was never invoked and no Firecrawl budget was spent.

Honest mismatch vs. the doc's ask ("trending preprints ... sorted by
downloads/citations"): WebSearch + this API's own /pubs/help documentation
confirm bioRxiv/medRxiv's real public API has NO "most-downloaded" /
"trending" / usage-metrics endpoint at all — `/details/<server>/<start>/
<end>/<cursor>` is a plain reverse-chronological listing of newly-POSTED
preprints in a date window, nothing more. There is no undocumented
endpoint for this either (checked `/covid19/0`, a real but unrelated
COVID-specific collection, returned 0 bytes for the window queried).
Rather than guess at homepage HTML for a "most read" ranking that may not
even be usable without a JS-rendered session, this parser uses the real,
structured, genuinely reliable "recent preprints" endpoint and is
transparent that "trending" (download/citation ranked) is NOT what it
delivers — it delivers "newest", which is the honest substitute this
API actually supports.

Real structure, confirmed by fetching and printing full responses (not
assumed from docs):

    {
      "messages": [{"status":"ok","category":"all",
                     "interval":"2026-08-04:2026-08-11","cursor":0,
                     "count":30,"count_new_papers":"1028","total":"1410"}],
      "collection": [
        {"title": "...", "authors": "...", "author_corresponding": "...",
         "author_corresponding_institution": "...", "doi": "10.64898/...",
         "date": "2026-08-04", "version": "2", "type": "new results",
         "license": "cc_by_nc_nd", "category": "neuroscience",
         "jatsxml": "https://www.biorxiv.org/content/early/...source.xml",
         "abstract": "...", "funder": "NA", "published": "NA",
         "server": "bioRxiv"},
        ...
      ]
    }

SURPRISE #1: the documented "100 articles per call" page size (per
api.biorxiv.org's own /pubs/help text, corroborated by third-party write-
ups) was NOT what was actually observed — every real call in testing
returned exactly 30 items (`"count":30`) regardless of how wide the date
window was, even though `"total"` for the same window was 1410. Cursor
pagination (`.../0`, `.../30`, `.../60`, ...) exists and would be needed
to walk the full window; this parser processes a single page (one real
call, per this build's budget discipline) and discloses that a 7-day
window's ~1000+ new bioRxiv papers are heavily undersampled by one call.

SURPRISE #2: `category` is per-item free text set by the submitting
author (e.g. "neuroscience", "immunology", "ecology", "bioengineering") —
there is no category *filter* query parameter on this endpoint (tested;
doesn't exist), so a health/performance-scoped feed has to filter/classify
client-side after fetching everything in the window, same as this parser
does below.

`type` field values seen: "new results" (bioRxiv) and "PUBLISHAHEADOFPRINT"
(medRxiv) — both are the same semantic thing (a newly posted/updated
version), used here only as pass-through context, not for classification.

health_domain / signal_type honesty: bioRxiv/medRxiv cover the entirety of
biology and medicine — a single 7-day window pulled in this build's real
test included categories like "ecology" and "animal behavior and
cognition" that have no honest mapping onto this platform's health/
performance-specific taxonomy (HEALTH_OSINT_IMPLEMENTATION.md section 3).
Per this task's brief ("a broad domain guess plus honest disclosure is
fine, don't force a bad fit"), items are classified by real keyword
matching over title + abstract + category (same technique as the sibling
parse_clinicaltrials_new.py in this batch) into section 3's granular
subcodes where a genuine match exists; anything that doesn't match falls
back to 'general_biomedical' — a value that is deliberately NOT one of
section 3's listed codes, because forcing e.g. "mechanism_discovery"'s
own signal_type value, or any specific factor_*/performance_* subcode,
onto an ecology or plant-biology preprint would be a fabricated
classification, not a rough guess. This is the same disclosed-mismatch
situation as parse_clinicaltrials_new.py's health_domain vocabulary note
(section 3's granular taxonomy vs. the different 6-value vocabulary
tools/health/collect_health_signals.py writes to production today) — see
that module's docstring for the full detail, not repeated here.

signal_type is fixed to 'mechanism_discovery' for every item per this
task's brief and HEALTH_OSINT_IMPLEMENTATION.md section 3/4 (bioRxiv/
medRxiv = mechanism discovery). This is a reasonable fit for the
preprints that ARE biomedical (a new pathway/mechanism paper) but an
honest overreach for items that are actually observational/ecological
findings rather than mechanism papers — not corrected per-item here since
the API gives no structured study-type tag to distinguish them (unlike
ClinicalTrials.gov's real designModule), and the task specified this
signal_type as fixed for this source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Section-3 subcode <- keyword match over title + abstract + category,
# checked in this order (first match wins). Same technique/discipline as
# parse_clinicaltrials_new.py in this batch.
_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("vaccine", "vaccination", "immuniz"), "epi_vaccination"),
    (("outbreak", "epidemic surveillance", "pandemic"), "epi_outbreak"),
    (("insomnia", "sleep"), "factor_sleep"),
    (("cortisol", "hpa axis", "hpa-axis", "chronic stress"), "mental_health_stress"),
    (("depression", "anxiety", "burnout", "mood disorder"), "mental_health_mood"),
    (("cognit", "memory", "neuroplastic", "attention", "learning and memory"), "mental_health_cognition"),
    (("nutrition", "dietary", "diet ", "macronutrient", "micronutrient"), "factor_nutrition"),
    (("resistance training", "endurance training", "training load", "periodization"), "factor_training"),
    (("altitude", "heat exposure", "cold exposure", "circadian", "thermoregulat"), "factor_environment"),
    (("vo2max", "vo2 max", "aerobic capacity", "cardiorespiratory fitness"), "performance_endurance"),
    (("muscle strength", "power output", "hypertroph", "muscle gain"), "performance_strength"),
    (("muscle recovery", "doms", "muscle soreness", "recovery from exercise"), "performance_recovery"),
    (("overtraining", "injury risk", "injury prevention"), "performance_risk"),
    (("retraction", "retracted", "no longer supported", "does not replicate"), "evidence_shift"),
]

# Section-3 factor_* subcode -> the separately CHECK-constrained
# contributing_factor_type column (migration 0141: sleep | stress |
# nutrition | training | environment | NULL).
_CONTRIBUTING_FACTOR_MAP = {
    "factor_sleep": "sleep",
    "mental_health_stress": "stress",
    "factor_nutrition": "nutrition",
    "factor_training": "training",
    "factor_environment": "environment",
}

# Deliberately not a section-3 code — see module docstring's
# "health_domain / signal_type honesty" section for why.
_DEFAULT_DOMAIN = "general_biomedical"


def _classify(text: str) -> tuple[str, str | None]:
    t = text.lower()
    for keywords, domain in _DOMAIN_KEYWORDS:
        if any(k in t for k in keywords):
            return domain, _CONTRIBUTING_FACTOR_MAP.get(domain)
    return _DEFAULT_DOMAIN, None


def _parse_date(date_str: str | None) -> str | None:
    """bioRxiv/medRxiv's `date` field was a plain 'YYYY-MM-DD' string in
    every real item seen during testing — no partial-date case observed
    here (unlike ClinicalTrials.gov), but this still fails closed
    (returns None) rather than raising or fabricating a date on any
    unexpected shape."""
    if not date_str:
        return None
    try:
        y, mo, d = date_str.split("-")
        return datetime(int(y), int(mo), int(d), tzinfo=timezone.utc).isoformat()
    except (ValueError, AttributeError):
        return None


def parse_biorxiv_trending(json_response: dict) -> list[dict]:
    """
    Parse a bioRxiv/medRxiv `/details/<server>/<start>/<end>/<cursor>`
    JSON response (the parsed dict — this source is fetched via a real
    direct API GET returning JSON, not Firecrawl markdown/HTML; see this
    module's docstring and parse_clinicaltrials_new.py's matching note for
    the disclosed gap this creates against health_signal_ingestion.py's
    current fetch_tool dispatch, which only returns strings).

    Returns a list of dicts covering health_signals' insertable columns
    (migration 0093): title, description, signal_type
    ('mechanism_discovery', fixed per this source's taxonomy assignment),
    health_domain, contributing_factor_type, published_at, canonical_url.
    study_design/sample_size/severity/adverse_event_text/fda_flagged/
    frequency_reported are intentionally omitted (None) — a preprint
    listing carries none of that; forcing values would be fabrication.
    `known_unknowns` is set to a real, structural fact (not peer
    reviewed) rather than left to imply false confidence.
    """
    items: list[dict] = []
    for entry in (json_response or {}).get("collection", []) or []:
        if not isinstance(entry, dict):
            continue

        title = (entry.get("title") or "").strip()
        doi = (entry.get("doi") or "").strip()
        if not title or not doi:
            # Never seen missing in real testing, but fail closed rather
            # than emit a signal with no title or no canonical identifier.
            continue

        abstract = (entry.get("abstract") or "").strip()
        category = (entry.get("category") or "").strip()
        authors = (entry.get("authors") or "").strip()
        server = entry.get("server") or "bioRxiv"
        preprint_type = entry.get("type") or ""
        already_published = entry.get("published") not in (None, "NA", "")

        classify_text = " ".join([title, category, abstract[:600]])
        health_domain, contributing_factor_type = _classify(classify_text)

        description = (
            f"{server} preprint ({category or 'uncategorized'}). "
            f"Authors: {authors[:200] or 'not listed'}. "
            f"{abstract[:400]}"
        ).strip()

        items.append({
            "title": title[:500],
            "description": description[:2000],
            "signal_type": "mechanism_discovery",
            "health_domain": health_domain,
            "contributing_factor_type": contributing_factor_type,
            "study_design": None,
            "sample_size": None,
            "severity": None,
            "adverse_event_text": None,
            "fda_flagged": False,
            "frequency_reported": None,
            "published_at": _parse_date(entry.get("date")),
            "canonical_url": f"https://doi.org/{doi}" if doi else None,
            "known_unknowns": {
                "peer_reviewed": False,
                "preprint_type": preprint_type,
                "published_in_journal": already_published,
            },
        })

    return items
