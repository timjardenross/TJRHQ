# REPLAY: tiered and clustered brief and alert payloads for three past incidents

> **REPLAY, not a record of what was sent.** Offline reconstruction from SELECT-only data (`intelligence_events`, 30 days to 2026-11-24). Nothing was sent, published or written. The production system produced none of the alert payloads below; the dispatcher ran in dry-run with an in-memory store. Alert times are COLLECTION times (feed lag excluded). Brief times assume 07:00 AEDT = 20:00Z.

## Microsoft 365 / Outlook global outage

Global outage, 12-13 Nov 2026.

Events: 42, first collected 12 Nov 20:16Z, last 24 Nov 05:16Z.

### Alert payloads (dry-run, in collection order)

**ALERT** at 12 Nov 23:16Z (3.0 h after first collection; dry_run=True, sent=False)

```
ALERT: Australia's cyber security chief looking into Microsoft outage
Status: ongoing. Reports: 4 (2 independent publishers). Evidence: corroborated.
Why this interrupts: high materiality, stated impact, live disruption, Australian relevance demonstrated, solid evidence, fresh report
First report: Breaking: Microsoft platforms suffering widespread outages, including Outlook [1ac9ea52]
Incident: inc-69dfb5f668
View: /intelligence#inc-69dfb5f668
```

### Tiered brief as rendered at 13 Nov 20:00Z (24 report ids shown)

```
🛰 TIERED INCIDENT PICTURE (clustered by incident; lifecycle per report)
Based on reports from the last 72 hours; incidents are consolidated, so one disruption is one entry.

ACTIVE ALERT-LEVEL INCIDENTS (live, stated impact, Australian relevance, solid evidence)
- Microsoft 'deeply sorry' for global outage, reports 'broad recovery' of services (partially restored; 24 reports; inc-e58ee4fe69)
    why: high materiality, stated impact, live disruption, Australian relevance demonstrated, solid evidence, fresh report
    view: /intelligence#inc-e58ee4fe69
    NEW 12 Nov 10:28Z: Microsoft users caught up in global M365 outage [a6d72e00]
    SUBSEQUENT x13, latest 13 Nov 13:19Z: US Futures Gain With Microsoft Outage, Producer Prices in Focus [7c491338]
    RESTORATION (full) 13 Nov 03:33Z: Microsoft 365 recovers with Outlook back online [a160eef1]
    RESTORATION (partial) 13 Nov 19:34Z: Microsoft 'deeply sorry' for global outage, reports 'broad recovery' of services [bbb1fb24]
    RELATED x8 (commentary, cost, aftermath)

Context only (supports an incident, no item of its own): 0. Reference retained (no demonstrated Australian relevance or no stated consequence): 0.
```

### Tiered brief as rendered at 24 Nov 06:16Z (0 report ids shown)

```
🛰 TIERED INCIDENT PICTURE (clustered by incident; lifecycle per report)
Based on reports from the last 72 hours; incidents are consolidated, so one disruption is one entry.

No alert-level, scheduled or monitored incident in the window. This is not an all-clear: see the counts below.

Context only (supports an incident, no item of its own): 0. Reference retained (no demonstrated Australian relevance or no stated consequence): 0.
```

### Incident tiers at the end of the window

| Incident | Reports | Tier | Reason |
|---|---|---|---|
| inc-e58ee4fe69: Microsoft says three-month-old bug behind global M365 outage | 41 | SCHEDULED_BRIEF | material (high) with corroborated evidence but not an interrupt (not live, not fresh, or relevance not demonst |
| inc-8f0566fc42: APRA calls Microsoft outage a "near miss" for financial system - Insur | 1 | CONTEXT | no factual report of a disruption in the window: only commentary, aftermath or historical references |

## Coles cyber incident

Retailer cyber attack, 16 Nov 2026.

Events: 4, first collected 16 Nov 06:23Z, last 16 Nov 19:00Z.

### Alert payloads (dry-run, in collection order)

No alert-level payload at any collection batch. Reason, from the final tiering below.

### Tiered brief as rendered at 16 Nov 20:00Z (4 report ids shown)

```
🛰 TIERED INCIDENT PICTURE (clustered by incident; lifecycle per report)
Based on reports from the last 72 hours; incidents are consolidated, so one disruption is one entry.

MONITORING (evidence not yet sufficient; will be re-tiered when it arrives)
- Coles supermarket cyber attack: Australia’s retailer investigates security breach - Beinsure (ongoing; 4 reports; inc-874e4f5143) - consequence unconfirmed at an essential-service or compromised entity: verification target, not yet material [/intelligence#inc-874e4f5143]

Context only (supports an incident, no item of its own): 0. Reference retained (no demonstrated Australian relevance or no stated consequence): 0.
```

### Incident tiers at the end of the window

| Incident | Reports | Tier | Reason |
|---|---|---|---|
| inc-874e4f5143: Coles supermarket cyber attack: Australia’s retailer investigates secu | 4 | MONITOR | consequence unconfirmed at an essential-service or compromised entity: verification target, not yet material |

## Telstra outage (aftermath family)

The original July national outage is OUTSIDE the 30-day sample; this family holds the local Stockton/Kingswood/AWS items and the aftermath reports, so it shows how an outage-and-aftermath cluster is handled, not the July alert.

Events: 12, first collected 27 Oct 07:56Z, last 21 Nov 11:44Z.

### Alert payloads (dry-run, in collection order)

No alert-level payload at any collection batch. Reason, from the final tiering below.

### Tiered brief as rendered at 21 Nov 12:44Z (0 report ids shown)

```
🛰 TIERED INCIDENT PICTURE (clustered by incident; lifecycle per report)
Based on reports from the last 72 hours; incidents are consolidated, so one disruption is one entry.

No alert-level, scheduled or monitored incident in the window. This is not an all-clear: see the counts below.

Context only (supports an incident, no item of its own): 1. Reference retained (no demonstrated Australian relevance or no stated consequence): 0.
```

### Incident tiers at the end of the window

| Incident | Reports | Tier | Reason |
|---|---|---|---|
| inc-da66433e27: Kingswood residents warned of Telstra mobile disruptions - New England | 1 | MONITOR | evidence unverified (aggregator-only or hedged): wait for a corroborating or primary report |
| inc-581cac0fbb: Telstra's problems in Australia continue with Amazon Web Services outa | 1 | MONITOR | evidence unverified (aggregator-only or hedged): wait for a corroborating or primary report |
| inc-40f15e5d82: What Does Telstra Group Limited (ASX:TLS), an S&P/ASX 50 Member, Make  | 1 | CONTEXT | no factual report of a disruption in the window: only commentary, aftermath or historical references |
| inc-aff6283fb9: Has Telstra been hacked? Technical issue bombards customers with myste | 1 | MONITOR | evidence unverified (aggregator-only or hedged): wait for a corroborating or primary report |
| inc-486a258d9f: Telstra users face 60-hour outage during Yornup upgrade - Manjimup Bri | 1 | MONITOR | evidence unverified (aggregator-only or hedged): wait for a corroborating or primary report |
| inc-e2aa6b4815: Telstra Outage -Barnaby Joyce Raises Question Of China Involvement - S | 2 | MONITOR | evidence unverified (aggregator-only or hedged): wait for a corroborating or primary report |
| inc-040fe39b0c: Telstra Outage Drives 72% Jump In Complaints As 4G And 5G Problems Per | 5 | CONTEXT | no factual report of a disruption in the window: only commentary, aftermath or historical references |

