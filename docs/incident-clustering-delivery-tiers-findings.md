# Incident clustering, delivery tiers and offline alert replay: findings (DRAFT, 2026-11-24)

Status: offline measurement. Nothing here is wired into a production path, no feature is activated, no data was written.
New behaviour sits behind two default-OFF flags read at call time: `INCIDENT_CLUSTERING_V2` and `DELIVERY_TIERS_V1`.

## What was added

| Path | Purpose |
|---|---|
| `intelligence/incident_clustering.py` | Consolidates groups that are one disruption; labels every report NEW / SUBSEQUENT / RESTORATION_UPDATE / RELATED / HISTORICAL_REFERENCE; derives incident restoration state from report roles |
| `intelligence/delivery_tiers.py` | IMMEDIATE_ALERT / SCHEDULED_BRIEF / MONITOR / CONTEXT / REFERENCE_RETAIN, derived from materiality, impact status, evidence status, liveness, Australian relevance and report roles. No rank threshold is read or changed |
| `tools/intelligence/alert_replay.py` | Replays an event export in collection order and reports alerts, latency, false urgency, false restoration, duplicates and surfacing. Prints JSON, sends nothing |
| `tests/test_incident_clustering.py`, `tests/fixtures/incident_clustering/events_30d_sample.tsv` | 22 tests; fixture holds id prefix, dates, source and title only |

The frozen V0/V1 reference sets are read, never edited or padded.

## Data and how it was read

SELECT-only on `intelligence_events` (project `cjvrpjwewsrumnbdydgg`), 30 days to 2026-11-24, no personal-health tables.
12,785 rows collected: 12,292 from non-status sources, 536 provider status pages (201 with outage-type words, 3 linked to a brief).

**The incident-level numbers below come from a 78-row, title-prefiltered sample** (outage/cyber/restoration words plus an Australia or
platform term; status-page rows excluded), not from all 12,785 rows. It is the Microsoft 365 outage (42 reports), seven Telstra
items, the Coles cyber attack and neighbours. Other disruption families in the 30 days are not measured.

## A. Duplicate incident representation (same 78 rows, same `now`)

| Family | Incidents before | Incidents after | Reports |
|---|---|---|---|
| Microsoft 365 outage | 5 (4 rated ESCALATE/VERIFY/WATCH) | 2 (2 actionable) | 42 -> 42 |
| Telstra items | 7 | 7 | 12 -> 12 |
| Coles cyber attack | 1 | 1 | 4 -> 4 |

- Microsoft: the three stragglers that the term-overlap correlator left as separate one-report "incidents" now join the main one: a
  pure restoration headline ("Microsoft 365 recovers with Outlook back online", which was not even a candidate, so the restoration was
  detached from the outage), an "Outlook outage expected to cost Australian businesses billions" story (no "Microsoft" in the headline,
  baseline rated it ESCALATE on its own) and a phishing follow-up. The remaining second incident is the APRA "near miss" story, published
  four days after the last report: outside the 72-hour chaining window, so it stays separate (tiered CONTEXT).
- Telstra: **no reduction, by design.** They are genuinely different items (Kingswood mobile disruptions, "mystery calls", a planned
  60-hour Yornup upgrade, the Stockton copper-theft outage, a Telstra/AWS item, a complaints aftermath, a July-outage share
  buyback). Non-platform subjects only absorb an unanchored follow-up when exactly one other incident of that subject is active. The
  original Telstra network outage that the five "complaints surge" reports refer to is not in the sample.
- One improvement is classification, not count: the 41 reports in the consolidated Microsoft incident are 1 NEW, 17 SUBSEQUENT,
  4 RESTORATION_UPDATE (2 partial, 2 full claims), 19 RELATED (the 42nd family report is the APRA item); "races to restore" and "recovery not progressing" are not restorations.

A known baseline error remains: the correlator joins the Stockton outage and the "Barnaby Joyce raises China question" Telstra item.

## B. Delivery tiers and material incidents never surfaced

Tier counts on the 78-row sample at 2026-11-24 06:00Z: SCHEDULED_BRIEF 3, MONITOR 7, CONTEXT 5, REFERENCE_RETAIN 9, IMMEDIATE_ALERT 0
(no incident is live and fresh at that instant; alerts are measured by replay in C).

Material = tier IMMEDIATE_ALERT or SCHEDULED_BRIEF. Surfaced = `brief_id` set on any member event.

| Population | Material incidents | Surfaced | Never surfaced |
|---|---|---|---|
| 78-row 30-day sample | 3 | 1 | 2 |
| Frozen v1 events export (a sample, <=3 brief rows per incident) | 5 | 1 | 4 |

Why (sample): the one surfaced incident (Microsoft 365, 42 reports) reached a brief **only through an Insurance Business commentary
report**, never through any of the factual reports; the other two (US-bound flights grounded, a four-minute Triple Zero outage) were
dispositioned WATCH or REFERENCE and have no path to a brief. Why (v1 export): 2 dispositioned ESCALATE/BRIEF but never attached to a
brief, 2 dispositioned WATCH only.

Whole-table context for the same 30 days (not incident-level): 633 events dispositioned BRIEF and 7 dispositioned ESCALATE, **none of them
with a `brief_id`**; WATCH 3,208 (5 linked). Of 69 daily briefs, 12 mention Microsoft/Outlook/M365, 0 mention Telstra, 2 mention Coles
(case-insensitive text match, weaker evidence than `brief_id`).

## C. Offline alert replay

Sample (collection order, one batch per distinct collection time): 2 alerts, identical under the v1 and consolidated grouping.

| Alert | Latency from first collection of the incident |
|---|---|
| Microsoft 365 outage (one alert for 42 reports) | 3.0 h |
| US-bound flights grounded (FAA) | 0 h |

The 3.0 h is the Australian-relevance gate: the first report ("Breaking: Microsoft platforms suffering widespread outages") names no
Australian impact, so it is a dependency-only report; the alert fires when ABC's "Australia's cyber security chief looking into
Microsoft outage" is collected. Baseline rates the single aggregator item "Kingswood residents warned of Telstra mobile disruptions"
VERIFY / immediate; the tiers rate it MONITOR (aggregator-only, unverified).

Versus frozen reference v1 (the 72-row export covers 23 records, 13 confirmed material):

| Measure | Result |
|---|---|
| Material records alerted | 3 of 13 (RS-001, RS-003, RS-008) |
| Alert latency vs first collection | RS-001 0 h, RS-003 0 h, RS-008 3.0 h (vs reference first public report: 0.2 h, 18.6 h, 3.8 h) |
| False urgency (alert on a scored negative) | 0 |
| Negatives reaching SCHEDULED_BRIEF or alert | 0 |
| False restoration (a full-restoration claim >1 h before reference end) | 1 (iTnews "recovers", 12.6 h early; partial restorations excluded) |
| Duplicate alerts for one record | 0 |
| Material records not alerted | 10 |

The 10 misses are not alerting-rule failures alone. Several never reach the rules: the headline states no consequence (Vocus cable
break), the Australian-relevance gate rejects it (NT government outage), only aftermath reports exist (Telstra AGM), or the item is a
vulnerability advisory. None of these were fixed here; lowering thresholds to catch them would trade the zero false-urgency result.

## Limitations

- Prefilter and size: 78 rows; families outside it (and status pages) are unmeasured. Counts are small; "5 to 2" is a description of one
  large incident, not an estimate of a general duplicate rate.
- Reference v1 is draft (`reviewed_by_human: false`), its events export is a sample, and the harness scores only covered records.
- **Not an independent test.** I read the reference outputs while building the tier rules (the low-materiality MONITOR rule and the
  dependency-only rule were adjusted after seeing Coles and "UK banks hit by Google Cloud outage"). Zero false urgency on that set is
  therefore weak evidence.
- Latency is measured from collection, so it excludes feed lag; the replay uses batch time as `now`.
- The consolidation window (72 h outage, 7 d cyber) is inherited, not tuned; a long incident with a gap longer than that splits.
- Subject aliases are a hand-written list (Microsoft family, AWS, Google Cloud, Cloudflare, CrowdStrike, Telstra, Optus, TPG/Vodafone,
  NBN, Coles, Woolworths, Qantas). Other operators fall through to the baseline grouping.
- Surfacing is judged by `brief_id`, not brief text.
- Nothing was activated: clustering and tiers are not called by `captains_brief` or the scheduler.
