---
title: Downdetector Australia adapter — crowdsourced outage report-volume signal, implemented
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: IMPLEMENTED (registered inactive — see Fetch mechanism below)
mission: Captain-directed implementation, following
  outage-source-coverage-expansion.md's gap analysis (Telstra/Optus/TPG/
  Vodafone status pages require per-address interactive form-fill, rejected)
  and outage-scale-detection-proposal.md /
  outage-scope-llm-check-implemented.md's existing 5-guard push-alert
  pipeline in intelligence/persistence/intelligence_store.py.
---

# Mission Summary

Built a new Downdetector Australia (downdetector.com.au) adapter covering AU
telecom, banking, and government digital services with one consistent
per-company-page pattern, gated by a two-layer "genuine outage-scale"
threshold before anything reaches `intelligence_events`. Registered 19
confirmed-live companies. Wired the gate into the same outage push-alert
pipeline built earlier tonight, with a deliberate, disclosed bypass of two
of its five existing guards for this specific source shape (reasoning
below).

# Fetch mechanism chosen, and why

**Investigated first, per the brief's own instruction, rather than assuming
firecrawl was needed.** A plain `urllib`/`curl` GET against a real
`downdetector.com.au/status/{slug}/` page from this build session's sandbox
returns **HTTP 403** — a Cloudflare "Just a moment..." bot-challenge page
(managed-challenge JS + `challenges.cloudflare.com`), confirmed both with
the platform's standard adapter UA string and a full browser UA. No
`__NEXT_DATA__`/JSON payload is reachable this way — the challenge blocks
before any real HTML is served.

A `firecrawl scrape --format html` fetch (this session's own tool access,
**not** a credential available to this platform's production code) bypasses
the challenge and returns the real rendered page. Confirmed live against
all 19 registered companies: the report-volume and status data are **not**
in a `__NEXT_DATA__`/RSC JSON blob — they're in the page's own accessible
`aria-label` text on the reports chart, e.g.:

```
aria-label="Reports chart for the last 24 hours with a peak of 34 reports, status: no problems"
```

This single string atomically carries both Downdetector's own 3-tier status
enum (`no problems` / `possible problems` / `problems`) and the real 24h
peak report count — a more reliable single match than the separate prose H1
("User reports show `<status>` with `<Company>`"), which is kept as a
status-only fallback.

**Checked for a deployable `FIRECRAWL_API_KEY`** per the brief's explicit
instruction: none exists anywhere in this platform's own `.env` files
(`.env`, `lcars-portal/.env*`, `platform-runtime/.env*`,
`core/command-centre/.env`, `telegram-bots/**/.env*`) or environment. The
firecrawl CLI available in this build session authenticates via
`/root/.config/firecrawl-cli`, a Claude Code plugin-level credential tied to
this sandbox/session — not something the production cron on the actual VM
can use.

**Conclusion, and why the sources are registered `active=False`:** the
adapter is built to do a plain `urllib` GET (same UA/pattern as every other
adapter in this codebase — no new dependency), which will currently fail
with the same Cloudflare block confirmed above. This is the **exact same
class of gap already found and disclosed tonight** for Fastly Status and
AEMO Market Notices in `outage-source-coverage-expansion.md` (Tier C): a
real, bot-protected source needing either (a) a live re-test from the
actual production VM — this sandbox's egress IP may simply be treated
differently by Cloudflare than the VM's, the same disclosed caveat already
on record for Fastly — or (b) the shared firecrawl-fetch-path capability in
`api_adapter.py`/`scrape_adapter.py`, which does not exist yet and is
already flagged as its own platform-wide, Captain-scoped piece of work, not
something to build ad hoc for one source. Registering these 19 sources
`active=True` while knowing the production fetch path is currently blocked
would misrepresent them as live when they are not — so they are registered,
fully built, parser-verified against real captured pages, and **staged
inactive** pending either of the two resolutions above, exactly matching
the Fastly precedent.

# Two-layer threshold — exact formula implemented

```python
_TOP_TIER = "problems"
_REPORT_COUNT_FLOOR = 150

def _passes_gate(status, report_count):
    if report_count is None:
        return False  # fails safe -- never fires on status alone
    return status == _TOP_TIER and report_count >= _REPORT_COUNT_FLOOR
```

Both layers must pass:
1. Downdetector's own status must be at the **top tier** ("problems" — not
   "possible problems" or "no current problems").
2. The 24h **peak report count** must be `>= 150`.

**Evidence behind 150** (per the Captain's brief — Wayback Machine
cross-referenced against the real 2026-07-07/08 nationwide Telstra outage,
confirmed in this platform's own `intelligence_events` via ABC News/Guardian
coverage and the Senate inquiry): quiet-day baseline 22-42 reports for
Telstra specifically; 230-354 during the real outage (6-10x spike, top
tier). Live-checked tonight (2026-08-10) across all 19 registered
companies at their current, real, quiet state: peak counts ranged **1-42**
across telecom (Telstra 34, Optus 17\*, NBN Co 20\*, TPG 7, Vodafone 10,
iiNet 8, Dodo 12, Aussie Broadband 10, Superloop 2, Activ8me 3), banking
(NAB 3, ANZ 3, CBA 7, Westpac 3, Bendigo 6, UBank 2), and government (MyGov
7, Centrelink 2, myID 1). (\*Optus and NBN Co were both at "possible
problems" tier tonight — real, live examples of the middle tier, not the
top one.)

150 is a **first-cut absolute floor**, not a rolling per-service baseline —
disclosed explicitly, not asserted as final:
- It sits comfortably below the real outage's own low end (230), giving
  margin to catch a genuine event before it fully peaks.
- It sits ~3.5x above the highest quiet-day baseline observed live tonight
  across all 19 services (42, Telstra) — real headroom above ambient noise
  for every registered company, not just Telstra.
- A genuine rolling 24-48h trailing-average baseline (the Captain's
  preferred approach if practical) was **not built this session** — it
  needs a new small persistence table (e.g. a per-check snapshot of
  status+report_count per source) and real runtime data accumulated over a
  few weeks before it would be more trustworthy than this evidence-grounded
  absolute number. The current adapter design (emit zero items on a quiet
  check, matching the AWS/Azure "intermittent" convention) doesn't persist
  every check's raw numbers, so there's currently no historical trail to
  compute a rolling baseline from — flagged as the natural v2, not a gap
  papered over.
- **Expected to need calibration** once this runs live for a few weeks
  across all 19 services (banking/government quiet-day floors may behave
  differently from telecom's under real conditions this one-night sample
  can't fully capture) — not presented as a fully-proven number.

# Adapter architecture

New file: `intelligence/ingestion/downdetector_adapter.py` —
`DowndetectorAdapter(BaseSourceAdapter)`, following the exact same contract
as `rss_adapter.py`/`api_adapter.py`/`scrape_adapter.py`/
`github_markdown_adapter.py` (same `collect() -> list[IntelligenceItem]`
shape, same `_make_item()` helper, same non-raising `run()` wrapper from
`base_adapter.py`).

**Why a new `source_type` (`downdetector`) rather than reusing `api` or
`scrape`:** `api_adapter.py`'s own module docstring already notes there is
no dedicated "statuspage" adapter type — Statuspage JSON is just one more
dispatch branch inside the generic `api` type, keyed by source name/endpoint
shape. Downdetector's fetch is genuinely different again: not a JSON
endpoint (`api`'s `_fetch_json` would fail immediately on HTML content-type)
and not generic article-list extraction (`scrape`'s purpose). It's a
purpose-built HTML fetch + targeted status/report-count regex extractor with
its own two-layer business-logic gate baked in *before* anything is
emitted — different enough to earn its own type, consistent with this
codebase already having 4 distinct types for 4 distinct mechanisms, not 1.

This required widening the DB `CHECK` constraint on
`intelligence_source_registry.source_type` (previously
`rss|api|scrape|manual|github_markdown`) — applied live via Supabase MCP
(`expand_source_type_constraint_downdetector`) and mirrored as
`core/infrastructure/supabase/migrations/0120_expand_source_type_constraint_downdetector.sql`,
following this table's own established, safe precedent for this exact kind
of change (`expand_jurisdiction_constraint_source_registry`,
`0036d_source_registry_category_expand`,
`add_cybersecurity_category_to_source_registry` all did the same additive,
non-breaking widen). No existing rows/values affected.

**No `classifier.py` change needed.** Every other adapter in this codebase
(AEMO/GCP/Salesforce/ServiceNow/etc.) constructs plain title/summary text
and lets the shared, 100%-keyword-based `classify()` decide `event_type` —
none of them hand-set it. The Downdetector adapter follows the same
discipline: `_build_item_text()` constructs sector-appropriate phrasing
(telecom/banking/government) engineered so the classifier's own keyword
rules naturally land on the right category:
- **Telecom** sources → `telecom_outage` (phrasing includes "network
  outage", "mobile network", "broadband", "internet outage",
  "connectivity" — enough distinct `telecom_outage` keyword hits to
  outweigh `technology_outage`'s single generic "outage" hit, since
  classify() picks the category with the highest keyword-match count).
- **Banking/government** sources → `technology_outage` (already a member
  of `intelligence_store.py`'s `_OUTAGE_EVENT_TYPES` — no new event_type
  needed). `banking_relevance` is separately set to `high` by the existing
  `_BANKING_KEYWORDS` matcher via company name/"bank"/"banking" text, so
  CPS230/banking-resilience downstream consumers still see these correctly
  flagged.

Live-classifier-verified (`intelligence.classification.classifier.classify`)
against representative synthetic outage-scale text for Telstra, Optus, NAB,
Westpac, MyGov, Centrelink, iiNet, Vodafone: all 8 land on
`event_type ∈ {telecom_outage, technology_outage}`, `customer_impact=high`,
`geography=AU`, `confidence` 0.77-0.90 (comfortably above the push-alert's
0.65 floor).

**Registered under `category=critical_infrastructure` for all 19 sources**
(telecom, banking, and government alike) rather than splitting banking into
`banking_payments`. Two reasons: (1) it's semantically defensible — AU
banking-as-critical-infrastructure is exactly this platform's own
CPS230/operational-resilience framing; (2) critically, `scheduler.py`'s
`_intraday_status_collection_job` (the fast ~3-hourly poll that actually
gives outage detection real-time reach, vs. the 06:00-only daily sweep) only
polls `_INTRADAY_STATUS_CATEGORIES = {"cloud_technology",
"critical_infrastructure"}`. Registering banking under `banking_payments`
would have silently limited bank-outage detection to once-daily lag,
defeating the point of a fast crowdsourced signal — so `critical_infrastructure`
was the correct choice, not just a convenient one. No `scheduler.py` change
needed.

# Push-alert integration — deliberate, disclosed guard bypass

Wired into the same pipeline built earlier tonight
(`intelligence/persistence/intelligence_store.py`'s
`_maybe_push_outage_alert()`), but **Downdetector-sourced events skip guard
5 (`_passes_vendor_tier_gate`) and guard 6 (`_passes_blast_radius_check`)**,
detected via a `source_name` prefix match (`"downdetector au"` —
case-insensitive), the same mechanism guard 5 already uses internally for
its own vendor-identity check.

**Why this is the right call, not scope creep:**

1. Guards 5 and 6 exist to *approximate* genuine blast radius from vendor
   self-report **text**, precisely because those sources carry no native
   scale signal. The Downdetector adapter's own two-layer gate is already a
   direct, numeric, ground-truth scale signal, computed and enforced
   *before* an item is even emitted — reapplying text/vendor-identity
   heuristics on top is redundant at best.
2. It would be actively **wrong** at worst, for two confirmed reasons:
   - Guard 5's Tier-A allowlist (AWS/Azure/Google Cloud/Cloudflare/NBN/
     Telstra/Optus/TPG only) would suppress every genuine,
     Downdetector-confirmed outage for every company this mission exists to
     add coverage for that isn't on that list — Vodafone, every smaller ISP,
     all four major banks, mygov/Centrelink/myID. That would silently
     defeat the entire point of this source.
   - Guard 6's LLM prompt explicitly defines "narrow" as "confined to one
     vendor's own service, product, or customer base (even if that vendor
     is itself a large hyperscaler or carrier)". A real, Downdetector-
     confirmed nationwide outage of one bank's own banking app — unable to
     access your money, for millions of Australians, exactly the kind of
     event this platform's CPS230/banking_relevance framing treats as
     first-class — is still, by the letter of that prompt, "confined to one
     company's own customer base", so the LLM would very plausibly answer
     "no" and suppress a genuine, materially significant event. That prompt
     was calibrated for a different question (vendor self-report/media text
     scale-guessing) than the one Downdetector's own gate already answers
     directly.

This is implemented as an early branch inside `_maybe_push_outage_alert()`
itself (the same push-alert-scoped, non-shared-module file every other
guard in this pipeline already lives in and has already been iteratively
extended in across multiple missions tonight) — not a change to
`classifier.py`, `filter.py`, or any other shared consumer. Guards 1-4
(`event_type` membership, `customer_impact=high`, `confidence>=0.65`,
`_has_outage_language`) still apply unchanged to Downdetector events — only
the two guards built specifically for vendor-self-report/media text shapes
are bypassed.

# Verification

`python3 -m py_compile` clean on all touched files:
`intelligence/ingestion/downdetector_adapter.py`,
`intelligence/ingestion/collection_engine.py`,
`intelligence/persistence/intelligence_store.py`,
`tools/intelligence/seed_source_registry.py`.

**Parsing verified against real captured pages** — `firecrawl scrape
--format html` against all 19 registered slugs tonight, then
`parse_status_and_count()` run directly against the real HTML (no live
network call): all 19 parsed correctly (status + peak report count),
company display names extracted correctly (including edge cases like
`:UBank`'s stray leading colon, handled via a display-name override in the
registry rather than the raw scraped text).

**Live regression check (the Captain's explicit ask)** — real current
(2026-08-10) values for Telstra (`no_problems`, 34 reports) and Optus
(`possible_problems`, 17 reports) run through the full `collect()` path
(network call mocked to return the real captured HTML, everything else
live code): **both correctly return zero items** — the gate does not fire
on either at current real report-count levels, confirming no noise on a
quiet-but-not-perfectly-clean day (Optus was at the middle tier, not
"no problems", and still correctly suppressed).

**Simulated outage-scale check** — same real Telstra HTML with the
aria-label's peak count/status substituted to a synthetic outage-scale value
(`peak of 260 reports, status: problems`), run through the full `collect()`
path: correctly returns exactly 1 item, with the expected
gate-evidence-bearing title/summary.

# What's registered

19 sources in `intelligence_source_registry` (mirrored in
`tools/intelligence/sources_live.csv` and
`tools/intelligence/seed_source_registry.py`'s `SOURCES` list, seeded live
via `tools/intelligence/seed_source_registry.py`):

**Telecom (10):** Telstra, Optus, TPG Telecom, Vodafone, iiNet, Dodo, Aussie
Broadband, Superloop, Activ8me, NBN Co.
**Banking (6):** NAB, ANZ Bank, Commonwealth Bank, Westpac, Bendigo Bank,
UBank.
**Government (3):** MyGov, Centrelink, myID.

All `category=critical_infrastructure`, `source_type=downdetector`,
`jurisdiction=AU`, `confidence_weight=0.85`, `content_expectation=intermittent`,
`priority_rank=2` (matching the existing Telstra/TPG/Optus precedent for
this category), **`active=False`** pending the fetch-mechanism resolution
above.

# Registry hygiene finding (disclosed, not fixed — out of scope)

Running `seed_source_registry.py` for real surfaced a **pre-existing**
duplicate-`source_name` defect, unrelated to this mission: `MIT Sloan
Management Review` and `Stanford Social Innovation Review` each exist as 2
rows in the live registry (both `wellness` category). This caused the
seed script's batch UPDATE of the other 140 pre-existing sources to fail
entirely in one command (`ON CONFLICT DO UPDATE command cannot affect row a
second time`) — **this new mission's 19 new INSERT rows were unaffected and
succeeded** (confirmed live in Supabase: all 19 present, correctly shaped).
Flagged per Chief Engineer disclosure duty, not fixed here — it's a
`wellness`-category data-quality issue, a different domain from this
mission's outage-detection scope, and needs its own investigation into
which duplicate row is the stale one before either can be safely removed.

# Mission Status

Implemented and verified as far as this sandbox allows. Parsing logic and
gate logic are both proven correct against real, live-captured data for all
19 companies, including a genuine no-false-positive regression check against
today's real Telstra/Optus state. The one open item is the production fetch
path itself (Cloudflare-blocked from this sandbox, same disclosed class of
gap as Fastly/AEMO) — sources are registered, fully built, and staged
inactive rather than claimed live. Next step: either a live re-test from
the actual production VM, or bundling this into the already-flagged,
Captain-scoped shared firecrawl-fetch-path decision alongside Fastly and
AEMO.
