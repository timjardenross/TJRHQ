"""
Parses ScienceDaily's real public RSS feed for autism/neurodivergence
research journalism — Health OSINT source #25, added 2026-08-22. See
parse_europepmc_neurodivergence.py's module docstring for the mission
context.

Real source, confirmed live 2026-08-22
────────────────────────────────────────
    GET https://www.sciencedaily.com/rss/mind_brain/autism.xml

No API key, plain unauthenticated GET, HTTP 200, real RSS 2.0 XML (not
scraped HTML) — this is ScienceDaily's own topic feed, the same kind of
real structured feed this codebase already prefers over scraping
elsewhere (see parse_who_alerts.py's docstring on GitHub Status/Google
Cloud Status's migration from RSS to real APIs — here the direction runs
the other way: RSS *is* the real structured source ScienceDaily actually
publishes for this topic, there being no richer API).

Honest scope: this is research-journalism (secondary reporting on
studies), not primary literature — lower evidentiary weight than
parse_europepmc_neurodivergence.py/parse_crossref_neurodivergence.py.
signal_type is fixed to 'efficacy_claim' would be wrong (that implies a
promotional claim); used 'study_result' is also wrong (it's not the
primary paper). Neither existing signal_type cleanly fits "someone
reported on a study" — 'mechanism_discovery' is the closest existing
value's intent (new finding reported) and is what's used here, same
disclosed-imperfect-fit discipline as parse_biorxiv_trending.py's
'general_biomedical' fallback.

Domain classification reuses the same keyword table as the other three
2026-08-22 neurodivergence parsers (duplicated per-file, not imported —
see parse_crossref_neurodivergence.py's docstring for why).
"""

from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_TAG_RE = re.compile(r"<[^>]+>")
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)

# Kept identical to parse_europepmc_neurodivergence.py's _DOMAIN_KEYWORDS —
# see parse_crossref_neurodivergence.py's docstring for why it's
# duplicated per-file rather than imported.
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

_DEFAULT_DOMAIN = "neuro_autism"  # feed is already autism-scoped by URL


def _classify(text: str) -> str:
    t = text.lower()
    for keywords, domain in _DOMAIN_KEYWORDS:
        if any(k in t for k in keywords):
            return domain
    return _DEFAULT_DOMAIN


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _html.unescape(_TAG_RE.sub(" ", text)).replace("\xa0", " ").strip()


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _field(block: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.DOTALL)
    return match.group(1).strip() if match else None


def _strip_cdata(text: str | None) -> str | None:
    if text is None:
        return None
    m = re.match(r"^\s*<!\[CDATA\[(.*)\]\]>\s*$", text, re.DOTALL)
    return m.group(1) if m else text


def _parse_pubdate(pub_date: str | None) -> str | None:
    """RSS pubDate is RFC 2822 (e.g. 'Fri, 21 Aug 2026 08:28:15 EDT').
    Fails closed (None) on anything unparseable rather than guessing."""
    if not pub_date:
        return None
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def parse_sciencedaily_neurodivergence(xml_response: str) -> list[dict]:
    """
    Parse ScienceDaily's real autism-topic RSS 2.0 feed (see module
    docstring for the confirmed live URL). Uses regex rather than an XML
    parser deliberately — RSS item bodies routinely contain unescaped
    ampersands and stray markup that trip strict XML parsers on real feeds
    (confirmed live 2026-08-22 on this exact feed); item/field extraction
    here is line-oriented and fails closed per-field, matching
    parse_who_alerts.py's "never guess on malformed input" discipline.

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    published_at, canonical_url, known_unknowns.
    """
    items: list[dict] = []
    for block in _ITEM_RE.findall(xml_response or ""):
        title = _collapse_ws(_strip_html(_strip_cdata(_field(block, "title"))))
        if not title:
            continue

        link = _strip_cdata(_field(block, "link"))
        if not link:
            # No canonical URL -> can't dedupe reliably, skip.
            continue

        description = _collapse_ws(_strip_html(_strip_cdata(_field(block, "description"))))
        pub_date = _field(block, "pubDate")

        classify_text = " ".join([title, description[:800]])
        health_domain = _classify(classify_text)

        items.append({
            "title": title[:500],
            "description": description[:2000] if description else None,
            "signal_type": "mechanism_discovery",
            "health_domain": health_domain,
            "published_at": _parse_pubdate(pub_date),
            "canonical_url": link.strip(),
            "known_unknowns": {
                "source_form": "research_journalism",
                "peer_reviewed": None,
            },
        })

    return items
