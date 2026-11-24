# Original-publisher and original-date verification (Google News items)

Status: module `intelligence/original_publisher.py` merged-ready, default OFF (`INTEL_ORIGINAL_PUBLISHER_VERIFY=1`), NOT WIRED.
Checklist item: "Original-publisher and original-date verification" (finding F-05).

## Measured on production (SELECT-only, 2026-11-24)

Population: `intelligence_events` from feeds named `Google News - ...`, collected in the last 30 days.

| Measure | Result |
|---|---|
| Google News items | 348 across 4 feeds (Telstra 120, Critical Infrastructure/Energy 110, Origin Energy 99, APRA/ASIC 19) |
| Title ends ` - Publisher` | 342 of 348 (98%); 6 have no suffix |
| Most common suffixes | Kalkine/Kalkine Media 59, WhistleOut 17, ABC 10, The Globe and Mail 10, Insurance Business 10, Reuters 7 |
| Link | 348 of 348 are `news.google.com/rss/articles/...` opaque ids. None embed the publisher URL (decoded all 348), so the publisher cannot be read offline |
| Stored date older than collection by more than 48 h | 154 of 348 (44%); more than 7 days: 67 (19%) |
| Collection minus stored date, percentiles (h) | p50 30, p75 136, p90 255, p99 327 |
| Same title (suffix stripped, normalised) also in a direct feed, 60-day window | 6 of 348 (1.7%), against 23,632 direct-feed items |
| Date difference on those 6 (Google News minus earliest direct feed) | median +4.6 h, range -12.9 h to +11.5 h; 2 of 6 within 1 h |

Limits: the lag figures are collection minus the aggregator's claimed date, not the true error (that needs the publisher date). The only true-error
sample from free data is n=6, too small for a distribution. Exact-title matching is deliberately strict (no `pg_trgm` in production; a fuzzy
match would raise coverage but was not built). Direct feeds mostly do not carry the same stories (the 4 Google News feeds target Telstra, Origin,
energy and APRA/ASIC; direct feeds are IT/security trade press), so title reconciliation cannot cover the problem. It is evidence only: a direct-feed
date is itself feed-supplied.

## Can the article be resolved to the publisher? (tested)

- Plain fetch from the container: `news.google.com` and the publisher hosts tested (abc.net.au, beinsure.com, insurancebusinessmag.com) are not
  on the network allowlist (proxy 403 / no connection). Not testable, and not a viable production path without an allowlist change.
- Firecrawl (4 calls, 1 credit each, `maxAge: 0`): all 4 high-materiality recent AU items followed the Google redirect to the publisher page.

| Item | Resolved to | Publisher's own date | Google News claim minus publisher | Class |
|---|---|---|---|---|
| APRA "near miss" (Insurance Business) | insurancebusinessmag.com | published 2026-11-21 01:52 UTC | -10.9 h (Google earlier) | verified_date |
| Telstra complaints (ABC) | abc.net.au | published 2026-11-18 13:03 UTC | +0.2 h | verified_date |
| Eyre Peninsula towers (ABC) | abc.net.au | published 2026-11-19 06:59 UTC | +3.0 h | verified_date |
| Coles cyber attack (Beinsure) | beinsure.com | modified 2026-11-16 14:55 only, no published time | n/a | publisher_known_date_unverified |

Measured: 4 of 4 resolved, 3 of 4 verified_date (75%), 1 of 4 publisher-known with no usable date. n=4 is a feasibility check, not a rate with
a confidence interval. All four were fresh (within 8 days), so this says nothing about whether old reporting looks fresh (the F-05 failure
case): no item in the sample was actually old. Modified time is never treated as publication time.

## What was built

- `resolve_publisher`: publisher from the title suffix using `weekly_evidence.publisher_family` / `source_kind` (no duplicate table). Always
  records `independence = "unproven"`: a name or domain is not evidence of independence.
- `label_date`: aggregator dates are labelled `aggregator_claimed` / `claimed` (same vocabulary as provenance v1). Collection time is never
  returned as a publication time; a missing date stays unknown.
- `reconcile_with_direct_feeds`: earliest same-title direct-feed date as evidence, with the signed hour difference.
- `eligible` + `classify_fetch` + `verify_batch`: HIGH materiality (>= 0.5, the weekly_evidence cut), Australian, recent (collected OR claimed
  within 7 days). The fetcher is injected (no network in the module) and `verify_batch` has a hard call budget (default 5). Outcome classes:
  `verified_date` (resolved off Google, page carries parseable, non-future published-time), `publisher_known_date_unverified`,
  `unresolved`. A fetch failure is an outcome, never an exception.

## Recommendation and cost

Cost is about 1 Firecrawl credit per HIGH-materiality item. The daily count of items clearing the high-materiality cut was not measured (the production
rows have no stored materiality); the per-run cap of 5 is what bounds spend regardless. Before enabling: (1) wire a Firecrawl fetcher behind the cap, (2) store the outcome with the
event (needs the provenance columns from `claude/provenance-v1-a7k2`, still unapplied), (3) re-measure on 30+ items including genuinely old
re-surfaced stories, which this sample did not contain. Not built: crawling, caching, fuzzy title matching, any ingestion or brief wiring.
