# Timestamp provenance and freshness states (v1)

Status: code merged-ready behind a default-OFF flag (`INTEL_PROVENANCE_COLUMNS`). The migration and backfill SQL under
`tools/intelligence/` are drafts and are NOT APPLIED. Absent provenance behaves exactly as before.

## Two separate dimensions

- **Precision** (`published_at_precision`): how exact the time is: `second`, `minute`, `day`, `unknown`.
- **Confidence** (`published_at_confidence`): how far the time can be trusted as the PUBLICATION time: `verified`, `claimed`, `feed`, `unknown`.

An explicit, authoritative publication DATE from a primary source (AEMO notice header) is `verified` at `day` precision. CISA KEV `dateAdded`
is `verified` at `day` precision as a CATALOGUE-ADDITION date (see the label below). Precision never upgrades confidence, and confidence never
upgrades precision. In particular, a verified DATE (`verified` + `day`) is not a verified TIMESTAMP (`verified`/`feed` + `second`/`minute`): only
the latter can count as hour-level freshness or live evidence.

## Date label (`published_at_label`)

What kind of date `published_at` holds: `publication`, `catalogue_addition` or `event`.
CISA KEV `dateAdded` is `catalogue_addition`: it dates the KEV catalogue entry (which is what the report is), NOT the vulnerability's disclosure.
The CVE was disclosed earlier; nothing here implies the disclosure date or the time since disclosure. `event` dates (a date named in a title)
are never publication times.

| Evidence | basis | precision | confidence |
|---|---|---|---|
| Source feed/API timestamp | feed | second | feed |
| AEMO header with time (NEM time converted to UTC) | feed_corrected_utc | minute | feed |
| AEMO header, date only | date_only | day | verified (label publication) |
| CISA KEV dateAdded | date_only | day | verified (label catalogue_addition) |
| Google News pubDate | aggregator_claimed | second | claimed |
| Other scraped date in element text | date_only / feed | day / minute | claimed |
| Date in the TITLE of a non-primary item (may be an event date) | unknown | day | unknown (date kept as `event_window_start`) |
| No date | unknown / collected_fallback | unknown | unknown |

An EVENT date (scheduled maintenance window, a date named in a title) is never stored as a publication date. A publisher domain is recorded for
display only and is never proof of independence (independence stays family/aggregator based).

## Four freshness states (per report, then best-of per incident)

1. **VERIFIED**: trusted publication time (feed / feed_corrected_utc, second or minute precision) within 24h.
2. **CLAIMED**: a parseable time or date that cannot establish currency (aggregator pubDate, day-precision date, claimed confidence) within the window.
3. **UNKNOWN**: no usable publication time (or provenance says the stored date is not a publication time); timed by collection, within 24h.
4. **KNOWN STALE**: best-known time older than 24h. A day-precision date is stale once the whole day is older than 24h (i.e. older than 48h from midnight).

## What each state may and may not do

- Only VERIFIED-grade times count as live continuation evidence for restoration status (`time_verified`). CLAIMED, UNKNOWN and any date-only evidence never do.
- CLAIMED and UNKNOWN reports CAN feed URGENT TO VERIFY (high materiality, stated impact, Australian relevance): a potentially severe emerging incident is
  surfaced for verification. The line says the publication time is unverified.
- KNOWN STALE never surfaces as urgent.
- Nothing produces "confirmed current" wording; freshness is a label about the publication time, not a statement of service state.

## What is NOT claimed

- Date-only evidence does not establish elapsed time at hour level or that an incident is ongoing.
- KEV `dateAdded` is not the CVE disclosure date and says nothing about how long the vulnerability has been known.
- Verified publication time does not mean the incident is current or resolved; restoration status has its own rule.
- Google News publisher domain/name is informative only; it does not make aggregator copies independent.
- Heuristics: "date-only" in scraped HTML is detected as the absence of an HH:MM in the element text; the title-date check recognises named-month, ISO and d/m/yyyy dates.
