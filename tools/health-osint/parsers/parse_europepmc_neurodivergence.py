"""
Parses Europe PMC's real public REST API for neurodivergence research —
Health OSINT source #23, added 2026-08-22 per
TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md §16 "Evidence
Metadata": capacity_interventions.evidence_strength has sat at 'unknown'
for all 30 seeded interventions since migration 0157 because nothing fed
it real evidence, and none of this platform's prior 6 health_domain
buckets cover autism/ADHD/sensory-regulation research at all.

Real source, confirmed live 2026-08-22
────────────────────────────────────────
    GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
        ?query=<terms>&format=json&resultType=core&pageSize=<n>
        &sort=P_PDATE_D desc

No API key, plain unauthenticated GET, HTTP 200, real JSON. `resultType=
core` (vs the default `lite`) was specifically checked live — it returns
`abstractText`, `journalInfo`, and `authorList`/affiliation data in the
SAME single call, which is why this source was chosen over a standalone
PubMed E-utils parser: PubMed's own API needs two calls (esearch for IDs,
then esummary/efetch for the actual title+abstract) to get equivalent
data, and this pipeline's fetch/parse contract (health_signal_ingestion.py
_fetch()) only supports one fetch per source per run. Europe PMC indexes
PubMed's own records plus preprints (bioRxiv, medRxiv, PsyArXiv, OSF) and
Crossref-registered DOIs, so this one source covers "PubMed" and most of
"Google Scholar"'s intended breadth (Scholar itself has no API and is
excluded — see HEALTH_OSINT_IMPLEMENTATION.md §4a).

Query used (built dynamically per neuro_ domain in health_source_fetch_config's
fetch_url — this module only parses whatever query was actually run):
covers autism, ADHD, AuDHD, autistic burnout, masking/camouflaging,
sensory processing, and lived-experience/qualitative autism research.
Verified live 2026-08-22 returning >100k hits combined and genuinely
current 2026 results (not stale/cached).

Classification is keyword-based over title + abstractText + journal title
+ author affiliation text, same discipline as parse_biorxiv_trending.py's
_DOMAIN_KEYWORDS table in this same directory: first match wins, ordered
most-specific-first, no ML, no fabricated confidence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

# Ordered most-specific-first — same convention as parse_biorxiv_trending.py's
# _DOMAIN_KEYWORDS. Checked in order; first match wins. Two categories
# (lived experience, AU policy) are checked ahead of the plain topic
# buckets because they're framings that can co-occur with any topic and
# are more actionable to surface distinctly (per
# HEALTH_OSINT_IMPLEMENTATION.md §3's NEURODIVERGENCE block).
_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("ndis", "medicare", "national autism strategy", "australian government",
      "department of health"), "neuro_australia_policy"),
    (("lived experience", "qualitative study", "autistic-led", "first-person account",
      "community perspective", "interview study", "phenomenological"), "neuro_lived_experience"),
    (("autistic burnout", "autism burnout", "camouflaging fatigue", "monotropic split"), "neuro_burnout"),
    (("masking", "camouflaging", "camouflage"), "neuro_masking"),
    (("sensory processing", "sensory overload", "interoception", "hypersensitivity",
      "hyposensitivity", "auditory processing", "tactile defensiveness"), "neuro_sensory"),
    (("emotional regulation", "self-regulation", "nervous system", "co-regulation",
      "stimming", "self-stimulatory"), "neuro_regulation"),
    (("executive function", "working memory", "task initiation", "cognitive flexibility",
      "task switching"), "neuro_executive_function"),
    (("employment", "workplace accommodation", "occupational participation",
      "vocational"), "neuro_work"),
    (("circadian", "insomnia", "sleep onset", "sleep disturbance"), "neuro_sleep"),
    (("occupational therapy", "psychotherapy", "medication adherence",
      "pharmacotherapy", "intervention efficacy"), "neuro_treatment"),
    (("audhd", "autism and adhd", "comorbid adhd and autism", "co-occurring adhd"), "neuro_audhd"),
    (("adhd", "attention deficit", "hyperactivity"), "neuro_adhd"),
    (("autism", "autistic", "asperger", "autism spectrum"), "neuro_autism"),
]

_DEFAULT_DOMAIN = "neuro_autism"  # only reached if the query itself matched but no keyword did


def _classify(text: str) -> str:
    t = text.lower()
    for keywords, domain in _DOMAIN_KEYWORDS:
        if any(k in t for k in keywords):
            return domain
    return _DEFAULT_DOMAIN


def _parse_date(date_str: str | None) -> str | None:
    """Europe PMC's firstPublicationDate is 'YYYY-MM-DD'; some preprint
    records only carry yearOfPublication. Fails closed (None) rather than
    fabricating a date on an unexpected shape — same discipline as
    parse_biorxiv_trending.py's _parse_date."""
    if not date_str:
        return None
    try:
        y, mo, d = date_str.split("-")
        return datetime(int(y), int(mo), int(d), tzinfo=timezone.utc).isoformat()
    except (ValueError, AttributeError):
        return None


def _affiliation_text(entry: dict) -> str:
    """Flattens every author's affiliation string into one blob for
    AU-policy keyword matching. Missing/absent on many records (Europe
    PMC does not guarantee affiliation data) — returns '' rather than
    raising, same fail-closed pattern as the rest of this parser."""
    parts: list[str] = []
    author_list = (entry.get("authorList") or {}).get("author") or []
    for a in author_list:
        for aff in (a.get("authorAffiliationDetailsList") or {}).get("authorAffiliation") or []:
            text = aff.get("affiliation")
            if text:
                parts.append(text)
    return " ".join(parts)


def parse_europepmc_neurodivergence(json_response: str) -> list[dict]:
    """
    Parse a real Europe PMC `/search?resultType=core` JSON response (see
    module docstring for the confirmed live endpoint/params).

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    published_at, canonical_url, known_unknowns.
    """
    try:
        data = json.loads(json_response)
    except (json.JSONDecodeError, TypeError):
        return []

    results = ((data.get("resultList") or {}).get("result")) or []
    if not isinstance(results, list):
        return []

    items: list[dict] = []
    for entry in results:
        if not isinstance(entry, dict):
            continue

        title = (entry.get("title") or "").strip().rstrip(".")
        if not title:
            # No usable title -> can't build a real signal, don't fabricate one.
            continue

        abstract = (entry.get("abstractText") or "").strip()
        journal = ((entry.get("journalInfo") or {}).get("journal") or {}).get("title") or ""
        affiliation = _affiliation_text(entry)
        pub_type = (entry.get("pubType") or "").lower()

        classify_text = " ".join([title, abstract[:800], journal, affiliation, pub_type])
        health_domain = _classify(classify_text)

        authors = (entry.get("authorString") or "").strip()
        description_parts = [
            f"{journal}." if journal else "",
            f"Authors: {authors[:200]}." if authors else "",
            abstract[:1200] if abstract else "(no abstract available)",
        ]
        description = " ".join(p for p in description_parts if p).strip()

        doi = (entry.get("doi") or "").strip()
        pmid = (entry.get("pmid") or "").strip()
        canonical_url = f"https://doi.org/{doi}" if doi else (
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
        )
        if not canonical_url:
            # No stable identifier -> can't dedupe reliably, skip rather
            # than risk silent duplicate accumulation.
            continue

        is_preprint = entry.get("source") == "PPR"

        items.append({
            "title": title[:500],
            "description": description[:2000],
            "signal_type": "mechanism_discovery" if is_preprint else "study_result",
            "health_domain": health_domain,
            "published_at": _parse_date(entry.get("firstPublicationDate")),
            "canonical_url": canonical_url,
            "known_unknowns": {
                "peer_reviewed": not is_preprint,
                "source_type": "preprint" if is_preprint else "published",
                "in_pubmed": entry.get("source") == "MED",
            },
        })

    return items
