---
title: Outage detection source coverage — implementation of Captain-approved items
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: IMPLEMENTED, pushed
supersedes: outage-source-coverage-expansion.md (proposal)
---

# Outage detection source coverage — implementation report

## Mission Summary

The Captain approved proceeding with the source-coverage expansion proposed
in `outage-source-coverage-expansion.md`. This mission implemented the five
achievable items (no new infrastructure required) and confirmed the
items requiring new infrastructure remain correctly out of scope.

Commits (both pushed to `origin/main`):
- `8e3db995` — CSV/DB drift fix + Akamai + 5 Statuspage migrations + ACMA
- `cc59f46c` — GCP custom parser + migration

## Item 1 — CSV/DB registry drift fix

**Confirmed exact list from the proposal doc** (re-verified live against
Supabase, not re-guessed): 7 sources existed in `intelligence_source_registry`
but were absent from `tools/intelligence/sources_live.csv` — **Anthropic
(Claude) Status, Supabase Status, Vercel Status, Notion Status, OpenAI
Status, DigitalOcean Status, Twilio Status**. All 7 in `cloud_technology`,
all `source_type=rss`, added 2026-08-09 (a prior session), added directly to
the live DB without the CSV sync step.

**Fix**: pulled the exact live field values for all 7 via direct SQL query
against Supabase (`url`, `rss_url`, `source_type`, `jurisdiction`,
`confidence_weight`, `active`, `notes`, etc.) and wrote them verbatim into
both `tools/intelligence/sources_live.csv` and
`tools/intelligence/seed_source_registry.py`'s `SOURCES` list — preserving
the CSV-is-canonical-input convention documented in that script's own
header (`seed_source_registry.py` is meant to be *generated from* the CSV,
not hand-diverge from it; both files now carry identical field values for
all 7 rows).

**Verification**: CSV row count went from 131 → 140 (7 drift + Akamai +
ACMA, see items 2/5 below). Full `source_name` diff between the CSV and a
live `select source_name from intelligence_source_registry` query confirms
identical sets (140 = 140, same two pre-existing duplicate names on both
sides — see "Findings not fixed" below).

**Bug found and fixed along the way**: `seed_source_registry.py`'s
`_upsert()` function normalises `content_expectation`/`useful_life_days`
with `setdefault()` before a batch POST, but not `terms_reviewed`/
`content_source` — ~36/140 `SOURCES` entries set those two keys explicitly
(the ORI curated-digest rows) and the rest omit them. PostgREST's batch API
rejects a batch where objects don't share an identical key set
(`PGRST102 "All object keys must match"`), so **a full run of this script
was silently failing on every row except brand-new inserts** before this
fix. Added the same `setdefault()` pattern for both keys. This is a
genuine, previously-latent correctness bug (not introduced by this
mission), fixed because task 1 explicitly required the sync mechanism to
actually work end-to-end.

Given that bug plus a second, unrelated pre-existing issue (two duplicate
`source_name` rows — see below — which break the script's merge-duplicates
upsert differently, by mapping two distinct SOURCES entries onto the same
existing `source_id`), a full bulk run of `seed_source_registry.py` against
production was **not** used to push these changes. Instead, every row this
mission touched was verified individually against the live DB via targeted
SQL (new-row upserts for Akamai/ACMA already succeeded via the script
before the duplicate-name error surfaced; the 6 migrated rows were updated
directly via SQL after confirming their target values matched
`seed_source_registry.py` exactly). The `_upsert()` fix is left in place
for whenever the duplicate-name issue is separately resolved and a full
run becomes viable again.

## Item 2 — Akamai Status (Statuspage API)

Re-verified live 2026-08-10 (proposal's claim held): `https://www.akamaistatus.com/api/v2/incidents.json`
returns real HTTP 200, genuine Statuspage v2 JSON, 50 incidents, real
`impact` field (42 minor, 8 none in the sampled window).

Registered as `source_type=api`, `api_endpoint` set directly to the
incidents.json path, `active=True`, `confidence_weight=0.88` (matched to
Cloudflare Status — same class of CDN/edge infrastructure dependency risk,
same data quality). Zero new code required — dispatches through the
existing `_parse_statuspage_incidents` (the exact function built for
Cloudflare), matched by the generic `endpoint.endswith("/incidents.json")`
check already in `api_adapter.py`.

**End-to-end verification** (real `APIAdapter` → `classify()` →
`should_suppress()` chain, not simulated): `health status: ok |
items_retrieved: 20`. 0/20 surfaced, 20/20 suppressed
(`status_page_low_impact_none`×6, `status_page_low_impact_minor`×14) — all
genuinely minor/none-impact in this window, correctly suppressed with a
real, auditable `[Impact: ...]` tag and reason.

## Item 3 — Migrate registered Statuspage-format sources to JSON API

**Confirmed exact list from the proposal doc**: GitHub Status, Atlassian
Status, Canva Status, DocuSign Status, Zoom Status, Oracle (OCI) Status,
Salesforce Trust Status.

**5 of 7 migrated** (live-verified individually before flipping, per the
proposal's own caution):

| Source | Endpoint verified | Impact distribution (sampled) |
|---|---|---|
| GitHub Status | `githubstatus.com/api/v2/incidents.json` | 27 minor, 10 critical, 10 major, 3 none |
| Atlassian Status | `status.atlassian.com/api/v2/incidents.json` | 26 none, 6 major, 1 minor, 1 critical |
| Canva Status | `canvastatus.com/api/v2/incidents.json` | 27 major, 13 minor, 8 critical, 2 none |
| DocuSign Status | `status.docusign.com/api/v2/incidents.json` | 44 minor, 5 none, 1 major |
| Zoom Status | `zoomstatus.com/api/v2/incidents.json` | 36 minor, 14 none |

All 5: `source_type` `rss`→`api`, `api_endpoint` set, `rss_url` left in
place as a documented fallback (unused by the `api` adapter path, same
convention as Cloudflare). Zero new code — same generic
`_parse_statuspage_incidents` dispatch.

**2 of 7 NOT migrated — found to be misclassified in the proposal, disclosed
rather than forced:**

- **Salesforce Trust Status** — the proposal grouped it with the RSS-to-API
  candidates, but it's **already** `source_type=api` (migrated in a prior
  session to `https://api.status.salesforce.com/v1/incidents/active`) with
  its own dedicated `_parse_salesforce()` parser in `api_adapter.py`. Its
  genuine public Statuspage-format endpoint
  (`status.salesforce.com/api/v2/incidents.json`) was tested live and
  returns **HTTP 403 `{"error":"Direct API access not allowed"}`** —
  Salesforce deliberately blocks that path. Its current custom-API setup is
  the best available and was left unchanged.
- **Oracle Cloud (OCI) Status** — the proposal assumed this was a real
  Atlassian Statuspage page (same naming convention). Live-tested:
  `ocistatus.oraclecloud.com/api/v2/incidents.json` returns **HTTP 404**.
  It is genuinely not Statuspage-hosted — its real structured API is a
  custom Oracle format at `/api/v2/components.json`
  (`{"realm":..., "regionHealthReports":[...]}`), a materially different
  shape requiring its own dedicated parser (same effort class as the GCP
  work in item 4, not a 2-field registry change). Left on its currently
  working `/api/v2/incident-summary.rss` feed (re-confirmed live, HTTP
  200), flagged as a genuine future follow-up rather than forced through
  the wrong code path.

**End-to-end verification** for all 5 migrated sources, real production
pipeline: surfaced/suppressed counts and real `[Impact: ...]` tags
confirmed per-source (see commit `8e3db995` message for full detail); e.g.
GitHub correctly surfaced 8/20 including real critical/major incidents,
Atlassian correctly suppressed 19/20 (mostly `none`-impact).

## Item 4 — Google Cloud Status → real API (new parser)

Confirmed live 2026-08-10: `status.cloud.google.com/incidents.json` returns
real HTTP 200 JSON, genuinely different shape from Statuspage (bare array,
no `incidents` wrapper key, `severity` low/medium/high/critical +
`status_impact` SERVICE_INFORMATION/SERVICE_DISRUPTION/SERVICE_OUTAGE
fields instead of a single `impact` field) — matches the proposal's
finding exactly.

Built `_parse_gcp_incidents()` in `intelligence/ingestion/api_adapter.py`
(~65 lines including the mapping-rationale docstring, close to the
proposal's ~20-line estimate for the parsing logic itself). Dispatched by
source name (`"google cloud status" in name`), checked **before** the
generic `/incidents.json` → `_parse_statuspage_incidents` branch — required
because GCP's endpoint also ends in `/incidents.json` and would otherwise
be silently routed through the wrong parser (no `impact` field → every item
tagged `unknown`, wrong title field entirely).

**Deliberate severity mapping** (not a 1:1 vocabulary copy, per the
proposal's own caution), onto the same `[Impact: none/minor/major/critical]`
tag `filter.py` already suppresses on:
- `SERVICE_INFORMATION` → `none` (informational notice, not a real disruption)
- `SERVICE_OUTAGE` → `critical` (a full outage is always high-signal regardless of GCP's own severity label)
- `SERVICE_DISRUPTION` → `major` if `severity` in (high, critical) else `minor`
- Unrecognized `status_impact` → derived from `severity` alone, `unknown` (fail-open) if neither is set

No `filter.py` changes needed — the new parser reuses the exact suppression
rule built for Cloudflare Status by emitting the same tag convention.

**End-to-end verification** against real live data: 4 real incidents in
the current window (3 `SERVICE_DISRUPTION`/`medium` severity → correctly
mapped to `minor`, 1 `SERVICE_INFORMATION` → correctly mapped to `none`),
all 4 correctly suppressed as `status_page_low_impact_*` with a real,
inspectable `[Impact: ...]` tag in `raw_summary`. Mapping logic validated
against real production data, not a synthetic test.

Registry: `source_type` `rss`→`api`, `api_endpoint` =
`https://status.cloud.google.com/incidents.json`, live DB row updated to
match.

## Item 5 — ACMA registration

Confirmed via `source_tier.py`: `acma.gov.au` is Tier-1 domain-authority
alongside `asic.gov.au`/`apra.gov.au`/`rba.gov.au`, but had zero presence in
`intelligence_source_registry` — exactly the gap the proposal flagged.

**Feed research**: no RSS or API found for ACMA (WebSearch confirmed —
ACMA offers a media-releases page and an email-subscription newsletter,
nothing machine-readable). Registered as `source_type=scrape` against
`https://www.acma.gov.au/media-releases`, `category=regulatory`,
`priority_rank=1`, `confidence_weight=0.90` (matched to the ASIC/APRA/OAIC
family of regulatory scrape sources in the same category, all in the
0.90–0.97 range).

**Registered inactive, honestly disclosed**: this sandbox's network cannot
reach `acma.gov.au` at all — TLS handshake completes, then the connection
hangs/times out (`HTTP 000`, both via direct `curl` and the `WebFetch`
tool), not a `403`. This matches the pattern already documented for other
Akamai/CDN-fronted `.gov.au` sources in this same registry (RBA, NSW SES —
both flagged "likely environment issue, investigate on VM"). Registered
inactive with that exact caveat rather than guessing at reachability;
activate after a real fetch attempt from the production VM confirms the
page is scrapeable.

## Confirmed correctly out of scope (not attempted, per explicit instruction)

- **Fastly Status** — re-tested live 2026-08-10: `fastlystatus.com/api/v2/incidents.json`
  still returns `HTTP 403 "Invalid request blocked (v1)"` after following
  redirects. Confirmed still blocked; needs the firecrawl fetch path
  (shared infrastructure gap, not source-specific).
- **AEMO Market Notices reactivation** — re-tested live 2026-08-10:
  `aemo.com.au/market-notices` still returns `HTTP 403` (Cloudflare bot
  challenge page). Confirmed still blocked, same firecrawl-fetch-path gap.
- **Telstra/Optus ACMA-mandated outage registers** — not investigated
  further this session, per instruction; the proposal's assessment (real
  regulatory change, but Telstra's register page is a JS search form with
  no visible static data, needs dedicated investigation before it's known
  to be scrapeable) stands as the current state of knowledge.

## Findings disclosed but not fixed (out of this mission's scope)

- **Two pre-existing duplicate `source_name` rows** in both
  `sources_live.csv` and the live DB: "Stanford Social Innovation Review"
  and "MIT Sloan Management Review" (wellness/media categories), each
  appearing twice. Confirmed pre-existing via `git show HEAD:...` — not
  introduced by this mission. These duplicates are what broke a full
  `seed_source_registry.py` bulk run (`ON CONFLICT DO UPDATE command
  cannot affect row a second time`, since both entries with the same name
  resolve to the same existing `source_id` within one upsert batch).
  Flagged for a future dedicated cleanup — unrelated to outage-source
  coverage, and out of scope to fix silently inside this mission given a
  concurrent session was working nearby in the same repo.

## Files changed

- `tools/intelligence/sources_live.csv` — 7 drift rows added, Akamai +
  ACMA rows added, 6 sources migrated to `api` source_type
- `tools/intelligence/seed_source_registry.py` — mirrors all of the above;
  `_upsert()` bug fix (terms_reviewed/content_source key normalisation);
  header count 131 → 140
- `intelligence/ingestion/api_adapter.py` — new `_parse_gcp_incidents()`
  method + dispatch check; module docstring updated
- Live Supabase `intelligence_source_registry` — all of the above applied
  as data-only changes (2 new rows via the seed script's insert path, 6
  existing rows updated via targeted SQL after the script's bulk-update
  path hit the pre-existing duplicate-name bug)
- No changes to `intelligence/classification/filter.py` — GCP and all
  migrated Statuspage sources reuse the existing `[Impact: ...]`
  suppression rule unchanged

## Mission Status

Implemented and pushed (`8e3db995`, `cc59f46c`). All 6
migrated/added-with-code sources (Akamai, GCP, GitHub, Atlassian, Canva,
DocuSign, Zoom) verified end-to-end through the real production
ingestion → classification → suppression pipeline against live data, not
simulated. Salesforce and OCI investigated and correctly left unchanged
with reasons disclosed. ACMA registered inactive with an honest
environment-limitation caveat. Fastly/AEMO/Telstra-Optus confirmed still
correctly out of scope. Two pre-existing unrelated data-quality issues
(duplicate source names, a latent seed-script bug) found and the bug
fixed; the duplicates flagged, not fixed, as out of scope.
