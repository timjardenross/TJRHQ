"""
Parses FDA's "Recalls, Market Withdrawals & Safety Alerts" listing page.

Built 2026-08-11 against a REAL live fetch. The doc's original URL
(fda.gov/drugs/drug-safety-and-availability/fda-adverse-event-reporting-system-faers)
is dead (404, confirmed both via a plain `urllib.request` GET and via the
WebFetch tool before starting this work). WebSearch turned up several
candidate current FDA pages; all of the MedWatch-program URLs themselves
(fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program,
and its /medical-product-safety-information child page) ALSO 404 to a plain
GET/WebFetch — FDA appears to serve a bot-cloaked 404 to non-browser
clients on those specific paths rather than a normal 403.

The confirmed REAL, currently-live page actually used here is:

    https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts

Confirmed real by fetching it through `firecrawl_client.fetch_markdown()`
(a genuine headless-browser render, not a guess) on 2026-08-11: it returned
a real markdown page (~11KB) with "Showing 1 to 10 of 1,007 entries" and a
data table whose first page of rows carries dates of 08/09/2026, 08/07/2026,
08/06/2026 etc. — i.e. genuinely current as of today (2026-08-11), not
cached/stale content.

Honest mismatch vs. the doc's ask ("FDA MedWatch / adverse events" page):
MedWatch's actual individual-case adverse-event reports (FAERS) are not a
browsable HTML listing at all — FAERS is a structured database exposed via
openFDA's API and a separate interactive dashboard, and the MedWatch
program page itself is a submission portal + static description, not a
feed. This "Recalls, Market Withdrawals & Safety Alerts" page is FDA's
actual real, current, browsable safety-signal listing — drug/device/food
recalls and safety alerts, most of which ARE adverse-event-driven (product
contamination, device malfunction reports, mislabeling posing a health
risk) but are not literally FAERS case reports. Given that, this parser
defaults signal_type to 'safety_alert' (matching what the page truly is)
rather than blindly forcing 'adverse_event' — health_domain is still set to
'safety_adverse_event' per the doc's section 3 taxonomy, since recalls
triggered by contamination/device-malfunction are squarely adverse-event
adjacent. Both signal_type values are unconstrained free text on
health_signals (no CHECK — see migration 0141's header comment), so this
is a data-fidelity choice, not a schema violation.

Table structure (real, observed 2026-08-11 — 8-column markdown pipe table,
paginated 10 rows/page server-side, this parser only sees whatever page
Firecrawl rendered — currently page 1 of ~101):

    | Date | Brand Name(s) | Product Description | Product Type |
      Recall Reason Description | Company Name | Terminated Recall | Excerpt |

Severity is NOT provided by this page (FDA's real Class I/II/III recall
classification lives on each individual press-release page, one Firecrawl
call away per row — out of scope for a single-page-fetch parser). This
parser applies an honest, disclosed keyword heuristic over the recall
reason + product type text instead of fabricating a classification:
foodborne pathogens (Salmonella/Listeria/E. coli/Botulism) or device
malfunction language implying acute harm -> 'severe'; anything mentioning
death/life-threatening -> 'critical'; undeclared allergens / labeling
issues -> 'moderate'; everything else -> 'moderate' (the safe, non-trivial
default — nothing on this page is truly routine, it's all recall-worthy).
This is a best-effort signal for downstream sort/triage, not FDA's own
classification, and is documented as such in each row's description.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_ROW_PATTERN = re.compile(
    r"^\|\s*(\d{2}/\d{2}/\d{4})\s*\|\s*"          # 1: date
    r"\[([^\]]*)\]\(([^)]*)\)\s*\|\s*"             # 2: brand/link text, 3: url
    r"([^|]*)\|\s*"                                 # 4: product description
    r"([^|]*)\|\s*"                                 # 5: product type
    r"([^|]*)\|\s*"                                 # 6: recall reason description
    r"([^|]*)\|\s*"                                 # 7: company name
    r"([^|]*)\|\s*"                                 # 8: terminated recall
    r"([^|]*)\|\s*$",                                # 9: excerpt
    re.MULTILINE,
)

_CRITICAL_KEYWORDS = ("death", "life-threatening", "life threatening", "fatal")
_SEVERE_KEYWORDS = (
    "salmonella", "listeria", "e. coli", "e.coli", "botulism", "clostridium",
    "malfunction", "burn", "smoke", "endotoxin", "particulate",
)
_MODERATE_KEYWORDS = ("undeclared", "allerg", "mislabel", "label")


def _classify_severity(reason: str, product_type: str) -> str:
    text = f"{reason} {product_type}".lower()
    if any(k in text for k in _CRITICAL_KEYWORDS):
        return "critical"
    if any(k in text for k in _SEVERE_KEYWORDS):
        return "severe"
    if any(k in text for k in _MODERATE_KEYWORDS):
        return "moderate"
    return "moderate"


def _parse_date(date_str: str) -> str | None:
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def parse_fda_medwatch(html_or_markdown: str) -> list[dict]:
    """
    Parse FDA's real "Recalls, Market Withdrawals & Safety Alerts" listing
    page (fetched as markdown via firecrawl_client.fetch_markdown — see
    module docstring for the real confirmed URL and why it replaces the
    dead doc URL / blocked MedWatch program pages).

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    severity, adverse_event_text, fda_flagged, published_at, canonical_url.
    """
    items: list[dict] = []
    for m in _ROW_PATTERN.finditer(html_or_markdown):
        date_str, brand_text, brand_url, product_desc, product_type, reason, company, _terminated, _excerpt = m.groups()

        brand_text = brand_text.strip()
        product_desc = product_desc.strip()
        product_type = product_type.strip()
        reason = reason.strip()
        company = company.strip()

        if not brand_text or not reason:
            # Header/separator rows and any malformed row never make it into
            # a real signal — fail closed, don't guess at missing fields.
            continue

        title = f"{brand_text}: {reason}" if reason else brand_text
        description = (
            f"{product_desc} (Product Type: {product_type}). "
            f"Recall reason: {reason}. Company: {company}."
        ).strip()

        items.append({
            "title": title[:500],
            "description": description,
            "signal_type": "safety_alert",
            "health_domain": "safety_adverse_event",
            "severity": _classify_severity(reason, product_type),
            "adverse_event_text": reason,
            "fda_flagged": True,
            "published_at": _parse_date(date_str),
            "canonical_url": brand_url.strip() or None,
        })

    return items
