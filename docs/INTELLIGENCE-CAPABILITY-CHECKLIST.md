# Intelligence capability checklist

The single living record of delivery. A capability is **Operational** only when it is running in production and has been observed working; code written, merged or deployed-but-unobserved is **Partial**. Engineering detail (changes, commits, tests) lives in the engineering records, not here.

Last updated: 24 Nov 2026 (baseline from the programme readout).

| Capability | Status | What's left to complete |
|---|---|---|
| Discovery and collection | Partial | Confirm the larger feed limit and paged vulnerability collection behave correctly after tonight's 19:00Z run; activate the new sources and see them collect. |
| Authoritative Australian and international sources | Partial | Activate ASIC (repaired), RBA, ATO agents, Optus outage register and verify each delivers; ATO business and PLS status pages are verified and waiting to be added; no authoritative Telstra, ASX or ACMA collection method exists yet. |
| Collection reliability and timeliness | Partial | Observe the 06:00 sweep, iTnews cadence and vulnerability paging in production; timestamp repair is verified. |
| Enrichment and corroboration | Operational | None for now; original-publisher resolution for Google News items is tracked separately below. |
| Australian relevance and materiality | Partial | Geography classification is operational; the relevance gate is built but off until it is fixed for fire and vulnerability terms and re-measured without losing material detection. |
| Incident clustering and deduplication | Partial | Grouping is operational; the improved consolidation is built but off until measured on a broader sample than one large incident. |
| Incident lifecycle and restoration | Operational | One known false-restoration case to correct. |
| Intelligence conversion and prioritisation | Partial | The enhanced tiers lose material detection (5 of 13 versus 8 of 13); being corrected and re-measured before any activation. |
| Proactive alerting | Partial | Existing outage alerts operate; the new once-per-incident alerting is built in test mode only and needs a destination, a sender and a live trial. |
| Daily executive brief | Operational | Assess tomorrow's 07:01 brief (first on the new code) for correctness, coverage and usefulness. |
| Missed-brief detection and recovery | Partial | Deployed but never exercised live; confirm it on a real or controlled miss. |
| Recurring provider disruption analysis | Partial | Built and tested offline; needs its storage created, activation and a first generation run. |
| Shared dependencies and concentration risk | Outstanding | No evidence of provider dependencies exists in what we collect; decide what extraction could find it, without inventing relationships. |
| Systemic and cascading risk | Outstanding | Depends on dependency evidence; no evidenced cross-sector link exists today. |
| Forward-looking intelligence | Partial | The 24 to 72 hour watch operates; provider maintenance windows are built but off; regulatory deadlines and technology lifecycle dates need sources that carry them. |
| Longitudinal analysis and emerging trends | Outstanding | Only provider recurrence exists; no trend analysis over time. |
| Portal and Telegram access | Partial | Telegram brief operational; the Intelligence workbench tabs (incidents, products, source coverage) are built and wait for portal deployment capacity. |
| Provenance and verified freshness | Partial | Built; needs its database change approved and applied, then activation. |
| Original-publisher and original-date verification | Outstanding | Google News items still lack a verified original publisher and date. |
| Reference set, weekly baseline and continuous improvement | Partial | 15 confirmed material incidents against a target of about 30; no weekly baseline yet; manual verification effort and brief usefulness not measured; no missed-incident learning loop. |
| Read-only SQL access | Outstanding | Deferred by owner as an efficiency improvement; not a blocker. |
