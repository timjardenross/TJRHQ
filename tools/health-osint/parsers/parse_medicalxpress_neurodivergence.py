"""
Parses Medical Xpress's real public RSS search feed for neurodivergence
research journalism — Health OSINT source #26, added 2026-08-22. See
parse_europepmc_neurodivergence.py's module docstring for the mission
context.

Real source, confirmed live 2026-08-22
────────────────────────────────────────
    GET https://medicalxpress.com/rss-feed/search/?search=autism+OR+adhd+OR+neurodivergent

No API key. Plain unauthenticated GET returns a 400 (WAF block, confirmed
live) with no User-Agent header; the exact same request with
`User-Agent: USS-TJR-Health-OSINT-Agent/1.0` (this pipeline's real UA,
already sent by health_signal_ingestion.py's `_direct_get()`) returns
HTTP 200 with real RSS 2.0 XML, 30 items, genuinely current 2026 content
mixing autism/ADHD/dyslexia coverage — confirmed by title inspection, not
assumed. Same feed format as parse_sciencedaily_neurodivergence.py's
source, so this parser reuses its exact regex-based item/field extraction
approach (RSS bodies here also carry unescaped ampersands on real items,
same reason a strict XML parser was avoided there).

Unlike ScienceDaily's autism-only feed, this source's search query is
already broadened to autism+ADHD+neurodivergent, so classification here
is not pre-scoped — the full keyword table decides the domain per item,
with `neuro_autism` as the honest fallback (not `neuro_adhd`, since the
underlying feed skews autism-heavier in real sampling).
"""

from __future__ import annotations

import html as _html
import re
from datetime import timezone
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

_DEFAULT_DOMAIN = "neuro_autism"


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
    if not pub_date:
        return None
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def parse_medicalxpress_neurodivergence(xml_response: str) -> list[dict]:
    """
    Parse Medical Xpress's real search-RSS feed (see module docstring for
    the confirmed live URL/UA requirement).

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
