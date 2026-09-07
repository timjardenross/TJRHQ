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

150 was this adapter's original first-cut ABSOLUTE floor, applied
identically to every sector. 2026-08-10 (Captain-directed follow-up, see
.claude/skills/bot-reviews/fixes-2026-08-09/cadence-tiering-and-learned-threshold.md):
that flat constant is now replaced by a PER-SOURCE, LLM-learned threshold
(migration 0121, `downdetector_learned_thresholds`) — Chief Engineer's
review (Finding 4) confirmed banking/government quiet-day baselines run
5-10x lower in absolute terms than telecom's, so one telecom-derived number
risked being too high to ever fire for a genuine, proportionally severe
bank/government outage. See `intelligence/ingestion/downdetector_thresholds.py`
for the full bootstrap -> LLM-learned pipeline (cold-start sector defaults,
the nightly recompute job, and the sanity guard on the LLM's recommendation)
and `intelligence/scheduler.py::_downdetector_threshold_recompute_job` for
where it runs. `get_report_count_floor()` below is what `_passes_gate()`
now calls instead of a flat module constant — it reads the current
per-source value (short-TTL cached), falling back to the same sector
bootstrap default the recompute job itself uses whenever no learned value
exists yet for a source.

2026-08-10 (coverage expansion round 2, see
.claude/skills/bot-reviews/fixes-2026-08-09/downdetector-coverage-expansion-round2.md):
added a fourth sector, `energy` (Origin Energy, AGL, EnergyAustralia — real,
live-confirmed Downdetector AU pages; Alinta Energy checked and confirmed
absent under the same slug convention). Energy retailers route to the
Bright Data fetch path (like banking/government), not Firecrawl — a
budget-health choice: Firecrawl's committed volume is comparatively tight,
Bright Data's has far more real headroom. `downdetector_baseline_history`'s
`sector` CHECK constraint was widened (migration 0136) to allow `'energy'`.

Every real fetch (not just ones that pass the gate) now also logs its
parsed (status, report_count) to `downdetector_baseline_history` — see
`_log_observation()` in `collect()` below — which is the real data the
nightly recompute job learns from. The original Telstra evidence this
module was first calibrated against (2026-07-07/08 real outage: 230-354
peak reports vs. a 1-42 quiet baseline, confirmed via Wayback Machine
against ABC News/Guardian coverage and this platform's own
intelligence_events) still anchors telecom's own bootstrap default (150,
unchanged) — see downdetector_thresholds.py's own module docstring for the
banking/government interim defaults and why they differ.
"""

import logging
import re
import time
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

# Diagnostic-only, for a total parse failure (neither pattern above matched):
# the page <title> is often the single most telling thing in a block/
# challenge page ('Just a moment...', 'Attention Required! | Cloudflare',
# 'Access Denied') that a plain "page shape may have changed" error can't
# distinguish from a genuine Downdetector layout change.
_TITLE_PATTERN = re.compile(r"<title[^>]*>([^<]*)</title>", re.IGNORECASE)

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

# 2026-08-10 (coverage expansion round 2, see
# .claude/skills/bot-reviews/fixes-2026-08-09/downdetector-coverage-expansion-round2.md):
# Australian energy retailers. Confirmed live via a real Bright Data
# Web Unlocker fetch (the same fetch path these sources use in production,
# not a guess) against real Downdetector AU pages -- all 3 return a real
# company-name match and a real parsed status/report-count aria-label, not
# Downdetector's own "page not found" page. Note the slug convention here is
# ONE WORD, no hyphen (unlike telecom/banking's hyphenated slugs) --
# confirmed by testing both shapes; "origin-energy"/"agl"/"agl-energy" all
# 404, "originenergy"/"aglenergy" are real. Alinta Energy was checked twice
# under the same convention ("alintaenergy") and consistently returned
# Downdetector's real "page not found" page (not a timeout, not a guess) --
# genuinely absent, not just untested; smaller retailers (Red Energy, Simply
# Energy, Momentum Energy, Powershop) were not conclusively resolved
# (network timeouts against a couple of slug guesses) and are not registered
# here -- not asked for by name, not conclusively confirmed either way.
_ENERGY_SLUGS = {"originenergy", "aglenergy", "energyaustralia"}


def slug_from_url(url: str) -> str:
    """Shared with downdetector_thresholds.py's recompute job so both the
    live gate and the nightly recompute agree on sector classification for
    a given registry row, without the recompute job reaching into this
    adapter's private per-instance methods."""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    return parts[-1] if parts else ""


def sector_for_slug(slug: str) -> str:
    if slug in _TELECOM_SLUGS:
        return "telecom"
    if slug in _BANKING_SLUGS:
        return "banking"
    if slug in _GOVERNMENT_SLUGS:
        return "government"
    if slug in _ENERGY_SLUGS:
        return "energy"
    return "other"


# ─── Per-source learned threshold lookup (migration 0121) ─────────────────
# Short-TTL in-process cache: the 6 tiered-cadence priority sources (see
# intelligence/scheduler.py::_priority_tiered_collection_job) can now be
# checked up to ~12x/day, so a live Supabase round trip on every single
# gate check would be wasteful — one bulk read, refreshed at most every
# _THRESHOLD_CACHE_TTL_SECONDS, is enough (the underlying value only ever
# changes once/night, via the recompute job).
_THRESHOLD_CACHE_TTL_SECONDS = 600
_threshold_cache: dict[str, dict] = {}
_threshold_cache_loaded_at: float = 0.0


def _refresh_threshold_cache() -> None:
    global _threshold_cache, _threshold_cache_loaded_at
    from intelligence.persistence import intelligence_store as store
    try:
        _threshold_cache = store.load_all_downdetector_thresholds()
    except Exception as exc:
        log.warning(
            "[downdetector] threshold cache refresh failed, keeping previous "
            "cache (%d source(s)): %s", len(_threshold_cache), exc,
        )
    finally:
        _threshold_cache_loaded_at = time.monotonic()


def get_report_count_floor(source_name: str, sector: str) -> int:
    """Replaces the old flat _REPORT_COUNT_FLOOR=150 constant. Reads the
    current per-source learned/bootstrap threshold (downdetector_learned_thresholds,
    short-TTL cached); falls back to the sector bootstrap default — the same
    one downdetector_thresholds.py's recompute job itself uses for
    cold-start sources — whenever no row exists yet for this source, or the
    cache can't be refreshed. Never raises, never blocks a real fetch on a
    Supabase read."""
    from intelligence.ingestion.downdetector_thresholds import bootstrap_default

    if time.monotonic() - _threshold_cache_loaded_at > _THRESHOLD_CACHE_TTL_SECONDS:
        _refresh_threshold_cache()

    row = _threshold_cache.get(source_name)
    if row and row.get("threshold_value"):
        return int(row["threshold_value"])
    return bootstrap_default(sector)


class DowndetectorAdapter(BaseSourceAdapter):

    def collect(self) -> list[IntelligenceItem]:
        html = self._fetch_html(self.source.url)
        status, report_count = parse_status_and_count(html)
        if status is None:
            raise RuntimeError(
                f"Could not parse Downdetector status from {self.source.url} "
                "(page shape may have changed) -- "
                f"{_diagnostic_snippet(html)}"
            )
        if report_count is None:
            # 2026-08-13: only the prose fallback matched — no atomic report
            # count available. _passes_gate() below always fails without a
            # count, indistinguishable in the logs from a genuinely quiet
            # day ("ok, 0 items") unless flagged here. If this fires
            # consistently for a source, its page shape likely changed and
            # the primary _STATUS_COUNT_PATTERN needs updating.
            log.warning(
                "[%s] parsed status via prose fallback only (no report count) — "
                "page shape may have drifted from the primary pattern",
                self.source.source_name,
            )

        # Every real fetch logs here — migration 0121's
        # downdetector_baseline_history, the accumulation ledger the nightly
        # recompute job (downdetector_thresholds.py) learns a per-source
        # threshold from. Deliberately unconditional (not just gate-passing
        # checks) — see that module's docstring for why.
        self._log_observation(status, report_count)

        if not self._passes_gate(status, report_count):
            # Correct, expected state for most checks — see module docstring.
            # No item, no push-alert audit-trail row (the observation above
            # is the audit trail now — see migration 0121).
            return []

        company = self._company_name(html) or self.source.source_name
        title, summary = self._build_item_text(company, status, report_count)
        return [self._make_item(title, summary, self.source.url, datetime.now(timezone.utc))]

    def _log_observation(self, status: str, report_count: Optional[int]) -> None:
        try:
            from intelligence.persistence import intelligence_store as store
            store.save_downdetector_observation(
                source_name=self.source.source_name,
                sector=self._sector(),
                status=status,
                report_count=report_count,
            )
        except Exception as exc:
            # Best-effort — a logging failure must never break real collection.
            log.warning(
                "[%s] failed to log baseline observation: %s",
                self.source.source_name, exc,
            )

    def _passes_gate(self, status: str, report_count: Optional[int]) -> bool:
        if report_count is None:
            return False  # fails safe — never fires on status alone
        floor = get_report_count_floor(self.source.source_name, self._sector())
        return status == _TOP_TIER and report_count >= floor

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
            with every other Firecrawl caller in this codebase). Committed
            volume here is real and comparatively tight (744/month against
            an 850 ceiling as of the 2026-08-10 coverage-expansion-round2
            headroom check) — see that report for the full math.
          - banking/government/energy (the 9 banking/government sources this
            platform's Firecrawl budget review explicitly excluded, see
            firecrawl-production-provisioning.md, plus the 3 energy
            retailers added 2026-08-10) -> the Bright Data Web Unlocker
            fetch path instead (Captain's separate Bright Data account,
            5,000 requests/month, its OWN budget — never falls back to
            Firecrawl). Energy retailers are deliberately routed here
            rather than to Firecrawl: Bright Data's committed volume
            (~1,008/month against a 4,500 ceiling) has far more real
            headroom than Firecrawl's, and there is no sector-specific
            reason energy needs the Firecrawl path specifically — this is a
            budget-health choice, not a content-shape one.

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
                if sector in ("banking", "government", "energy"):
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
        return slug_from_url(self.source.url)

    def _sector(self) -> str:
        return sector_for_slug(self._slug())

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
        sector = self._sector()
        floor = get_report_count_floor(self.source.source_name, sector)
        gate_note = (
            f"[Downdetector two-layer gate PASSED: status='{status}' (top tier) AND "
            f"24h peak reports={report_count} >= floor={floor} "
            f"(per-source learned/bootstrap threshold, see migration 0121)]"
        )

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
        elif sector == "energy":
            # Deliberately does NOT use energy-grid language ("electricity",
            # "power outage", "gas supply", "grid", "blackout" — see
            # intelligence/classification/classifier.py's energy_disruption
            # keyword list). Two real reasons: (1) it would be inaccurate —
            # a Downdetector AU retailer page tracks user reports about the
            # RETAILER's own digital services (billing app, online account
            # portal, customer service), not the physical electricity/gas
            # network itself (that's the distribution network operator's
            # job — Ausgrid/Energex/etc — a different, unregistered source
            # category); (2) it would be wrong for push-alert routing —
            # energy_disruption is not in intelligence_store.py's
            # _OUTAGE_EVENT_TYPES, so a text that classified there would
            # silently never reach the push-alert pipeline even if this
            # adapter's own gate passed. Phrasing instead mirrors the
            # banking branch's proven pattern (same "outage"/"unavailable"/
            # "service disruption" keywords that already correctly land on
            # technology_outage), so this is a deliberate choice, not an
            # oversight.
            title = (
                f"Downdetector AU: {company} — crowdsourced reports indicate a "
                f"service outage (problems, top tier)"
            )
            summary = (
                f"{gate_note} Independent crowdsourced report-volume signal from "
                f"Downdetector Australia shows a genuine outage for {company}, an "
                f"Australian energy retailer: {report_count} user reports in the "
                f"last 24 hours (peak), status classified 'problems' (top tier) — "
                f"indicating a service disruption with {company}'s online account "
                f"portal, billing app, and customer service channels unavailable "
                f"for a significant proportion of customers in Australia (this "
                f"signal reflects the retailer's own digital services, not "
                f"necessarily the physical electricity/gas network). This is "
                f"aggregated third-party user-report telemetry (not a vendor "
                f"self-report), calibrated against real historical Australian "
                f"outage baselines."
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


def _diagnostic_snippet(html: str, max_body_len: int = 300) -> str:
    """Best-effort context attached to a total parse failure's error_message
    (base_adapter.run() truncates the final exception string to 500 chars,
    so this stays well inside that budget alongside the surrounding message
    text). Surfaces the page <title> when present -- often the one thing
    that immediately tells a genuine Downdetector layout change apart from
    a CAPTCHA/interstitial/block page returned by a fetch path (e.g. Bright
    Data's Web Unlocker) that wasn't actually unblocked -- plus a
    whitespace-collapsed slice of the raw response as a fallback. Never
    raises; a title-extraction failure just falls back to the body slice."""
    if not html:
        return "empty response body"

    title_match = _TITLE_PATTERN.search(html)
    title = title_match.group(1).strip() if title_match else None

    collapsed = re.sub(r"\s+", " ", html).strip()
    body_slice = collapsed[:max_body_len]

    if title:
        return f"title={title!r} body_start={body_slice!r}"
    return f"body_start={body_slice!r}"


def _normalise_tier(text: str) -> str:
    if "no current problems" in text or "no problems" in text:
        return "no_problems"
    if "possible problems" in text:
        return "possible_problems"
    return "problems"
