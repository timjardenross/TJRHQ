"""
Shared Firecrawl fetch-path capability.

Genuinely reusable, last-resort fetch layer for sources whose plain
urllib.request fetch a) doesn't just get a UA-based bot block that a
different header would fix, but b) hits a real Cloudflare/Azure Front Door
JS-challenge or WAF block — confirmed live from THIS production host
(not a sandbox artifact) for Downdetector Australia, AEMO Market Notices,
and Fastly Status (see
.claude/skills/bot-reviews/fixes-2026-08-09/firecrawl-production-provisioning.md
for the full write-up and the real cost math).

Calls Firecrawl's REST API directly (POST https://api.firecrawl.dev/v1/scrape)
with FIRECRAWL_API_KEY — NOT the interactive `firecrawl` CLI, which is
session-local tooling with no place in an unattended production cron path.

── Cost discipline (read before adding a new caller) ───────────────────────
FIRECRAWL_API_KEY is the Captain's own personal Firecrawl account. Free plan:
1,000 scrapes/month HARD CAP shared across ALL usage on that account (this
pipeline + any ad hoc interactive use), 2 concurrent requests max. Every call
into this module spends one real credit — there is no free retry.

  1. This module enforces the 2-concurrent-request account limit itself via
     a process-wide semaphore, regardless of how many adapter threads
     (collection_engine.py's ThreadPoolExecutor, max_workers=8) call it at
     once. Callers do not need to (and should not try to) manage
     concurrency themselves.
  2. Cadence/source-count discipline (which sources, how often) still lives
     in intelligence/scheduler.py and each adapter's own allowlist — this
     module does not decide who's allowed to call it. But it DOES enforce a
     real hard cap regardless of what that discipline does or doesn't
     prevent: every call to `scrape()` below is gated by
     intelligence/ingestion/external_fetch_budget.py's atomic,
     DB-backed check-and-increment against a safe ceiling (850/1,000 —
     85% of the real Free-plan cap, see that module's docstring for the
     full design and the cycle-rollover handling). A call past the ceiling
     raises instead of firing — a cron misconfiguration, a retry-loop bug,
     or a new caller added without doing this math can no longer silently
     blow through the account's monthly quota.
  3. Adapters should call this ONLY as a fallback after a plain fetch has
     already failed with a genuine blocking signal (e.g. HTTP 403) — never
     as the first attempt — so a source that stops being blocked stops
     costing credits automatically, with no code change required.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Optional

from intelligence.config import FIRECRAWL_API_KEY, HTTP_TIMEOUT_SECONDS
from intelligence.ingestion import external_fetch_budget

log = logging.getLogger(__name__)

_SCRAPE_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
_UA = "USS-TJR-Intelligence-Agent/1.0"

# Firecrawl Free plan hard limit: 2 concurrent requests. Process-wide
# (module-level singleton), so it caps real concurrency against the
# Firecrawl API regardless of how many adapter threads call this module.
_CONCURRENCY_LIMIT = 2
_semaphore = threading.Semaphore(_CONCURRENCY_LIMIT)

# A rendered-page fetch legitimately takes longer than a plain HTTP GET —
# give it real headroom rather than reusing the tight plain-fetch timeout.
_DEFAULT_TIMEOUT = HTTP_TIMEOUT_SECONDS * 3


class FirecrawlNotConfigured(RuntimeError):
    """Raised when FIRECRAWL_API_KEY is unset — fails loud, never silently skips."""


def scrape(url: str, formats: Optional[list[str]] = None, timeout: Optional[int] = None) -> dict:
    """
    Fetch `url` through Firecrawl's real /v1/scrape REST endpoint (a genuine
    headless-browser render — bypasses the plain-HTTP JS-challenge/bot-
    detection blocks the calling adapter already hit). Returns the API's
    `data` dict (keys depend on `formats`, e.g. markdown/rawHtml/metadata).

    Raises RuntimeError (or FirecrawlNotConfigured) on any failure — never
    returns partial or fabricated content. Also raises
    external_fetch_budget.FetchBudgetExceeded /
    external_fetch_budget.FetchBudgetCheckFailed (both RuntimeError
    subclasses) if the account's monthly hard-cap circuit breaker refuses
    this call — see external_fetch_budget.py and this module's own
    docstring, point 2.
    """
    if not FIRECRAWL_API_KEY:
        raise FirecrawlNotConfigured(
            "FIRECRAWL_API_KEY not set — cannot use the Firecrawl fetch path "
            "(see .claude/skills/bot-reviews/fixes-2026-08-09/"
            "firecrawl-production-provisioning.md)"
        )

    # Hard-cap circuit breaker: gate BEFORE the real outbound call, and
    # count this attempt regardless of whether it goes on to succeed or
    # fail below (see external_fetch_budget.py's billing-verification
    # notes). Deliberately NOT caught here — a refusal must propagate to
    # the caller so it degrades gracefully at the adapter/collection-engine
    # layer instead of silently being swallowed.
    external_fetch_budget.check_and_increment("firecrawl")

    formats = formats or ["markdown", "rawHtml"]
    payload = json.dumps({"url": url, "formats": formats}).encode("utf-8")
    req = urllib.request.Request(
        _SCRAPE_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": _UA,
        },
    )

    with _semaphore:
        try:
            with urllib.request.urlopen(req, timeout=timeout or _DEFAULT_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Firecrawl scrape HTTP {exc.code} for {url}: {detail}") from exc
        except Exception as exc:
            raise RuntimeError(f"Firecrawl scrape request failed for {url}: {exc}") from exc

    if not body.get("success"):
        raise RuntimeError(f"Firecrawl scrape unsuccessful for {url}: {body.get('error', body)}")

    data = body.get("data") or {}
    upstream_status = (data.get("metadata") or {}).get("statusCode")
    if upstream_status and upstream_status >= 400:
        raise RuntimeError(
            f"Firecrawl reached {url} but the upstream page itself returned "
            f"HTTP {upstream_status}"
        )

    log.info("Firecrawl scrape ok: %s (upstream status %s)", url, upstream_status)
    return data


def fetch_html(url: str, timeout: Optional[int] = None) -> str:
    """Convenience wrapper for adapters that want raw HTML (Downdetector's
    regex parser, ScrapeAdapter's BeautifulSoup extraction)."""
    data = scrape(url, formats=["rawHtml"], timeout=timeout)
    html = data.get("rawHtml")
    if not html:
        raise RuntimeError(f"Firecrawl returned no rawHtml for {url}")
    return html


def fetch_markdown(url: str, timeout: Optional[int] = None) -> str:
    """Convenience wrapper for adapters that want cleaned markdown text."""
    data = scrape(url, formats=["markdown"], timeout=timeout)
    md = data.get("markdown")
    if not md:
        raise RuntimeError(f"Firecrawl returned no markdown for {url}")
    return md
