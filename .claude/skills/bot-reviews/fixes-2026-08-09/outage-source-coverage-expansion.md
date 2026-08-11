---
title: Outage detection source coverage — Australian critical infrastructure & global tech outages
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: PROPOSAL ONLY — no sources added, no code changed
---

# Outage detection source coverage — gap analysis & expansion proposal

## Mission Summary

Following tonight's real outage-detection work (Cloudflare impact-field fix,
outage-push durable logging), the Captain asked: what is our actual source
coverage for (1) Australian critical infrastructure and (2) global tech
outages, and how should we expand it. This is research + design only —
nothing below has been implemented or added to the live registry.

## Method

1. Read `tools/intelligence/sources_live.csv` in full (131 data rows).
2. Queried live Supabase `intelligence_source_registry` directly (138 rows)
   and diffed it against the CSV by `source_name`.
3. Read `intelligence/ingestion/api_adapter.py`, `rss_adapter.py`,
   `scrape_adapter.py` in full to confirm what adapter types/parsers exist.
4. Read `intelligence/classification/classifier.py` (CPS230/banking_relevance
   logic) and `intelligence/classification/source_tier.py` (domain-authority
   tiering) in full.
5. Live-verified (via WebSearch + direct `curl`/WebFetch against the actual
   endpoints, not assumption) which candidate sources are real Statuspage.io
   JSON APIs, which are custom formats, and which don't exist at all.

---

## Finding 0 — registry drift (found while checking, not asked for, disclosed per Chief Engineer duty)

The live Supabase `intelligence_source_registry` has **7 sources that exist
in the database but are absent from the tracked
`tools/intelligence/sources_live.csv`**, all in `cloud_technology`:
Anthropic (Claude) Status, Supabase Status, Vercel Status, Notion Status,
OpenAI Status, DigitalOcean Status, Twilio Status. These appear to have been
added directly to the live DB (likely by a concurrent session tonight) without
the CSV/seed-script sync step that `cloudflare-noise-filter.md` explicitly
followed for its own registry change. Not a regression I'm fixing here — just
disclosed, since "check the CSV against the live DB, note drift" was
explicitly asked for and this is real drift, consistent with the standing
pattern flagged in prior SUOC governance-fragmentation reviews.

Also notable: `intelligence/classification/source_tier.py` (a separate,
domain-based URL tiering table used for signal provenance) already lists
`acma.gov.au`, `telstra.com.au`, `optus.com.au`, `tpgtelecom.com.au`, and
`vodafone.com.au` as **Tier 1 — Primary/Authoritative** domains. But no
`acma.gov.au` source exists anywhere in `intelligence_source_registry` — the
platform is configured to trust ACMA content highly if it ever arrives, but
nothing currently makes it arrive. This is a config-anticipates-a-source-that-
was-never-added gap, distinct from a coverage gap.

---

## Focus Area 1 — Australian critical infrastructure

### What exists today

| Sub-domain | Registered source(s) | Real / structured? |
|---|---|---|
| Energy | AEMO NEMweb Market Notices (`scrape`, active, 0.97) | **Real** — official AEMO data-dissemination directory, confirmed HTTP 200 with real notices. Second AEMO source (AEMO Market Notices, `aemo.com.au/market-notices`) exists but is deactivated (403 bot-blocked; confirmed firecrawl bypasses it, adapter doesn't support firecrawl yet). |
| Telecom | Telstra Service Alerts (`scrape`, active) — adapter fails loudly, no real feed exists behind it (confirmed 2026-07-08, still true). TPG Telecom Service Status (`rss`, active, real working feed). Optus Network Status (`scrape`, **deactivated**, times out). | **Partial** — TPG genuinely covered; Telstra/Optus are not, by design (loud failure, not fabrication). |
| Water | *(none registered)* | **Gap.** No source of any kind. |
| Transport | Melbourne Airport, Sydney Trains Alerts (both `scrape`, active); PTV Disruptions and Transurban both deactivated (bot-blocked/404). | **Thin** — 2 active, both scrape-only, low structure. |
| Banking/finance infrastructure | APRA Publications/Media Releases/Consultations, RBA (mostly deactivated — SSL failures), ASX Operational Notices (deactivated, 404), AusPayNet Insights (active, scrape) | **Regulatory-document coverage is real** (APRA/ASIC/ASD/OAIC all genuinely scraping official regulator pages). **Real-time payment-system-outage coverage does not exist** — no NPP (New Payments Platform), no bank-specific incident feed. RBA's own payments-oversight RSS is deactivated (SSL cert failure, flagged as environment issue, never re-verified). |
| Government digital services | *(none registered)* | **Gap.** No myGov/Services Australia/digital.gov.au source. |

### Is CPS230/banking_relevance backed by real dedicated sources, or incidental keyword matching?

Checked `intelligence/classification/classifier.py` directly (lines
127–282). **It is keyword matching**, not source-specific: `cps230_relevance`
and `banking_relevance` are computed from a keyword list (`_CPS230_HIGH`,
`_CPS230_MEDIUM` — "cps 230", "operational resilience", "material service
provider", etc.) run against the text of **any** ingested item, regardless of
source. It will fire correctly on genuine APRA-sourced content (since APRA
publications are real, dedicated, high-confidence sources already in the
registry — that part is real), but it will equally fire on an ABC News
Business article that happens to use the phrase "operational resilience," and
it cannot fire at all on a real APRA/bank operational incident that never
gets published anywhere the platform scrapes. The framing is real (APRA
publications are genuinely ingested), the detection mechanism riding on top
of it is generic keyword classification, not a dedicated
incident/advisory feed. There is no CPS230-specific structured feed (APRA
does not publish one) — this is a **fundamental gap in what's ingestable**, not
a bug in the classifier.

### Research: what real structured AU critical-infrastructure sources exist

- **ACMA outage registers (new, materially changes the picture).** Since
  30 June 2026 ACMA requires all telcos to publish/link resolved-outage
  registers on their own websites (Telecommunications Customer
  Communications for Outages Standard amendment). Confirmed live:
  `https://www.telstra.com.au/outages/outage-register` and
  `https://www.optus.com.au/living-network/service-status/national-outage-register`
  both exist and are new since the July 2026 Telstra investigation (which
  only checked the *live* outage-checker page, `/outages`, not this
  register). **Caveat, checked live:** Telstra's register page is a search
  form, not a static list — no visible table/rows in the raw HTML, no
  CSV/API mentioned. This is a genuine capability the platform doesn't yet
  have, but it is **not** a drop-in RSS/API fix; it needs a real
  interaction-capable fetch (likely firecrawl, same class of tool already
  proven necessary for AEMO's bot-blocked page) to confirm whether search
  results render server-side. Flagging as "investigate further," not
  "ready to wire up."
- **ACMA itself** — no outage/incident RSS or API of its own found. ACMA is
  a regulator, not an operator; it doesn't run a live status feed. (This
  matches the existing `source_tier.py` anticipation of `acma.gov.au` as
  Tier 1 for whatever *does* get published there — e.g. enforcement actions,
  consultations — just not real-time outage data.)
- **Water utilities** (Sydney Water, Melbourne Water, SA Water) — no public
  RSS/API found for any of the big three. State-based, fragmented,
  web-page-only. Confirms this is a real, structured-source-free gap.
- **NPP (New Payments Platform)** — no public status page/API found. RBA's
  own payments RSS is registered but currently deactivated (SSL issue).
- **Government digital services (myGov, Services Australia)** — no official
  status.gov.au-style page found; only third-party outage trackers
  (isitdownrightnow-style sites), which are exactly the kind of unverified
  Tier-4 source this platform already deliberately avoids.

**Bottom line for Focus Area 1:** the platform's Australian-finance framing
(CPS230/banking_relevance) is real in the sense that APRA/ASIC/ASD are
genuinely, structurally ingested — but it is keyword classification riding on
general regulatory-document scraping, not a dedicated incident feed, because
no dedicated AU critical-infrastructure incident feed exists to plug in for
most sub-domains (water, telecom real-time, NPP, gov digital services). AEMO
is the one genuine exception — a real official structured source, already
registered and active.

---

## Focus Area 2 — global technology outages beyond Cloudflare

### What exists today (post-drift-reconciliation)

`cloud_technology` category has 26 live DB rows (19 in the tracked CSV — see
drift finding above). Confirmed live and reachable by direct HTTP fetch
tonight:

- **AWS** (global + Sydney region), **Azure**, **GCP** — all registered,
  active, `rss`/Atom only. **None carry a structured severity field over
  RSS.** Confirmed live: Azure's feed
  (`azurestatuscdn.azureedge.net/en-us/status/feed/`) is plain title+
  description RSS, no impact/severity field. AWS is the same shape (per
  existing registry notes). **GCP is different and better than assumed**:
  `https://status.cloud.google.com/incidents.json` is a real, live JSON
  endpoint (confirmed HTTP 200, non-Statuspage schema) carrying genuine
  `severity` (low/medium/high/critical) and `status_impact`
  (SERVICE_INFORMATION/SERVICE_DISRUPTION/SERVICE_OUTAGE) fields per
  incident — GCP is already registered as `rss` when a real severity-bearing
  JSON API exists for it, exactly the same situation Cloudflare was in
  before tonight's fix, just a different (non-Statuspage) JSON shape.
- **GitHub, Slack, Atlassian, Canva, DocuSign, Zoom, Oracle OCI, Salesforce,
  Miro** — registered. Most are genuine Atlassian Statuspage-powered pages
  per their own registry notes but still on the `rss`/Atom variant, same
  structural gap Cloudflare had before tonight (flagged explicitly as a
  known follow-up in `cloudflare-noise-filter.md`, not yet executed for
  these).
- **Missing entirely:** Fastly, Akamai — both live-checked tonight, both
  real Statuspage.io-format status pages, neither registered anywhere in
  the CSV or DB.
- **Tier-1 backbone/transit providers** (NTT, Lumen/Level3, Cogent, Arelion/
  Telia, GTT) — researched, no public structured status pages found for any
  of them. These are wholesale carriers with no consumer-facing dashboards;
  this is a genuine "no good source exists" gap, not an oversight.

### Live verification of the two new candidates

- **Akamai** (`https://www.akamaistatus.com/api/v2/incidents.json`) —
  confirmed HTTP 200 via direct `curl` with the same UA string
  `api_adapter.py` uses, real Statuspage v2 JSON, 50 incidents returned,
  `impact` field present (`none`/`minor`/`major`/`critical`, same vocabulary
  as Cloudflare). **This is a clean, zero-new-code fit** — `api_adapter.py`'s
  existing dispatch already matches any endpoint ending `/incidents.json` and
  routes it through `_parse_statuspage_incidents`, the exact function built
  for Cloudflare tonight. Registering Akamai is a **pure registry-row
  addition**, no code change.
- **Fastly** (`https://www.fastlystatus.com/api/v2/incidents.json`) — same
  Statuspage v2 format confirmed via documentation, but **live-checked
  tonight and currently returns HTTP 403** to both the WebFetch tool and a
  direct `curl` with realistic headers (redirects 302 → 403 on the final
  hop). This is the same class of bot-blocking already seen and solved once
  for AEMO Market Notices (firecrawl bypasses it; `api_adapter.py`/
  `scrape_adapter.py` don't have a firecrawl fetch path yet — flagged in the
  registry notes as a known, not-yet-built capability). Fastly should be
  **registered but left inactive** with this exact caveat noted, same
  pattern already used for AEMO Market Notices, pending either (a) the
  firecrawl fetch path getting built, or (b) a live re-test from the actual
  VM (this sandbox's egress IP may simply be rate-limited/blocked
  differently than the production host — worth a real re-check before
  assuming it's permanently blocked).

---

## Adapter fit assessment

Read `intelligence/ingestion/base_adapter.py`, `api_adapter.py`,
`rss_adapter.py`, `scrape_adapter.py`, `github_markdown_adapter.py` in full.
Four adapter types exist, selected by `source_type`: `rss`, `api`, `scrape`,
`github_markdown`. There is **no dedicated "statuspage" adapter type** —
Statuspage JSON is just one of several dispatch branches inside the generic
`api` adapter (`_parse_statuspage_incidents`, matched by endpoint suffix, not
a hardcoded source list). This means:

- Any source with a real Statuspage.io `/api/v2/incidents.json` endpoint
  (Akamai, and any future migration of GitHub/Atlassian/Canva/DocuSign/Zoom/
  OCI/Salesforce off their current RSS variant) is a **two-field registry
  change** (`source_type: rss → api`, set `api_endpoint`), zero new code —
  exactly the pattern proven end-to-end tonight for Cloudflare.
- GCP needs a **new small parser method** (`_parse_gcp_incidents`, modeled
  directly on `_parse_geoscience`/`_parse_cisa_kev` — same effort class,
  maybe 20 lines) because its JSON shape genuinely differs from Statuspage
  (`severity`/`status_impact` fields, not `impact`). Moderate work, not
  "new adapter type" work — same file, same pattern, one more dispatch
  branch.
- Fastly is adapter-ready (same `_parse_statuspage_incidents` path) but
  blocked on the firecrawl-fetch-path gap already known from AEMO — that gap
  is genuinely "extra scope," shared infrastructure work, not specific to
  Fastly.
- Telstra/Optus outage-register pages, water utilities, myGov — none of
  these have a machine-readable format at all right now; any coverage there
  would be `scrape` adapter at best (lower confidence per the adapter's own
  documented convention), and for Telstra's register specifically, likely
  blocked by the same JS-search-form problem the current `/outages` page
  already has.

---

## Prioritized recommendations

**Tier A — clean fit, register only, no code change, do first**

1. **Akamai Status** (`cloud_technology`) — real live Statuspage v2 API,
   confirmed reachable tonight, `impact` field present. Same adapter path as
   Cloudflare. Zero engineering cost beyond a registry row + one live
   ingestion smoke test. Closes the most obvious "Cloudflare-but-not-Akamai"
   gap the Captain named directly.
2. **Migrate the already-registered, confirmed-Statuspage sources off
   RSS/Atom onto their `/api/v2/incidents.json` endpoints** — this is not a
   new source, it's finishing the work `cloudflare-noise-filter.md` already
   flagged as a scoped-out follow-up. Candidates needing individual live
   verification before flipping (per that document's own caution): GitHub
   Status, Atlassian Status, Canva Status, DocuSign Status, Zoom Status,
   Oracle (OCI) Status, Salesforce Trust Status. Each is a 2-field change +
   a live check, same as Cloudflare's fix.

**Tier B — real structured source confirmed, needs a small new parser**

3. **Google Cloud Status → migrate `rss` to `api`** against
   `status.cloud.google.com/incidents.json`, with a new
   `_parse_gcp_incidents` method mapping `severity`/`status_impact` into the
   same `[Impact: <level>]` tag convention `filter.py` already reads for
   suppression. This gets GCP the same "critical/major only" signal quality
   Cloudflare has, for AWS/Azure/GCP's third member — genuinely closes a
   "break the internet" detection gap (GCP outages are exactly the kind of
   event this whole effort is about). Moderate effort: one parser method,
   one filter-rule check that the GCP severity vocabulary maps sensibly onto
   the existing suppression thresholds (it won't map 1:1 to
   none/minor/major/critical — needs a deliberate mapping decision, not just
   a copy-paste).

**Tier C — real source, but requires the not-yet-built firecrawl fetch path (shared infra work, not source-specific)**

4. **Fastly Status** — register `source_type=api` but leave **inactive**
   with the 403 caveat recorded (same convention as AEMO Market Notices).
   Activate once a firecrawl fetch path exists in `api_adapter.py`/
   `scrape_adapter.py` — which would *also* unblock AEMO Market Notices and
   CISC, so this is worth bundling as one piece of shared infrastructure
   work rather than three separate asks.
5. **AEMO Market Notices reactivation** — not new, but directly relevant to
   energy-grid coverage (Focus Area 1): already registered, already
   confirmed real and bypassable via firecrawl, just blocked on the same
   fetch-path gap as #4. Cheap to bundle.

**Tier D — real regulatory change, worth investigating further, not ready to wire up**

6. **Telstra/Optus ACMA-mandated outage registers**
   (`telstra.com.au/outages/outage-register`,
   `optus.com.au/living-network/service-status/national-outage-register`) —
   genuinely new (post-30-June-2026 regulation), genuinely closes the
   "Telstra-class outage has no real feed" gap flagged as unresolved since
   MSN-0339. But live-checked tonight: Telstra's page is a search form with
   no visible static data — needs a proper investigation (possibly
   firecrawl, possibly a hidden JSON endpoint behind the search form,
   inspect network requests) before it's known whether this is even
   scrapeable. Recommend a small, dedicated follow-up investigation, not a
   registry addition yet.
7. **ACMA registration for its own regulatory content** — `acma.gov.au` is
   already Tier-1 in `source_tier.py` but has zero presence in
   `intelligence_source_registry`. Low effort (`scrape`, same pattern as
   ASIC/APRA), doesn't solve real-time outage detection, but is a genuine
   gap in the regulatory category and cheap to close, closing the
   config-anticipates-a-source-that-doesn't-exist mismatch noted in Finding 0.

**No good structured source exists — free-text/lower-confidence only, not recommended to chase further right now**

8. Water utilities (Sydney Water/Melbourne Water/SA Water), NPP/payment-
   system-specific outage status, myGov/Services Australia official status,
   Tier-1 backbone/transit providers (NTT/Lumen/Cogent/Arelion/GTT). None
   have a public structured feed. The only path to any coverage here is
   general news (already covered by the existing media-category RSS
   sources) or unverified third-party outage-tracker sites the platform
   already deliberately excludes as Tier-4/unverified. Not recommended as a
   near-term project; revisit if any of these providers ever launch a real
   public status page.

---

## Cost / governance notes

- **Ingestion volume**: each new active RSS/API source adds at most
  `MAX_ITEMS_PER_SOURCE` (currently 20) items per scheduler run, same as
  every existing source — Akamai/GCP additions are not meaningfully
  different in volume from the sources already live. No rate-limit concern
  identified for Akamai or GCP's public JSON endpoints (no auth, no key,
  same UA-header pattern already used platform-wide).
- **Terms of service**: Statuspage.io-hosted incident JSON is the page
  operator's own public, unauthenticated API, explicitly designed for
  third-party consumption (same basis already relied on for Cloudflare,
  Miro, Salesforce, OCI) — no scraping-ToS concern for Tier A/B items.
  Fastly's 403 is a bot-detection response, not a documented ToS
  restriction — worth a real VM-side re-test before assuming it's blocked
  by policy rather than by this sandbox's network path.
- **Firecrawl fetch path (Tier C blocker)**: this is a genuine new-capability
  ask (a fetch path that survives bot detection), already implicitly
  approved in spirit by the AEMO Market Notices registry note
  ("Reactivate once the adapter gets a firecrawl-backed fetch path") but
  never built. Flagging explicitly per the Chief Engineer escalation rule —
  this touches the shared `api_adapter.py`/`scrape_adapter.py` fetch layer
  used by every source in the registry, so it's a platform-wide decision,
  not a per-source one, and should go to the Captain as its own scoped
  piece of work rather than being bundled silently into a "just add Fastly"
  ask.
- **Registry hygiene**: recommend the CSV/DB sync step
  (`tools/intelligence/seed_source_registry.py` regeneration or equivalent)
  happen as part of whichever session actually implements any of the above,
  to close Finding 0's drift rather than let it compound further.

## Mission Status

Advisory / research only, as commissioned. No sources added, no registry
rows changed, no code touched. Ready for Captain sign-off on which tier(s)
to authorize for implementation.
