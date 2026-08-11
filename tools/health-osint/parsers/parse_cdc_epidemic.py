"""
Parses CDC's "Current Outbreak List" page.

Built 2026-08-11 against a REAL live fetch. The doc's original URL
(cdc.gov/coronavirus/2019-ncov/index.html) is COVID-era and, while it still
technically resolves (it shows up as a live link INSIDE the page this
parser now uses, filed under "U.S. Outbreaks" dated "Jan 2020" — i.e. it's
real but years stale, exactly the staleness this mission flagged), it is
not a page listing current epidemiological signals — it's a single
disease's landing page.

WebSearch surfaced CDC's actual current outbreak index. Confirmed real by
fetching it through `firecrawl_client.fetch_markdown()` (both a plain
`urllib.request` GET and the WebFetch tool were blocked with HTTP 403 on
this URL — a genuine bot block, not a dead page — so this went through the
Firecrawl fallback path exactly as this codebase's other adapters do, e.g.
downdetector_adapter.py):

    https://www.cdc.gov/outbreaks/index.html

Fetched 2026-08-11: real, current page (~6.7KB markdown), titled "CDC
Current Outbreak List", with entries dated as recently as "Aug 2026" —
genuinely current as of today, not stale/cached content. Structure
(observed directly, not assumed):

  ## U.S. Outbreaks
  [_Salmonella_ Outbreak Linked to Jalapeños](url)

  Aug 2026

  [...next entry...]
  ...

  ## International Outbreaks
  [Ebola](url)

  May 2026
  ...

  ## International Travel Health Notices
  [Level 2 - Zika in Indonesia](url)

  Aug 2026
  ...

Each entry is a markdown link followed (after one or two blank lines) by a
"Mon YYYY" string — no day-of-month is given anywhere on this index page,
so published_at is set to the 1st of that month/year and this is
disclosed as month-level precision, not fabricated day-level precision.

This parser emits two signal_type values depending on which real section
an entry came from — not a single forced value — because the page itself
distinguishes them:

  - "U.S. Outbreaks" / "International Outbreaks" entries -> signal_type
    'outbreak' (per the doc's section 3 taxonomy), health_domain
    'epi_outbreak'.
  - "International Travel Health Notices" entries -> signal_type
    'safety_alert' (these are graded travel advisories — "Level 1-4" —
    not outbreak-cluster reports themselves), health_domain 'epi_outbreak'
    still (they're outbreak-driven advisories, e.g. "Level 3 - Ebola ...
    Congo"). Severity is derived directly from the real "Level N" prefix
    CDC itself publishes on these notices (Level 1=mild advisory ...
    Level 4=avoid nonessential travel=critical) — not a guessed heuristic.

Honest limitation: this index page gives no case counts, death counts, or
transmissibility data for the "Outbreaks" sections (that detail lives one
click deeper, on each outbreak's own page — out of scope for a
single-page-fetch parser) — severity is therefore left as None for those
two sections rather than fabricated. Only the Travel Health Notices
entries get a real, page-sourced severity.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_ENTRY_PATTERN = re.compile(
    r"\[([^\]]+)\]\(([^)]+)\)\s*\n\s*\n\s*(?:\n\s*)?"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})"
)

_SECTION_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

_LEVEL_SEVERITY = {
    "1": "mild",
    "2": "moderate",
    "3": "severe",
    "4": "critical",
}
_LEVEL_PREFIX = re.compile(r"^Level\s+(\d)\b", re.IGNORECASE)


def _month_year_to_iso(mon: str, year: str) -> str:
    dt = datetime(int(year), _MONTHS[mon], 1, tzinfo=timezone.utc)
    return dt.isoformat()


def _sections(markdown: str) -> dict[str, str]:
    """Split the page into {heading text: section body} using the real
    '## ' headings CDC's page uses, so each entry can be attributed to the
    real section it actually appeared under rather than guessed."""
    headings = list(_SECTION_PATTERN.finditer(markdown))
    sections: dict[str, str] = {}
    for i, h in enumerate(headings):
        start = h.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        sections[h.group(1).strip()] = markdown[start:end]
    return sections


def parse_cdc_epidemic(html_or_markdown: str) -> list[dict]:
    """
    Parse CDC's real "Current Outbreak List" page (fetched as markdown via
    firecrawl_client.fetch_markdown — see module docstring for the real
    confirmed URL, why it replaces the stale doc URL, and the real section
    structure this regex is built from).

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    severity, published_at, canonical_url.
    """
    sections = _sections(html_or_markdown)
    items: list[dict] = []

    for heading, is_outbreak_section in (
        ("U.S. Outbreaks", True),
        ("International Outbreaks", True),
        ("International Travel Health Notices", False),
    ):
        body = sections.get(heading)
        if not body:
            continue

        for m in _ENTRY_PATTERN.finditer(body):
            title_text, url, mon, year = m.groups()
            title_text = title_text.strip().replace("_", "")  # strip markdown italics markers
            if title_text.lower() == "view all":
                continue

            published_at = _month_year_to_iso(mon, year)

            if is_outbreak_section:
                signal_type = "outbreak"
                severity = None
                description = (
                    f"CDC Current Outbreak List — {heading} entry: "
                    f"\"{title_text}\", listed as of {mon} {year}. "
                    f"(Index page only — no case/death counts on this page; "
                    f"see canonical_url for CDC's full outbreak page.)"
                )
            else:
                signal_type = "safety_alert"
                level_m = _LEVEL_PREFIX.match(title_text)
                severity = _LEVEL_SEVERITY.get(level_m.group(1)) if level_m else None
                description = (
                    f"CDC International Travel Health Notice: \"{title_text}\", "
                    f"issued {mon} {year}. Severity derived from CDC's own "
                    f"published advisory level in the title."
                )

            items.append({
                "title": title_text[:500],
                "description": description,
                "signal_type": signal_type,
                "health_domain": "epi_outbreak",
                "severity": severity,
                "published_at": published_at,
                "canonical_url": url.strip() or None,
            })

    return items
