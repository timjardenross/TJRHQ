# Intelligence capability checklist

The single living record of delivery. A capability is **Operational** only when it is running in production and has been observed working; code written, merged or deployed-but-unobserved is **Partial**. Engineering detail (changes, commits, tests) lives in the engineering records, not here.

Last updated: 24 Nov 2026 (evening). 20 capabilities: 3 Operational, 17 Partial, 0 Outstanding.

| Capability | Status | What's left to complete |
|---|---|---|
| Discovery and collection | Partial | Confirm the larger feed limit and paged vulnerability collection behave correctly after tonight's 19:00Z run; activate the new sources and see them collect. |
| Authoritative Australian and international sources | Partial | ASIC and the new sources are seeded and deployed; confirm they collect in the 19:00Z run. OAIC repair is built but needs its two registry rows repointed. ATO business and PLS status pages are verified and not yet added. Telstra and ASX have no compliant automated method (owner decision: Telstra access, ASX consent or paid feed); ACMA is practical only as low-value regulatory context. |
| Collection reliability and timeliness | Partial | Observe the 06:00 sweep, iTnews cadence and vulnerability paging in production; timestamp repair is verified. |
| Enrichment and corroboration | Operational | None for now; original-publisher resolution for Google News items is tracked separately below. |
| Australian relevance and materiality | Partial | Geography classification is operational; the relevance gate is built but off until it is fixed for fire and vulnerability terms and re-measured without losing material detection. |
| Incident clustering and deduplication | Partial | Grouping is operational; the improved consolidation is built but off until measured on a broader sample than one large incident. |
| Incident lifecycle and restoration | Operational | One known false-restoration case to correct. |
| Intelligence conversion and prioritisation | Partial | Corrected tiering now detects 9 of 13 material reference incidents against Morning V1's 8, but the measurement is not independent. Left: independent check on live briefs, activation after tomorrow's assessment. |
| Proactive alerting | Partial | Existing outage alerts operate; the new once-per-incident alerting is built in test mode only and needs a destination, a sender and a live trial. |
| Daily executive brief | Operational | Assess tomorrow's 07:01 brief (first on the new code) for correctness, coverage and usefulness. |
| Missed-brief detection and recovery | Partial | Deployed but never exercised live; confirm it on a real or controlled miss. |
| Recurring provider disruption analysis | Partial | Built and tested offline; needs its storage created, activation and a first generation run. |
| Shared dependencies and concentration risk | Partial | Extractor built and audited: 47 documented relationships from 6 vendor documents, but only 1 demonstrated operational dependency in 90 days, so no concentration statement is supportable. Next: fetch the remaining provider documents and measure recall of incident statements; any collector for sub-processor lists is an owner decision. |
| Systemic and cascading risk | Partial | A default-off, unwired cascading exposure view is built and tested offline (documented, demonstrated, inferred and unknown kept apart; see `docs/CASCADING-EXPOSURE-FINDINGS.md`). Needs owner acceptance of its scope lines, wider documented evidence (6 vendors today), customer-side evidence, and activation. |
| Forward-looking intelligence | Partial | Dated-event extractor built and audited (62 events in 90 days, none regulatory); source coverage work for regulatory deadlines, technology lifecycle dates and Australian telecom, energy and government maintenance is in progress. ATO status and ATO/ABR/myID/DVS maintenance parsers are built with their sources staged inactive (see `docs/INTEL-FORWARD-SOURCES-MAINT-2026-11-24.md`). APRA, Treasury and ASIC closing dates, KEV due dates and endoflife.date lifecycle dates now have adapters (built, tested offline, not activated; see `docs/INTEL-FORWARD-SOURCES-2026-11-24.md`); commencement dates and Cisco/Ivanti/Citrix lifecycle remain unobtainable. |
| Longitudinal analysis and emerging trends | Partial | Built and run on 17 weeks of real history with collection-coverage handling: repeated status-page disruption is evidenced for GitHub, Anthropic, Supabase, Cloudflare and Salesforce Trust, and the September jump in incident counts is a collection artefact, not a trend. Precision is single-reviewer and in-sample; generic emerging terms, restoration trends (7 of 168 outages dated) and sector mix are not supported. Left: activation, an independent precision check on live weeks, and more dated restoration evidence. |
| Portal and Telegram access | Partial | Telegram brief operational; the Intelligence workbench tabs (incidents, products, source coverage) are built and wait for portal deployment capacity. |
| Provenance and verified freshness | Partial | Database change and backfill are applied (45,502 rows labelled, flag still off). Left: turn the flag on and restart the scheduler after tomorrow's brief assessment, decide KEV labelling, and show claimed and unknown states in the portal. |
| Original-publisher and original-date verification | Partial | Publisher resolution and date-claim labelling built and measured (4 of 4 high-materiality items resolved through a rendered fetch, 3 with a verified date). Not wired in; needs the provenance flag and a test on genuinely old re-surfaced stories. |
| Reference set, weekly baseline and continuous improvement | Partial | 16 candidate incidents are proposed for review toward the target of about 30 (15 confirmed today); the weekly baseline command and missed-incident log exist. Left: your review of candidates, a weekly cadence, and the manual-verification and usefulness measures. |

## Deferred

- **Read-only SQL access:** an operational efficiency improvement (fewer query approval prompts), deferred by the owner. Not part of the capabilities above and not a blocker.
