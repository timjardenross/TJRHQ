"""
Parses Europe PMC's real public REST API for chronic pain research —
Health OSINT source #27, added 2026-08-27 per Captain-directed priority
work: of the 7 research areas the Captain named as personally important
(Mental Health, ADHD, Autism, AUDHD, Chronic Pain, Supplement,
Performance), Chronic Pain was the one with zero coverage anywhere in
this platform — confirmed live: no existing source or health_domain tag
touches it at all.

Reuses the exact same real, already-proven endpoint the neurodivergence
sources use (see parse_europepmc_neurodivergence.py's module docstring
for the full case for Europe PMC over PubMed E-utils/Google Scholar) —
same JSON shape, same fetch/parse contract, only the search query and
domain classifier differ. Confirmed live 2026-08-27:

    GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
        ?query=(TITLE:"chronic pain" OR ABSTRACT:"chronic pain" OR
                TITLE:fibromyalgia OR ABSTRACT:fibromyalgia OR
                TITLE:"central sensitization" OR ABSTRACT:"central sensitization" OR
                TITLE:"neuropathic pain" OR ABSTRACT:"neuropathic pain")
        &format=json&resultType=core&pageSize=25&sort=P_PDATE_D desc

Field-restricted (TITLE:/ABSTRACT:) for the same reason migration 0160's
neurodivergence query is — an earlier free-text version would let Europe
PMC's synonym expansion pull in unrelated hits. Verified live 2026-08-27:
110,091 hits, current 2026 results, overwhelmingly on-topic (occasional
tangential hit — e.g. an aromatherapy/diabetes quality-of-life study that
matched a co-occurring pain-management term — is exactly the residual
noise class the curation LLM already filters for every other source, not
something to over-engineer the query against).

Classification is keyword-based, same discipline as
parse_europepmc_neurodivergence.py's _DOMAIN_KEYWORDS table — first match
wins, most-specific-first, no ML, no fabricated confidence. New chronic_pain_*
health_domain values (free-text, no CHECK constraint, migration 0141) — see
tools/health-osint/priority_domains.py, which needs its own follow-up once
these are live to confirm the exact tag names match (see that module's own
docstring for why Chronic Pain isn't in PRIORITY_DOMAINS yet).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

# Ordered most-specific-first — same convention as
# parse_europepmc_neurodivergence.py's _DOMAIN_KEYWORDS.
_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("lived experience", "qualitative study", "patient-led", "first-person account",
      "community perspective", "interview study", "phenomenological"), "chronic_pain_lived_experience"),
    (("central sensitization", "central sensitisation", "nociplastic"), "chronic_pain_central_sensitization"),
    (("fibromyalgia",), "chronic_pain_fibromyalgia"),
    (("neuropathic pain", "neuropathy", "nerve injury", "diabetic neuropathy"), "chronic_pain_neuropathic"),
    (("opioid", "buprenorphine", "analgesic", "nsaid", "pharmacotherapy",
      "medication adherence"), "chronic_pain_medication"),
    (("physical therapy", "physiotherapy", "exercise therapy", "pacing",
      "graded exposure", "cognitive behavioral therapy", "cbt"), "chronic_pain_treatment"),
    (("flare", "flare-up", "symptom fluctuation", "pain diary"), "chronic_pain_flare"),
]

_DEFAULT_DOMAIN = "chronic_pain"  # only reached if the query itself matched but no keyword did


def _classify(text: str) -> str:
    t = text.lower()
    for keywords, domain in _DOMAIN_KEYWORDS:
        if any(k in t for k in keywords):
            return domain
    return _DEFAULT_DOMAIN


def _parse_date(date_str: str | None) -> str | None:
    """Same fail-closed discipline as parse_europepmc_neurodivergence.py's
    _parse_date — never fabricates a date on an unexpected shape."""
    if not date_str:
        return None
    try:
        y, mo, d = date_str.split("-")
        return datetime(int(y), int(mo), int(d), tzinfo=timezone.utc).isoformat()
    except (ValueError, AttributeError):
        return None


def _affiliation_text(entry: dict) -> str:
    """Same as parse_europepmc_neurodivergence.py's _affiliation_text —
    flattens author affiliations for classification context; returns ''
    rather than raising when absent."""
    parts: list[str] = []
    author_list = (entry.get("authorList") or {}).get("author") or []
    for a in author_list:
        for aff in (a.get("authorAffiliationDetailsList") or {}).get("authorAffiliation") or []:
            text = aff.get("affiliation")
            if text:
                parts.append(text)
    return " ".join(parts)


def parse_europepmc_chronic_pain(json_response: str) -> list[dict]:
    """
    Parse a real Europe PMC `/search?resultType=core` JSON response (see
    module docstring for the confirmed live endpoint/params).

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    published_at, canonical_url, known_unknowns. Identical shape to
    parse_europepmc_neurodivergence.py's return value — same source API,
    same downstream contract.
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
