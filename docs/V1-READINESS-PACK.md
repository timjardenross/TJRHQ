# V1 readiness pack — shared evidence foundation across the Morning, Weekly and Communications briefs

Branch `claude/v1-brief-evidence-uplift-7n6u2j` = #661 (privacy) + #658 (comms editorial, flag off) + #660 (evidence foundation) + the V1 integration. #659 is excluded.
Nothing is merged, deployed, scheduled or sent. All integration is behind default-off flags; with flags off the three briefs render exactly as before (tested).

## 1. #661 privacy release status
CI green on `40364379` (18 of 18 checks complete; 17 success, 1 skipped as not applicable, including `merge-gate`). Privacy controls verified by 126 tests plus an end-to-end XO handler test (exact fallback wording; only loopback hosts requested), a
live fallback demonstration (cloud keys set, no local model: `(None, None)`, only `localhost` attempted), telemetry/log checks, and a no-repository-enables-the-flag check.
**Blocked on one thing: no VM access path from this session** (the only attached computer's folders are not offered to cloud sessions), so an authorised operator must (a) confirm `HEALTH_LLM_EXTERNAL_ALLOWED` is unset and (b) run
`python3 scripts/check_health_llm_local.py` and record the exit code. Exact production action needing approval: merge #661 to `main` (auto-deploys within about 5 minutes, restarts ten services), followed by the operator health checks in `docs/PRIVACY-CONTAINMENT-661-ASSESSMENT.md` §8.

## 2. Shared evidence foundation against the 75% targets (one bounded run; model frozen at `27a9ceaa`, `wk-detect/0.5.1-v1`)
Evidence: 437 headlines labelled under frozen rubric 2.1 by two AI reviewers of the same model family (**provisional, not independent ground truth**), scored at the **incident** level, plus 23 verified historical sentinel incidents. Intervals are Wilson 95%.
| V1 criterion | Target | Measured (run 1) | Verdict |
|---|---|---|---|
| High-materiality recall | ≥75% | 5/7 = 71% (CI 36–92%); 'both-reviewers' labels 3/3 | **not demonstrated** (7 positives) |
| High-materiality precision | ≥75% | 5/9 = 56% (27–81%); 'both' labels 3/9 | **not met** |
| Incident-grouping recall | ≥75% | 44/86 pairs = 51% (41–61%); 44/67 = 66% for pairs between detector candidates | **not met** |
| Incident-grouping precision | ≥90% | 44/44 = 100% (92–100%), 0 false merges | **met** |
| Critical sentinels detected or retained for verification | all | 18/23 = 78% (58–90%) by best contemporary headline; 16/23 on the first headline | **not met** (5 missed) |
Sentinel misses were investigated: three were detector defects (a list-style headline mis-read as a roundup, "network failure" not recognised, an energy-market suspension with no event word) and were fixed generically; a **post-fix re-run on the same data (not an independent test)** gives
21/23 = 91% (73–98%) best headline, 19/23 = 83% first headline, and 23/23 at least WATCH. Still missed: Log4Shell advisory headlines (no exploitation wording) and Jaguar Land Rover (manufacturer not in the sector lexicon; it reaches WATCH, not VERIFY). Labelled-event metrics did not change.
Negatives (15 verified non-incidents): 1 reached ESCALATE (a real global outage that was not a cyber-attack, which is correct for outage detection), 6 reached VERIFY, none was dismissed as a routine notice by error that we can see.
**Representative week (not enriched):** the full 7 days to 23 Nov, 2,514 reports, produce 2,496 incidents of which 6 ESCALATE (provisional unless corroborated), 22 VERIFY, 13 WATCH, versus the legacy report's "327 high". Of the 6 escalations the author judges 4 clearly in scope; 1 is borderline (104 flights cancelled by weather) and 1 is
overseas military casualties (outside the operational-resilience remit). Precision on this week is **not measured**: no human has reviewed these 41 items. An earlier run on the same week, before the V1 guards, produced 24 escalations, most of them false (summaries as input, court verdicts, market commentary, politics, hedged reports); those defects were fixed and tested.
Known weaknesses: tiny positive counts (7 high-materiality incidents in 437 events); AI-correlated labels; hand-written sector/event lexicons (headline-only, no body text); grouping misses differently worded reports; advisories are never grouped by prose; the weekly "what changed" section needs a stored prior-week snapshot (`previous_ids`) and shows none until one exists.

## 3. Before and after (internal preview, 16–23 Nov data, nothing sent; full text in `docs/previews/`)
**Morning Command Brief.** Before (legacy posture + signals): "What matters today: Microsoft's Friday 13th outage continues…, US ports face wave of cyberattacks…, What's next after no deal at COP31 climate talks?"; "OTHER SIGNALS (24h) 4 HIGH": Victoria election/nature, gas reservation policy, AI national security, an obituary.
After (flag on): CONFIRMED incidents "None confirmed in the last 24 hours"; REQUIRES VERIFICATION: APRA "near miss" Microsoft outage (aggregator feeds, confidence 0.30), US ports cyberattack claim (aggregator, 0.30), Russian ship explosion (BBC, unconfirmed cause) — each with incident id, report count, publishers and a next verification action; implications "none supported by confirmed reports"; forward watch lists the same verification items.
**Weekly Intelligence & Decision Brief.** Before: "TECH OSINT — WEEKLY (1000) 327 high · 447 medium…", top items a status page, a security diary and a politics piece, a health block of trial registrations, and a "Recovery confidence 10%" built from two pulses. After: 6 escalations with incident ids and provenance (SA Eyre Peninsula outage, Microsoft M365/near-miss outages, US airlines shutdown, Sydney flight cancellations, one overseas blast),
patterns that met the ≥3 incidents/≥3 publishers/≥2 days threshold (cloud platforms 7, finance 6, telecom 4, retail/food 3), shared providers (Microsoft in 3 incidents, Telstra in 2) with no causal claim, implications that each cite an incident, and DECIDE/MONITOR lines (4 provisional escalations to confirm or stand down, 4 items to verify).
**Communications & Presence Brief.** Before: legacy ranking of internal lessons ("Specialists Advise, Captains Decide", "Authority Hierarchy Must Be Explicit"…). After: the same content plus evidence-based contribution candidates (Triple Zero outage in Canberra, White House cyber chief removal after outages, AI-found bugs and outages, NSA outage, APRA/Microsoft near miss), each with pillar relevance, originality (not
assessed when no existing titles are supplied), evidence confidence and source kinds, publication readiness ("needs a second or primary source", never "ready" on aggregator feeds alone) and a research gap; publication is approval-only.
All three views read the **same** `EvidenceSet`: the same incident ids (checked by test), materiality and report provenance; none has its own scoring.

## 4. Safeguards
Flags default off (`BRIEF_EVIDENCE_V1`, `_MORNING`, `_WEEKLY`, `_COMMS`); a failure in the evidence layer returns nothing and the legacy brief renders; every incident line cites incident id, report count and publishers; unconfirmed breaches and KEV listings never escalate; provisional escalations are marked with a follow-up;
commentary, retrospective items and aggregator-only evidence cannot reach ESCALATE or "ready to draft"; no causal links are produced; the evidence layer reads public OSINT only and never touches personal-health tables (privacy #661 unchanged); schedules, interfaces and delivery are untouched; external publication stays approval-only.

## 5. Proposed merge and rollout sequence (each step needs your approval)
1. VM operator checks, then merge #661. 2. Merge #658 (flag off). 3. Merge the V1 branch in place of #660 (it contains #660's commits; flags off; #659 stays parked). 4. Internal preview only: turn on `BRIEF_EVIDENCE_V1_MORNING` for one week while the legacy brief still sends; compare daily. 5. Human review of the 98-event queue and of that week's ESCALATE/VERIFY items; measure precision. 6. Weekly flag, then comms flag, each after a human-reviewed precision check. 7. Only then consider replacing legacy sections.

## 6. Decisions required
(a) Operator to run the two VM checks, then authorise the #661 merge. (b) Whether to proceed to an internal preview given that high-materiality precision (56%) and grouping recall (51%) are below 75% on provisional labels; my recommendation is yes, as a flag-on preview with human review, not activation. (c) Assign human reviewers for the 98-event queue (minimum independent review). (d) Approve the V1 branch merge order above.
