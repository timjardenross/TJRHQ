# Longitudinal trends: method, real-history run and audit

Status: offline prototype, default OFF (`INTELLIGENCE_LONGITUDINAL_TRENDS`), not wired into any report, scheduler or service.
Method `wk-trends/0.1.0-prototype`. Run date 2026-11-24. Reviewer: one (the agent that built it); no second reviewer, no inter-rater check.

Code: `intelligence/longitudinal_trends.py` (measures), `intelligence/trends_product.py` (weekly markdown), `scripts/longitudinal_trends.py`
(runner), `tests/test_longitudinal_trends.py` (34 tests). Generated sample: `docs/INTELLIGENCE-TRENDS-SAMPLE-2026-11-16.md`.

## What it measures

Incidents come from the existing `intelligence/event_detection.py` (`detect_candidate`, `correlate`, `decide`), run over every stored report
except the earthquake feed. An incident counts only if it states (or reports as unconfirmed) a service-affecting event
(outage, cyber incident, service disruption, supply shortfall, water quality, physical); hazards, vulnerability advisories, warnings,
forecasts, retrospectives and commentary are excluded. Each incident goes in the week (Monday to Sunday, UTC) of its earliest **verified
publication time**; a report with no parseable publication time, or one dated after its collection, is "undated" and is never placed by its
collection time.

| Measure | Definition |
|---|---|
| Incidents by sector, by Australian relevance | Counts per week; sector = highest-tier sector found in the incident's reports; relevance = the detector's (operational, dependency, editorial, none) |
| Restoration duration | Restoration report's own timestamp minus the incident's first publication, only where a later report affirms restoration; median withheld below 3 durations; spans over 14 days dropped |
| Repeated disruption | Same named subject (organisation lexicon, or the status-page feed name), 3+ distinct episodes (>= 12 h apart for status feeds, >= 96 h for news) inside 28 days; aftermath/planned-work headlines excluded |
| Emerging terms | Share of a week's incidents carrying a term vs a pooled trailing baseline of up to 6 reliable weeks. Needs >= 4 incidents, >= 3 independent publishers, >= 2 days, ratio >= 3, one-sided binomial p <= 0.001, baseline >= 4 weeks and >= 30 incidents |
| Volume denominator | Reports collected and reports published (dated) per week, by source class; undated count |

Coverage handling (owner direction): every week carries a coverage record (active sources by class, sources first seen, last stored report
last week, dated changes, known broken sources, zero-collection days) and a reliability flag. Results are produced on two bases, **all
sources** and a **constant-source set** (sources collecting in >= 90% of the window's weeks, present in its first and last week, with no
weekly-volume step above 2x across a rate change). A trend whose span crosses a persistent coverage change and that does not hold on the
constant set is labelled `coverage-confounded`.

## Data and provenance

Read-only `SELECT` on `intelligence_events` joined to `intelligence_source_registry` (project `cjvrpjwewsrumnbdydgg`): 45,427 rows, collected
2026-07-12 to 2026-11-24, fields id prefix, source, geography, collected_at, published_at (as repaired on 24 Nov), title, first 160 characters of
summary, suppressed. No personal-health table was read; no writes. Export saved at
`/tmp/claude-0/-workspace-TJRHQ/5c99c3a1-6417-5a53-9b31-7e56f4d316a6/scratchpad/longitudinal/events_export.jsonl` (14.6 MB, not committed), with
the per-run outputs in `.../out_full/` and `.../out_post/`. Suppressed rows are kept (the detector, not the suppression flag, decides what is an
incident; the suppression rate itself changed on 24 Aug).

Windows analysed: **full** = 19 complete weeks 13 Jul to 16 Nov; **post-step** = the 11 weeks 7 Sep to 16 Nov (after the largest collection change).
The 6 Jul week (one collection day) and the 23 Nov week (partial, and the day of the feed-ceiling and timestamp changes) are excluded.

## Coverage record (what changed in collection)

Evidence for each date: repository history (#688, #689, #696, #703), registry creation dates, and the stored events' own daily counts.

| Date | Change | Effect on trends |
|---|---|---|
| 2026-07-12 | Collection begins | 13 and 20 Jul weeks: 15 to 19% of reports undated; unreliable |
| 2026-08-09/10 | Status-page sources registered; AEMO Market Notices repaired | New incident source class from this date |
| 2026-09-06 | Per-run feed ceiling raised: ABC 45 to about 200 reports a day (3.9x), Bloomberg, BBC, FT, Guardian likewise; six sources added | Weekly incident counts rise 2.3x with it |
| 2026-09-26/27 | Collection at 55 to 65% of a normal day | 21 Sep week flagged |
| 2026-10-02 to 04 | No reports collected on three days | 28 Sep week flagged |
| 2026-11-06 | AEMO NEMweb retired (duplicate source) | Recorded, not confounding |
| 2026-11-24 | RSS `published_at` repair (+10 h on 34,238 rows, 487 not corrected) and larger feed ceiling | The 23 Nov week is partial |

Known broken or silent: ASIC News Centre (4 events, none after 7 Sep; zero successful health checks in the retained history), ASIC Enforcement
Activity (never produced a row), OAIC Breach Notifications (none after 10 Aug) and OAIC Privacy Determinations (none after 29 Aug), Financial
Newswire (none 20 Jul to 30 Aug), Geoscience Australia (none 20 Jul to 2 Aug). `derive_silent_gaps` also lists long silences in status feeds
(for example GitHub Status 31 Aug to 1 Nov, Atlassian Status 92 days): the stored events cannot tell a quiet status page from a broken collector,
so these are flagged, not resolved. The source-health table keeps only about five weeks, so it cannot settle them.

Weekly record (all sources; "constant" = the 17 sources steady over the full window):

| Week (Mon) | Collected | Published (dated) | Undated | Active sources | Incidents all | Incidents constant | Reliable | Why not |
|---|---|---|---|---|---|---|---|---|
| 2026-07-13 | 1742 | 1386 | 267 | 42 | 14 | 6 | NO | 267/1742 undated |
| 2026-07-20 | 1377 | 1261 | 195 | 34 | 15 | 6 | NO | 195/1377 undated |
| 2026-07-27 | 1300 | 1255 | 107 | 32 | 14 | 10 | yes | |
| 2026-08-03 | 1462 | 1326 | 73 | 40 | 7 | 2 | yes | |
| 2026-08-10 | 1657 | 1443 | 105 | 52 | 13 | 5 | yes | |
| 2026-08-17 | 1555 | 1547 | 77 | 43 | 21 | 4 | yes | |
| 2026-08-24 | 1726 | 1619 | 89 | 53 | 10 | 4 | yes | |
| 2026-08-31 | 1881 | 1885 | 75 | 58 | 17 | 10 | NO | rate change 6 Sep |
| 2026-09-07 | 3165 | 3039 | 136 | 57 | 37 | 8 | yes | |
| 2026-09-14 | 3168 | 2859 | 70 | 51 | 34 | 8 | yes | |
| 2026-09-21 | 2915 | 2725 | 130 | 50 | 30 | 7 | NO | outage 26-27 Sep |
| 2026-09-28 | 1847 | 2026 | 43 | 53 | 10 | 2 | NO | no collection 2-4 Oct |
| 2026-10-05 | 2984 | 2741 | 69 | 63 | 18 | 4 | yes | |
| 2026-10-12 | 3078 | 3010 | 101 | 52 | 29 | 6 | yes | |
| 2026-10-19 | 2835 | 2829 | 66 | 54 | 23 | 5 | yes | |
| 2026-10-26 | 2908 | 2813 | 84 | 55 | 29 | 5 | yes | |
| 2026-11-02 | 2989 | 2689 | 146 | 53 | 30 | 9 | yes | |
| 2026-11-09 | 3053 | 2901 | 53 | 68 | 41 | 12 | yes | |
| 2026-11-16 | 2998 | 2797 | 27 | 56 | 29 | 5 | yes | |

**Unreliable weeks: 13 Jul, 20 Jul, 31 Aug, 21 Sep, 28 Sep.** The 6 Jul and 23 Nov weeks are partial and outside the window. Within the post-step
window the constant set has 38 sources; within the full window only 17, almost all blogs, security feeds and two status pages, so full-window
constant-set counts (2 to 12 incidents a week) are thin.

## Results on the real history

**The one robust finding is about collection, not the world.** Weekly incident counts rose from about 13 (27 Jul to 24 Aug, reliable weeks) to
about 30 (reliable weeks from 7 Sep): 65 incidents in 7,190 published reports before, 270 in 25,678 after. Per 1,000 published reports that is
9.0 against 10.5, not a distinguishable change (two-proportion z about 1.1). The rise in counts is the 6 Sep feed-ceiling step. Reported without the
denominator it would have looked like a 2.3x increase in incidents.

Totals over the full window (all sources, 421 incidents): by type outage 164, physical 125, cyber incident 123, water quality 5, service
disruption 4. Sector: **unclassified 198 (47%)**, finance 40, cloud platform 36, aviation 32, transport/water 24, telecom 20, energy 20,
emergency services 19, retail/food 13, health 12, consumer service 7. Australian relevance: none 222, operational 164, dependency 34, editorial 1.
Restoration: of 168 outage-class incidents **7 (4%)** have a dated restoration report, so no weekly median can be reported in any week.

Current rules, post-step window (11 weeks): 3 repeat records on all sources (5 on the constant set), 1 emerging term (see below). Full window: 5 repeat
records on all sources.

## Audit: 26 flagged items read against the evidence

Method: for each flagged item I read the incident headlines and up to five member report titles (source, title), then judged whether the
item is what it claims to be. Verdicts: S supported, N not supported, P partly. One reviewer. The first pass used the first thresholds (strict
flags plus a relaxed sensitivity run, to get enough items to audit).

| # | Item | Verdict | Reason |
|---|---|---|---|
| 1 | repeat github, 5 episodes 14 Jul to 10 Aug | S | Five distinct GitHub Status disruptions (one episode merges several) |
| 2 | repeat anthropic, 3 (14 Aug x2, 1 Sep) | S | Three distinct status incidents |
| 3 | repeat cloudflare, 3 (17 Aug to 9 Sep) | S | Three Cloudflare incidents; one episode's headline was a merged GitHub item |
| 4 | repeat optus, 3 | N | One real outage (11 Sep) counted twice (follow-up 31 h later) plus a 23 Aug "advice after outages" article |
| 5 | repeat supabase, 4 (1 to 22 Sep) | S | Four distinct components and dates |
| 6 | repeat telstra, 6 | N | Retrospective commentary on the July outage, a planned outage, a share buy-back |
| 7 | repeat telstra, 5 (27 Oct to 12 Nov) | N | Planned outages and commentary; only small local disruptions are real |
| 8 | repeat cloudflare, 3 (23 Oct to 18 Nov) | S | Three Cloudflare incidents (one headline mislabelled by a merge) |
| 9 | repeat salesforce trust, 9 | S | Status-page disruptions on distinct dates |
| 10 | emerging `widespread` (9 Nov) | N | Generic adjective across four unrelated incidents, one not a service incident (Spain strike) |
| 11 | emerging `tech` (16 Nov) | P | A real run of US tech outages, but four of five "incidents" are political follow-ups of one story and one is unrelated |
| 12 | relaxed `another` | N | Generic |
| 13 | relaxed `major` | N | Generic |
| 14 | relaxed `government` | N | One NT network outage split in two plus an unrelated item |
| 15 | relaxed `fridge` (12 Oct) | S | French supermarket fridge cyberattack, one event reported several ways, plus follow-up |
| 16 | relaxed `europe` (2 Nov) | S | Second wave of supermarket freezer attacks across Europe (plus one unrelated item) |
| 17 | relaxed `expos` (stem) | N | Stem of "exposed/exposes" across unrelated cyber items |
| 18 | relaxed `supermarket` (2 Nov) | S | Same freezer-attack wave, plus the French blood-bank attack |
| 19 | relaxed `abc news` | N | Outlet-suffix leakage from aggregator titles |
| 20 | relaxed `communication` | N | Generic |
| 21 | relaxed `headlin` | N | Outlet-suffix leakage |
| 22 | relaxed `headlines` | N | Outlet-suffix leakage |
| 23 | relaxed `home` | N | Generic |
| 24 | relaxed `news` | N | Outlet-suffix leakage |
| 25 | relaxed `being` | N | Generic |
| 26 | relaxed `watch` | N | Generic |

**First-pass precision: 9 of 26 supported = 35% (95% Wilson 19% to 54%).** Repeats 6/9 (67%, 35% to 88%). Emerging terms 3/17 (18%, 6% to 41%),
and all three supported ones concern one story (the French and European fridge/freezer cyberattacks). Neither strict emerging flag (`widespread`,
`tech`) was a trend. Recall was not measured: nobody listed the trends that should have been found, so missed trends are unknown.

### Changes made after the audit, and how far to trust the new numbers

Failures found: episode subject taken from a merged group's first member; commentary and planned-work headlines counted as disruptions; one
news story's follow-ups counted as separate episodes; outlet names and generic words becoming "emerging". Changes: subject read from the incident's
headline report; an aftermath/planned-work headline filter; a 96 h episode gap for news-headed episodes; outlet and generic-word stoplists applied
to words and entities; multi-day coverage outages and derived zero-collection days now mark their weeks unreliable (this moved the 28 Sep week
from reliable to unreliable); a transient outage confounds only the weeks it touches.

Re-reading what the final rules flag (full and post-step windows): 7 of 8 repeat records are supported (github, anthropic, supabase,
cloudflare x2, salesforce on both bases; telstra not). The single strict emerging term is `supermarket` (2 Nov, 4 of 30 incidents against
2 of 170), the supported freezer-attack wave, labelled `all-sources-only` because the constant set did not reproduce it. The Cloudflare repeats were flagged only on the constant set: in the all-sources run the correlator merged their items with other
services' items, an instability of the grouping rather than of the data. The relaxed
sensitivity run now yields only the three freezer-story terms (`fridge`, `europe`, `supermarket`), all supported. **These
numbers are in-sample: the rules were tuned on the same items, there was no holdout, and a 7/8 or 3/3 result is optimistic.** The honest
statement is that the method finds real repeated status-page disruption and, at most, one genuine emerging story in 19 weeks.

## What is supported, what is not

Supported:
- Incident counts rose with collection volume, not with the rate of incidents (9.0 to 10.5 per 1,000 published reports, not significant).
- Repeated reported disruption on status pages: GitHub (5 episodes 14 Jul to 10 Aug), Anthropic (3, 14 Aug to 1 Sep), Supabase (4, 1 to 22 Sep),
  Cloudflare (4, 17 Aug to 9 Sep; 4, 23 Oct to 18 Nov), Salesforce Trust (10 episodes 17 Aug to 17 Nov, 4 in the 28 days to 17 Nov). This is
  reported disruption frequency, not service quality. GitHub counts are a lower bound (no events 31 Aug to 1 Nov).
- One emerging story: freezer and fridge cyberattacks on supermarkets (France 12 Oct, Europe-wide 2 Nov), at most one story, found once.

Not supported:
- Any emerging-term trend from the first thresholds other than the freezer story; generic words and outlet names look "emerging" on a short baseline.
- The Telstra and Optus repeats (retrospective or planned items, double-counted follow-ups).
- Any trend in restoration duration (7 of 168 outage incidents have evidence), in sector mix (47% unclassified) or in Australian relevance
  (no weekly count is large enough to test).
- Any claim spanning 13 Jul to 6 Sep against later weeks without the constant set.

## Limits

- Headline-only classification and keyword vocabularies; the correlator sometimes merges two services into one incident and splits one story into
  several. `physical` is noisy world news. Counts are detected groups, not verified incidents.
- Status feeds store incidents only, so a feed's silence cannot be told from a broken collector except where health data exists.
- 19 weeks, one steady collection regime for the last 11, no seasonality, one reviewer, no holdout, no inter-rater agreement.
- The 24 Nov repair assumed a constant +10 h shift; 487 rows are uncorrected, so at most a few reports near a Monday boundary may sit one week off.
- The constant set removes the confound by removing most mainstream news from the full window; it is a weaker detector, and failure to reproduce a
  signal there is weak evidence against it.

## Reproduce

```
python3 scripts/longitudinal_trends.py EXPORT.jsonl --window 2026-09-07 2026-11-16 --week 2026-11-16 --out DIR
```
`EXPORT.jsonl` rows are `[id8, source, geography, collected_at, published_at, title, summary160, suppressed, event_type, sector]`, from
`select ... from intelligence_events e join intelligence_source_registry r using(source_id)`. The runner is an offline tool and sets `force=True`; library callers
get `{"enabled": false}` unless `INTELLIGENCE_LONGITUDINAL_TRENDS` is on. Nothing in the platform imports these modules (a test enforces it).
