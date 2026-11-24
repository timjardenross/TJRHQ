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

---

# Conversion to an integrated, flag-gated capability (2026-11-24, PR on `claude/clustering-tiers-2kq`)

Everything below is default OFF, read at call time. No flag was activated, no migration applied, nothing sent, no production write; production access was SELECT only on `intelligence_events`.

| Capability | Flag (default OFF) | Where |
|---|---|---|
| AU relevance gate | `AU_RELEVANCE_DISRUPTION_GATE_V1` | `intelligence/classification/classifier.py` |
| Tiered/clustered morning view | `DELIVERY_TIERS_V1` (+ `BRIEF_EVIDENCE_V1_MORNING`) | `intelligence/tiered_brief.py`, hook `captains_brief._morning_view_lines` |
| Alert dispatcher (dry-run default) | `INCIDENT_ALERTS_V1`; real send also needs `INCIDENT_ALERTS_SEND` + `INCIDENT_ALERT_DESTINATION` + an injected sender | `intelligence/alert_dispatcher.py` |
| Brief event recording | `CAPTAINS_BRIEF_RECORD_EVENTS` | `intelligence/brief_event_links.py` |
| Workbench views | `INCIDENT_VIEW_V1` (portal env) | `lcars-portal` Intelligence page, Hub Needs You, Decisions inbox |

## 1. Relevance inflation (A/B, 30 days to 2026-11-24, full table, same pattern run in PostgreSQL)

Cause: `regulatory` base 0.70 + the 0.15 AU lift = exactly 0.85, and `cyber` 0.75 + 0.15 = 0.90, for any text naming an Australian institution; the 0.20 "major/significant/critical" bump adds more. With the gate on, a score at or above 0.85 needs a stated disruption/consequence signal in title or summary; otherwise it is capped at 0.80.

| Population (30 d) | HIGH before | HIGH after |
|---|---|---|
| All events (12,828) | 475 | 156 (-67%) |
| geography AU | 301 | 76 |
| regulatory | 198 | 13 |
| cyber | 172 | 95 |
| other types | 105 | 48 |

(The brief's "279" was an earlier cut; the same query now returns 301 AU rows.) Recall on the frozen v1 reference (70 of the 72 export events exist in the DB; 2 are synthetic ids): 46 events belong to confirmed-material records, 20 of them are HIGH today, **19 stay HIGH**; every material record keeps at least one HIGH event. **Lost: 1 event**, RS-031 `4a65276c` "CRITICAL ALERT: Critical vulnerabilities in Citrix NetScaler ADC..." (an advisory with no stated consequence; the gate is doing what it is designed to do, but it is a confirmed-material record). 0 non-material reference events were HIGH before or after. The first pattern also lost two RS-002 events ("hack", "infiltrated"); those words were added, which is a post-hoc adjustment seen against this set, so the recall figure is optimistic. Pattern limits: "failed"/"breach" also match some regulatory enforcement text; no summary was available for the 2 synthetic ids. Reference files were not modified.

## 2-4. Integration

Brief: with flags off `_evidence_lines('morning')` is identical text (`tests/test_tiered_brief.py`, golden generated from the unchanged `brief_evidence.morning_view`). With `DELIVERY_TIERS_V1` on, the morning evidence block is one entry per consolidated incident with NEW / SUBSEQUENT / RESTORATION / RELATED lifecycle and tier sections (alert-level, material, monitoring; context and reference as counts).
Dispatcher: once per incident (identity = any shared report id), one restoration update, never repeated, dry-run state kept apart from real state, rate limit 3 per hour (deferred, not dropped), failed sends not recorded. State store is pluggable; in-memory shipped; table drafted in `docs/migration-drafts/DRAFT-incident-alert-state.sql` (not applied).
Recording: **`link_events_to_brief` is not suitable.** It PATCHes `intelligence_events.brief_id`, a foreign key to `intelligence_briefs`; captains briefs live in `captains_daily_briefs` (checked with SELECT on `pg_constraint`). A separate join table is drafted (`DRAFT-captains-brief-events.sql`, not applied). The brief id is resolved by newest row of that `brief_type` after persisting (small race; documented). The legacy persist path is untouched.

## 5. Replay sample

`docs/incident-replay-sample-2026-11-24.md` (generated by `tools/intelligence/replay_sample.py`, checked by a test): Microsoft 365 (one alert, 3.0 h after first collection, 41-report incident with lifecycle), Coles (MONITOR only, no alert), Telstra (the July national outage is outside the sample; local items plus aftermath only). Labelled REPLAY, nothing sent.

## 6. Measurement vs legacy and Morning V1 (`tools/intelligence/conversion_measure.py`, one definition set, frozen reference export: 13 material, 5 negative records covered)

| Measure | Legacy (dispositions) | Morning V1 | Tiered |
|---|---|---|---|
| Material detected (briefed level) | 7/13 | 8/13 | 5/13 |
| Material alerted (immediate level) | 1/13 | 3/13 | 3/13 |
| Median alert latency from reference first report | 33.4 h | 3.8 h | 3.8 h |
| False urgency (negatives at immediate level) | 0 | 0 | 0 |
| Negatives reaching brief level | 2 | 2 | 0 |
| False restoration (full claim >1 h early) | n/a | 1 (RS-008) | 1 (RS-008) |
| Records split across incidents (sample) | n/a | 10 | 9 |

Honest reading: the tiers are more precise (no negative reaches a brief) but detect fewer confirmed-material records than Morning V1 (5 vs 8): a precision/recall trade, not an improvement on every axis. Duplicate representation barely moves on this sample because the export holds at most 5 earliest events per record (the 42-report Microsoft reduction is in section A above). Limits: not independent (rules were tuned after reading these outputs), reference v1 is draft and partly sampled, latency is collection-time, the legacy column uses dispositions (no incident or restoration concept), 07:00 brief time approximated.

## Workbench delivery path (lcars-portal)

Backend publishes read-only rows (`tools/intelligence/publish_incident_snapshot.py`, dry-run default; table drafted in `DRAFT-intelligence-incident-snapshots.sql`, not applied). With `INCIDENT_VIEW_V1` on: Intelligence page shows the clustered incident list with lifecycle and tier; Hub "Needs You" shows alert-level incidents and material exceptions; Decisions shows "Incidents to verify" (read-only links: no acknowledge write path exists and none was invented); `GET /api/home/needs-attention` adds an `incidents` array. All use `incident_key`, the key in the Telegram payload, so one incident is one entry in every channel. Without the applied table and a publisher run the views report unavailable, never all-clear.

## Canonical incident id and alert guards

One id everywhere: `tiered_brief.incident_id` = `inc-` + sha1(earliest member report id | that report subject)[:10] (the portal/DB column is `incident_key`, same value). The brief entries, Telegram alert payload (`incident_id`, `incident_key`, `link`), snapshot rows, Home Needs You (`incident-<id>`), Decisions (`inc:<id>`) and the Incidents tab anchor all use it; every channel links to `<PORTAL_BASE_URL>/intelligence-workbench?tab=incidents#<id>`. Known limit: a late-collected report published earlier than the first report changes the computed id; the dispatcher pins the id it first alerted with (restoration reuses it), but a brief or snapshot rendered afterwards can show the new id for that rare case.

The dispatcher independently refuses to alert unless a factual report is published within `INCIDENT_ALERT_FRESH_HOURS` (default 6 h) with a verified publication time and a non-register source (`is_register_source`: names containing register / outage register / statutory). Tests: an ASIC release dated 14 days ago and an "Optus National Outage Register" entry never alert; a 10 h old report is blocked by the dispatcher even though the 12 h tier rule would alert. PR #710 (brief_evidence guards) is not on this base; these guards do not depend on it.

---

# Tiering quality pass (2026-11-24, branch `claude/tiering-quality-2kq-s015`)

Objective: improve usefulness WITHOUT losing material detection. Still default OFF behind the same flags; flags-off output is byte-identical (golden test unchanged).

## What changed
- D5 additive: with `DELIVERY_TIERS_V1` the tier sections are followed by the Morning V1 sections (confirmed/unconfirmed incidents, implications, forward watch, WORTH KNOWING, "nothing to report"). V1 incidents made only of HISTORICAL_REFERENCE reports are dropped (not current).
- D2: `intelligence/freshness.py` is the one definition (alert 6 h, brief 24 h, live 72 h) read by tiers, dispatcher and `brief_evidence`.
- D6: SCHEDULED/MONITOR need a factual report inside the brief window (or still ongoing within 72 h); hazard policy/staffing stories are not incidents.
- D4/5: pattern gains fire/wildfire, vulnerability, critical flaw, RCE; credible advisories (EMERGING EXPOSURES section) and warnings are kept at SCHEDULED/MONITOR instead of "reference retained". Unconfirmed consequence at a corroborated compromised entity is SCHEDULED (verification target) again.
- Planned-outage demotion needs affirmative future-window wording judged on the latest report; a stated live impact always wins (NAB "outages after failed upgrade" regression test).
- NT government is an Australian marker (RS-033).
- Identity/links: V1 citations in the tiered view carry the canonical `tiered_brief.incident_id`; alert payload, snapshot and portal link already did (`tests/test_tiering_quality.py`).

## Re-measurement (frozen v1 reference, 72-event export, 13 covered material records; same `conversion_measure.py` definitions)
| | Morning V1 (before) | tiered, before | tiered (tiers only) | tiered additive |
|---|---|---|---|---|
| material detected | 8/13 | 5/13 | 8/13 | 9/13 |
| alerted | 3/13 | 3/13 | 3/13 | 3/13 |
| false urgency | 0 | 0 | 0 | 0 |
| negatives reaching a brief | 2 | 0 | 0 | 1 (RS-022, foreign Google Cloud outage) |
| false restoration | 1 (RS-008) | 1 | 1 | 1 (unchanged, not fixed) |
| median alert latency vs reference first report | 3.8 h | 3.8 h | 3.8 h | 3.8 h |
V1 itself rises 8 to 9 after the NT marker fix (RS-033), which is shared code. Still missed by every system: RS-011, RS-028, RS-030, RS-034 (no stated consequence / no Australian marker in the headline). Duplicate representation (records split across incidents) is not improved (V1 10, tiers 9).

## HIGH counts (PostgreSQL A/B, 30 days to 2026-11-24, SELECT-only, window rolls)
All events 12,814: HIGH before gate 473; old pattern 154; new pattern 187 (AU 299 -> 74 -> 77; regulatory 198 -> 13 -> 13; cyber 171 -> 94 -> 126). The extra HIGH are cyber advisories (vulnerability terms). Recall of confirmed-material HIGH events on the 70 export rows present in the DB: 20 of 20 stay HIGH (was 19 of 20; RS-031 recovered). Parity fixture re-recorded from PostgreSQL.

## Over-fitting disclosure
This is NOT an independent test: I read the reference outputs while writing the rules (RS-005/009/031/033 shaped the vulnerability, Coles and NT rules; the HISTORICAL-only drop separates RS-019 from RS-005). Mitigation: rules are stated generally and tested on synthetic cases; a held-out replay over 28 daily snapshots of 10,303 production rows I did not examine during tuning (`other.jsonl`, collected_at := published_at) went from 18 to 74 SCHEDULED incident-snapshots (overlapping 72 h windows), the increase being 9 distinct CISA/vendor exposure advisories (now in their own section) and Coles; IMMEDIATE fell 2 to 0 there only because 21:00Z snapshots are older than the 6 h window (collection-order replay latency is unchanged). No labels exist for that data, so it measures volume, not precision.
