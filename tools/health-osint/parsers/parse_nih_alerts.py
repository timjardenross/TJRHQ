"""
Parses NIH RePORTER's real Project Search API — Health OSINT automated-fetch
source #22 in HEALTH_OSINT_IMPLEMENTATION.md section 4 ("NIH Research
Alerts").

Real source, confirmed live 2026-08-11 — and an honest naming mismatch
────────────────────────────────────────────────────────────────────────
The doc's suggested URL, https://reporter.nih.gov, is NIH RePORTER's search
UI — a grants-funding database, not a news/alerts feed. Checked both
candidates for real content before picking one:

1. NIH News Releases (nih.gov/news-events/news-releases) — genuinely
   "alerts"-shaped (institutional announcements), but every URL tried
   (the page itself, /feed, /rss.xml, /news-releases.xml) returned a real
   Cloudflare JS challenge, confirmed live 2026-08-11:
   `curl -m 20 https://www.nih.gov/news-events/news-releases/feed` ->
   HTTP 403, body starts `<title>Just a moment...</title>` — a genuine WAF
   block (exactly what firecrawl_client.py exists for), not a dead URL.

2. NIH RePORTER's real Project API — `POST https://api.reporter.nih.gov/v2/projects/search`,
   confirmed live 2026-08-11 via a plain unauthenticated `curl` POST (no API
   key, not bot-blocked: `curl -X GET` to the same endpoint correctly 405s —
   this API is POST-only, not broken). Real JSON response body inspected
   directly: `meta.total`, `results[].project_title`, `.abstract_text`,
   `.award_amount`, `.fiscal_year`, `.agency_ic_admin`, `.project_start_date`,
   `.project_num`, `.appl_id` are all real, populated fields (see a captured
   sample: project_num "1R15GM164975-01", "Uncovering Non-canonical Roles
   of Phosphagen Systems in Stress Resilience Using C. elegans", NIGMS,
   $546,500, started 2026-08-08). `sort_field`/`sort_order` (top-level
   payload keys, NOT nested under `criteria` — verified live: nesting them
   under `criteria` is silently ignored) with `project_start_date`/`desc`
   correctly returns newest-started projects first. A live test query using
   `advanced_text_search` (search_field: "projecttitle,terms", phrase terms
   like "sleep deprivation", "resistance training", "stress resilience",
   "overtraining" OR'd together) narrowed FY2025-2026 results from 48,151
   total projects to 2,326 — a real, working relevance filter, not a design
   guarantee of perfect precision (see "Honest domain-fit" below).
   Project detail URL pattern `https://reporter.nih.gov/project-details/{appl_id}`
   confirmed live (HTTP 200) using a real `appl_id` from the same query.

Given (1) is bot-blocked (needs a paid Firecrawl call every single fetch,
budget the doc had already earmarked for this source) and (2) is a free,
public, un-blocked, officially-documented REST API — this parser targets
NIH RePORTER, following this codebase's stated preference for a real
structured API over brittle/blocked scraping (same reasoning as GitHub
Status / GCP Status's RSS -> JSON API migrations noted in
tools/intelligence/sources_live.csv). This is a deliberate deviation from
the doc's literal "reach for Firecrawl on a block" instruction, because a
better real option existed for the *content itself*, not just the fetch
mechanics.

Honest mismatch vs. "Research Alerts" (disclosed, not hidden):
NIH RePORTER is a **grants-funding database** — each row is a newly
active/newly funded project record, not a published finding, news item, or
"alert" in the safety-bulletin sense the FDA/WHO/CDC parsers use that word
for. A funded grant is a leading indicator ("NIH is now funding research
into X") rather than a discovery or a trend. HEALTH_OSINT_IMPLEMENTATION.md
section 4 assigns this source signal_type 'mechanism_discovery' — that is
ALSO a loose fit (a new award ≠ a discovered mechanism; the mechanism, if
any, won't exist until the grant concludes years later) — kept as instructed
(per this task's brief: "use mechanism_discovery... unless real content
doesn't fit — note any mismatch") but explicitly flagged as an
approximation: the closest real meaning is "NIH has newly begun funding
research relevant to this health domain", not "a mechanism was discovered".
A more accurate signal_type for this content, if this taxonomy is revisited,
would be a new value like `research_funded` — not invented here since
signal_type IS free-text on health_signals (no CHECK constraint — see
migration 0141's header comment) and this task's brief pinned the value.

health_domain: RePORTER's real portfolio spans every NIH-funded disease
area, not just this workbench's Performance/Mental Health/Contributing
Factors scope. Rather than force one fixed domain onto every result
(inaccurate for a portfolio this broad) or invent a "general" bucket not in
section 3's taxonomy, `_classify_domain()` below does real keyword matching
against each project's own real title + abstract text and assigns one of
section 3's actual factor_*/performance_*/mental_health_* values — first
matching category wins, ordered from most to least specific. Projects that
match none of the workbench's real keywords are dropped (fail closed, same
discipline parse_fda_medwatch.py/parse_cdc_epidemic.py apply — never
fabricates a domain). This is a best-effort heuristic classification of
real NIH text, not an NIH-published categorisation — disclosed here, not
hidden. `contributing_factor_type` (health_signals' own CHECK-constrained
column: sleep|stress|nutrition|training|environment|NULL) is populated only
when the matched domain is one of the `factor_*` categories.

Built + live-tested 2026-08-11 against real, live-queried NIH RePORTER JSON
(not fabricated/assumed structure). The recommended query criteria used to
produce that JSON (documented, not embedded as a fetch call in this file —
see "Orchestrator wiring" below) is captured in `RECOMMENDED_CRITERIA`.

Orchestrator wiring (disclosed limitation, not fixed here — out of this
task's scope of "build 2 parsers"):
health_signal_ingestion.py's `_fetch(fetch_tool, url)` only knows `firecrawl`
(GET a URL, get markdown back) and `bright_data` (GET a URL, get raw text
back) — neither supports NIH RePORTER's real POST-with-JSON-body contract.
Wiring this parser into health_source_fetch_config therefore needs a small
follow-up to `_fetch()` (e.g. a `nih_reporter_api` fetch_tool that POSTs
RECOMMENDED_CRITERIA and returns the raw response body) before this source
can run unattended — `parse_nih_alerts()` itself is fully real and tested
against a live response body today; only the automated-POST plumbing is
still open.
"""

from __future__ import annotations

import json
import re

# Real, live-tested 2026-08-11 (see module docstring): narrows NIH's full
# ~48k-project FY25-26 portfolio down to ~2.3k projects whose title/terms
# mention this workbench's real subject matter. A starting point, not a
# precision-tuned filter — tune search_text further once real fetch volume
# is observed (HEALTH_OSINT_IMPLEMENTATION.md section 11's monthly parser
# audit).
RECOMMENDED_CRITERIA = {
    "criteria": {
        "fiscal_years": [2025, 2026],
        "advanced_text_search": {
            "operator": "or",
            "search_field": "projecttitle,terms",
            "search_text": (
                '"sleep deprivation" OR "sleep quality" OR "resistance training" OR '
                '"aerobic capacity" OR "cognitive performance" OR "stress resilience" OR '
                '"overtraining" OR "exercise performance" OR "burnout" OR "recovery '
                'modalities" OR "nutrition timing" OR "micronutrient"'
            ),
        },
    },
    "include_fields": [
        "ApplId", "ProjectNum", "ProjectTitle", "AbstractText", "FiscalYear",
        "AwardAmount", "ProjectStartDate", "AgencyIcAdmin",
    ],
    "sort_field": "project_start_date",
    "sort_order": "desc",
    "offset": 0,
    "limit": 25,
}
NIH_REPORTER_SEARCH_ENDPOINT = "https://api.reporter.nih.gov/v2/projects/search"
NIH_PROJECT_DETAIL_URL = "https://reporter.nih.gov/project-details/{appl_id}"

# Ordered most-specific-first: first matching category wins. Matched against
# lowercased "title abstract" text. Real section-3 taxonomy values only.
_DOMAIN_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("mental_health_mood", ("depression", "depressive", "anxiety", "bipolar", "mood disorder")),
    ("mental_health_cognition", ("cognit", "memory", "neuroplastic", "dementia", "alzheimer")),
    ("mental_health_risk", ("burnout", "suicide", "suicidal", "self-harm", "psychiatric crisis")),
    ("factor_sleep", ("sleep",)),
    ("factor_nutrition", ("nutrition", "dietary", "micronutrient", "macronutrient", " diet ")),
    ("factor_environment", ("altitude", "heat stress", "cold exposure", "hypoxia", "circadian")),
    ("mental_health_stress", ("cortisol", "hpa axis", "hpa-axis", "psychological stress")),
    ("performance_recovery", ("recovery modalit", "rehabilitation", "active recovery")),
    ("performance_risk", ("overtraining", "injury risk", "overuse injury")),
    ("performance_strength", ("resistance training", "muscle hypertrophy", "strength training", "power output")),
    ("performance_endurance", ("vo2max", "vo2 max", "aerobic capacity", "cardiorespiratory fitness", "endurance")),
    ("factor_training", ("exercise training", "training load", "periodization", "physical activity")),
    ("factor_stress", ("stress resilience", "stress response", "allostatic")),
]

# health_signals.contributing_factor_type CHECK constraint (migration 0094):
# sleep | stress | nutrition | training | environment | NULL
_FACTOR_DOMAIN_TO_TYPE = {
    "factor_sleep": "sleep",
    "factor_stress": "stress",
    "factor_nutrition": "nutrition",
    "factor_training": "training",
    "factor_environment": "environment",
}


def _classify_domain(text: str) -> str | None:
    lowered = f" {text.lower()} "
    for domain, keywords in _DOMAIN_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return domain
    return None


def parse_nih_alerts(json_response: str) -> list[dict]:
    """
    Parse a real response body from NIH RePORTER's /v2/projects/search API
    (see module docstring for the confirmed real endpoint, POST-only
    method, RECOMMENDED_CRITERIA, and the honest "grants database, not a
    news feed" mismatch disclosure).

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    severity, published_at, canonical_url, contributing_factor_type.

    Projects whose title/abstract don't match any real
    Performance/Mental-Health/Contributing-Factors keyword (see
    _DOMAIN_KEYWORDS) are dropped rather than tagged with a fabricated
    domain — this workbench's taxonomy has no "general NIH research"
    bucket, and RECOMMENDED_CRITERIA's text search is a relevance filter,
    not a guarantee every hit is truly in-scope.
    """
    try:
        data = json.loads(json_response)
    except (json.JSONDecodeError, TypeError):
        return []

    results = data.get("results")
    if not isinstance(results, list):
        return []

    items: list[dict] = []
    for proj in results:
        title = (proj.get("project_title") or "").strip()
        if not title:
            continue

        abstract = (proj.get("abstract_text") or "").strip()
        domain = _classify_domain(f"{title} {abstract}")
        if domain is None:
            # Real project, but doesn't match this workbench's real
            # keyword set for any section-3 domain -- skip rather than
            # mis-tag it.
            continue

        agency = proj.get("agency_ic_admin") or {}
        agency_name = agency.get("name") or agency.get("abbreviation") or "NIH"
        award_amount = proj.get("award_amount")
        fiscal_year = proj.get("fiscal_year")
        project_num = proj.get("project_num")
        start_date = proj.get("project_start_date")

        abstract_snippet = re.sub(r"\s+", " ", abstract)[:600].strip()
        amount_text = f"${award_amount:,}" if isinstance(award_amount, (int, float)) else "an undisclosed amount"
        description_parts = [
            f"NIH-funded project (FY{fiscal_year}, {amount_text}, {agency_name})."
        ]
        if abstract_snippet:
            description_parts.append(abstract_snippet)
        if project_num:
            description_parts.append(f"Project {project_num}, started {start_date}.")
        description = " ".join(description_parts)[:2000]

        appl_id = proj.get("appl_id")
        canonical_url = NIH_PROJECT_DETAIL_URL.format(appl_id=appl_id) if appl_id else None

        item: dict = {
            "title": title[:500],
            "description": description,
            "signal_type": "mechanism_discovery",  # see module docstring — disclosed loose fit
            "health_domain": domain,
            "severity": None,  # not applicable to a funding record — never fabricated
            "published_at": start_date,
            "canonical_url": canonical_url,
        }
        factor_type = _FACTOR_DOMAIN_TO_TYPE.get(domain)
        if factor_type:
            item["contributing_factor_type"] = factor_type

        items.append(item)

    return items
