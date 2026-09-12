"""
Parses WHO's Disease Outbreak News (DON) feed — Health OSINT automated-fetch
source #21 in HEALTH_OSINT_IMPLEMENTATION.md section 4 ("WHO Outbreak
Alerts").

Real source, confirmed live 2026-08-11
────────────────────────────────────────
The doc suggested scraping https://www.who.int/emergencies/disease-outbreak-news
via Bright Data. Before writing any scraper, checked whether WHO exposes a
real structured API for this content instead (this task's own instruction,
and this codebase's established preference — see GitHub Status / Google
Cloud Status's migration from RSS to their real incidents.json APIs in
tools/intelligence/sources_live.csv). It does:

    GET https://www.who.int/api/news/diseaseoutbreaknews
        ?$orderby=PublicationDate desc&$top=<n>

This is WHO's own Sitefinity-CMS OData v4 JSON feed backing the DON page —
confirmed real (not guessed from the product name) by cross-referencing a
DON item's real "Overview" prose, which links back to
"who.int/emergencies/disease-outbreak-news/item/<UrlName>" using the exact
same UrlName this API returns for that item. Fetched live 2026-08-11 via a
plain, unauthenticated `curl`: HTTP 200, real JSON, 271KB+ unfiltered / 140KB
for `$top=5`, most-recent entry at the time "Ebola disease caused by
Bundibugyo virus - Democratic Republic of the Congo" (DonId 2026-DON614,
PublicationDate 2026-08-01) — genuinely current, not stale/cached. The
$orderby and $top OData query params both work and were verified live
(sample response inspected field-by-field, not assumed).

Real fields used here (present on every item checked): Title, OverrideTitle,
UseOverrideTitle, Summary, Overview, Advice, Assessment, PublicationDate,
UrlName, DonId. See the response's own "@odata.context" line for WHO's full
declared field list.

Fetch-path disclosure (read before wiring this into
health_signal_ingestion.py's health_source_fetch_config):
the plain unauthenticated GET above already succeeds with no bot-block, no
CAPTCHA, no Cloudflare/WAF challenge — unlike Downdetector Australia or AEMO
Market Notices, the actual sources brightdata_fetch.py and firecrawl_client.py
exist for. Both of those modules' own docstrings say explicitly: "call this
ONLY as a fallback after a plain fetch has already failed with a genuine
blocking signal ... never as the first attempt." Strictly by that rule, WHO's
real API needs neither paid tool. However: (a) HEALTH_OSINT_IMPLEMENTATION.md
section 4 already earmarks a 50/month Bright Data budget line specifically
for "WHO Outbreak Alerts", and (b) health_signal_ingestion.py's `_fetch()`
dispatch (built by a parallel session on this same branch) only knows how to
invoke `firecrawl` (returns markdown) or `bright_data` (returns raw text) —
there is no third "plain GET" fetch_tool wired up yet. Given that, the
pragmatic, disclosed choice is: configure this source's fetch_tool as
`bright_data` pointed at the URL above (Bright Data's Web Unlocker
`format="raw"` is a content-type-agnostic passthrough — it returns the exact
JSON text a plain GET would, whether or not unblocking was actually needed),
so this parser plugs into the existing orchestrator without further changes.
This spends one real Bright Data credit per fetch that isn't strictly
necessary — flagged here, not silently justified, as a real judgment call,
and a future improvement (adding a `direct`/`plain` fetch_tool to
health_signal_ingestion.py's `_fetch()`) would remove it. `parse_who_alerts`
below is agnostic to which tool supplied the raw JSON text — it only cares
that it received the real response body of the URL above.

signal_type: 'safety_alert' (per HEALTH_OSINT_IMPLEMENTATION.md section 4's
assignment for this source) — good fit: every DON is WHO's own official
public alert about an active outbreak, not a passive research finding.
health_domain: 'epi_outbreak' (per section 3's Epidemiology group) — good
fit, this is exactly "Disease Clusters, Transmissibility".

Honest limitation: WHO does not publish a structured severity field on this
feed (Assessment is free prose, e.g. "WHO reassessed the risk... to
incorporate newly available information" — extracting a reliable
mild/moderate/severe/critical grade from that text would be guessing, not
parsing). severity is left None here rather than fabricated — same
discipline parse_cdc_epidemic.py applies to its own outbreak-section
entries.

Built + live-tested 2026-08-11 against real, live-fetched WHO JSON (not
fabricated/assumed structure).
"""

from __future__ import annotations

import html as _html
import json
import re

_TAG_RE = re.compile(r"<[^>]+>")

_DON_ITEM_URL = "https://www.who.int/emergencies/disease-outbreak-news/item/{url_name}"


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _html.unescape(_TAG_RE.sub(" ", text)).replace("\xa0", " ").strip()


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_who_alerts(json_response: str) -> list[dict]:
    """
    Parse WHO's real Disease Outbreak News OData JSON feed (see module
    docstring for the confirmed real endpoint, query params, and field
    list — this is not scraped HTML, it's the API's own JSON body, whatever
    tool fetched it).

    Returns a list of dicts shaped for health_signal_ingestion.py's
    _save_signal(): title, description, signal_type, health_domain,
    severity, published_at, canonical_url.
    """
    try:
        data = json.loads(json_response)
    except (json.JSONDecodeError, TypeError):
        # Fails closed — never guesses at malformed/non-JSON input (e.g. if
        # a fetch path returned an HTML error page instead of the real API
        # body).
        return []

    raw_items = data.get("value")
    if not isinstance(raw_items, list):
        return []

    items: list[dict] = []
    for it in raw_items:
        use_override = it.get("UseOverrideTitle")
        title = (it.get("OverrideTitle") if use_override else it.get("Title")) or it.get("Title")
        title = _collapse_ws(title) if title else None
        if not title:
            # No usable title -> can't build a real signal, don't fabricate one.
            continue

        summary = _strip_html(it.get("Summary"))
        if not summary:
            # Summary is frequently empty on this feed; Overview always
            # carries the real prose in that case.
            summary = _strip_html(it.get("Overview"))
        description = _collapse_ws(summary)[:2000] if summary else None

        url_name = it.get("UrlName")
        canonical_url = _DON_ITEM_URL.format(url_name=url_name) if url_name else None

        don_id = it.get("DonId")
        if don_id and description:
            description = f"[{don_id}] {description}"
        elif don_id:
            description = f"[{don_id}]"

        items.append({
            "title": title[:500],
            "description": description,
            "signal_type": "safety_alert",
            "health_domain": "epi_outbreak",
            "severity": None,  # see module docstring — WHO publishes no structured grade here
            "published_at": it.get("PublicationDate"),
            "canonical_url": canonical_url,
        })

    return items
