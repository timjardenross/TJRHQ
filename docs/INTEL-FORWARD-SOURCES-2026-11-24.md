# Forward-looking source coverage: regulatory dates and vendor lifecycle (2026-11-24)

Branch `claude/forward-sources-regdates-2kq`, draft PR. Closes source gaps found by the dated-events extractor
(`docs/INTEL-DATED-EVENTS-2026-11-24.md`, branch `claude/forward-dated-2kq`). Nothing is activated: the two new registry rows are `active=False`;
the adapter fixes take effect only when the already-active sources next collect. No production writes, flags, deployments or infrastructure.

## Result by class

| Class | Verdict |
|---|---|
| Regulatory deadlines | **Partially closed.** APRA, Treasury, ASIC consultation closing dates and CISA KEV due dates are now obtainable. Not obtainable: commencement dates and CPS 230-type milestones (they live in PDFs, not on any listing or page we fetch), RBA (not examined; 0 rows, activation pending). |
| Technology lifecycle | **Partially closed.** endoflife.date gives dated vendor milestones for 14 default products. Not obtainable free and machine-readable as observed: Cisco (EoL index has no public feed), Ivanti, Citrix, Palo Alto, Oracle roadmaps (not examined beyond endoflife.date coverage of `oracle-jdk`, `oracle-database`, `fortios`, `cisco-ios-xe`). |

## Evidence (observed 2026-11-24)

| Item | URL | What it carries | Volume | Cost | Terms |
|---|---|---|---|---|---|
| APRA consultations | `https://www.apra.gov.au/consultations` (plain fetch, 200) | Teaser pill "Open until 3 February 2027" / "Closed 6 November 2026" **on the listing itself**; no detail fetch needed for closing dates | 145 consultations, 10 per page; 1 open | 0 credits | public pages, no terms read beyond site use |
| APRA news | `/news-and-publications` (plain) | "Published 24 November 2026" per teaser (our rows had NULL `published_at`) | 10 per page | 0 | as above |
| APRA detail | e.g. `/consultations/strengthening-superannuation-investment-governance` | "submissions close on 3 February 2027" in body; no commencement dates | per open item | 0 | as above |
| Treasury | `https://treasury.gov.au/consultation` (proxy blocks plain fetch; Firecrawl) | status + opening and closing date in `<time>` | 1,215 total, 10 per page, 5 open | 2 credits | not read |
| ASIC | `https://www.asic.gov.au/regulatory-resources/regulatory-resources-search?filter=document&type=consultation+paper&superseded=false&sort=lastUpdated` (client-rendered; Firecrawl) | "Date closing: 22/01/2027" per open row | 11 open (24 Nov 2026 to 22 Jan 2027), 456 closed | 1 credit for the landing page (it only points here) plus one render of the search page (credits not reported) | page robots meta is `noindex, nofollow`; not read otherwise |
| CISA KEV | `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` | `dueDate`, `requiredAction`, `vendorProject`, `product`, `knownRansomwareCampaignUse`; adapter kept only name, description, dateAdded | whole catalogue | 5 credits (query format) | public US government data |
| MSRC | `https://api.msrc.microsoft.com/cvrf/v3.0/updates` | 141 updates, all with `DocumentTitle`; no empty titles. The "empty title" finding was empty **text**: the adapter passed `None` as summary. The newest-revised sort also surfaced "Mariner Release Notes" (1999 to 2000 entries re-touched Nov 2026) | 141 | 5 | public |
| endoflife.date | `https://endoflife.date/api/v1/products/<slug>` | `releases[].eolFrom / eoasFrom / eoesFrom` plus vendor `releasePolicy` link; windows-server payload has 20 releases | 489 products | 1 (one product) + 5 (index) | MIT licence stated on the API docs page; v0 API deprecated; no rate limit or caching rule seen (docs page is a Swagger UI, not fully read) |
| Cisco EoL | `https://www.cisco.com/c/en/us/products/eos-eol-listing.html` | index only; "subscribe by email or RSS" via My Notifications (login) | n/a | 5 | not read |

Firecrawl: 11 calls of the 20 allowed, about 35 credits plus the ASIC render (page scrapes 1 credit, "query" format 5; one call, the endoflife Swagger page, returned nothing). Plain fetches: 6 to `www.apra.gov.au` only. The proxy allowlist blocked plain fetches to cisa.gov, api.msrc.microsoft.com, endoflife.date and treasury.gov.au.
Caveat: KEV, MSRC and endoflife index facts came back through Firecrawl's LLM `query` format, so field names and sample values are model-extracted, not byte-verbatim; the windows-server endoflife payload and the Treasury and ASIC pages were read as raw markdown/HTML.

## What changed

- `intelligence/ingestion/forward_dates.py` (new, pure functions): APRA/Treasury/ASIC listing parsers, KEV summary, MSRC filter and summary, endoflife.date milestone records.
- `scrape_adapter.py`: for APRA Consultations / Media Releases / Publications, Treasury and ASIC Consultations, rows now carry "open until <date> (closing date)" and, for APRA news, `published_at`. Open APRA consultations get at most `OR_INTEL_APRA_DETAIL_MAX` (default 3) plain detail fetches per run for "submissions close / commence" sentences. If a parser finds no rows the generic extractor runs as before.
- `api_adapter.py`: KEV keeps the due date, product and ransomware flag and is ordered newest-added first; MSRC drops Mariner notes, orders by initial release, fills the summary (the newest month also states the next Patch Tuesday, labelled as derived from the second-Tuesday rule, never a past date); `endoflife` sources do one GET per slug (`OR_INTEL_ENDOFLIFE_PRODUCTS`, default 14) and emit only milestones within 730 days, stable title per milestone.
- Registry: `ASIC Consultations` and `endoflife.date Vendor Lifecycle`, both inactive. Scheduler: ASIC Consultations joins the once-daily Firecrawl set.
- Tests: `tests/test_forward_dates_sources.py` (20 cases) with fixtures in `tests/fixtures/forward_dates/` (APRA, Treasury, KEV, MSRC, endoflife are real excerpts; **the ASIC fixture is synthetic**, rebuilt from rendered text because live HTML was not captured). Two existing tests that pin the render set and registry kinds were updated for the new ASIC row.
- Ran the new items through the `claude/forward-dated-2kq` extractor offline: consultations, KEV due dates, MSRC and endoflife records all produce dated events. Two edits are needed in that extractor, **not made here** (file not on this branch): drop `Known Exploited` from `EXCLUDED` (it excluded KEV because rows had no due date) and add `endoflife` to `VENDOR`; without them KEV and endoflife rows are skipped and the other sources work as-is.

## Not verified

The ASIC parser has not seen live HTML; verify the first live run. Treasury parser matches the HTML Firecrawl returned, not necessarily what our plain fetch receives (plain fetch is blocked here; Treasury `/consultations` in the registry may redirect to `/consultation`). Volumes after activation are estimates from one snapshot.
