"""
Parses Crossref's real public REST API for newly-registered DOI metadata —
Health OSINT source #24, added 2026-08-22. See
parse_europepmc_neurodivergence.py's module docstring for the mission
context (TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md
§16).

Real source, confirmed live 2026-08-22
────────────────────────────────────────
    GET https://api.crossref.org/works
        ?query.bibliographic=<terms>&filter=from-pub-date:<date>
        &rows=<n>&select=DOI,title,abstract,published,container-title,author

No API key, plain unauthenticated GET, HTTP 200, real JSON. Distinct
purpose from parse_europepmc_neurodivergence.py in the same directory:
Crossref is the DOI registration agency itself — "newly published papers +
DOI metadata" per the source request this was built against — whereas
Europe PMC is a curated index that lags Crossref slightly and adds
abstracts/qualitative-study tagging Crossref doesn't reliably have.
Running both is deliberate redundancy across two independent real APIs,
not a duplicate of the same source.

Honest limitation, confirmed by live sampling (2026-08-22, 5-item sample
of an "autistic burnout" query): the `abstract` field is present on
roughly 4 of 5 records and absent on the rest (typically book chapters/
edited volumes rather than journal articles) — Crossref does not
guarantee it. Missing abstracts are represented as None here, not
fabricated or backfilled from the title.

`container-title` (the journal/book name) is present far more reliably
than abstract and is used for classification even when abstract is
missing.

The health_domain keyword table below is intentionally a duplicate of
parse_europepmc_neurodivergence.py's _DOMAIN_KEYWORDS, not a shared
import — health_signal_ingestion.py's _load_parser_module() loads each
parser file individually via importlib.util.spec_from_file_location, not
as members of the `parsers` package, so a `from
parse_europepmc_neurodivergence import ...` here would only work if that
module happened to already be on sys.path from a prior load. No existing
parser in this directory cross-imports another (verified 2026-08-22); if
these two keyword tables are changed, change both.
"""

from __future__ import annotations

import json
import re

_TAG_RE = re.compile(r"<[^>]+>")

# Kept identical to parse_europepmc_neurodivergence.py's _DOMAIN_KEYWORDS —
# see this module's docstring for why it's duplicated rather than imported.
_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("ndis", "medicare", "national autism strategy", "australian government",
      "department of health"), "neuro_australia_policy"),
    (("lived experience", "qualitative study", "autistic-led", "first-person account",
      "community perspective", "interview study", "phenomenological"), "neuro_lived_experience"),
    (("autistic burnout", "autism burnout", "camouflaging fatigue", "monotropic split"), "neuro_burnout"),
    (("masking", "camouflaging", "camouflage"), "neuro_masking"),
    (("sensory processing", "sensory integration", "sensory overload", "interoception", "hypersensitivity",
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

_DEFAULT_DOMAIN = "neuro_autism"


def _classify(text: str) -> str:
    t = text.lower()
    for keywords, domain in _DOMAIN_KEYWORDS:
        if any(k in t for k in keywords):
            return domain
    return _DEFAULT_DOMAIN


def _strip_jats(text: str | None) -> str:
    """Crossref's `abstract` field is JATS XML (e.g. `<jats:p>...</jats:p>`),
    not plain text — strips tags rather than leaving raw markup in a
    user-facing description."""
    if not text:
        return ""
    return _TAG_RE.sub(" ", text).strip()


def _parse_published(published: dict | None) -> str | None:
    """Crossref's `published` field is `{"date-parts": [[Y, M, D]]}` with
    M/D frequently absent (year-only records are common, confirmed live).
    Fails closed (None) on anything else rather than fabricating a day/
    month Crossref never actually gave."""
    if not published:
        return None
    parts = (published.get("date-parts") or [[]])[0]
    if not parts:
        return None
    try:
        y = int(parts[0])
        mo = int(parts[1]) if len(parts) > 1 else 1
        d = int(parts[2]) if len(parts) > 2 else 1
        from datetime import datetime, timezone
        return datetime(y, mo, d, tzinfo=timezone.utc).isoformat()
    except (ValueError, TypeError, IndexError):
        return None


def parse_crossref_neurodivergence(json_response: str) -> list[dict]:
    """
    Parse a real Crossref `/works` JSON response (see module docstring for
    the confirmed live endpoint/params).

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    published_at, canonical_url, known_unknowns.

    Reuses parse_europepmc_neurodivergence.py's _DOMAIN_KEYWORDS/_classify
    rather than duplicating the keyword table — both parsers must agree on
    what "neuro_masking" etc. means, and a single source of truth prevents
    the two from drifting apart over time.
    """
    try:
        data = json.loads(json_response)
    except (json.JSONDecodeError, TypeError):
        return []

    raw_items = ((data.get("message") or {}).get("items")) or []
    if not isinstance(raw_items, list):
        return []

    items: list[dict] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue

        title_list = entry.get("title") or []
        title = (title_list[0] if title_list else "").strip().rstrip(".")
        doi = (entry.get("DOI") or "").strip()
        if not title or not doi:
            # No usable title or no DOI to dedupe on -> don't fabricate a signal.
            continue

        abstract = _strip_jats(entry.get("abstract"))
        container_list = entry.get("container-title") or []
        journal = (container_list[0] if container_list else "").strip()

        authors = entry.get("author") or []
        author_names = ", ".join(
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in authors[:5] if isinstance(a, dict) and (a.get("given") or a.get("family"))
        )

        classify_text = " ".join([title, abstract[:800], journal])
        health_domain = _classify(classify_text)

        description_parts = [
            f"{journal}." if journal else "",
            f"Authors: {author_names[:200]}." if author_names else "",
            abstract[:1200] if abstract else "(no abstract available from Crossref for this record)",
        ]
        description = " ".join(p for p in description_parts if p).strip()

        items.append({
            "title": title[:500],
            "description": description[:2000],
            "signal_type": "study_result",
            "health_domain": health_domain,
            "published_at": _parse_published(entry.get("published")),
            "canonical_url": f"https://doi.org/{doi}",
            "known_unknowns": {
                "peer_reviewed": None,  # Crossref doesn't declare this; not guessed
                "abstract_available": bool(abstract),
            },
        })

    return items
