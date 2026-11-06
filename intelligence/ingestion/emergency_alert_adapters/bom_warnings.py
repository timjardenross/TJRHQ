"""Bureau of Meteorology — state/territory warnings (migration 0176).

Real, confirmed live 2026-08-27: one plain public RSS feed per state at
bom.gov.au/rss/ — https://www.bom.gov.au/fwo/IDZ000{54..60,85}.warnings_
{state}.xml. Requires a browser-shaped User-Agent (bare urllib default is
403'd — same class of block as core/notifications/resend_email.py's
Cloudflare finding, different vendor).

Deliberately sparse RSS feed — confirmed live, only title/link/pubDate/
guid per item, no severity/lat-lon/description fields at all (unlike
every other adapter in this package). Two real signals ARE extractable
from the title text, both BOM's own product-naming convention (not a
guess):
  - alert_type, from the product name itself ("Flood Warning", "Severe
    Weather Warning", "Fire Weather Warning", "Tropical Cyclone Warning",
    "Tsunami Warning", "Severe Thunderstorm Warning" -> 'storm').
  - closed, from a "Final " prefix BOM adds when cancelling/superseding a
    warning (same closure-signal class as sa_cfs.py's Status: COMPLETE).

Detail-page fetch (2026-08-27, Captain: "bring more of the content of the
warning across"): each item's <link> is a real BOM bulletin page with a
clean semantic `<div id="content">...<!-- End: Content --></div class="product">`
region — confirmed live: product ID, real issue timestamp ("Issued at
9:34 am AEST on Thursday 27 August 2026" — a genuinely more precise source
than the RSS pubDate, parsed into issued_at below), the full warning body
text, and a safety-advice list. Fetched once per alert per run and cached
in-process for the run's duration (module-level dict, cleared on process
restart) so re-fetching a still-open warning across consecutive 15-minute
runs doesn't re-hit BOM's server for unchanged content — keyed by link,
invalidated whenever the RSS item's pubDate changes (a real update).
River-height tables are stripped (noisy tabular data, not the warning
text itself); everything else in the product body is kept.

severity stays 'unknown' for every BOM alert — there is no AWS-tier
(Advice/Watch and Act/Emergency Warning) data in this feed, and BOM's own
intensity words for floods (Minor/Moderate/Major) are a different scale
that doesn't map cleanly onto AWS tiers; inventing that mapping would
misrepresent BOM's actual warning level. Real, documented gap, not an
oversight — same honesty standard already applied to vic_emergency.py.

Excludes (same discard discipline as every other source in this hub):
Frost Warning and Sheep Graziers Warning (agricultural, not public
emergency), Marine Wind Warning (mariner-specific, out of this hub's
land-based public-emergency scope), and any product name that doesn't
match a real kept category — never guessed into a bucket.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET  # nosec B314 - defused parser, safe against XXE/entity-expansion on external feed XML

from . import bom_cap
from .base import (
    CanonicalAlert,
    DropLedger,
    convert_items,
    require_rss_channel,
    stable_event_key,
)

log = logging.getLogger(__name__)

_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# jurisdiction -> (source_key, feed URL) — from migration 0176's alert_sources seed.
_STATE_FEEDS: dict[str, tuple[str, str]] = {
    "NSW": ("bom_nsw", "https://www.bom.gov.au/fwo/IDZ00054.warnings_nsw.xml"),
    "NT":  ("bom_nt",  "https://www.bom.gov.au/fwo/IDZ00055.warnings_nt.xml"),
    "QLD": ("bom_qld", "https://www.bom.gov.au/fwo/IDZ00056.warnings_qld.xml"),
    "SA":  ("bom_sa",  "https://www.bom.gov.au/fwo/IDZ00057.warnings_sa.xml"),
    "TAS": ("bom_tas", "https://www.bom.gov.au/fwo/IDZ00058.warnings_tas.xml"),
    "VIC": ("bom_vic", "https://www.bom.gov.au/fwo/IDZ00059.warnings_vic.xml"),
    "WA":  ("bom_wa",  "https://www.bom.gov.au/fwo/IDZ00060.warnings_wa.xml"),
    "ACT": ("bom_act", "https://www.bom.gov.au/fwo/IDZ00085.warnings_act.xml"),
}

# Product-name substring -> alert_type. Checked in order; first match wins.
_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("FLOOD", "flood"),
    ("FIRE WEATHER", "bushfire"),
    ("TROPICAL CYCLONE", "cyclone"),
    ("TSUNAMI", "tsunami"),
    ("HEATWAVE", "heatwave"),
    ("SEVERE THUNDERSTORM", "storm"),
    ("SEVERE WEATHER", "severe_weather"),
    ("DAMAGING WIND", "storm"),
    ("GALE", "storm"),
    ("STORM", "storm"),
)

_EXCLUDED_KEYWORDS = ("FROST", "SHEEP GRAZIERS", "MARINE")

SOURCE_INFO = {
    "source_key": "bom_*",
    "source_keys": [key for key, _url in _STATE_FEEDS.values()],
    "jurisdiction": "NSW, NT, QLD, SA, TAS, VIC, WA, ACT (one feed each)",
    "feed_urls": [url for _key, url in _STATE_FEEDS.values()] + [bom_cap._INDEX_URL],
    "format": "RSS 2.0 per state, plus one HTML bulletin page per item (detail); CAP-AU 1.2 messages from the WMO alert hub index as an enrichment (event, urgency, certainty, severity)",
    "fixture_dir": "tests/fixtures/emergency_alerts/bom_nsw",
    "severity_field": "none - the BOM feed carries no AWS tier (always 'unknown')",
    "severity_map": None,
    "alert_type_rule": "product name in the title, first match: FLOOD -> flood; FIRE WEATHER -> bushfire; TROPICAL CYCLONE -> cyclone; TSUNAMI -> tsunami; SEVERE THUNDERSTORM / DAMAGING WIND / GALE / STORM -> storm; SEVERE WEATHER -> severe_weather; HEATWAVE -> heatwave (Captain-approved 2026-11-06, as WA already did; BOM does not state a level in the title, so these stay severity 'unknown' at standard attention).",
    "exclusions": [
        {"reason": "excluded_agricultural", "field": "title", "match": "contains FROST or SHEEP GRAZIERS", "decided": "adapter rule 2026-08-27 (agricultural, not public emergency)"},
        {"reason": "excluded_marine", "field": "title", "match": "contains MARINE", "decided": "adapter rule 2026-08-27 (mariner-specific, out of land-based scope)"},
        {"reason": "excluded_unmatched_product", "field": "title", "match": "no product keyword matches (e.g. Hazardous Surf Warning)", "decided": "adapter rule 2026-08-27 ('never guessed into a bucket')"},
    ],
    "invalid_reasons": [],
    "stale_after_hours": None,
    "expected_fields": ['updated_at_src'],
    "known_gaps": [
        "No AWS tier (Advice / Watch and Act / Emergency Warning) exists in BOM's feed, so every BOM row is severity 'unknown'; BOM's own flood intensity words (Minor / Moderate / Major) are a different scale and are not mapped. High-attention emails use the platform's own bom_attention label.",
        "Products whose name matches no keyword are dropped (counted excluded_unmatched_product), so a NEW BOM warning product is invisible until a keyword is added.",
        "Needs a browser-shaped User-Agent (BOM 403s the shared default); detail pages are best-effort and fall back to a title-only alert.",
        "The detail-page 'Issued at' line varies by state (AEST, bare EST/EDT, long 'Australian Eastern Daylight Time', trailing full stop, or no timezone at all on bom_wa); fixed 2026-11-06 after 57 of 91 stored rows had issued_at NULL. A line with no timezone is read as the state's local time: a constant offset for states without daylight saving (WA +8, QLD +10, NT +9:30) and the IANA zone for NSW/ACT (Sydney), VIC (Melbourne), SA (Adelaide) and TAS (Hobart), so the daylight-saving offset for that date is applied (before 2026-11-06 these lines were left NULL; the 15 stored rows were backfilled that day and each lands 0-1 minute before its RSS pubDate). emergency_alerts._issued_text still reads the stored text as a fallback.",
        "CAP fields (cap_event / cap_urgency / cap_certainty / cap_severity) come from the WMO mirror of BoM's CAP-AU stream (bom_cap.py), matched to each RSS alert by warning type plus location words, or by a unique same-type message sent within 90 s of the RSS pubDate for the same state. The RSS items and bulletin pages carry no product code, so the match is conservative: ambiguous or unmatched alerts keep no CAP fields (18 of 24 non-marine items matched when measured 2026-11-06, none wrongly; unmatched were older QLD flood warnings beyond the index's ~8-day window). BoM CAP severity is a different scale from our tier and is never used for it; urgency and certainty are often 'Unknown'. Measured 2026-11-06: 120 of 120 sampled CAP messages validate against the OASIS CAP 1.2 XSD and 115 of 120 against the CAP-AU v3.0 XSD (the 5 are Bushwalkers Weather Alerts whose <event> 'Exposure' is outside the CAP-AU event list); fixtures are checked in tests/test_cap_schema_conformance.py. There are no polygons (BoM area codes only). Personal-use only (BoM's RSS terms limit reuse); set EMERGENCY_ALERTS_BOM_CAP=0 to switch the enrichment off. An outage keeps the RSS-only alerts and logs a warning (no FIELD DRIFT check, since coverage is partial by design).",
        "BOM cross-lists some border-river warnings in neighbouring states' feeds, so one product can appear under two source_keys (canonical_url is left empty to avoid the unique-index clash).",
    ],
    "last_verified": "2026-08-27",
}

_TITLE_RE = re.compile(r"^\d{2}/\d{2}:\d{2}\s+\w+\s+(.*)$")


def _http_get_bom(url: str) -> bytes:
    # base.http_get always sends a plain custom User-Agent, which BOM's
    # front end 403s — confirmed live 2026-08-27 — so this adapter needs
    # its own browser-shaped one rather than the shared default.
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 - url is this adapter's own fixed BOM feed constant, not user input
        return resp.read()


_CONTENT_RE = re.compile(r'<div id="content">(.*?)<!-- End: Content -->', re.DOTALL)
_ISSUED_RE = re.compile(r"Issued at\s+(.+?)\s*</p>", re.DOTALL)
_TAG_BREAK_RE = re.compile(r"</(p|h1|h2|h3|h4|li|tr)>", re.IGNORECASE)
_TABLE_RE = re.compile(r"<table.*?</table>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n{3,}")

# link -> (pubdate_raw seen when fetched, extracted {issued_at, body}).
# Process-lifetime cache so an unchanged, still-open warning isn't
# re-fetched from BOM's server every 15-minute run — see module docstring.
_detail_cache: dict[str, tuple[str, dict]] = {}


# Fixed UTC offsets for the timezone words BOM prints in "Issued at ..." lines.
# Observed in production (2026-11-06, bom_* rows): the AEST/AEDT family, the
# bare "EST"/"EDT" BOM uses for the Eastern states (NSW/ACT/VIC/TAS bulletins),
# and the long form "Australian Eastern Daylight Time". In this feed EST/EDT
# mean Australian Eastern Standard/Daylight time (UTC+10/+11), not US Eastern.
# Both standard and daylight names are handled whatever the season, so a
# bulletin is never read with the wrong offset. Anything not listed is left
# unparsed (None) rather than guessed.
_TZ_OFFSETS = {
    "AEST": timedelta(hours=10), "AEDT": timedelta(hours=11),
    "EST": timedelta(hours=10), "EDT": timedelta(hours=11),
    "ACST": timedelta(hours=9, minutes=30), "ACDT": timedelta(hours=10, minutes=30),
    "CST": timedelta(hours=9, minutes=30), "CDT": timedelta(hours=10, minutes=30),
    "AWST": timedelta(hours=8), "WST": timedelta(hours=8),
}
_AU_TZ_OFFSETS = _TZ_OFFSETS  # old name, kept for compatibility

_TZ_LONG_NAMES = {
    "AUSTRALIAN EASTERN STANDARD TIME": "AEST", "AUSTRALIAN EASTERN DAYLIGHT TIME": "AEDT",
    "AUSTRALIAN CENTRAL STANDARD TIME": "ACST", "AUSTRALIAN CENTRAL DAYLIGHT TIME": "ACDT",
    "AUSTRALIAN WESTERN STANDARD TIME": "AWST",
}

# When the line carries NO timezone at all (seen on bom_wa: "Issued at 2:42 pm
# Friday, 6 November 2026."), the time is the state's local time. Only states
# WITHOUT daylight saving get a default, because their offset is a constant and
# needs no season guess; every other state stays unparsed (None) as before.
_FIXED_STATE_OFFSETS = {
    "WA": timedelta(hours=8),
    "QLD": timedelta(hours=10),
    "NT": timedelta(hours=9, minutes=30),
}

# States WITH daylight saving: a no-timezone line is the state's local time, and the zone
# database picks the right offset for that date (measured 2026-11-06: all 15 stored rows of
# this kind land 0-1 minute before the RSS pubDate when read this way, in both DST seasons).
# NSW and ACT share Sydney's rules. Without zone data on the host the issue time stays
# unparsed (None); an offset-less timestamp would be stored as UTC.
_DST_STATE_ZONES = {
    "NSW": "Australia/Sydney", "ACT": "Australia/Sydney", "VIC": "Australia/Melbourne",
    "SA": "Australia/Adelaide", "TAS": "Australia/Hobart",
}


def _issued_in_state_zone(issued_local: str, jurisdiction: str) -> str | None:
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.fromisoformat(issued_local).replace(tzinfo=ZoneInfo(_DST_STATE_ZONES[jurisdiction])).isoformat()
    except Exception as exc:  # noqa: BLE001 - missing tzdata must not break ingestion; the issue time just stays unparsed
        log.warning("[bom_warnings] timezone data unavailable for %s (%s): issued_at left unparsed", jurisdiction, type(exc).__name__)
        return None

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_ISSUED_PARTS_RE = re.compile(
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>[ap]m)\b(?P<middle>.*?)"
    r"\b(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})",
    re.IGNORECASE | re.DOTALL,
)
_TZ_ABBR_RE = re.compile(r"\b(" + "|".join(sorted(_TZ_OFFSETS, key=len, reverse=True)) + r")\b")


def _parse_issued(text: str) -> tuple[str | None, str | None]:
    """BOM's "Issued at ..." line -> (offset-aware ISO string | None, naive local ISO string | None).

    Wordings seen in production (2026-11-06), all handled:
      "Issued at 9:34 am AEST on Thursday 27 August 2026"
      "Issued at 4:08 pm EDT on Friday 6 November 2026."        (trailing full stop)
      "Issued at 11:51 am Australian Eastern Daylight Time on Friday 6 November 2026"
      "Issued at 2:42 pm Friday, 6 November 2026."              (no timezone: WA)
    The first value is set only when the line names a timezone BOM prints; the second
    is the same wall-clock time with no offset, for the caller to resolve from the
    state when the line has none. Bug history: stripping a timezone without applying
    its offset once stored local time as UTC (10 h off, 2026-08-27)."""
    m = _ISSUED_RE.search(text)
    if not m:
        return None, None
    raw = re.sub(r"\s+", " ", _TAG_RE.sub(" ", m.group(1))).strip()
    parts = _ISSUED_PARTS_RE.search(raw)
    if not parts:
        return None, None
    month = _MONTHS.get(parts["month"].lower())
    if month is None:
        return None, None
    hour = int(parts["hour"])
    if not 1 <= hour <= 12:
        return None, None
    hour = hour % 12 + (12 if parts["ampm"].lower() == "pm" else 0)
    try:
        from datetime import datetime
        naive = datetime(int(parts["year"]), month, int(parts["day"]), hour, int(parts["minute"]))  # noqa: DTZ001 - offset applied explicitly below, or the caller resolves a fixed-offset state
    except ValueError:
        return None, None
    middle = parts["middle"].upper()
    tz_word = next((abbr for long_name, abbr in _TZ_LONG_NAMES.items() if long_name in middle), None)
    if tz_word is None:
        found = _TZ_ABBR_RE.search(middle)
        tz_word = found.group(1) if found else None
    if tz_word is None:
        return None, naive.isoformat()
    return naive.replace(tzinfo=timezone(_TZ_OFFSETS[tz_word])).isoformat(), naive.isoformat()


def _parse_bom_issued_at(text: str) -> str | None:
    """Offset-aware issue time from BOM's "Issued at ..." line, or None when it names no
    timezone (see _parse_issued; the per-state default is applied by the caller)."""
    return _parse_issued(text)[0]


def parse_detail(html: str) -> dict:
    """Pure parse of a BOM bulletin page -> {"issued_at", "issued_local", "body"}:
    issued_at is offset-aware when the line names a timezone; issued_local is the same
    wall-clock time without an offset, for states whose line has none (see _parse_issued).
    Separate from _fetch_detail() so it can be tested against a page fixture."""
    m = _CONTENT_RE.search(html)
    if not m:
        return {"issued_at": None, "issued_local": None, "body": None}
    content_html = _TABLE_RE.sub("", m.group(1))
    issued_at, issued_local = _parse_issued(content_html)
    text = _TAG_BREAK_RE.sub("\n", content_html)
    text = _TAG_RE.sub("", text)
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&lt;", "<").replace("&gt;", ">"))
    text = _BLANK_LINES_RE.sub("\n\n", text).strip()
    return {"issued_at": issued_at, "issued_local": issued_local, "body": text or None}


def _fetch_detail(link: str, pubdate_raw: str) -> dict:
    """Returns {"issued_at", "issued_local", "body"} (see parse_detail). Never raises —
    the detail page is an enrichment, not a requirement; the RSS title
    alone is still a usable alert if this fails."""
    cached = _detail_cache.get(link)
    if cached and cached[0] == pubdate_raw:
        return cached[1]

    try:
        result = parse_detail(_http_get_bom(link).decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 - best-effort detail-page fetch, already logged; caller falls back to the documented {issued_at: None, body: None} shape
        log.warning("[bom_warnings] detail fetch failed for %s: %s", link, exc)
        result = {"issued_at": None, "issued_local": None, "body": None}

    _detail_cache[link] = (pubdate_raw, result)
    return result


def _fetch_state(jurisdiction: str, ledger: DropLedger | None = None) -> list[CanonicalAlert]:
    _source_key, url = _STATE_FEEDS[jurisdiction]
    alerts = parse_state_feed(jurisdiction, _http_get_bom(url), detail_for=_fetch_detail, ledger=ledger)
    bom_cap.enrich(alerts, jurisdiction)  # best effort: CAP fields only; never changes which alerts exist or their tier
    return alerts


# keyword -> drop-ledger reason for _EXCLUDED_KEYWORDS (frost and sheep
# graziers are both agricultural products). First match wins.
_EXCLUDED_REASONS = (
    ("FROST", "agricultural"),
    ("SHEEP GRAZIERS", "agricultural"),
    ("MARINE", "marine"),
)


def parse_state_feed(jurisdiction: str, raw: bytes, detail_for=None, ledger: DropLedger | None = None) -> list[CanonicalAlert]:
    """Pure parse of one state's warnings RSS. `detail_for(link, pubdate_raw)`
    returns the {"issued_at", "body"} dict for an item's bulletin page; the
    live path passes _fetch_detail (network, cached). None means title-only
    alerts, which is also what a failed detail fetch degrades to. Passing a
    ledger records every skipped item and makes one malformed item count as
    invalid_unparseable_item instead of failing the parse."""
    guard = ledger is not None
    ledger = ledger if ledger is not None else DropLedger()
    source_key, _url = _STATE_FEEDS[jurisdiction]
    root = ET.fromstring(raw)
    require_rss_channel(root, source_key, guard)
    return convert_items(root.findall(".//item"), lambda item: _to_alert(item, source_key, jurisdiction, detail_for, ledger), ledger, guard)


def _to_alert(item, source_key: str, jurisdiction: str, detail_for, ledger: DropLedger) -> CanonicalAlert | None:
    title_el = item.find("title")
    link_el = item.find("link")
    pubdate_el = item.find("pubDate")
    guid_el = item.find("guid")

    title = title_el.text.strip() if title_el is not None and title_el.text else "—"
    title_upper = title.upper()
    if pubdate_el is not None and pubdate_el.text:
        try:
            ledger.observe(parsedate_to_datetime(pubdate_el.text.strip()))
        except (TypeError, ValueError):
            pass

    excluded = next((reason for kw, reason in _EXCLUDED_REASONS if kw in title_upper), None)
    if excluded:
        ledger.exclude(excluded, sample=title)
        return None

    alert_type = next((v for kw, v in _TYPE_KEYWORDS if kw in title_upper), None)
    if alert_type is None:
        # Deliberate, per the module docstring: "any product name that
        # doesn't match a real kept category — never guessed into a bucket".
        # (Live 2026-11: Hazardous Surf Warning lands here.)
        # Name the product (title minus BOM's time prefix, up to " for <area>") so a NEW
        # BOM warning type shows up in the heartbeat as an unmapped product, not just
        # as an anonymous count.
        flat = re.sub(r"\s+", " ", title).strip()
        prefix = _TITLE_RE.match(flat)
        product = (prefix.group(1) if prefix else flat).split(" for ")[0][:60]
        ledger.exclude("unmatched_product", sample=flat)
        ledger.unmapped(f"product {product}")
        return None

    # Collapse embedded whitespace/newlines first (confirmed live: some
    # states, e.g. WA, wrap the title across lines) — needed before the
    # timestamp-prefix regex, which otherwise fails to match and leaves
    # the raw multi-line mess as the headline.
    title_flat = re.sub(r"\s+", " ", title).strip()

    # Strip BOM's "DD/HH:MM TZ " time prefix for a cleaner headline —
    # the real issue timestamp is already carried in pubDate. Not every
    # item has the prefix (confirmed live: ACT's items sometimes don't).
    m = _TITLE_RE.match(title_flat)
    headline = m.group(1) if m else title_flat

    # "Final " is BOM's own cancel/supersede marker — must be checked
    # on the prefix-stripped headline (confirmed live: checking the raw
    # title missed every NSW item, since "Final" sits after the time
    # prefix, not at the very start).
    closed = headline.upper().startswith("FINAL ")

    updated_at_src = None
    if pubdate_el is not None and pubdate_el.text:
        try:
            updated_at_src = parsedate_to_datetime(pubdate_el.text.strip()).isoformat()
        except (TypeError, ValueError):
            pass

    link = link_el.text.strip() if link_el is not None and link_el.text else None
    guid = guid_el.text.strip() if guid_el is not None and guid_el.text else None
    pubdate_raw = pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else ""

    # Real warning body text from the detail page (Captain: "bring
    # more of the content of the warning across") — see module
    # docstring and _fetch_detail. Best-effort: a failed detail fetch
    # still leaves a usable, title-only alert.
    detail = detail_for(link, pubdate_raw) if (link and detail_for) else {"issued_at": None, "body": None}
    issued_at = detail["issued_at"]
    if issued_at is None and detail.get("issued_local") and jurisdiction in _FIXED_STATE_OFFSETS:
        # The line named no timezone: use the state's constant (no-DST) offset.
        from datetime import datetime
        issued_at = datetime.fromisoformat(detail["issued_local"]).replace(tzinfo=timezone(_FIXED_STATE_OFFSETS[jurisdiction])).isoformat()
    elif issued_at is None and detail.get("issued_local") and jurisdiction in _DST_STATE_ZONES:
        issued_at = _issued_in_state_zone(detail["issued_local"], jurisdiction)

    return CanonicalAlert(
        source_key=source_key,
        jurisdiction=jurisdiction,
        headline=headline,
        event_key=guid or link or stable_event_key(jurisdiction, headline),
        alert_type=alert_type,
        severity="unknown",  # see module docstring — no AWS-tier data in this feed
        description=detail["body"],
        location=None,  # not present as its own field; only embedded in free-text headline
        issued_at=issued_at,
        updated_at_src=updated_at_src,
        # Not canonical_url: confirmed live (2026-08-27, bom_vic/bom_act
        # 409s) that BOM cross-lists the same warning link across
        # neighbouring jurisdictions' feeds for border rivers (e.g. the
        # Tumut River warning appears identically in both the NSW and
        # ACT feeds) — a genuinely shared URL across two different
        # source_keys, which collides with alerts.idx_alerts_canonical_url
        # (global unique). Same fix as qld_fire.py/sa_cfs.py's shared-URL
        # case; dedupe here relies on (source_key, event_key) only.
        canonical_url=None,
        # Full warning body when the detail fetch succeeded, else just
        # the title + link (the real per-item link is preserved here
        # either way — it can't be the DB's canonical_url, see above).
        raw_text=(detail["body"] + f"\n\n{link}") if detail["body"] else (f"{title}\n{link}" if link else title),
        closed=closed,
    )


class _StateAdapter:
    """Thin per-state adapter object matching the `.fetch()` interface
    intelligence/emergency_alerts.py expects — one BOM module serves all 8
    jurisdictions rather than 8 near-identical files."""

    SOURCE_INFO = SOURCE_INFO  # shared by all 8 states (expected_fields etc.)

    def __init__(self, jurisdiction: str):
        self._jurisdiction = jurisdiction

    def fetch(self) -> list[CanonicalAlert]:
        return _fetch_state(self._jurisdiction)

    def fetch_with_ledger(self) -> tuple[list[CanonicalAlert], DropLedger]:
        """fetch() plus an account of every item skipped, and why (see base.DropLedger)."""
        ledger = DropLedger()
        return _fetch_state(self._jurisdiction, ledger), ledger


nsw = _StateAdapter("NSW")
nt = _StateAdapter("NT")
qld = _StateAdapter("QLD")
sa = _StateAdapter("SA")
tas = _StateAdapter("TAS")
vic = _StateAdapter("VIC")
wa = _StateAdapter("WA")
act = _StateAdapter("ACT")
