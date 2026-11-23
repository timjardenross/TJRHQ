# V1 Three-Brief Acceptance Pack (internal preview; nothing sent, scheduled, merged or activated)

Frozen evidence snapshot: 2,514 read-only intelligence events, 16–23 Nov 2026 (72 h slice for the morning view), detector `wk-detect/0.5.1-v1`, rubric 2.1. The three V1 views read the same `EvidenceSet` (same incident ids, materiality, provenance; checked by test). Legacy briefs are unchanged.
Independent checks used here are **blind AI reviewers of the same model family** (not humans): a classifier over 81 V1 candidate incidents (41 actionable + 40 random REFERENCE) and a scan of all 2,514 headlines for material incidents. The scanner dropped lifestyle sources and, from the second half of the week, hid Bloomberg/FT/Financial Newswire (mostly markets), so recall on those feeds is not covered.

## Verdicts
| Brief | Recommendation | Why |
|---|---|---|
| Morning Command Brief | **NEEDS LIMITED CORRECTION** | Finds 8 of the 9 incidents an independent scan rated ESCALATE/VERIFY and keeps evidence discipline, but the ESCALATE tier over-fires and emergency/hazard warnings are not seen (fixes 1, 2) |
| Weekly Intelligence & Decision Brief | **NEEDS LIMITED CORRECTION** | Far better than the legacy "327 high" count and every claim is traceable, but duplicate reports are poorly grouped on a real week (fix 3) and "what changed" needs a stored prior-week snapshot (fix 5) |
| Communications & Presence Brief | **NOT READY** | Candidates are externally relevant and honestly marked "needs a second source", but V1 proposes no argument/angle and cannot assess originality without the existing-content corpus (fix 4) |


## 1. Morning Command Brief — legacy vs V1
**Legacy** (existing posture + signals code, run on the real latest brief row and the real top-12 24 h signals):
```
<legacy code path: _format_intelligence_posture_block + _format_signals_block>
<b>📡 INTELLIGENCE POSTURE</b>
  Posture: <b>🟡 AMBER</b>
  <b>What matters today</b>
  1. Microsoft's Friday 13th outage continues with fraud and employee risk warnings - Insurance Business — Assess dependency on affected platform; activate contingency if critical
  2. US ports face wave of cyberattacks as Los Angeles blocks 120 million attempts - Gulf News — Assess exposure, review controls, monitor ACSC advisories
  3. What's next after no deal at COP31 climate talks? — Monitor situation; assess operational exposure and escalate if conditions worsen
  <b>Changed since yesterday</b>
  - New: Microsoft's Friday 13th outage continues with fraud and employee risk warnings - Insurance Business
  - New: US ports face wave of cyberattacks as Los Angeles blocks 120 million attempts - Gulf News
  - New: What's next after no deal at COP31 climate talks?
  <i>⚠️ 4 intelligence sources were unavailable during this morning collection cycle.</i>

<b>📡 OTHER SIGNALS (24h)</b> <i>(4 HIGH)</i>
  🔴 Guardian Australia: Victoria faced devastating bushfires and an ‘extinction emergency’ this year. So why is nature missing from the election?
  🔴 ABC News: Giants clash over Australia's gas reservation policy
  🔴 ABC News: Foreign minister to elevate AI as national security challenge
  🔴 Guardian Australia: Fred Nile, former NSW politician and figurehead of the rightwing Christian Democratic Party, dies aged 92
```
**V1** (flag-on preview):
```
🛰 EVIDENCE-BASED PICTURE (V1)
274 incident(s) assessed from 868 report(s); method wk-detect/0.5.1-v1.

What matters today — CONFIRMED incidents
- None confirmed in the last 24 hours.

REQUIRES VERIFICATION (unconfirmed or weakly evidenced; not treated as fact)
- [VERIFY] APRA calls Microsoft outage a "near miss" for financial system - Insurance Business — confirmed, ongoing; confidence 0.30 [inc-5449338675; 2 report(s); Google News - APRA/ASIC Operational Resilience, Google News - Criti
    next: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- [VERIFY] US ports face wave of cyberattacks as Los Angeles blocks 120 million attempts - Gulf News — reported; confidence 0.30 [inc-ebd7b7452d; 1 report(s); Google News - Critical Infrastructure/Energy Cyberattack AU]
    next: obtain the organisation's own statement or the regulator's notice confirming what was affected
- [VERIFY] Explosion on Russian ship at Libya port likely caused by drone attack, officials say — reported; confidence 0.60 [inc-6c7faa3ef7; 1 report(s); BBC News]
    next: confirm casualties, damage and service impact with the responsible authority

Operational implications (only what the cited reports state)
- No operational implication is supported by confirmed reports today.

Forward watch, next 24–72 hours
- Verify: APRA calls Microsoft outage a "near miss" for financial system - Insurance Business → confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- Verify: US ports face wave of cyberattacks as Los Angeles blocks 120 million attempts - Gulf News → obtain the organisation's own statement or the regulator's notice confirming what was affected
```

## 2. Weekly Intelligence & Decision Brief — legacy vs V1
**Legacy** (existing weekly OSINT renderer on the same week; the LLM paragraph, capacity and outage-alert blocks need live services and are omitted):
```
<legacy renderer _format_weekly_osint_block; LLM paragraph omitted>
<b>🛰 TECH OSINT — WEEKLY (1000)</b>
  🔴 321 high  ·  🟡 450 medium  ·  🟢 26 low  ·  ⚪ 203 unscored
  🔴 Cloudflare Status: Cloudflare Dashboard and Cloudflare API service issues in EU region (resolved)
  🔴 Java4Shell, NGINX2Shell and more: Why we are not at "Yellow", (Wed, Nov 18th)
  🔴 Anthropic (ANT) IPO on Nasdaq Overcame AI Fears and Warnings
```
**V1**:
```
📊 EVIDENCE-BASED WEEK (V1)
2496 incidents from 2514 reports: 6 escalate, 22 verify, 13 watch; method wk-detect/0.5.1-v1.

What changed this week
- No prior-week snapshot to compare; showing the week's actionable incidents only.

Major incidents
- [ESCALATE provisional] El Salvador Troops Killed in Haiti Blast After Rescue Deployment — confirmed, ongoing; confidence 0.60 [inc-f6adeda659; 1 report(s); Bloomberg]
    next: confirm casualties, damage and service impact with the responsible authority
- [ESCALATE corroborated via aggregator feeds only] APRA calls Microsoft outage a "near miss" for financial system - Insurance Business — confirmed, 130,000 customers, restored; confidence 0.50 [inc-bbd53663f2; 4 report(s); Google
    next: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- [ESCALATE corroborated] Live: Power still out after SA transmission line downed — confirmed, ongoing; confidence 0.70 [inc-3ce4d32eee; 4 report(s); ABC News, Google News - Telstra]
    next: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- [ESCALATE provisional] Microsoft says three-month-old bug behind global M365 outage — confirmed, ongoing; confidence 0.50 [inc-e60e8c0bd7; 1 report(s); iTnews]
    next: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- [ESCALATE provisional] US Airlines Race to Recover From Shutdown — confirmed, ongoing; confidence 0.60 [inc-6eb8a91098; 1 report(s); Bloomberg]
    next: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- [ESCALATE provisional] 104 flights cancelled due to weather conditions at Sydney Airport — confirmed, ongoing; confidence 0.60 [inc-559fa9e396; 1 report(s); ABC News]
    next: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)

Recurring patterns (threshold: ≥3 incidents, ≥3 publishers, ≥2 days)
- cloud_platform: 7 incidents, 7 publishers, 5 days [inc-bbd53663f2, inc-e60e8c0bd7, inc-51055e5a47, inc-c0edb885a5]
- finance: 6 incidents, 7 publishers, 2 days [inc-bbd53663f2, inc-ef80595f75, inc-62c1f4d006, inc-41697a193d]
- telecom: 4 incidents, 7 publishers, 3 days [inc-196727a4bc, inc-aadc26cd36, inc-1ea17ea395, inc-99ff181970]
- retail_food: 3 incidents, 6 publishers, 3 days [inc-eb00ac63a0, inc-7e0bc55c3e, inc-be46a15f69]

Systemic dependencies (named providers appearing in ≥2 incidents; no causal link asserted)
- microsoft: shared by 3 incidents [inc-bbd53663f2, inc-e60e8c0bd7, inc-51055e5a47]
- telstra: shared by 2 incidents [inc-aadc26cd36, inc-1ea17ea395]

Evidence-supported implications (each cites its incident)
- El Salvador Troops Killed in Haiti Blast After Rescue Deployment: confirmed, ongoing; dependencies none recognised [inc-f6adeda659; 1 report(s); Bloomberg]
- APRA calls Microsoft outage a "near miss" for financial system - Insurance Business: confirmed, 130,000 customers, restored; dependencies cloud_platform, finance [inc-bbd53663f2; 4 report(s); Google News - APRA/ASIC Operational 
- Live: Power still out after SA transmission line downed: confirmed, ongoing; dependencies energy [inc-3ce4d32eee; 4 report(s); ABC News, Google News - Telstra]
- Microsoft says three-month-old bug behind global M365 outage: confirmed, ongoing; dependencies cloud_platform [inc-e60e8c0bd7; 1 report(s); iTnews]

Decisions and emerging risks to monitor
- DECIDE: confirm or stand down provisional escalation — El Salvador Troops Killed in Haiti Blast After Rescue Deployment (confirm casualties, damage and service impact with the responsible authority)
- DECIDE: confirm or stand down provisional escalation — Microsoft says three-month-old bug behind global M365 outage (confirm the customer count, affected area and restoration estimate with the network operator or regulator (prim
- DECIDE: confirm or stand down provisional escalation — US Airlines Race to Recover From Shutdown (confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source))
- DECIDE: confirm or stand down provisional escalation — 104 flights cancelled due to weather conditions at Sydney Airport (confirm the customer count, affected area and restoration estimate with the network operator or regulator 
- MONITOR: Microsoft's Friday 13th outage continues with fraud and employee risk warnings - Insurance Business — unresolved: confirm the customer count, affected area and restoration estimate with the network operator or regulator
- MONITOR: US ports face wave of cyberattacks as Los Angeles blocks 120 million attempts - Gulf News — unresolved: obtain the organisation's own statement or the regulator's notice confirming what was affected
- MONITOR: Explosion on Russian ship at Libya port likely caused by drone attack, officials say — unresolved: confirm casualties, damage and service impact with the responsible authority
- MONITOR: FBI database reportedly hacked — unresolved: obtain the organisation's own statement or the regulator's notice confirming what was affected
```

## 3. Communications & Presence Brief — legacy vs V1
**Legacy** (existing composer on the platform's current Command Memory lessons; the legacy brief ranks internal records, not external events):
```
*Weekly Thought Leadership Brief — Mon 23 Nov 2026*
_Communications & Presence Officer · "What should I be talking about this week?"_

*Recommended this week — prioritised, evidence-backed:*
1. *Specialists Advise, Captains Decide* — _AI-Augmented Leadership_ · suggest a *Lessons Learned*
     ↳ evidence: Specialists Advise, Captains Decide _(source lesson:LL-003)_
     ↳ advances: Career & Professional Impact
2. *Authority Hierarchy Must Be Explicit* — _Operational Resilience_ · suggest a *Lessons Learned*
     ↳ evidence: Authority Hierarchy Must Be Explicit _(source lesson:LL-006)_
     ↳ advances: Career & Professional Impact
3. *Competing Authority Claims Accumulate Unless Prevented* — _Operational Resilience_ · suggest a *Lessons Learned*
     ↳ evidence: Competing Authority Claims Accumulate Unless Prevented _(source lesson:LL-007)_
     ↳ advances: Career & Professional Impact
4. *Authority Separation Is a First-Class Architectural Constraint* — _Operational Resilience_ · suggest a *Lessons Learned*
     ↳ evidence: Authority Separation Is a First-Class Architectural Constraint _(source lesson:LL-009)_
     ↳ advances: Career & Professional Impact

*Themes in the pipeline:* Operational Resilience (3) · AI-Augmented Leadership (1)
*Strategic alignment:* Career & Professional Impact (4)

_Generate a draft with `/comms draft <n>`. Communications & Presence Officer scaffolds; the Captain writes, edits, and publishes._
```
**V1** (legacy output unchanged, plus the evidence section):
```
*Weekly Thought Leadership Brief — Mon 23 Nov 2026*
_Communications & Presence Officer · "What should I be talking about this week?"_

*Recommended this week — prioritised, evidence-backed:*
1. *Specialists Advise, Captains Decide* — _AI-Augmented Leadership_ · suggest a *Lessons Learned*
     ↳ evidence: Specialists Advise, Captains Decide _(source lesson:LL-003)_
     ↳ advances: Career & Professional Impact
2. *Authority Hierarchy Must Be Explicit* — _Operational Resilience_ · suggest a *Lessons Learned*
     ↳ evidence: Authority Hierarchy Must Be Explicit _(source lesson:LL-006)_
     ↳ advances: Career & Professional Impact
3. *Competing Authority Claims Accumulate Unless Prevented* — _Operational Resilience_ · suggest a *Lessons Learned*
     ↳ evidence: Competing Authority Claims Accumulate Unless Prevented _(source lesson:LL-007)_
     ↳ advances: Career & Professional Impact
4. *Authority Separation Is a First-Class Architectural Constraint* — _Operational Resilience_ · suggest a *Lessons Learned*
     ↳ evidence: Authority Separation Is a First-Class Architectural Constraint _(source lesson:LL-009)_
     ↳ advances: Career & Professional Impact

*Themes in the pipeline:* Operational Resilience (3) · AI-Augmented Leadership (1)
*Strategic alignment:* Career & Professional Impact (4)

_Generate a draft with `/comms draft <n>`. Communications & Presence Officer scaffolds; the Captain writes, edits, and publishes._

📡 EVIDENCE-BASED CONTRIBUTION CANDIDATES (V1) — recommendation only; publication is approval-only

- Authorities investigating four-minute Triple Zero outage in Canberra [inc-99ff181970; 1 report(s); ABC News]
    relevance: Operational Resilience · originality: new angle (similarity 0.00)
    evidence: confidence 0.60, sources mainstream, 1 independent publisher(s)
    publication readiness: needs a second or primary source before drafting
    research gap: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- White House removes cyber-security chief after series of tech outages [inc-4a23144426; 1 report(s); BBC News]
    relevance: Operational Resilience · originality: new angle (similarity 0.00)
    evidence: confidence 0.60, sources mainstream, 1 independent publisher(s)
    publication readiness: needs a second or primary source before drafting
    research gap: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- US tech outages blamed on rush to fix bugs found by AI [inc-9a4abe3142; 1 report(s); Financial Times]
    relevance: AI-Augmented Leadership · originality: new angle (similarity 0.00)
    evidence: confidence 0.60, sources mainstream, 1 independent publisher(s)
    publication readiness: needs a second or primary source before drafting
    research gap: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- NSA hit with system outage as US tech woes continue [inc-fcf75348a7; 1 report(s); ABC News]
    relevance: Operational Resilience · originality: new angle (similarity 0.00)
    evidence: confidence 0.60, sources mainstream, 1 independent publisher(s)
    publication readiness: needs a second or primary source before drafting
    research gap: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
- APRA calls Microsoft outage a "near miss" for financial system - Insurance Business [inc-bbd53663f2; 4 report(s); Google News - APRA/ASIC Operational Resilience, Google News - Telstra]
    relevance: Operational Resilience · originality: new angle (similarity 0.00)
    evidence: confidence 0.50, sources aggregator, 3 independent publisher(s)
    publication readiness: needs a second or primary source before drafting
    research gap: confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)
```

Per-incident detail for every item above, with URLs, is in `docs/review/v1_review_pack.csv`.

## 4. Material improvements
* **Morning:** legacy "what matters today" led with a one-week-old Microsoft outage and a climate-talks story and filled "OTHER SIGNALS" with four politics/obituary items; V1 states plainly that nothing was confirmed in 24 h, separates unconfirmed items, names the missing evidence and gives a next verification action for each.
* **Weekly:** replaces "321 high / 450 medium" (a source-confidence label) with 6 ESCALATE, 22 VERIFY and 13 WATCH, each citing incident id, report count and publishers; patterns and shared providers use stated thresholds and assert no causes; open decisions are listed.
* **Comms:** adds evidence status, source kinds, publication readiness and a research gap to each candidate and never calls aggregator-only evidence ready to draft.

## 5. Significant misses, false positives and unsupported claims (independent blind AI review; not human)
* **ESCALATE precision is weak.** Of 6 V1 ESCALATE items the reviewer rated 1 E, 3 V and 2 R (irrelevant): overseas military casualties and weather-related flight cancellations. Of the 22 VERIFY items it rated 12 V, 8 W and 2 R (a drone explosion on a Russian ship at a Libyan port; a crime story). Overall 37 of 41 actionable items were relevant (W or above) and 4 were not.
* **Material misses are few at the top, many at the bottom.** Of 9 incidents the scan rated ESCALATE/VERIFY, V1 reached VERIFY or ESCALATE on 8; the miss was an anonymously sourced USDA cyberattack report. Of 24 incidents the scan rated WATCH, 15 were REFERENCE in V1: natural-hazard and emergency warnings (Darwin magnitude-6.6 earthquake, hail, an emergency fire warning), health/water items (ambulance-delay deaths, metals in tap water, vape hospitalisations), a forecast reserve shortfall notice (AEMO LOR2), a University of Melbourne exam "tech failure", US bank online-banking delays (headline begins "What to know…" so it is treated as commentary), and open-source flaws. Of the 40 sampled REFERENCE incidents the reviewer rated 5 as W/V, none as E.
* **Grouping on a real week is weak.** Only 43 of 245 same-incident report pairs in the scan's groups were grouped by V1 (18%; the scan's groups are looser than single incidents, so this overstates the gap, but the Eyre Peninsula blackout split four ways and the M365 outage five ways). One V1 incident merged two scan incidents. Duplicates therefore inflate counts and can hide corroboration.
* **Unsupported claims:** none found in V1 text (every incident line is generated from fields and cites incident id and reports). Limits: "confirmed" reflects a consequence word in the headline, not a verified fact; aggregator-only incidents can show "corroborated" when several named outlets repeat a report; the SA outage shows "corroborated" although all reports come from one publisher plus an aggregator feed.
* **Original sentinel misses** (run-1 AEMO market suspension, Optus triple-zero failure, CrowdStrike, Log4Shell, JLR): after generic fixes the first three are VERIFY/ESCALATE on at least one contemporary headline; Log4Shell and JLR reach only WATCH or REFERENCE (listed in `docs/review/v1_review_pack_sentinels.csv`).

## 6. Human-review findings
None yet from a human. The Captain's review pack is `docs/review/v1_review_pack.csv` (63 rows: 6 ESCALATE; the 22 VERIFY ranked by sector tier, materiality and event type; the 5 Communications candidates; 30 sampled REFERENCE incidents with why-excluded) and `v1_review_pack_sentinels.csv` (the 5 original sentinel misses with every contemporary headline and its current V1 result). V1 values and the blind AI labels are frozen in their own columns; corrections go in `human_decision`, `human_correction`, `human_notes` and never overwrite them. Suggested effort: the 6 + 22 + 5 candidates + 5 sentinel groups (about 40 items); the 30-item REFERENCE sample is optional.

## 7. Remaining defects, ranked by consequence
1. **ESCALATE over-fires on out-of-remit events** (overseas conflict casualties; weather cancellations): erodes trust in the top of the morning and weekly briefs.
2. **No handling of natural-hazard, emergency-warning and forecast-notice events**: the morning forward watch cannot see an emergency fire warning, an earthquake or an AEMO reserve notice.
3. **Poor grouping of outage reports on real data** (splits an incident across 4–5 items; the same organisation's reports are separated by the service-conflict guard).
4. **Communications brief has no proposed argument and no originality input**, and most candidates rest on a single mainstream report.
5. **"What changed this week" has no prior snapshot**, so it cannot show changes.
6. **Headline-only detection**: sector and event lexicons are hand-written; Log4Shell-type advisories and manufacturers such as JLR stay low.
7. Aggregator syndication is judged from a wire-name suffix, which undercounts independence (conservative) but can mislabel corroboration.
8. Targets: high-materiality recall 5/7 (71%) and precision 5/9 (56%), grouping recall 44/86 (51%), grouping precision 44/44 on the provisional labels (see the readiness pack); none is demonstrated, and none is a prerequisite for this preview.

## 8. Recommended minimum-fix list for initial release
(1) Restrict ESCALATE on safety/physical events to in-remit geography or recognised sectors. (2) Add a hazard/emergency-warning class and primary-advisory forward notices (AEMO market notices, BoM/emergency warnings). (3) Fix outage grouping (relax the service-conflict guard for same-organisation outages within 72 h; add a regression test from the Eyre Peninsula and M365 cases). (4) Comms: supply existing-content titles for originality and add a one-line proposed angle with its evidence. (5) Wire the existing `SnapshotStore` so the weekly view has `previous_ids`. (6) Human review of this pack before any flag is turned on for live delivery.

## 9. Proposed merge and rollout sequence (each step needs approval)
1. #661: operator VM checks (external flag unset; diagnostic exit code), then merge. **Final #661 recommendation: GO once the two VM checks pass** — CI is green on head `40364379`; the only open item is VM access, which this session does not have.
2. #658 (flag off). 3. PR #662 (V1) in place of #660, flags off; #659 stays parked. 4. Internal preview: run the three previews daily offline for one week (no flags in production). 5. Human review of the pack and of that week's ESCALATE/VERIFY items; apply fixes 1–5. 6. Enable `BRIEF_EVIDENCE_V1_MORNING` alongside the legacy brief for the Captain only, then weekly, then comms, each after a precision check against the live targets (recall ≥75%, precision ≥75%, grouping recall ≥75%, grouping precision ≥90%). 7. Replace legacy sections only after that.
