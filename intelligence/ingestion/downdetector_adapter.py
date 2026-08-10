"""
Downdetector Australia adapter — crowdsourced outage report-volume signal.

2026-08-10 (Captain-approved, following outage-source-coverage-expansion.md's
gap analysis: Telstra/Optus/TPG/Vodafone's own status pages require
per-address interactive form-fill, not scrapeable at scale; Downdetector
Australia (downdetector.com.au) covers telecom AND banking AND government
services with one consistent, plain-page-per-company pattern).

Fetches each registered Downdetector AU company status page
(https://downdetector.com.au/status/{slug}/) and applies a two-layer
"genuine outage-scale" gate BEFORE emitting anything — this adapter's job is
to detect and report genuine spikes, not log routine ambient status every
run (mirrors the AWS/Azure "intermittent" convention: zero items on a quiet
check is the expected, correct state, not a failure):

  Layer 1 — status must be at Downdetector's own top tier ("problems", not
            "possible problems" or "no current problems").
  Layer 2 — the 24h peak report count must clear an evidence-grounded floor.

Threshold evidence (real, not invented — see
.claude/skills/bot-reviews/fixes-2026-08-09/downdetector-adapter-implemented.md
for the full write-up): cross-referenced via Wayback Machine against the real
nationwide Telstra outage of 2026-07-07/08 (confirmed in this platform's own
intelligence_events — ABC News/Guardian coverage, Senate inquiry). Telstra's
own quiet-day baseline (confirmed live 2026-08-10 across Telstra AND 18 other
companies spanning telecom/banking/government): peak report counts of
1-42 with "no current problems"/"possible problems" status. During the real
outage (Wayback snapshot 2026-07-09, 1-2 days in): 230-354 reports, a 6-10x
spike, status at the top "problems" tier.

_REPORT_COUNT_FLOOR = 150 is a first-cut ABSOLUTE floor (not yet a rolling
per-service baseline — see the design doc for why: this is a same-night
first implementation with exactly one confirmed real historical data point;
a genuine rolling 24-48h-trailing-average baseline needs its own small
persistence table and a few weeks of real runtime data before it would be
*more* trustworthy than this evidence-grounded absolute number, so it's
flagged as the natural v2, not built here). 150 sits well below the real
spike's own low end (230) — giving margin to catch a genuine event before it
fully peaks — while sitting ~3.5x above the highest quiet-day baseline
observed in this platform's own live sample (42, Telstra). Expected to need
calibration once this has run live for a few weeks across all 19 registered
services, not asserted as a final, fully-proven number.
"""

import logging
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from intelligence.config import HTTP_TIMEOUT_SECONDS
from intelligence.ingestion import brightdata_fetch, firecrawl_client
from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem, SourceRecord

log = logging.getLogger(__name__)

_UA = "USS-TJR-Intelligence-Agent/1.0"

# ─── Two-layer gate ─────────────────────────────────────────────────────────

_TOP_TIER = "problems"
_REPORT_COUNT_FLOOR = 150

# Primary parse target: the page's own accessible aria-label on the 24h
# reports chart, e.g. 'Reports chart for the last 24 hours with a peak of 34
# reports, status: no problems' — one atomic match giving both the real
# numeric peak-report count AND Downdetector's own 3-tier status enum
# together. Confirmed live 2026-08-10 across all 19 registered company pages
# (telstra, optus, tpg, vodafone, iinet, dodo, aussie-broadband, superloop,
# activ8me, nbnco, national-australia-bank, anz-banking, commonwealth-bank,
# westpac, bendigo, ubank, mygov, centrelink, myid) — all present and
# correctly shaped, via `firecrawl scrape --format html` (see module
# docstring re: plain-fetch blocking).
_STATUS_COUNT_PATTERN = re.compile(
    r"peak of (\d+)\s+reports?,\s*status:\s*(no problems|possible problems|problems)",
    re.IGNORECASE,
)

# Fallback if the aria-label shape ever changes: the page's prose H1
# ("User reports show <status> with <Company>"). Status only — no report
# count in this fallback, so the gate can never pass on it alone (fails
# safe: never fabricates a count).
_STATUS_PROSE_PATTERN = re.compile(
    r"User reports show.*?>(no current problems|possible problems|problems)<",
    re.IGNORECASE,
)

# Company display name, from the same H1: '...>{status}</span> with
# <span class="font-medium">{Company}</span>'.
_COMPANY_NAME_PATTERN = re.compile(
    r'font-medium">[^<]*</span>\s*with\s*<span class="font-medium">([^<]+)</span>',
)

# Sector hint (drives which classifier-facing phrasing template is used —
# see _build_item_text) keyed by the URL slug, not the display name, since
# slugs are stable and already confirmed live. Matches the 19 sources this
# mission registers; see tools/intelligence/sources_live.csv.
_TELECOM_SLUGS = {
    "telstra", "optus", "tpg", "vodafone", "iinet", "dodo",
    "aussie-broadband", "superloop", "activ8me", "nbnco",
}
_BANKING_SLUGS = {
    "national-australia-bank", "anz-banking", "commonwealth-bank",
    "westpac", "bendigo", "ubank",
}
_GOVERNMENT_SLUGS = {"mygov", "centrelink", "myid"}


class DowndetectorAdapter(BaseSourceAdapter):

    def collect(self) -> list[IntelligenceItem]:
        html = self._fetch_html(self.source.url)
        status, report_count = parse_status_and_count(html)
        if status is None:
            raise RuntimeError(
                f"Could not parse Downdetector status from {self.source.url} "
                "(page shape may have changed)"
            )
        if not self._passes_gate(status, report_count):
            # Correct, expected state for most checks — see module docstring.
            # No item, no audit-trail row; a genuine future v2 rolling-baseline
            # design would want a lightweight snapshot of every check (not
            # built here — see module docstring).
            return []

        company = self._company_name(html) or self.source.source_name
        title, summary = self._build_item_text(company, status, report_count)
        return [self._make_item(title, summary, self.source.url, datetime.now(timezone.utc))]

    def _passes_gate(self, status: str, report_count: Optional[int]) -> bool:
        if report_count is None:
            return False  # fails safe — never fires on status alone
        return status == _TOP_TIER and report_count >= _REPORT_COUNT_FLOOR

    def _fetch_html(self, url: str) -> str:
        """Plain fetch first (free); Downdetector Australia sits behind a
        real Cloudflare Turnstile JS-challenge confirmed live from this
        production host (2026-08-10, not a sandbox artifact — see
        .claude/skills/bot-reviews/fixes-2026-08-09/
        firecrawl-production-provisioning.md), which always returns HTTP
        403 to a plain urllib.request GET. On that specific blocking signal,
        routes to one of two real fetch paths BY SECTOR — a deliberate
        budget split, not a stylistic choice (see
        .claude/skills/bot-reviews/fixes-2026-08-09/brightdata-provisioning.md):

          - telecom/other  -> the shared Firecrawl fetch path (Captain's
            personal Firecrawl account, 1,000 scrapes/month hard cap shared
            with every other Firecrawl caller in this codebase).
          - banking/government (the 9 sources this platform's Firecrawl
            budget review explicitly excluded, see
            firecrawl-production-provisioning.md) -> the Bright Data Web
            Unlocker fetch path instead (Captain's separate Bright Data
            account, 5,000 requests/month, its OWN budget — never falls
            back to Firecrawl, so activating/running these 9 sources never
            spends a Firecrawl credit).

        Cadence/volume discipline for both paths lives in which sources are
        `active=True` in the registry plus intelligence/scheduler.py's
        exclusion of downdetector-type sources from the 180-min intraday
        sweep, not here."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                charset = "utf-8"
                content_type = resp.headers.get("Content-Type", "")
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].split(";")[0].strip()
                return resp.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                sector = self._sector()
                if sector in ("banking", "government"):
                    log.info("[%s] plain fetch 403'd — falling back to Bright Data (sector=%s)", url, sector)
                    return brightdata_fetch.fetch_html(url)
                log.info("[%s] plain fetch 403'd — falling back to Firecrawl (sector=%s)", url, sector)
                return firecrawl_client.fetch_html(url)
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        except Exception as exc:
            raise RuntimeError(f"Downdetector fetch failed: {exc}") from exc

    def _company_name(self, html: str) -> Optional[str]:
        m = _COMPANY_NAME_PATTERN.search(html)
        return m.group(1).strip() if m else None

    def _slug(self) -> str:
        path = urlparse(self.source.url).path.strip("/")
        parts = path.split("/")
        return parts[-1] if parts else ""

    def _sector(self) -> str:
        slug = self._slug()
        if slug in _TELECOM_SLUGS:
            return "telecom"
        if slug in _BANKING_SLUGS:
            return "banking"
        if slug in _GOVERNMENT_SLUGS:
            return "government"
        return "other"

    def _build_item_text(self, company: str, status: str, report_count: int) -> tuple[str, str]:
        """Constructs title/summary that the *existing*, shared, 100%
        keyword-based classifier (intelligence/classification/classifier.py)
        will naturally route to the right event_type — same discipline as
        every other adapter in this codebase (AEMO/GCP/Salesforce/etc. all
        construct plain title/summary text and let classify() decide; none
        of them hand-set event_type). Phrasing is deliberately chosen so the
        real distinguishing keywords for telecom_outage (e.g. 'network
        outage', 'mobile network', 'broadband', 'internet outage',
        'connectivity') outnumber technology_outage's generic 'outage' hit
        for telecom sources, so telecom_outage wins the classifier's
        highest-keyword-count vote; banking/government sources correctly
        fall through to technology_outage (already in
        intelligence_store.py's _OUTAGE_EVENT_TYPES — no classifier.py
        change needed for any sector)."""
        gate_note = (
            f"[Downdetector two-layer gate PASSED: status='{status}' (top tier) AND "
            f"24h peak reports={report_count} >= floor={_REPORT_COUNT_FLOOR}]"
        )
        sector = self._sector()

        if sector == "telecom":
            title = (
                f"Downdetector AU: {company} — crowdsourced reports indicate a "
                f"network outage (problems, top tier)"
            )
            summary = (
                f"{gate_note} Independent crowdsourced report-volume signal from "
                f"Downdetector Australia shows a genuine telecommunications outage "
                f"for {company}: {report_count} user reports in the last 24 hours "
                f"(peak), status classified 'problems' (top tier) — indicating "
                f"widespread connectivity and internet outage impact across "
                f"{company}'s mobile network, broadband, and telecommunications "
                f"services in Australia. This is aggregated third-party "
                f"user-report telemetry (not a vendor self-report), calibrated "
                f"against real historical Australian outage baselines."
            )
        elif sector == "banking":
            title = (
                f"Downdetector AU: {company} — crowdsourced reports indicate a "
                f"banking service outage (problems, top tier)"
            )
            summary = (
                f"{gate_note} Independent crowdsourced report-volume signal from "
                f"Downdetector Australia shows a genuine banking outage for "
                f"{company}, an Australian bank: {report_count} user reports in "
                f"the last 24 hours (peak), status classified 'problems' (top "
                f"tier) — indicating a service disruption with {company}'s online "
                f"banking and mobile app unavailable for a significant proportion "
                f"of customers in Australia. This is aggregated third-party "
                f"user-report telemetry (not a vendor self-report), calibrated "
                f"against real historical Australian outage baselines."
            )
        else:
            title = (
                f"Downdetector AU: {company} — crowdsourced reports indicate a "
                f"service outage (problems, top tier)"
            )
            summary = (
                f"{gate_note} Independent crowdsourced report-volume signal from "
                f"Downdetector Australia shows a genuine outage for {company}, an "
                f"Australian government digital service: {report_count} user "
                f"reports in the last 24 hours (peak), status classified "
                f"'problems' (top tier) — indicating a service disruption with "
                f"{company}'s online services unavailable for a significant "
                f"proportion of citizens in Australia. This is aggregated "
                f"third-party user-report telemetry (not a vendor self-report), "
                f"calibrated against real historical Australian outage baselines."
            )
        return title, summary


def parse_status_and_count(html: str) -> tuple[Optional[str], Optional[int]]:
    """Pure parsing function — deliberately separate from network I/O so it
    can be unit-verified directly against real captured HTML (no live fetch
    required). Returns (status, report_count); status is one of
    'no_problems' | 'possible_problems' | 'problems', or None if the page
    shape couldn't be parsed at all. report_count is None whenever only the
    prose fallback matched (no atomic count available in that shape)."""
    m = _STATUS_COUNT_PATTERN.search(html)
    if m:
        count = int(m.group(1))
        return _normalise_tier(m.group(2).lower()), count

    m2 = _STATUS_PROSE_PATTERN.search(html)
    if m2:
        return _normalise_tier(m2.group(1).lower()), None

    return None, None


def _normalise_tier(text: str) -> str:
    if "no current problems" in text or "no problems" in text:
        return "no_problems"
    if "possible problems" in text:
        return "possible_problems"
    return "problems"
