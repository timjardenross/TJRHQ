"""
Shared Bright Data Web Unlocker fetch-path capability.

2026-08-10 (Bright Data production provisioning): the Captain's own Bright
Data account, provisioned specifically to cover the 9 banking/government
Downdetector AU sources that
.claude/skills/bot-reviews/fixes-2026-08-09/firecrawl-production-provisioning.md
explicitly excluded from the shared Firecrawl fetch path (Firecrawl's real
free-tier cap — 1,000 scrapes/month, shared across the whole platform — only
had room for core telecom + Fastly + AEMO; banking/government needed either
a non-Firecrawl alternative or deactivation). See
.claude/skills/bot-reviews/fixes-2026-08-09/brightdata-provisioning.md for
the full write-up.

Product used: Bright Data's **Web Unlocker API** — verified against Bright
Data's own docs (docs.brightdata.com/scraping-automation/web-unlocker), not
guessed from the product name. Not Scraping Browser (a remote Puppeteer/
Playwright session for multi-step interactive automation — overkill for
"fetch one page"), not SERP API (search-engine results only), not Datasets
(pre-built bulk/structured extraction, not on-demand single-URL fetch). Web
Unlocker is the one product that matches "render one page, get content
back, on demand": one REST call in, the target site's real rendered
response out, with CAPTCHA-solving and anti-bot-challenge bypass (including
the Cloudflare Turnstile challenge that blocks a plain urllib.request GET
against downdetector.com.au) handled server-side by Bright Data — no
headless browser to run/maintain on this platform's own infrastructure.

  Endpoint : POST https://api.brightdata.com/request
  Auth     : Authorization: Bearer <BRIGHTDATA_API_KEY>
  Body     : {"zone": <BRIGHTDATA_ZONE>, "url": <target>, "format": "raw"}
  Response : the target site's raw HTML body (format="raw" — simpler than
             the {"status", "headers", "body"} JSON envelope format="json"
             returns, and matches every other adapter's "fetch returns a
             string" contract in this codebase).

Mirrors intelligence/ingestion/firecrawl_client.py's shape deliberately
(module doc laying out product choice + cost discipline up front, a
`*NotConfigured` exception, a plain `fetch_html()` entrypoint used by
DowndetectorAdapter) — this is the closest existing precedent in the
codebase for "shared fetch-path module wrapping a paid render-and-unblock
API", even though the two providers' request/response shapes differ (single
`format: raw` POST vs. Firecrawl's `formats: [...]` multi-output scrape).
Not force-fit beyond that: Bright Data's Web Unlocker needs no per-account
concurrency semaphore the way Firecrawl's 2-concurrent-request Free-plan cap
does — Bright Data's free tier is a flat 5,000 requests/month with no
documented concurrency ceiling, and this module's own real usage (9
sources, once/day, per intelligence/scheduler.py's intraday-sweep exclusion
for the whole `downdetector` source_type) is ~270 requests/month, nowhere
near a level where concurrency-limiting would matter.

── Cost discipline (read before adding a new caller) ───────────────────────
BRIGHTDATA_API_KEY is the Captain's own Bright Data account. Free plan:
5,000 requests/month. Every call into this module spends real quota — there
is no free retry.

  1. Cadence/source-count discipline (which sources, how often) still lives
     in intelligence/scheduler.py and each adapter's routing logic (see
     DowndetectorAdapter._fetch_html's sector-based routing: banking/
     government only, never telecom) — this module does not decide who's
     allowed to call it. But it DOES enforce a real hard cap regardless of
     what that discipline does or doesn't prevent: every call to
     `fetch_html()` below is gated by
     intelligence/ingestion/external_fetch_budget.py's atomic, DB-backed
     check-and-increment against a safe ceiling (4,500/5,000 — 90% of the
     real Free-tier cap; see that module's docstring for the full design
     and cycle-rollover handling). A call past the ceiling raises instead
     of firing.
  2. Callers should call this ONLY as a fallback after a plain fetch has
     already failed with a genuine blocking signal (e.g. HTTP 403) — never
     as the first attempt — so a source that stops being blocked stops
     spending quota automatically, with no code change required.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from intelligence.config import (
    BRIGHTDATA_API_KEY,
    BRIGHTDATA_TIMEOUT_SECONDS,
    BRIGHTDATA_ZONE,
)
from intelligence.ingestion import external_fetch_budget

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.brightdata.com/request"
_UA = "USS-TJR-Intelligence-Agent/1.0"


class BrightDataNotConfigured(RuntimeError):
    """Raised when BRIGHTDATA_API_KEY is unset — fails loud, never silently skips."""


def fetch_html(url: str, timeout: Optional[int] = None) -> str:
    """
    Fetch `url` through Bright Data's Web Unlocker API and return the
    target site's rendered HTML (format="raw" — a genuine unblocked fetch,
    bypassing the plain-HTTP JS-challenge/bot-detection block the calling
    adapter already hit).

    Raises BrightDataNotConfigured if no API key is set, or RuntimeError on
    any HTTP/network failure or non-2xx response — never returns partial or
    fabricated content. Also raises external_fetch_budget.FetchBudgetExceeded
    / external_fetch_budget.FetchBudgetCheckFailed (both RuntimeError
    subclasses) if the account's monthly hard-cap circuit breaker refuses
    this call — see external_fetch_budget.py and this module's own
    docstring, point 1.
    """
    if not BRIGHTDATA_API_KEY:
        raise BrightDataNotConfigured(
            "BRIGHTDATA_API_KEY not set — cannot use the Bright Data fetch path "
            "(see .claude/skills/bot-reviews/fixes-2026-08-09/"
            "brightdata-provisioning.md)"
        )

    # Hard-cap circuit breaker: gate BEFORE the real outbound call, and
    # count this attempt regardless of whether it goes on to succeed or
    # fail below (see external_fetch_budget.py's billing-verification
    # notes). Deliberately NOT caught here — a refusal must propagate to
    # the caller so it degrades gracefully at the adapter/collection-engine
    # layer instead of silently being swallowed.
    external_fetch_budget.check_and_increment("brightdata")

    payload = json.dumps({
        "zone": BRIGHTDATA_ZONE,
        "url": url,
        "format": "raw",
    }).encode("utf-8")

    req = urllib.request.Request(
        _ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": _UA,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout or BRIGHTDATA_TIMEOUT_SECONDS) as resp:
            charset = "utf-8"
            content_type = resp.headers.get("Content-Type", "")
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            html = resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Bright Data Web Unlocker HTTP {exc.code} for {url}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Bright Data Web Unlocker fetch failed for {url}: {exc}") from exc

    if not html:
        raise RuntimeError(f"Bright Data Web Unlocker returned empty content for {url}")

    log.info("Bright Data Web Unlocker fetch ok: %s", url)
    return html
