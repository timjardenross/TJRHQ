# Forward-looking sources: planned maintenance in AU telecom, energy and government services (2026-11-24)

Status: parsers built and tested offline; six registry rows staged `active=False`; nothing activated, no flags, no writes, no deployments.
Branch `claude/forward-sources-maint-2kq`. Builds on the dated-events extractor (`claude/forward-dated-2kq`), which this branch does not contain.

Method: plain fetches through the agent proxy (allowlisted hosts only, no bypass), 13 Firecrawl calls (of 20), SELECT-only reads of project `cjvrpjwewsrumnbdydgg`
(`intelligence_source_registry`, `intelligence_events`). "Volume" is windows per month as observed on 2026-11-24.

## Findings by source

| Source / observed URL | Free and compliant | Structure | Volume | Firecrawl cost | Dates provided | Recommendation |
|---|---|---|---|---|---|---|
| ATO status osfa, osb, pls: `https://{osfa,osb,pls}.status.ato.gov.au/api/v2/scheduled-maintenances.json` (plain fetch, HTTP 200 for all three) | Yes. Public JSON, same Statuspage API already collected for incidents | Statuspage JSON, 50 windows each (20 to 23 scheduled, into Oct/Nov 2027) | osfa/osb/pls 3 to 8 per month recently; 1 to 4 per month in the advance schedule | 0 | `scheduled_for`/`scheduled_until` (ISO, +11:00) and the same dates in words | **Build (done).** Adapter dispatch + 3 inactive rows. Activation is a decision |
| ATO "System maintenance": `https://www.ato.gov.au/online-services/system-maintenance` | Public page; plain fetch gets an Akamai 403 (not bypassed). Read via Firecrawl | HTML table, 17 dated rows to Nov 2027 plus an undated weekly table | 1 to 2 per month | 1/run; once daily = ~30/month | Start and end date, time, AEDT/AEST, type | **Build (done), low priority.** Overlaps the three status feeds (same windows); adds SBR/API-only and integrated-release windows. Not worth the credits until the status feeds are live and a gap is shown |
| ABR "Scheduled site maintenance": `https://www.abr.gov.au/general-information/scheduled-site-maintenance` | Public page. Plain fetch not reachable here (host not allowlisted); Firecrawl worked | Tables per system; ABN table dated (3 rows), others recurring or blank | 1 to 3 per month | 1/run; ~30/month | Day, date, time (AEDT in caption) | **Build (done), optional.** Same ~30 credits/month; ABN registration only |
| myID "System maintenance": `https://www.myid.gov.au/system-maintenance` | Public page, plain fetch 200 | HTML table Impacted service / Start / End; one past row (13 Nov), usually empty | 0 to 1 per month | 0 | Full date, time, AEDT | **Build (done).** Existing registry row (inactive since 2026-11-06 for a failed content check) is untouched; the parser is keyed to its name, so re-activating it is now meaningful. Owner decision to re-activate |
| DVS "Upcoming Scheduled Outages": `https://dvsstatus.idmatch.gov.au/Home/UpcomingScheduledOutages` | Public page. Plain fetch not reachable here; Firecrawl worked | Per document type cards, next 14 days only; Production and Test sections | 2 to 6 per fortnight (WA BDM, test-only visa types) | 1/run; ~30/month | D/M/YYYY start and end with times; **no time zone stated** | **Build (done), optional.** Production only by default. Verifies identity documents behind myID/bank onboarding, not a consumer service |
| AEMO Network Outage Schedule: `https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/network-data/network-outage-schedule`, data `https://www.aemo.com.au/aemo/data/NOS/PUBLIC_NOSDAILY.zip` | Free, AEMO states it is public, updated every 30 minutes, "Bookings up to two years in advance"; disclaimer: TNSP-supplied, may change at short notice. Plain fetch is blocked by a Cloudflare challenge (not bypassed); the proxy does not allow `nemweb.com.au` or `visualisations.aemo.com.au` | CSV in a zip: region, station, equipment, kV, start, end, status (SUBMIT, MTLTP, STLTP, PDLTP, PTP, ISSUES...), constraint set | Hundreds of rows (transmission work, not consumer-facing) | Firecrawl returns the zip as mangled text (1 credit, unusable) | Planned start and end datetimes (NEM time) | **Needs owner decision.** Not built: no real sample CSV could be obtained, and a parser without one would be invented. Needs an allowlist for the AEMO data host or a browser-capable fetch; and a scope call (transmission outages rarely matter to a bank) |
| AEMO Market Notices (already collected, active) | n/a | 526 rows in 90 days, titles only (`raw_summary` null); 141 `[EventId` rows, 114 contingency cancel/reclassify, 15 SA directions, a few forecast MSL/LOR and transfer-limit notices | n/a | existing | Forecast notices carry a date in the title (12 in the sample) | No change. Forecast conditions, not planned outages. The planned-outage list is the NOS above |
| NBN Co: `https://www.nbnco.com.au/support/network-status` (map: "No nbn network outage planned in the next 12 days") and `.../utility/major-significant-local-outages-register` | Public, but the planned list is an address/suburb map lookup; the register covers unplanned Major/Significant outages after the event | Map tiles and a register table with start/end dates of past outages | Register ~3 per month, all retrospective | 0 to 1 | Past outage times only | **Not worth it.** Per-address lookups are out of scope and the public register has no future dates. RSPs get a planned-outage API; that is a commercial arrangement (owner decision if ever wanted) |
| Telstra: `https://www.telstra.com.au/outages` | Public; outage search is by address or suburb; restored-outage register at `/outages/outage-register` | Search form, no list | n/a | 1 (page has no list) | None | **Not worth it.** Planned mobile works are notified to affected customers and posted by councils; no public dated list. Existing Telstra Service Alerts row stays inactive |
| Optus: `https://www.optus.com.au/living-network/service-status` and the National Outage Register (active) | Public; register is retrospective | Statutory register of past outages | n/a | existing | Past only | **Not worth it.** No public planned-works list found |
| myGov: `https://my.gov.au/en/about/help/mygov-service-disruptions` (existing row, active) | Public; Firecrawl read | One sentence: "We haven't been notified of any maintenance or outages for myGov services." Lists maintenance as it arises | 2 rows in 90 days | existing | Dated notices when present, none today | No change. Already collected; a dated notice will reach the extractor if its text states the window |
| Services Australia (Medicare, Centrelink): `https://www.servicesaustralia.gov.au/customer-service-changes` | Public; Firecrawl read (plain not reachable here) | Temporary service-centre closures only (one WA centre); no system-maintenance list. Past planned downtime was announced via social posts and media | None | 1 | None on this page | **Not worth it** as a source. Site notices page (`/site-notices`) not read |
| DTA / digital.gov.au status | No machine-readable planned-outage page found | n/a | n/a | 0 | n/a | **Not worth it** |

Not checked (hosts not allowlisted in this environment): `sses.status.ato.gov.au`, `bp.status.ato.gov.au`, `status.abr.gov.au` Statuspage endpoints (likely the same shape,
unverified), `info.authorisationmanager.gov.au/system-maintenance` (Relationship Authorisation Manager) and `softwaredevelopers.ato.gov.au/APIsm`, both linked from the ATO page.

## What was built

- `intelligence/ingestion/maintenance_parsers.py`: pure parsers (JSON or HTML in, plain records out). Records: `event_id, source_name, published_at, canonical_url, raw_title,
  raw_summary, window_start, window_end`. `raw_summary` states the window in the page's own words ("Scheduled maintenance from Friday 27 November 2026 11:30 pm AEDT to
  Monday 30 November 2026 7:00 am AEDT (System maintenance)"). Explicit dates only; recurring weekly windows and blank tables are skipped; completed Statuspage windows are
  skipped; no time zone is guessed (DVS carries none; ABR gets AEDT from its own caption).
- Wiring: `api_adapter` routes any `/scheduled-maintenances.json` endpoint to the Statuspage parser (before the incidents dispatch); `scrape_adapter` uses `PAGE_PARSERS` for
  the named page sources. ATO, ABR and DVS pages are on the Firecrawl fallback list and the once-daily list (`scheduler._FIRECRAWL_FETCH_SOURCE_NAMES`) so they cannot be
  swept 8 times a day. `weekly_evidence.source_kind` treats the new agency names as primary.
- Registry (`tools/intelligence/seed_source_registry.py`), all `active=False`, names grepped first and unique: ATO Online Services for Agents / for Business / Practitioner
  Lodgment Service Scheduled Maintenance (api), ATO System Maintenance, ATO ABR Scheduled Site Maintenance, DVS Status Scheduled Outages (scrape). `tests/test_au_source_activation.py`
  was adjusted to allow these sibling rows on the same status-page host.
- Tests: `tests/test_maintenance_parsers.py` (17 cases) with fixtures in `tests/fixtures/maintenance/`. Statuspage JSON (trimmed) and the myID table are real captures. The ATO, ABR
  and DVS HTML fixtures are **reconstructed from Firecrawl markdown** (real `rawHtml` not captured; marked inside each file), so the real markup of those three is untested.

## Checked against the dated-events extractor

Fed the fixtures to `dated_events.extract_events` (the `claude/forward-dated-2kq` version, run locally, not committed here): ATO status, ATO page, ABR and DVS rows all yield
`planned_maintenance` events with the stated dates. Two things for that branch:

1. Its official-source pattern lists `ATO` but not ABR, DVS, myID, myGov or Services Australia, so a source name without one of those words is tiered NEWS and skipped. The new
   names were chosen to match (`ATO ABR ...`, `DVS Status ...`); the existing `myID System Maintenance` row would still be skipped until `myID` is added to `AU_OFFICIAL`.
2. A window that starts and ends on the day the notice is published (the 24 Nov 23:30 ATO window, created 24 Nov 13:33 local) is dropped as not after publication: the known
   same-UTC-day miss, unchanged.

## Decisions for the owner

1. Activate the three ATO status maintenance rows (no cost; also verify `scheduled-maintenances` volume stays ~3 to 8 rows per month per page, each a new row on reschedule).
2. Whether the ATO page, ABR and DVS pages are worth ~30 Firecrawl credits per month each (ATO page duplicates the status feeds; recommend leaving off).
3. Re-activate myID (parser now exists) once `myID` is in the extractor's official-source list.
4. AEMO NOS: allow the AEMO data host or a browser-capable fetch, and decide whether transmission outages are in scope; provide one real CSV for a parser fixture.
