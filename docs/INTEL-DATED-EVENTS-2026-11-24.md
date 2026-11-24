# Forward-looking intelligence: dated future events (2026-11-24)

Status: extractor built and tested, default OFF, not wired into any service. Checklist item "Forward-looking intelligence" (Partial).
**Recommendation: keep it at Partial.** The extraction now works on what we collect, but the regulator and lifecycle classes the item
names are mostly not in the collected text (section 3). Marking it Operational would overstate what the forward watch can see.

## 1. What was built

| Piece | Where |
|---|---|
| Extractor | `tools/intelligence/analytics/dated_events.py` (flag `--enable` or `INTEL_DATED_EVENTS_ENABLED=1`) |
| Fifth forward-watch input "Dated events" | `forward_watch.py --dated-events` (or `INTEL_DATED_EVENTS_ENABLED=1`); adds one section, existing sections and the default output are unchanged (tested) |
| Tests | `tests/test_dated_events.py` (41 cases), existing forward-watch tests in `tests/test_systemic_intel_products.py` |


Record: `{event, date, end_date, time, date_basis, source, evidence_span, kind, uncertainty_label, event_id, published_at, reference_date}`.
`kind` is regulatory, vendor_lifecycle, planned_maintenance or advisory_deadline. Rules, all deterministic:
only dates the text states; "future" means after the item's own publication date; a kind cue is required in the same clause; "Revised on" and
"Published:" dates and past-tense phrasing are skipped; a year-less date takes the publication year and is labelled `INFERRED_YEAR` (never rolled forward a year
if it has passed); relative dates (tomorrow, next Friday, next week) resolve only against a verified publication date (not an aggregator, not later than
collection) and are labelled `RELATIVE_DATE_LOWER_CONFIDENCE`; D/M/YYYY for Australian official sources, ambiguous numeric dates from others skipped;
a later AEMO cancellation removes the matching forecast; news is skipped unless `--include-news`; rows with no `published_at` use the collection date and
only explicit-year dates. AEMO forecast notices are filed under `advisory_deadline` with label `OPERATOR_FORECAST` (the four kinds had no forecast class).

## 2. Run over collected data

Read-only SELECTs (project `cjvrpjwewsrumnbdydgg`), 90 days to 2026-11-24. A SQL pre-filter kept rows whose text holds an explicit date after the row's publication
date, plus a second pre-filter for year-less and relative wording with a cue. The 117 selected rows were copied by hand into JSONL (ids shortened to 8 characters;
Twilio limited to the last 35 days and latest row per title; AEMO a 35-row subset of the dated notices). It is a recall-biased sample of candidate rows, not the whole corpus.

- Emitted 62: planned_maintenance 45 (Twilio 38, Supabase 4, Cloudflare 2, DigitalOcean 1), advisory_deadline 15 (AEMO 12, Cisco 2, ACSC 1), vendor_lifecycle 2 (Google Cloud, CISA/Ivanti).
- Year-less and relative pre-filter found no authoritative item that needed them; both paths are covered by synthetic tests only.
- News enabled: 2 emitted, both wrong (Airbnb rules mis-kinded as regulatory; a veterans cap the government had dropped). News stays off.

**Audit (single reviewer: Claude, who also wrote the extractor; not independent).** 32 items read against their evidence: all 24 non-Twilio items plus every fifth of 38 Twilio items.
Date and existence correct: 32/32. Kind: 12 AEMO forecasts are correct dates but "advisory_deadline" is a convention, not a deadline. Known weaknesses seen: two LOR/MSL notices
published late UTC on the stated local day count as future (UTC versus AEST); duplicate AEMO notices for one condition appear as two events. Precision on a mostly structured, easy sample is not
a general figure. **Recall was not measured.** Known misses: a maintenance window that began before publication (Akamai), an ambiguous numeric date (Twilio TNX-DE1 `02/12/2027`),
same-UTC-day windows (ATO 24 Nov), and events outside the four kinds (iTnews retreat, ex-dividend dates).

## 3. Next 30 days (to 2026-12-24) and what the sources cannot supply

From collected data, 16 events, all provider maintenance: Twilio 12 (carrier work 24 Nov to 3 Dec, plus 6 Dec UK), Supabase 4 (30 Nov, 8 Dec, two on 9 Dec). **No regulatory, vendor lifecycle or advisory deadline falls in the window.**
Just beyond it: Google Cloud Application Integration requirement 15 Jan 2027, Cisco next advisory publication 20 Jan 2027, Twilio TNX-AU1 22 Jan 2027, Ivanti Connect Secure 22.8 end of life 31 Jan 2027.
Not in the database: ATO status scheduled maintenance, 3 windows in the window (27 Nov, 5 Dec, 12 Dec), see below.

| Class | Why the current sources cannot supply it |
|---|---|
| APRA and Treasury consultation closing dates | Collected (APRA Consultations 25 rows, Treasury 20) but title only, `published_at` NULL. The date is on the detail page ("Consultation is now open, until 2 October 2026", seen on 3 APRA pages; all three already closed). Needs a detail-page fetch: a collection change, not done. |
| APRA Publications/Media, ASIC | APRA Publications and Media Releases are titles with NULL dates; ASIC News Centre 4 rows ever, ASIC Enforcement 0, no ASIC consultation source; ASIC appears only through a Google News aggregator (titles). RBA Media Releases 0 rows. |
| CISA KEV due dates | KEV rows hold the description only (103 rows, 0 due dates). |
| Microsoft/MSRC | 54 rows titled like "June 2022 Security Updates", empty text, no dates. |
| Vendor end-of-life calendars | Not collected (Microsoft lifecycle, Cisco EoX, cloud deprecation notices). End-of-life dates appear only when an advisory mentions one (Ivanti via CISA). |
| AEMO | Notices are titles; forecasts cover days, not weeks; AEMO NEMweb rows (905) are file names. No planned-outage schedule. |
| AU telecom, energy, payments maintenance | Telstra Service Alerts inactive; NBN 1 row, myID 2 rows, none with a future date; AusPayNet Insights are articles. |
| ATO status scheduled maintenance | `https://osfa.status.ato.gov.au/api/v2/scheduled-maintenances.json` answers HTTP 200 by plain fetch (22 open windows in `/upcoming.json`, 18 beyond 30 days, into Nov 2027), but only `incidents.json` is collected. `rows_from_statuspage_maintenances` converts the JSON for the extractor; not wired. |

## 4. Use

`python tools/intelligence/analytics/dated_events.py --enable --input rows.jsonl --as-of 2026-11-24 --horizon-days 30 --out events.json` (add `--all` for every event,
`--include-news` for relays). `python tools/intelligence/analytics/forward_watch.py --enable --dated-events --input rows.jsonl --as-of 2026-11-24 --out watch.md`.
Rollback: unset the flag. Cost: CPU only; no LLM and no network in the extractor. This session: SELECTs only, 3 Firecrawl scrapes of existing APRA URLs, one plain fetch of the public ATO status page; no writes, migrations, sources or deployments.

## 5. To reach Operational

1. Fetch APRA/Treasury consultation detail pages (existing sources) and store the page text, so closing dates reach the extractor.
2. Collect the ATO `scheduled-maintenances` endpoint alongside `incidents.json`.
3. Collect a vendor lifecycle feed (Microsoft lifecycle, Cisco EoX) if lifecycle dates matter; keep KEV due dates from the catalogue's `dueDate` field.
4. Second reviewer on a random 100-item sample for precision and a seeded missed-event list for recall.
