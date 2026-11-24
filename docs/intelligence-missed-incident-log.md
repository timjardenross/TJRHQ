# Intelligence missed-incident log

One entry per incident the intelligence product should have surfaced and did not (or surfaced late, wrongly, or silently).
Add an entry the day a miss is found; update its **Correction** line when the fix lands. Keep it short. The weekly baseline
(`tools/intelligence/weekly_baseline.py`) lists misses against the reference set; this file records why and what changed.

Facts below were read from production `intelligence_events` and the source registry on 2026-11-24 (SELECT only) unless noted.
"Observed" means seen in those rows. "Cause (inferred)" means a reasoned explanation not yet confirmed by reading the code path.

## Entry template

```
### LOG-NNN  <short name>  (found YYYY-MM-DD)
- What happened: <the real incident, one line, with the first public report time>
- How TJR handled it: <observed: collected? when? disposition? reached a brief?>
- Miss type: not collected | collected late | suppressed | detected but not briefed | wrong disposition | source silently empty
- Cause: <observed or inferred, say which>
- Correction made: <change, PR or commit, date; or "none yet">
- Correction needed: <what is still open, who decides>
- Reference set: <RS-id / C2-id, or "not yet in a set">
```

## Entries

### LOG-001  Victorian VCE exam-paper hack  (found 2026-11-24)
- What happened: the VCAA website was hacked during the VCE exam period; a hacker claimed to have sold exam papers to hundreds of students. First report TJR collected: ABC News, 2026-11-11T09:15Z.
- How TJR handled it: observed. ABC item collected 31 minutes after publication, disposition REFERENCE. Guardian Australia follow-up (2026-11-11T23:28Z) collected within 2 hours, disposition WATCH. Neither reached a brief.
- Miss type: detected but not briefed.
- Cause (inferred): the disposition step did not treat a state-government exam-integrity hack as brief-worthy; not yet traced to a specific rule.
- Correction made: none yet. Proposed as candidate C2-014 in `knowledge/intelligence-reference-set/reference_set_v2_candidates.json`.
- Correction needed: owner decides whether it is material (promote C2-014); trace why REFERENCE/WATCH was assigned and whether education or exam authorities need a relevance rule.
- Reference set: C2-014 (candidate).

### LOG-002  ABC staff devices wiped after cyber attack  (found 2026-11-24)
- What happened: ABC wiped staff devices after a sophisticated cyber attack. Reported 2026-10-22 (Google News copy of the ABC story) and 2026-10-23T01:41Z (ABC News).
- How TJR handled it: observed. The direct ABC item was collected 15 minutes after publication but dispositioned WATCH and never briefed. The only BRIEF-disposition copy was the Google News copy, collected 2026-11-04, 13 days after publication, and it also did not reach a brief.
- Miss type: detected but not briefed; aggregator copy collected late.
- Cause (inferred): WATCH assigned to the direct item; Google News feed lag of about two weeks for that item.
- Correction made: none yet for disposition. Original-publisher and original-date verification for Google News items is tracked as its own checklist capability.
- Correction needed: owner decides materiality (C2-011); check why a named-organisation cyber incident was WATCH.
- Reference set: C2-011 (candidate).

### LOG-003  Citrix NetScaler critical alert never reached a brief  (found 2026-11-24)
- What happened: ASD/ACSC critical alert on Citrix NetScaler ADC/Gateway zero-days exploited including Australian organisations. First report TJR collected 2026-09-27T10:33Z (ACSC page says 28 Sep). An earlier ACSC Citrix critical alert was also collected on 2026-09-04.
- How TJR handled it: observed in the reference set (RS-031): first collected 2026-09-28T20:00Z, about 33 hours after the first report, from 5 non-aggregator publishers (9 events); the ACSC item was dispositioned ESCALATE; 3 of the 9 events were suppressed; 0 events reached a brief and 0 daily briefs mention it.
- Miss type: detected but not briefed (and part suppressed).
- Cause (inferred): ESCALATE did not translate into brief inclusion, and suppression was applied to related items. Consistent with the checklist note that the enhanced prioritisation tiers lose material detection; not traced for this incident.
- Correction made: none for this incident. The prioritisation correction and re-measurement are tracked under the checklist's conversion and prioritisation capability.
- Correction needed: re-run this incident through the corrected tiers when they are measured; confirm an ESCALATE primary-authority alert for Australian exposure always reaches the morning brief.
- Reference set: RS-031 (confirmed_material, draft v1).

### LOG-004  ASIC sources silently returned nothing  (found 2026-11)
- What happened: ASIC News Centre and ASIC Enforcement Activity returned "no items" on every check from early September while registered as active, so no ASIC release was collected. Last ASIC News Centre event in the table: 2026-09-07.
- How TJR handled it: observed. Source health looked "ok" with zero items; nothing alerted. The plain fetch held only navigation chrome (the newsroom is client-rendered) and the link extraction skipped every link.
- Miss type: source silently empty.
- Cause (observed in the repair commit): client-rendered page plus an extraction pattern that matched nothing, with no rule that flags an active source delivering nothing for weeks.
- Correction made: the ASIC newsroom is now read through Firecrawl with link extraction (in main via #717), and source effectiveness states (HEALTHY, QUIET, UNVERIFIED, DEGRADED, BROKEN, UNCOVERED) now make an empty-but-active source visible.
- Correction needed: activation and verification in production. On 2026-11-24 06:33Z both ASIC sources still showed 14 of 14 failed checks in the last 7 days and no event since 7 Sep (state BROKEN in the first weekly baseline). Confirm a real ASIC release is collected after activation.
- Reference set: not applicable (coverage failure, no single incident).

### LOG-005  Victorian court data leak suppressed  (found 2026-11-24)
- What happened: hackers leaked sensitive Victorian court data to the dark web. First report TJR collected: ABC News, 2026-08-06T19:10Z.
- How TJR handled it: observed. Collected 50 minutes after publication, disposition SUPPRESS, `suppressed` true, never briefed.
- Miss type: suppressed.
- Cause (inferred): suppression rules treated it as not relevant; reason not read from `suppression_reason`.
- Correction made: none yet. Proposed as candidate C2-001.
- Correction needed: read `suppression_reason` for this event and fix the rule if it was wrong; owner decides materiality.
- Reference set: C2-001 (candidate).

### LOG-006  OAIC notification sources not delivering  (found 2026-11-24 by the first weekly baseline)
- What happened: OAIC Breach Notifications and OAIC Privacy Determinations & News have failed 14 of 14 checks in the last 7 days; last events 2026-08-10 and 2026-08-29. RBA Media Releases and the Optus National Outage Register are registered active but were not checked at all in the last 7 days.
- How TJR handled it: observed in the source-coverage section of `docs/intelligence-weekly-baseline-2026-11-24.md` (BROKEN).
- Miss type: source not collecting.
- Cause: unknown; not investigated.
- Correction made: none. The weekly baseline now counts source-coverage states every week.
- Correction needed: owner decides whether each is wanted; if so, diagnose and repair, then confirm a real item is collected.
- Reference set: not applicable.
