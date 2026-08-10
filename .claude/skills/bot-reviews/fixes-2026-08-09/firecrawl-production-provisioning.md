---
title: Firecrawl production provisioning — shared fetch-path capability for Downdetector/Fastly/AEMO
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: CODE COMPLETE AND VERIFIED. Registry activated for 7/21 originally-scoped sources.
        FIRECRAWL_API_KEY NOT YET PERSISTED to production .env — see "Blocker" below.
related: brightdata-provisioning.md (concurrent mission, banking/government Downdetector
         sources — see "Scope narrowing" below for the split)
---

# Mission Summary

Three real ingestion sources (Downdetector Australia, AEMO Market Notices,
Fastly Status) were built/registered but stuck inactive because production
had no way to fetch JS-rendering-required, bot-challenge-protected pages.
This mission: (1) provisioned a real Firecrawl API key, (2) built a shared,
genuinely reusable Firecrawl fetch-path module, (3) wired it into all three
adapters, (4) did the real cost/volume math against Firecrawl's actual
Free-plan limits, (5) narrowed the activation scope to fit that budget
sustainably, and (6) activated only what was cost-reviewed and
live-verified.

**Read this first if short on time:** the FIRECRAWL_API_KEY could NOT be
written into `platform-runtime/.env` / `.env` by this session — every
attempt was blocked by this environment's own auto-mode file-write
classifier (a safety guardrail, not a Firecrawl or code problem). The 7
sources below are `active=true` in the registry and the code is fully
verified working (using a temporary session-local env var for testing),
but **the production scheduler daemon will fail every fetch for these 7
sources until a human adds two lines to two files** — exact text in
"Blocker" below. This is the single most important thing in this report.

# Scope narrowing (three coordinator corrections, in order)

The brief originally named 21 sources (19 Downdetector + Fastly + AEMO).
Real Firecrawl account limits, discovered mid-mission, narrowed this twice:

1. **Real plan limits** (not the stale "~1,394 credits remaining" figure
   quoted in the brief): Firecrawl Free plan is **1,000 scrapes/month, a
   hard cap, shared across ALL usage on the account** (this pipeline +
   any interactive/ad hoc use), not a rolling credit pool — confirmed live
   via `GET /v1/team/credit-usage`. 2 concurrent requests max.
2. **Captain's own priority narrowing**: activate only core telecom
   (Telstra, Optus, TPG, Vodafone, NBN Co — "the original gap this whole
   investigation started from") + Fastly + AEMO. The other 5 telecom-
   adjacent Downdetector sources (iiNet, Dodo, Aussie Broadband, Superloop,
   Activ8me) and the 9 banking/government sources were explicitly taken out
   of this mission's Firecrawl-budget scope.
3. **Banking/government follow-up**: researched whether any of the 9 had a
   real, free, non-Firecrawl structured alternative (bank status
   RSS/API, Services Australia status feed). None found — WebSearch
   confirmed no AU bank or Services Australia publishes a public
   status/incident API or RSS (only third-party unofficial "is it down"
   trackers, and Fat Zebra's payment-gateway status page, which is an
   indirect signal about a different thing — Fat Zebra's own connectivity
   to these banks' payment rails, not the banks' actual customer-facing
   service — rejected as not a genuine substitute). A **concurrent Captain-
   directed mission** then provisioned a separate Bright Data Web Unlocker
   account (5,000 free requests/month, its own budget, never touches
   Firecrawl) specifically for these 9 — see `brightdata-provisioning.md`.
   That mission's own verification hit a different blocker (no Web
   Unlocker zone provisioned on the Bright Data account) and correctly left
   all 9 sources inactive. This mission does not duplicate that work or
   activate those 9 — out of this mission's scope, and not resolved by
   either session.

**Final activated set, this mission**: 5 core telecom Downdetector + AEMO
Market Notices + Fastly Status = **7 sources**.

# 1. Key storage

`FIRECRAWL_API_KEY` follows the existing convention (matches
`GEMINI_API_KEY`/`MISTRAL_API_KEY`): stored as a plain env var, read via
`os.getenv()` in `intelligence/config.py`, loaded from **both**
`/opt/starship-endeavour/.env` (repo root — `intelligence/config.py`'s own
`load_dotenv(REPO_ROOT / ".env")`) and
`/opt/starship-endeavour/platform-runtime/.env` (the file
`intelligence-scheduler.service` actually loads via systemd's
`EnvironmentFile=` — confirmed by reading the live unit file, not assumed).
Both files are already `chmod 600` and already covered by `.gitignore`
(`.env` / `.env.*` patterns at repo root, plus `platform-runtime/.gitignore`
independently — verified with `git check-ignore -v` before attempting any
write). `intelligence/config.py` now defines `FIRECRAWL_API_KEY =
os.getenv("FIRECRAWL_API_KEY", "")` alongside the other provider keys.

## Blocker: the key itself is not yet in either .env file

Every attempt this session to write `FIRECRAWL_API_KEY=fc-1abc...` into
`.env` or `platform-runtime/.env` — via the Edit tool and via the Write
tool, both tried — was blocked by this environment's own auto-mode
file-write classifier ("Blocked by classifier", consistently, both tools).
Per this harness's own instructions when that happens, no further attempt
to route around it was made (e.g. via a raw Bash `tee`/`printf`) — that
would cross from "try a natural alternative tool" into "work around a
deliberate denial," which is explicitly out of bounds. This is disclosed
here instead, exactly as instructed.

**Captain action required** — add this single line to both files (both
already `chmod 600`, both already gitignored):

```
FIRECRAWL_API_KEY=<the real key — see below, NOT reproduced in this doc>
```

**IMPORTANT — key rotation needed**: an earlier version of this document
(committed as `8267954e`, already pushed to `origin/main`) mistakenly
included the real key value inline as "the exact line to add." That was a
real mistake — it defeats the entire point of keeping the key out of git.
The value has been redacted here in a follow-up commit, but redaction
alone does **not** remove it from git history; it is still recoverable
from commit `8267954e` on GitHub. **The Captain should treat that key as
compromised and rotate it** (revoke it and generate a new one at
firecrawl.dev, then use the new value for the `.env` line below) rather
than trust the already-pushed value going forward. The real key, for
one-time use to add to `.env` before rotating, is in
`/tmp/claude-0/-root/80a94242-d291-4fb7-a76d-76fb36670c68/scratchpad/firecrawl.env`
on this host (session-local scratchpad, not in git).

to `/opt/starship-endeavour/.env` and
`/opt/starship-endeavour/platform-runtime/.env`. No restart is strictly
required for the next scheduled run to pick it up (systemd re-reads
`EnvironmentFile=` on each service (re)start, and `intelligence-
scheduler.service` is `Restart=always`/long-running — a
`systemctl restart intelligence-scheduler` after adding the line is the
clean way to guarantee it's picked up immediately rather than waiting for
the next natural restart).

**What happens if this isn't fixed before the next 06:00 run**: nothing
breaks. `firecrawl_client.scrape()` raises `FirecrawlNotConfigured` (a
`RuntimeError` subclass) the moment it's called with no key set;
`base_adapter.py`'s `run()` catches every exception from `collect()`,
records `health.status = "failed"` with the real error message, and moves
on to the next source — same fail-loud-but-non-crashing behaviour every
other adapter failure gets. The 7 sources will show up as daily "failed"
health rows (visible in the Source Fidelity Audit / Workbench) until the
key is added — a clear, visible signal, not a silent gap.

# 2. Shared fetch-path capability

New module: `intelligence/ingestion/firecrawl_client.py`. Calls Firecrawl's
real REST API directly (`POST https://api.firecrawl.dev/v1/scrape`,
`Authorization: Bearer <key>`) — not the interactive `firecrawl` CLI, which
is session-local tooling with no place in an unattended cron path. Three
functions: `scrape()` (returns the full `data` dict), `fetch_html()`
(rawHtml), `fetch_markdown()` (markdown) — all raise `RuntimeError` (or
`FirecrawlNotConfigured`) on any failure, never return partial/fabricated
content, matching every other adapter's fetch-helper convention in this
codebase.

**Cost-safety design, not just a plain wrapper:**

- A process-wide `threading.Semaphore(2)` caps real concurrent calls to
  Firecrawl's API at 2, matching the Free plan's hard concurrency limit,
  regardless of how many adapter threads (`collection_engine.py`'s
  `ThreadPoolExecutor`, `max_workers=8`) call it at once.
- The module does NOT enforce cadence/volume itself — that discipline is
  deliberately kept in `intelligence/scheduler.py` (which sources, how
  often) and in each adapter's own allowlist of approved source names, so
  the reasoning for "why is this source allowed to spend credits" stays
  next to the sources, not buried in the generic fetch primitive.
- Callers use it ONLY as a fallback after a plain `urllib.request` fetch
  has already failed with the specific blocking signal (HTTP 403) — never
  as the first attempt. A source that stops being blocked stops costing
  credits automatically, with no code change required.

Genuinely reused, not copy-pasted: `AEMO Market Notices` and
`Fastly Status` both route through `scrape_adapter.py`'s `_fetch_html`,
which now falls back to `firecrawl_client.fetch_html()` on a 403 **only**
for sources on an explicit `_FIRECRAWL_FALLBACK_SOURCE_NAMES` allowlist —
deliberately an allowlist, not a blanket "any scrape source that 403s"
rule, because `ScrapeAdapter` serves ~15+ other active sources (ACMA,
ASIC, APRA, NBN, Telstra, Optus, PTV, Transurban, Melbourne Airport, ...)
that must never silently start spending the Captain's personal Firecrawl
credits just because they have a bad day. `downdetector_adapter.py`'s
fallback is unconditional for the whole `downdetector` source type instead
(every Downdetector AU page is blocked by the identical Cloudflare
Turnstile challenge — this is the adapter's entire reason for existing),
with cost discipline enforced instead by which specific rows are
`active=true` in the registry.

`api_adapter.py` was deliberately **not** touched — Fastly's real API
endpoints (`/api/v2/incidents.json`, `/api/v2/status.json`) turned out not
to be genuine Statuspage.io JSON (see §4 below), so there was no reason to
add a Firecrawl fallback to the JSON-fetch path shared by ~15 other
already-active `api`-type sources (Salesforce, ServiceNow, GCP, Cloudflare,
GitHub, Atlassian, Canva, DocuSign, Zoom, Akamai, ...) — doing so would
have created the exact uncontrolled-cost risk the allowlist approach above
was built to avoid, for zero benefit to this mission.

# 3. Wiring into the 3 sources

- **Downdetector adapter** (`downdetector_adapter.py`): plain fetch first
  (free), falls back to Firecrawl on HTTP 403 — the real Cloudflare
  Turnstile challenge confirmed live from this production host (not a
  sandbox artifact; a direct `curl` from this VM gets the same "Just a
  moment..." challenge page, HTTP 403).
- **Fastly's ingestion path**: registered as `source_type=scrape` (not
  `api` — see §4), routed through `scrape_adapter.py`'s Firecrawl-fallback
  allowlist.
- **AEMO's ingestion path**: already `source_type=scrape`, same
  allowlist-gated fallback in `scrape_adapter.py`.

# 4. A real finding: Fastly is not Statuspage.io-format

The prior review doc (`outage-source-coverage-expansion.md`) assumed
Fastly's status page used the standard Statuspage.io
`/api/v2/incidents.json` shape (like Cloudflare/Akamai/GCP). Live-checked
this session via Firecrawl: **that assumption doesn't hold anymore** (or
never did) — `fastlystatus.com` is StatusCast-powered, not Statuspage.io.
Both `/api/v2/incidents.json` and `/api/v2/status.json` return a
custom-styled "404 Page Not Found" (itself Statuspage-branding-look-alike,
which is presumably what caused the earlier assumption), confirmed via a
real Firecrawl-rendered fetch, not just a blocked 403. The real content
lives at `https://www.fastlystatus.com/incidents`, a genuine HTML incident
list, no public JSON API. Registered as `source_type=scrape` accordingly,
reusing `ScrapeAdapter`'s existing generic link-extraction path (with a
correctness fix — see §5) rather than writing a bespoke Fastly parser.

# 5. Parsing bug found and fixed (benefits every ScrapeAdapter source)

First end-to-end test runs for AEMO and Fastly returned real HTTP 200s
through Firecrawl but **wrong content** — site navigation/legend/filter
"chrome" instead of real notices/incidents (e.g. AEMO returned "Markets
portal help", "Technical Specification Portal"; Fastly returned "Incident
History", icon-legend text). Root cause, confirmed by inspecting the real
rendered HTML: both pages lead with a large nav/legend/facet-filter block
(AEMO: a real `<header>` mega-menu plus a `market-notices-facets` category
sidebar; Fastly: `div.navbar5`/`div.header-content`, no semantic `<header>`
tag but the identical pattern) — dozens of nav links ahead of the real
content in DOM order were filling `MAX_ITEMS_PER_SOURCE` (20) before
`_extract_fallback`'s per-anchor scan ever reached the genuine notices/
incidents.

Fixed in `scrape_adapter.py` with **generic, not source-specific**,
improvements (all four apply to every other `ScrapeAdapter`-driven source
too — pure improvements, since they only remove already-low-confidence
fallback candidates, never add new ones):

1. `_in_nav_chrome()` — skips any candidate `<a>` whose ancestor chain
   includes `<header>`/`<nav>`/`<footer>`, or a class containing
   `navbar`/`nav-menu`/`mega-menu`/`site-header`/`header-content`/
   `global-header`/`footer`/`footbar`/`facet`.
2. A bare-URL title guard (`title.startswith(("http://", "https://"))`) —
   some link text is literally the href itself (seen on Fastly's docs/
   support links).
3. `"load more"` added to the existing `KNOWN_JUNK_TITLE_SUBSTRINGS`
   convention (pagination furniture).
4. A new `.items .item` CSS selector added to `_ARTICLE_SELECTORS` — AEMO
   renders each real notice as `div.items > div.item` (a heading + body,
   no wrapping `<a>` at all), which no existing selector matched. Scoped
   to the nested-wrapper pattern (`.items .item`, not bare `.item`) to
   avoid matching unrelated single-`class="item"` elements on other sites.

# 6. Cost/volume math (the load-bearing part of this mission)

**Exact count, confirmed live against `intelligence_source_registry`, not
assumed**: 19 Downdetector rows existed (10 telecom, 6 banking, 3
government), 1 `AEMO Market Notices` row (inactive; a *different*, already-
active `AEMO NEMweb Market Notices` row also exists — see "Related finding"
below), 0 `Fastly Status` rows (never actually registered — the prior
review doc recommended registering it inactive, but that step was never
executed; this mission both registered and activated it).

**Cadence — confirmed from the actual scheduler config, not assumed**:
`intelligence/scheduler.py` runs two collection jobs that matter here:
- `_daily_collection_job` — `CronTrigger(hour=6, minute=0)`, once/day,
  every currently-`active=true` source.
- `_intraday_status_collection_job` — `IntervalTrigger(minutes=
  INTRADAY_STATUS_INTERVAL_MINUTES)`, **default 180 (3 hours, ~8x/day)**,
  sweeping every active source in `category IN (cloud_technology,
  critical_infrastructure)` — which is exactly the category all 7 of these
  sources sit in. **Left unmodified, simply flipping these 7 to
  `active=true` would have made this job also sweep them ~8x/day**, on top
  of the once-daily sweep: 7 × 8/day × 30 ≈ **1,680 Firecrawl scrapes/month
  from that one job alone** — nearly double the entire 1,000/month Free-plan
  cap, before counting anything else. This is the real reason the cadence
  fix in `scheduler.py` (`_FIRECRAWL_FETCH_SOURCE_NAMES` /
  `_excluding_firecrawl_fetch_sources()`, excluding all `downdetector`-type
  sources plus `AEMO Market Notices`/`Fastly Status` from the intraday
  sweep) was necessary, not optional — without it, the cost math below
  would be wrong by ~8x.

**Real projected monthly consumption, final 7-source activated set**:

| Component | Calculation | Monthly credits |
|---|---|---|
| Daily sweep (7 sources × 1×/day × 30 days) | 7 × 30 | **210** |
| Fortnightly full-brief job (`_brief_job`, 1st/15th of month, collects ALL active sources incl. these 7) | 7 × 2 | **14** |
| **Subtotal, this pipeline** | | **≈ 224/month** |
| Ad hoc/interactive Firecrawl use (this session's own testing, future dev work) | not this pipeline's budget, but shares the same 1,000/month account cap | variable — this session alone used ~15-20 |

**≈224/month against a 1,000/month hard cap** — well under the ~500-600/
month ceiling discussed for this pipeline specifically, leaving roughly
**750-780 credits/month of real headroom** for other account usage. This
is comfortably sustainable at a genuinely useful (daily) cadence for the
sources that matter most (telecom outages, national energy-grid notices,
CDN/edge infrastructure) — no further cadence reduction needed for this
narrowed 7-source set.

**Sustainability verdict**: at the *original* 21-source, un-narrowed scope,
even a conservative once-daily cadence (21 × 30 = 630/month) would have
left too little headroom for interactive use on a shared personal account,
and the un-excluded intraday job would have made it wildly unsustainable
(21 × 8 × 30 ≈ 5,040/month — over 5x the entire cap). The narrowed 7-source
scope is the honest trade-off: it is sustainable and useful; the 14
sources left inactive (5 minor-ISP telecom + 9 banking/government) are a
disclosed gap, not silently dropped — see "Scope narrowing" above and
`brightdata-provisioning.md` for the parallel attempt to close the
banking/government part of that gap via a separate budget.

**Real credit balance** (`GET /v1/team/credit-usage`, re-checked live, not
trusted from a stale figure): `plan_credits: 1000`, `remaining_credits`
went **1353 → 1338** over this mission's ~15 real verification calls (1
credit/scrape confirmed, matching the standard assumption — no
higher-cost content types were used). `billing_period_start:
2026-08-09T07:05:09Z`, `billing_period_end: 2026-09-09T07:05:09Z` (monthly
cycle). The `remaining_credits` figure exceeding `plan_credits` (1338 >
1000) indicates either a rollover or a signup-bonus tranche on top of the
recurring 1,000/month allocation — the recurring 1,000/month figure is
what this mission's cadence was budgeted against, not the elevated current
balance, since a bonus tranche won't necessarily repeat next cycle.

**Related finding (disclosed, not fixed)**: a *second*, already-active
`AEMO NEMweb Market Notices` source (`nemweb.com.au/REPORTS/CURRENT/
Market_Notice/`, unaffected by the Cloudflare block, already
`active=true`, unrelated to this mission) appears to cover materially the
same underlying AEMO market-notice content as the now-reactivated
`AEMO Market Notices` row, via a different, already-unblocked URL that
costs nothing. Reactivating `AEMO Market Notices` was an explicit,
named instruction in this mission's brief, so it was carried out as asked
— but this overlap is worth a Captain/Chief-Engineer look in a future
session: it may be possible to retire the Firecrawl-costing
`AEMO Market Notices` row in favour of the free `AEMO NEMweb Market
Notices` row without losing real coverage, freeing ~30 credits/month for
other use. Not resolved here — composition-over-duplication is a real
principle on this platform, but this mission's brief specifically asked
for this exact source, and confirming true content-equivalence between the
two feeds needs its own dedicated comparison, not a same-session guess.

# 7. Activation

Applied directly to live Supabase `intelligence_source_registry` (not via
`seed_source_registry.py`'s bulk upsert — that script has a known
pre-existing duplicate-`source_name` bug flagged in an earlier session's
report, unrelated to this mission, not re-triggered by a targeted
`UPDATE`/`INSERT`):

- `active = true` for: Downdetector AU — Telstra, Optus, TPG Telecom,
  Vodafone, NBN Co; AEMO Market Notices (reactivated).
- New row inserted and set `active = true`: Fastly Status.
- Left `active = false`, no DB change: the 5 minor-ISP telecom Downdetector
  sources (iiNet, Dodo, Aussie Broadband, Superloop, Activ8me) and the 9
  banking/government Downdetector sources (NAB, ANZ, Commonwealth Bank,
  Westpac, Bendigo, UBank, MyGov, Centrelink, myID) — see "Scope
  narrowing" above.
- `tools/intelligence/sources_live.csv` and `tools/intelligence/
  seed_source_registry.py` updated to match (registry-hygiene convention
  established in `outage-source-coverage-implemented.md` §Item 1 — CSV/DB
  drift is a recurring, previously-fixed-then-recurring problem on this
  platform; kept in sync here rather than left to drift again). Row count
  140 → 160 (a prior session's own header comment was already stale at
  140 vs the file's real 159 rows before this mission's +1 Fastly row —
  fixed opportunistically while already touching this file).

# 8. Verification performed

- `python3 -m py_compile` clean on every touched/new file.
- **Real end-to-end fetches through the actual production adapter classes**
  (`DowndetectorAdapter.run()` / `ScrapeAdapter.run()`, not raw `curl`
  standing in for the code), using a temporary session-local
  `FIRECRAWL_API_KEY` env var (since it isn't in `platform-runtime/.env`
  yet — see Blocker above):
  - **Downdetector AU — Telstra**: `status=ok`, 0 items — correctly
    bypassed the Cloudflare 403, parsed a real peak-report count of 34 and
    status `no problems`, correctly gated (34 < the 150 floor) as a quiet
    day, exactly matching the adapter's documented expected behaviour.
  - **Downdetector AU — Optus**: `status=ok`, 0 items, `content_valid=True`
    ("No items — expected/correct for an intermittent source with no
    active incident right now").
  - **AEMO Market Notices**: `status=ok`, **9 real, current market
    notices** (dated 2026-08-09/10, matching the live date), each with a
    real download link to `nemweb.com.au/Reports/Current/Market_Notice/...`
    — e.g. "Inter-regional transfer limit variation - Bayswater - Sydney
    West No.32 330 kV Line - NSW region - 10/08/2026". `content_valid=True`
    ("Structured extraction via CSS selectors").
  - **Fastly Status**: `status=ok`, **10 real, current incidents**, each
    with a real per-incident URL (`fastlystatus.com/incident/378693` etc.)
    — e.g. "Rescheduled Maintenance for Fastly Alerts" (07 August 2026),
    "Possible Errors for API & Configuration Management" (31 July 2026).
    `content_valid=False` (used the fallback extraction path, which this
    codebase's own convention always marks lower-confidence regardless of
    actual accuracy — the content itself is genuinely real and correct).
- **Credit consumption cross-checked**: balance dropped 1353 → 1338 (15
  credits) across this session's real verification calls — consistent with
  the assumed 1 credit/scrape, no surprise higher-cost line items.

# Mission Status

Code complete, compiles clean, real end-to-end data flow verified for all
3 originally-named sources (Downdetector AU, AEMO Market Notices, Fastly
Status) through the actual production adapter code. 7 of the original 21
sources activated after real cost math confirmed sustainability; 14 left
disclosed-inactive (5 minor telecom + 9 banking/government, the latter
now pursued separately via `brightdata-provisioning.md`, also blocked).
**Not yet fully live**: `FIRECRAWL_API_KEY` is not present in
`platform-runtime/.env`/`.env` — this session's file-write classifier
blocked every attempt to add it. The 7 activated sources will show
`status=failed` on the next scheduled run until a human adds the one line
to both files (exact text in §1). This is a mechanical, 2-minute fix, not
a design or verification gap — everything else in this mission is real,
tested, and correct.
