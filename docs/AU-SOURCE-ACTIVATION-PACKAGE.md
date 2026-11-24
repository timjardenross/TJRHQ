# AU Source Activation Package (au-sources-2kq)

Status: DRAFT for approval. The seed script was **not** run against the database.

## Evidence legend

- **observed**: seen directly in this build session (repo files, a command result).
- **documented/unverified**: from the host's published feed convention or the registry's own notes; not confirmed live.

**Reachability (observed):** one `curl -I` per candidate host via the agent proxy. Every HTTPS host returned a proxy `403 Forbidden (agent proxy: no rule or network setting allows this host)` (curl exit 000/56): RBA, Okta, Google Cloud / Workspace status, ACMA, ASX, ATO, cyber.gov.au, APRA, GA, AEMO, NBN, Telstra, USGS, ASIC, Optus. BoM (plain http) returned 403, so BoM is also unreachable from here. TLS and the proxy were not bypassed. No feed content was fetched, so **every feed fact below is documented/unverified**.

## Per-source assessment

| Source | Already in registry (observed) | Feed type | Authority / timeliness / unique value | Cost | Risk | Tier |
|---|---|---|---|---|---|---|
| RBA (media releases) | No. Existing `Council of Financial Regulators` is a different publisher | RSS `rba.gov.au/rss/rss-cb-media-releases.xml` (documented/unverified) | Primary source for the cash rate, payments system and FMI/clearing and settlement announcements. Event-driven, low volume | 0 credits (direct RSS) | Feed path unverified | **activate** (row added, active) |
| Okta | No | Statuspage-style RSS `status.okta.com/history.rss` (documented/unverified) | Identity-provider incidents. Not AU-specific, so needs a relevance check | 0 | Feed path unverified; global incident noise | **pilot** (row added, `active=false`) |
| Google Workspace | No (Google Cloud Status and GCP Security Bulletins exist) | Atom `google.com/appsstatus/dashboard/en/feed.atom` (documented/unverified) | Workspace outages, distinct from GCP | 0 | Feed path unverified; high incident volume | **pilot** (row added, `active=false`) |
| Google Cloud status | Yes: `Google Cloud Status` | - | - | - | - | skip (covered) |
| Telstra | Yes: `Telstra Service Alerts` (scrape, inactive) and `Downdetector AU - Telstra` | scrape / Downdetector | Official page is a scrape needing Firecrawl credits | credits if enabled | Existing decision to keep inactive | skip (covered) |
| Optus | Yes: `Downdetector AU - Optus` | - | - | - | No official Optus status feed known | skip (covered) |
| NBN Co | Yes: `NBN Network Status`, `Downdetector AU - NBN Co` | - | - | - | - | skip (covered) |
| AEMO | Yes: `AEMO Market Notices` (scrape, active), `AEMO NEMweb Market Notices` (inactive) | - | Reactivating NEMweb (a directory listing, cheaper than a scrape) is a separate decision | - | - | skip (covered); NEMweb is a defer candidate |
| ACSC / cyber.gov.au | Yes: `ACSC Advisories`, `ACSC Alerts & Advisories` (RSS) | - | - | - | - | skip (covered) |
| APRA | Yes: `APRA - Speeches and Publications` (RSS), Consultations, Media, Publications, changedetection | - | - | - | - | skip (covered) |
| ASIC | Yes: `ASIC News Centre`, `ASIC Enforcement Activity`, changedetection | - | - | - | - | skip (covered) |
| myID / myGov / ATO DVS | Yes: `myID System Maintenance` (inactive), `myGov Service Disruptions` (active), Downdetector myID/MyGov | - | - | - | - | skip (covered) |
| Geoscience Australia | Yes: `Geoscience Australia Earthquakes` | - | USGS is global, overlaps GA, and adds little AU authority | - | - | skip (covered); USGS defer |
| BoM | Warnings handled by `intelligence/ingestion/emergency_alert_adapters/bom_cap.py` and `bom_warnings.py` (observed in repo) | CAP / XML | - | - | - | skip (covered) |
| ASX | No | No feed I can document with confidence (announcements are a scrape or licensed data) | Operational notices matter for FMI, but would need a scrape | credits | Inventing a feed URL would be unsafe | **defer** |
| ATO online services status | No | HTML status page only, no feed known | Useful for government services but scrape-only | credits | - | **defer** |
| ACMA | No | Possible site RSS, not confirmed | Telecom regulator, low operational urgency | 0 if RSS | Unverified | **defer** (re-test when network is open) |

## Bounded activation decision

- **Approve now:** `RBA Media Releases` (active). **Pilot (staged inactive):** `Okta Status`, `Google Workspace Status`. Nothing else is added, because every other candidate is already covered or lacks a documented machine-readable feed.
- **Expected volume:** RBA about 0-3 items/day (roughly 5-15/month). Okta and Workspace stay at 0 until enabled; each is intermittent, a few incidents per week, capped by `MAX_FEED_ITEMS_PER_SOURCE`.
- **Credit cost:** 0 Firecrawl credits. All three use the existing `RSSAdapter` (direct HTTP), so the Free-plan 1,000-scrape cap is untouched.
- **Code:** no new adapter was needed. `tests/test_au_source_activation.py` uses offline RSS and Atom fixtures through `RSSAdapter` (no network), plus registry dedupe and key-set checks.
- **Before enabling a pilot:** confirm one live fetch returns entries from a network that can reach the host. If the feed path is wrong the row will report `failed` in source health; the fix is to correct `rss_url`, not to use a scrape.
- **Rollout:** run `python tools/intelligence/seed_source_registry.py --dry-run`, review, then seed. Seeding is a separate human-approved step and has not been done here.
- **Rollback:** set `active=false` on the row (`UPDATE intelligence_source_registry SET active=false WHERE source_name IN ('RBA Media Releases','Okta Status','Google Workspace Status');`) and flip `"active": False` in `SOURCES` so a re-seed does not re-enable it. Collected events age out by `useful_life_days`.

## Notes

- `seed_source_registry.py` header counts ("172 sources") were already stale (observed: 130 rows before this change, 133 after); left untouched to keep the diff scoped.
- `sources_live.csv` is a live DB export and was not edited.


## Live verification update (2026-11-24, after the network allowlist)
Observed from the verification container (plain fetch or Firecrawl; the production VM fetches from its own network):
| Source | Result |
|---|---|
| RBA Media Releases | **Verified.** HTTP 200, RSS 1.0; valid but very low volume (one item, 6 Nov 2026). Active. |
| Okta Status `history.rss` | **Not usable.** HTTP 401 / login wall (redirects to `status.okta.com/login`), not a feed. Row removed from this package. |
| Google Workspace Status feed | **Verified but stale.** Valid Atom; last updated 2026-09-25 with one entry. Stays staged inactive (pilot); expect near-zero volume. |
| ATO Online services for agents | **Verified and added.** `osfa.status.ato.gov.au/api/v2/incidents.json`: HTTP 200 JSON, 50 incidents, standard Statuspage shape handled by the existing `/incidents.json` dispatch; plain fetch, 0 credits. Replaces the Okta pilot. |
| ATO business (`osb`) and PLS status pages | Verified via Firecrawl (osb: RSS and JSON, 200); **not reachable from the container** (hosts not on the allowlist), so not added. Allowlist request: `osb.status.ato.gov.au`, `pls.status.ato.gov.au`. |
| ASX | No economical method (company announcements feed is a paid subscription). Genuine gap. |
| ACMA | No RSS (`/rss` returns 404) and no documented machine-readable method. Genuine gap. |
| ASIC | Collection repaired separately (PR on branch `claude/asic-source-repair-2kq`): the newsroom is client-rendered. |
Further hosts blocked from the container: `asic.gov.au` (bare), `www.cyber.gov.au`, `www.cfr.gov.au`, `status.cloud.google.com`.
