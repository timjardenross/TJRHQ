"""
Parses ClinicalTrials.gov's real v2 JSON API for newly-posted RECRUITING /
NOT_YET_RECRUITING trials — HEALTH_OSINT_IMPLEMENTATION.md section 4 dynamic
source #19 ("ClinicalTrials.gov New Trials").

Built + confirmed live 2026-08-11. Real API, not scraping:

    GET https://clinicaltrials.gov/api/v2/studies
        ?query.cond=exercise+OR+sleep
        &filter.overallStatus=RECRUITING|NOT_YET_RECRUITING
        &pageSize=20
        &sort=StudyFirstPostDate:desc

No API key required, plain `urllib.request` GET, HTTP 200, no bot-block of
any kind hit — so the Firecrawl fallback this repo reserves for genuine
blocks was never needed and no Firecrawl budget was spent building or
testing this parser.

The doc's suggested URL (clinicaltrials.gov/search?status=RECRUITING,...)
is the JS-rendered search UI and was NOT used — confirmed via WebSearch
that ClinicalTrials.gov exposes the same data through a real, documented,
public v2 REST API instead (no key, Essie query syntax: query.cond for
condition/disease terms, filter.overallStatus, sort, pageSize). This
matches the pattern this repo already favors (GitHub Status / GCP Status
migrated from RSS/scraping to real JSON APIs in tools/intelligence/
sources_live.csv) and is also the exact API `tools/health/
collect_health_signals.py` already uses for its own (differently-scoped,
per-health_domain) Phase 1 ClinicalTrials.gov queries — see "Relationship
to the existing Phase 1 pipeline" below.

Real structure, confirmed by fetching and printing full responses (not
assumed from docs):

  - Every field lives inside `study["protocolSection"]["<module>"]` — e.g.
    identificationModule.nctId/briefTitle, statusModule.overallStatus,
    statusModule.studyFirstPostDateStruct.date, designModule.studyType/
    designInfo.allocation/enrollmentInfo.count, descriptionModule.
    briefSummary, conditionsModule.conditions (list) + .keywords (list,
    often present and useful for classification, e.g. a sleep-supplement
    trial's real keywords were ["Muscle Damage","Sleep","Supplementation",
    "Recovery"]), sponsorCollaboratorsModule.leadSponsor.name.
  - `date` fields are sometimes only "YYYY-MM" (estimated dates) rather
    than full "YYYY-MM-DD" — studyFirstPostDateStruct in particular was
    always a full date in every real response seen here, but this parser
    still defensively handles the month-only case (day defaulted to 1,
    never fabricated to a specific day).
  - SURPRISE #1: the documented `fields=` param (meant to slim the
    response to flat field names like "NCTId,BriefTitle") did NOT return a
    flat structure in testing — the response still came back as full
    nested protocolSection modules, just possibly module-filtered. Not
    relied upon here; this parser reads the full nested shape instead.
  - SURPRISE #2: `query.cond` with 3+ "OR"-joined terms visibly degrades
    into fuzzy/irrelevant matching — e.g. "sleep OR stress OR nutrition"
    returned an unrelated adrenal-cancer radiotherapy trial as its first
    result. 1-2 terms ("sleep OR nutrition", "exercise OR sleep") returned
    consistently on-topic results in every test run. This parser's
    recommended production query therefore stays at 2 OR-terms per call;
    a weekly cron wanting broader taxonomy coverage should rotate the
    term-pair across runs rather than widen a single query.
  - The default page size actually returned was 20 (== requested
    pageSize) with `nextPageToken` present for cursor pagination — not
    used here (this parser is a single-page, single-call source, per the
    ~1-call-per-fetch budget discipline for this build).

Relationship to the existing Phase 1 pipeline (tools/health/
collect_health_signals.py): that script already queries this same v2 API,
but per-health_domain with a fixed CTGOV_QUERIES dict, feeding
`_save_signal()`'s richer row (which includes study_design/sample_size/
p_value and computes confidence_level from source tier + methodology
quality). This parser is deliberately narrower and is NOT a duplicate: it
is a real-time "newest first" (sort=StudyFirstPostDate:desc) feed meant
for HEALTH_OSINT_IMPLEMENTATION.md's automated weekly Firecrawl/API
ingestion path (health_signal_ingestion.py), which inserts everything as
auto_ingested=True + suppressed=True (pending manual curation) rather than
auto-scoring confidence — see that orchestrator's docstring.

health_domain vocabulary note (disclosed mismatch, not fixed here): this
parser follows HEALTH_OSINT_IMPLEMENTATION.md section 3's granular
taxonomy (e.g. "factor_sleep", "performance_recovery", "epi_vaccination"),
matching the convention already used by the sibling parsers built in this
same batch (parse_fda_medwatch.py -> "safety_adverse_event",
parse_cdc_epidemic.py -> "epi_outbreak"). This is DIFFERENT from the
6-value vocabulary (epidemiology | treatment | supplement | performance |
mental_health | vaccine) that tools/health/collect_health_signals.py
actually writes into production today and that lcars-portal's
confidence-matrix route.ts specifically pattern-matches on (its
categorize() only special-cases health_domain === 'epidemiology' or
'performance' — everything else, including every section-3 subcode used
here, falls into a generic "Treatment" bucket in that view). Both
vocabularies are schema-legal (health_domain has no CHECK constraint,
per migration 0141's own header comment) but they are NOT the same
vocabulary, and no migration/mapping reconciles them yet. Flagging this
here since it affects how these signals will actually render, not fixing
it — out of this parser's scope.

Per-item classification is real-content-driven keyword matching over
title + conditions + keywords + a slice of the abstract (same technique
already used by tools/health/collect_health_signals.py's
_infer_health_domain), NOT a fabricated per-trial judgement. Most trials
returned by a 2-term query. are on-topic given the query itself, but
condition lists on ClinicalTrials.gov are free text and can span multiple
plausible subcodes (e.g. "resistance training strength gains" matches
both a contributing-factor and a performance-outcome keyword) — ties are
broken by keyword-list order below, disclosed rather than hidden.
Genuinely unclassifiable trials (query drift, e.g. the adrenal-cancer
example above) fall back to 'outcome_evidence', matching this exact
source's own listed health_domain in HEALTH_OSINT_IMPLEMENTATION.md
section 4's table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Section-3 subcode <- keyword match, checked in this order (first match
# wins). Real trial text -> real subcode, not guessed structure.
_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("vaccine", "vaccination", "immuniz"), "epi_vaccination"),
    (("outbreak", "epidemic", "surveillance", "pandemic"), "epi_outbreak"),
    (("insomnia", "sleep"), "factor_sleep"),
    (("cortisol", "hpa-axis", "hpa axis", "stress management", "stress reduction"), "mental_health_stress"),
    (("depression", "anxiety", "burnout", "psychiat", "mood disorder"), "mental_health_mood"),
    (("cognit", "memory", "neuroplastic", "attention", "concentration"), "mental_health_cognition"),
    (("nutrition", "dietary", "diet", "macronutrient", "micronutrient", "supplement", "vitamin"), "factor_nutrition"),
    (("resistance training", "endurance training", "training load", "periodization", "exercise program"), "factor_training"),
    (("altitude", "heat exposure", "cold exposure", "circadian", "light exposure", "temperature regulation"), "factor_environment"),
    (("vo2max", "vo2 max", "aerobic capacity", "cardiorespiratory fitness", "endurance performance"), "performance_endurance"),
    (("strength", "power output", "muscle gain", "hypertroph"), "performance_strength"),
    (("recovery", "doms", "muscle soreness", "active recovery"), "performance_recovery"),
    (("overtraining", "injury risk", "injury prevention"), "performance_risk"),
    (("athletic performance", "exercise performance", "sports medicine"), "performance_endurance"),
    (("retract", "contradict", "reversal", "no longer supported"), "evidence_shift"),
]

# Section-3 factor_* subcode -> the (unrelated, separately CHECK-constrained)
# contributing_factor_type column added in migration 0141 (sleep | stress |
# nutrition | training | environment | NULL). Only the factor_* domains have
# a direct 1:1 mapping onto that column.
_CONTRIBUTING_FACTOR_MAP = {
    "factor_sleep": "sleep",
    "mental_health_stress": "stress",
    "factor_nutrition": "nutrition",
    "factor_training": "training",
    "factor_environment": "environment",
}

_DEFAULT_DOMAIN = "outcome_evidence"  # per section 4's table row for this exact source


def _classify(text: str) -> tuple[str, str | None]:
    t = text.lower()
    for keywords, domain in _DOMAIN_KEYWORDS:
        if any(k in t for k in keywords):
            return domain, _CONTRIBUTING_FACTOR_MAP.get(domain)
    return _DEFAULT_DOMAIN, None


def _parse_ctgov_date(date_str: str | None) -> str | None:
    """Handles both real observed shapes: 'YYYY-MM-DD' (seen on every
    studyFirstPostDateStruct in testing) and 'YYYY-MM' (seen on some
    estimated startDateStruct/completionDateStruct fields) — day defaults
    to 1 for the month-only case, never fabricated to a specific day."""
    if not date_str:
        return None
    parts = date_str.split("-")
    try:
        if len(parts) == 3:
            dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
        elif len(parts) == 2:
            dt = datetime(int(parts[0]), int(parts[1]), 1, tzinfo=timezone.utc)
        else:
            return None
        return dt.isoformat()
    except (ValueError, IndexError):
        return None


def _study_design(design_module: dict[str, Any]) -> str:
    """Same real-field mapping tools/health/collect_health_signals.py's
    _parse_ctgov_study already uses for this same API (studyType +
    designInfo.allocation are real structured CTgov fields, not inferred
    from free text)."""
    study_type = design_module.get("studyType", "")
    allocation = (design_module.get("designInfo") or {}).get("allocation", "")
    if study_type == "INTERVENTIONAL" and allocation == "RANDOMIZED":
        return "RCT"
    if study_type == "OBSERVATIONAL":
        return "observational"
    return "observational"


def parse_clinicaltrials_new(json_response: dict) -> list[dict]:
    """
    Parse a ClinicalTrials.gov v2 `/studies` JSON response (the parsed
    dict, e.g. `json.loads(urllib.request.urlopen(url).read())` — this
    source is fetched via a real direct API GET, not Firecrawl markdown/
    HTML, so this function's input contract is a dict, not a string; see
    module docstring's "Relationship to health_signal_ingestion.py" note
    below for why that doesn't yet plug into that orchestrator's fetch
    dispatch as-is).

    Returns a list of dicts covering health_signals' insertable columns
    (migration 0093): title, description, signal_type ('study_result',
    fixed per this source's taxonomy assignment), health_domain,
    contributing_factor_type, study_design, sample_size, published_at,
    canonical_url. severity/adverse_event_text/fda_flagged/
    frequency_reported are intentionally omitted (None) — CTgov trial
    listings carry none of that; forcing values would be fabrication.

    Disclosed integration gap: health_signal_ingestion.py's `_fetch()`
    only knows fetch_tool in {firecrawl, bright_data, manual} — both
    firecrawl and bright_data return a markdown/HTML *string*, not a
    parsed dict. Wiring this parser into that orchestrator's automated
    weekly run needs either a new fetch_tool value (e.g. 'direct_json')
    added to that dispatch + the health_source_fetch_config CHECK/comment,
    or an adapter that does the urllib GET + json.loads before calling
    this function. Not built here — out of this task's scope (parser
    only), disclosed so it isn't silently assumed to already work.
    """
    studies = (json_response or {}).get("studies", [])
    items: list[dict] = []

    for study in studies:
        proto = study.get("protocolSection", {}) if isinstance(study, dict) else {}
        ident = proto.get("identificationModule", {}) or {}
        status = proto.get("statusModule", {}) or {}
        design = proto.get("designModule", {}) or {}
        desc_mod = proto.get("descriptionModule", {}) or {}
        conds_mod = proto.get("conditionsModule", {}) or {}
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {}) or {}

        nct_id = ident.get("nctId")
        if not nct_id:
            # Never seen in real testing, but fail closed rather than
            # emit a signal with no canonical identifier/URL.
            continue

        title = ident.get("briefTitle") or ident.get("officialTitle") or "(untitled trial)"
        overall_status = status.get("overallStatus", "")
        conditions = conds_mod.get("conditions", []) or []
        keywords = conds_mod.get("keywords", []) or []
        brief_summary = (desc_mod.get("briefSummary") or "").strip()
        sponsor = (sponsor_mod.get("leadSponsor") or {}).get("name")

        classify_text = " ".join([title, " ".join(conditions), " ".join(keywords), brief_summary[:500]])
        health_domain, contributing_factor_type = _classify(classify_text)

        published_at = _parse_ctgov_date((status.get("studyFirstPostDateStruct") or {}).get("date"))

        description = (
            f"Status: {overall_status}. Sponsor: {sponsor or 'unknown'}. "
            f"Conditions: {', '.join(conditions[:5]) or 'not specified'}. "
            f"{brief_summary[:400]}"
        ).strip()

        items.append({
            "title": title[:500],
            "description": description[:2000],
            "signal_type": "study_result",
            "health_domain": health_domain,
            "contributing_factor_type": contributing_factor_type,
            "study_design": _study_design(design),
            "sample_size": (design.get("enrollmentInfo") or {}).get("count"),
            "severity": None,
            "adverse_event_text": None,
            "fda_flagged": False,
            "frequency_reported": None,
            "published_at": published_at,
            "canonical_url": f"https://clinicaltrials.gov/study/{nct_id}",
        })

    return items
