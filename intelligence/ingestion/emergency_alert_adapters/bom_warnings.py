"""Bureau of Meteorology — state/territory warnings (migration 0176).

Real, confirmed live 2026-08-27: one plain public RSS feed per state at
bom.gov.au/rss/ — https://www.bom.gov.au/fwo/IDZ000{54..60,85}.warnings_
{state}.xml. Requires a browser-shaped User-Agent (bare urllib default is
403'd — same class of block as core/notifications/resend_email.py's
Cloudflare finding, different vendor).

Deliberately sparse feed — confirmed live, only title/link/pubDate/guid
per item, no severity/lat-lon/description fields at all (unlike every
other adapter in this package). Two real signals ARE extractable from the
title text, both BOM's own product-naming convention (not a guess):
  - alert_type, from the product name itself ("Flood Warning", "Severe
    Weather Warning", "Fire Weather Warning", "Tropical Cyclone Warning",
    "Tsunami Warning", "Severe Thunderstorm Warning" -> 'storm').
  - closed, from a "Final " prefix BOM adds when cancelling/superseding a
    warning (same closure-signal class as sa_cfs.py's Status: COMPLETE).

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
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .base import CanonicalAlert, http_get, stable_event_key

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
    ("SEVERE THUNDERSTORM", "storm"),
    ("SEVERE WEATHER", "severe_weather"),
    ("DAMAGING WIND", "storm"),
    ("GALE", "storm"),
    ("STORM", "storm"),
)

_EXCLUDED_KEYWORDS = ("FROST", "SHEEP GRAZIERS", "MARINE")

_TITLE_RE = re.compile(r"^\d{2}/\d{2}:\d{2}\s+\w+\s+(.*)$")


def _http_get_bom(url: str) -> bytes:
    # base.http_get always sends a plain custom User-Agent, which BOM's
    # front end 403s — confirmed live 2026-08-27 — so this adapter needs
    # its own browser-shaped one rather than the shared default.
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def _fetch_state(jurisdiction: str) -> list[CanonicalAlert]:
    source_key, url = _STATE_FEEDS[jurisdiction]
    raw = _http_get_bom(url)
    root = ET.fromstring(raw)
    out: list[CanonicalAlert] = []

    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        guid_el = item.find("guid")

        title = title_el.text.strip() if title_el is not None and title_el.text else "—"
        title_upper = title.upper()

        if any(kw in title_upper for kw in _EXCLUDED_KEYWORDS):
            continue

        alert_type = next((v for kw, v in _TYPE_KEYWORDS if kw in title_upper), None)
        if alert_type is None:
            continue

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

        out.append(CanonicalAlert(
            source_key=source_key,
            jurisdiction=jurisdiction,
            headline=headline,
            event_key=guid or link or stable_event_key(jurisdiction, headline),
            alert_type=alert_type,
            severity="unknown",  # see module docstring — no AWS-tier data in this feed
            description=None,
            location=None,  # not present as its own field; only embedded in free-text headline
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
            # The real per-item link is preserved here (not lost) even
            # though it can't be the DB's canonical_url — see the comment
            # above.
            raw_text=f"{title}\n{link}" if link else title,
            closed=closed,
        ))
    return out


class _StateAdapter:
    """Thin per-state adapter object matching the `.fetch()` interface
    intelligence/emergency_alerts.py expects — one BOM module serves all 8
    jurisdictions rather than 8 near-identical files."""

    def __init__(self, jurisdiction: str):
        self._jurisdiction = jurisdiction

    def fetch(self) -> list[CanonicalAlert]:
        return _fetch_state(self._jurisdiction)


nsw = _StateAdapter("NSW")
nt = _StateAdapter("NT")
qld = _StateAdapter("QLD")
sa = _StateAdapter("SA")
tas = _StateAdapter("TAS")
vic = _StateAdapter("VIC")
wa = _StateAdapter("WA")
act = _StateAdapter("ACT")
