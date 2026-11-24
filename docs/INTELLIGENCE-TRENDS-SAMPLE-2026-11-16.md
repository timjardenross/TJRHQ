# Trends: week commencing 2026-11-16 (UTC)

> **GENERATED FROM THE REAL STORED HISTORY, OFFLINE.** Produced by `intelligence/longitudinal_trends.py` (`wk-trends/0.1.0-prototype`) from a read-only export of `intelligence_events` (2026-07-12 to 2026-11-24). Not a live product: the generator is default OFF (`INTELLIGENCE_LONGITUDINAL_TRENDS`) and nothing schedules it. Generated on 2026-11-24. Single-reviewer audit; see the limitations in the Unknowns section and `docs/INTELLIGENCE-LONGITUDINAL-TRENDS-AUDIT.md`.

## Headline

**Only weak signals this week (2026-11-16 to 2026-11-22).** No term met the minimum-evidence rule on both bases, and the incident rate is not distinguishable from its baseline. Nothing below should be read as an established trend.

## Volume denominator and coverage (read first)

Every count below is per the reports that were stored. The table shows how much was collected and published each week, so a change in collection cannot be mistaken for a change in the world. **Constant set** = sources that collected at a steady rate throughout the window (38 sources: window 2026-09-07 to 2026-11-16); it is the primary basis for any trend.

| Week (Mon, UTC) | Reports collected | Reports published (dated) | Undated | Of published: primary / mainstream / specialist / aggregator / content / other | Active sources | Incidents (all) | Incidents (constant set) | Reliable |
|---|---|---|---|---|---|---|---|---|
| 2026-09-28 | 1847 | 2026 | 43 | 216 / 1236 / 84 / 45 / 277 / 168 | 53 | 10 | 10 | NO: coverage change 2026-10-02 (outage); no reports collected on 2026-10-02, 2026-10-03, 2026-10-04 |
| 2026-10-05 | 2984 | 2741 | 69 | 181 / 1722 / 89 / 54 / 402 / 293 | 63 | 18 | 18 | yes |
| 2026-10-12 | 3078 | 3010 | 101 | 178 / 1918 / 92 / 92 / 448 / 282 | 52 | 29 | 29 | yes |
| 2026-10-19 | 2835 | 2829 | 66 | 197 / 1787 / 98 / 58 / 405 / 284 | 54 | 23 | 21 | yes |
| 2026-10-26 | 2908 | 2813 | 84 | 197 / 1799 / 90 / 70 / 415 / 242 | 55 | 29 | 29 | yes |
| 2026-11-02 | 2989 | 2689 | 146 | 126 / 1735 / 102 / 82 / 403 / 241 | 53 | 30 | 30 | yes |
| 2026-11-09 | 3053 | 2901 | 53 | 200 / 1836 / 100 / 71 / 404 / 290 | 68 | 41 | 40 | yes |
| 2026-11-16 | 2998 | 2797 | 27 | 47 / 1867 / 100 / 81 / 438 / 264 | 56 | 29 | 29 | yes |

- Active sources this week by class: aggregator 4, content 10, mainstream 6, primary 8, specialist 4, unknown 24.
- Sources first seen this week: none. Sources whose last stored report was last week (sparse feeds can be quiet without being broken): APRA Consultations, APRA — Speeches and Publications, Cambridge Wellbeing Institute, Google Cloud Status, McKinsey & Company — Insights, Melbourne Airport, NBN Network Status, VicEmergency, myGov Service Disruptions.
- Dated coverage changes in this week: none.
- Known broken or retired sources overlapping this week: AEMO NEMweb Market Notices, ASIC Enforcement Activity, ASIC News Centre, OAIC Breach Notifications, OAIC Privacy Determinations & News.

## Confirmed evidence

Counted directly from stored reports (incident = a group of reports from the existing incident detection that states, or reports as unconfirmed, a service-affecting event; natural-hazard notices, vulnerability advisories, warnings, forecasts, retrospectives and commentary are not counted).

- Incidents with first publication in the week: **29** from all sources, **29** from the constant set (denominator: 2797 dated reports published in the week, 2740 from the constant set).

| Sector | All sources | Constant sources |
|---|---|---|
| unclassified | 13 | 13 |
| cloud_platform | 5 | 5 |
| finance | 3 | 3 |
| transport_water | 3 | 3 |
| emergency_services | 2 | 2 |
| aviation | 1 | 1 |
| retail_food | 1 | 1 |
| telecom | 1 | 1 |

| Australian relevance | All sources | Constant sources |
|---|---|---|
| none | 16 | 16 |
| dependency | 8 | 8 |
| operational | 5 | 5 |

| type | All sources | Constant sources |
|---|---|---|
| cyber_incident | 13 | 13 |
| outage | 10 | 10 |
| physical | 3 | 3 |
| service_disruption | 2 | 2 |
| water_quality | 1 | 1 |

`physical` is the detector's broad fire/explosion/collapse/attack vocabulary and includes much world news; treat it as the noisiest class.

- Restoration duration: 12 outage-class incidents, 0 with a dated restoration report; insufficient evidence (n=0, need 3) (1 dropped as implausible).

### Repeated disruption of the same service (3+ episodes in 28 days) detected this week

- **salesforce trust**: 4 episodes in the 28 days to 2026-11-17 (10 in the overlapping run since 2026-08-17). Basis: supported in constant sources; also holds on the constant set.

  - 2026-08-17 outage: Salesforce Disruption — B2CCore
  - 2026-08-30 outage: Salesforce Disruption — coreService
  - 2026-09-03 outage: Salesforce Disruption — B2CCore
  - 2026-09-16 outage: Salesforce Disruption — AdvertisingAudiences, AnalyticsBuilder, AudienceBuilder, AutomationStudio, CloudPages…
  - 2026-09-25 outage: Salesforce Disruption — Platform
  - 2026-10-14 outage: Salesforce Disruption — coreService
  - 2026-10-23 outage: Salesforce Disruption — coreService
  - 2026-10-27 outage: Salesforce Disruption — coreService
  - 2026-11-07 outage: Salesforce Disruption — Customer360Audiences
  - 2026-11-17 outage: Salesforce Disruption — coreService

## Analytical inference

Comparisons and inferences. These depend on the detector's grouping and on the labelled assumptions; they are not facts.

### Incident rate against the trailing baseline

- all sources: 29 incidents per 2797 published reports = 10.37 per 1,000; baseline 123 per 11232 = 10.95 per 1,000 (weeks 2026-10-19, 2026-10-26, 2026-11-02, 2026-11-09). Result: **no change distinguishable from the baseline** (one-sided p up 0.64, down 0.43; a change is reported only with >= 8 incidents and p <= 0.01).
- constant sources: 29 incidents per 2740 published reports = 10.58 per 1,000; baseline 120 per 10974 = 10.93 per 1,000 (weeks 2026-10-19, 2026-10-26, 2026-11-02, 2026-11-09). Result: **no change distinguishable from the baseline** (one-sided p up 0.59, down 0.48; a change is reported only with >= 8 incidents and p <= 0.01).

### Emerging terms and entities

No term met the minimum-evidence rule this week (>= 4 incidents, >= 3 independent publishers, >= 2 days, ratio >= 3.0, p <= 0.001, against a pooled baseline of up to 6 reliable weeks).


### Interpretation limits

- A flagged term is a candidate for human reading, not a finding: in the audit most flagged words were one story reported several ways, or a generic word that a short baseline made look new.
- Repeats are counted per named service from status-page items and news; status-page feeds report many small incidents, so a repeat there is evidence of reported disruption frequency, not of service quality.

## Potential exposure

What the week's incident set could mean for Australian operations (`physical` incidents with no recognised sector are left out as noise). Relevance is the detector's, from headlines and summaries only; **dependency means a plausible platform dependency, not demonstrated Australian impact.**

| First published | Type | Sector | Australian relevance | Independent publishers | Headline |
|---|---|---|---|---|---|
| 2026-11-16 | service_disruption | unclassified | operational | 1 | Tech failure forces hundreds of University of Melbourne students to abandon final exams mid-test |
| 2026-11-17 | service_disruption | emergency_services | operational | 1 | Four Qlders died 'avoidable deaths' waiting for an ambulance this month |
| 2026-11-17 | cyber_incident | unclassified | operational | 1 | Hijacked website testing tool plants card skimmer on Australian brands’ sites |
| 2026-11-17 | outage | cloud_platform | dependency | 1 | Salesforce Disruption — coreService |
| 2026-11-17 | cyber_incident | cloud_platform | dependency | 0 | Ikea and Zoom among websites hit by major security incident at third-party provider - SmartCompany |
| 2026-11-18 | outage | cloud_platform | dependency | 0 | Apple Pay outage a “difficult situation” for retailers in Black Friday sales mode - SmartCompany |
| 2026-11-18 | outage | unclassified | dependency | 1 | Rubio says US not 'under systemic attack' after series of tech outages |
| 2026-11-18 | outage | cloud_platform | dependency | 2 | GitHub Status: Degraded availability for GPT-6 Luna in Copilot (investigating) |
| 2026-11-18 | outage | unclassified | dependency | 1 | US tech outages blamed on rush to fix bugs found by AI |
| 2026-11-19 | cyber_incident | finance | dependency | 1 | JPMorgan, Visa, Mastercard say third-party vendors targeted in cyberattack |
| 2026-11-19 | cyber_incident | finance | operational | 1 | Australia's Bell Financial says some client data likely accessed |
| 2026-11-20 | outage | unclassified | dependency | 1 | Gateway availability disruption |
| 2026-11-21 | outage | emergency_services | operational | 1 | Authorities investigating four-minute Triple Zero outage in Canberra |

Repeated-disruption subjects above are candidates for dependency review (check whether the organisation relies on them); nothing here shows they affected it.

## Unknowns

- **Unreliable weeks in this window (2 of 11):** 2026-09-21 (coverage change 2026-09-26 (outage)); 2026-09-28 (coverage change 2026-10-02 (outage); no reports collected on 2026-10-02, 2026-10-03, 2026-10-04).
- **Collection changed during the history.** 2026-07-12: First stored events: collection began (the 6 and 13 July weeks are ramp-up). 2026-08-09: Status-page sources registered (Twilio, OpenAI, Supabase, Vercel, ...); AEMO Market Notices repaired from 10 Aug. 2026-09-06: Per-run feed ceiling raised: ABC, Bloomberg, BBC, FT, Guardian volume stepped about 4x (about 45 to about 200 items a day); six sources added (Google News x4, iTnews, ARN). 2026-09-26: Reduced collection on 26 and 27 Sep (about 55-65% of a normal day). 2026-10-02: No reports collected at all on 2, 3 and 4 Oct (collection gap). 2026-11-06: AEMO NEMweb Market Notices retired (duplicate of AEMO Market Notices, which continues): recorded, not a coverage reduction. 2026-11-24: RSS published_at repair (+10h, 34,238 rows; 487 rows not corrected) and a further feed-ceiling increase (#703). The 23 Nov week is partial.
- **Known broken or silent sources:** ASIC News Centre (from 2026-09-08: Only 4 events (24 Aug to 7 Sep), none since; 0 successful health checks in the retained history.); ASIC Enforcement Activity (from 2026-07-12: No events ever stored; health checks all failing.); OAIC Breach Notifications (from 2026-08-11: No events after 10 Aug; health checks failing from 9 Nov.); OAIC Privacy Determinations & News (from 2026-08-30: No events after 29 Aug; health checks failing from 9 Nov.); Financial Newswire (from 2026-07-20 to 2026-08-30: Zero events for six weeks, then resumed.); Geoscience Australia Earthquakes (from 2026-07-20 to 2026-08-02: Zero events for two weeks, then resumed.); AEMO NEMweb Market Notices (from 2026-11-06: Retired; AEMO Market Notices continues.)
- **Constant-source set** excludes 46 sources that were not steady across the window; it is smaller and less diverse than the full set, so absence of a trend there is weak evidence of absence.
- **Publication dates:** a report is placed in a week by its own verified publication time; undated reports (shown per week) are excluded from weekly counts. The 24 Nov RSS repair assumed a constant +10 h shift and left 487 rows uncorrected; at most a few reports near a Monday boundary could sit in the wrong week.
- **Detector limits:** headline-only classification, keyword vocabularies, and a correlator that sometimes merges two services or splits one story into several incidents (both seen in the audit). Counts are of detected incident groups, not of verified incidents.
- **Restoration duration** exists only where a later report in the same group affirms restoration with its own timestamp; most incidents have none.
- **Short history:** about 18 complete weeks, one coverage regime for only the last 11. No seasonality can be assessed. Single human reviewer; no inter-rater check.
