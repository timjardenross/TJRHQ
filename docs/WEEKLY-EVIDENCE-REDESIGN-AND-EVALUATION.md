# Evidence detection redesign (wk-detect/0.3.0-staged) and evaluation methodology

Offline only. `intelligence/event_detection.py` is not imported by any live path. The frozen `b92c1b39`
module (`intelligence/weekly_evidence.py`) is unchanged and is the comparison baseline.

## 1. Why the previous model failed (root causes of the seven holdout misses)
The holdout (127 events, 3–16 Nov) is preserved unchanged and is now **contaminated**: its failures informed this design,
so it is historical evidence only and must not be used to claim performance.

| # | Missed event (shortened) | Root cause | Category |
|---|---|---|---|
| 1 | Coles "cybersecurity incident" | Vocabulary has "cyber incident", not "cybersecurity incident"; no entity/sector awareness | lexical |
| 2 | Microsoft "deeply sorry" for global disruption | No "outage" token; "disruption" unscored | lexical |
| 3 | Bloomberg "Microsoft races to fix outage" | scored medium: term present but no entity/scale reasoning | calibration |
| 4 | Shop freezers hit by cyber-attack | "cyber-attack" hyphen form not matched; consequence (food supply) invisible | lexical + consequence |
| 5 | NSW Health "cybersecurity breach … major incident" | same vocabulary gap; health system not recognised as essential | lexical + entity |
| 6 | Reuters "ongoing cyber threat to refrigeration systems" | aggregator + no sector link | entity |
| 7 | National Parks booking service hacked in three states | "hacked", "personal data stolen" absent from the scored list | lexical |
Common cause: scoring depended on title terms instead of **who/what is affected and how**. A vocabulary patch fixes
these seven and fails the next seven; hence the staged redesign.

The earlier "eight events hidden below the legacy rank floor" (legacy sample floor 18.6 of 2,376 usable events) share
the cause on the *legacy* side: the legacy ranker sorts by relevance/recency, so single high-impact reports (retailer
cyber incident, card-skimmer campaign, vendor attack on card networks, brokerage client-data access) rank below a cut
that keeps 1,000 events. Stage 1 never ranks before detecting, so they cannot be cut.

## 2. Architecture and deterministic rules
**Stage 1 — candidate detection.** Extract sectors/entities (lexicon in the module), event type (cyber incident, outage,
vulnerability), scale cues, actual-vs-potential cues, commentary/roundup markers. A candidate needs an event type plus a
sector, a scale cue, or a stated compromise; vulnerability alone needs exploitation evidence. A bare cyber mention with no
sector or scale is not a candidate. A stated compromise of unknown reach is kept (impact `potential_high` → VERIFY).
**Stage 2 — incident correlation.** Two reports link when they share an event class, fall within a class window
(outage 72 h, cyber 7 d), and score ≥0.6 (or ≥0.5 with a named entity or 2 rare shared terms) from: shared named entity
(+0.5), shared sector (+0.2), shared rare content terms by IDF (+0.15 each, max 0.3), minus a geography conflict. Same
organisation with disjoint named services (Outlook vs Azure) never links. Clusters merge by average linkage (≥50% of cross
pairs linked and every member tied), so one chance pair cannot chain incidents. Commentary attaches through one link and
never bridges clusters. Publisher-suffix boilerplate ("- ABC News & Headlines") is stripped before matching. Syndicated
copies (≥0.8 stem overlap or a wire suffix) are marked and do not count as independent publishers. Each group records member
report IDs, per-pair confidence and reason, and overall grouping confidence. Advisories are never grouped by prose.
**Stage 3 — materiality and evidence.** Impact: `actual_major` (actual disruption of an essential service, or scale),
`actual_moderate`, `potential_high`, `potential_low`. Commentary and roundups cannot be actual impact. Evidence confidence
comes from source kind and independent-publisher count and is a separate axis. No causal edges are produced anywhere.
**Stage 4 — decision.** ESCALATE: `actual_major` with primary/mainstream/specialist evidence or ≥2 independent publishers
(single report allowed, marked provisional with a verification follow-up); or an advisory with exploitation + known exposure
+ primary source. VERIFY: `actual_major` on aggregator-only evidence, potential high-impact, stated compromise of unknown
reach. WATCH: moderate actual impact, exploited advisory without known exposure. REFERENCE: otherwise. CISA KEV is never
critical by itself.
**Uncertainty handling.** Uncertain high-impact candidates are retained as VERIFY; nothing is dropped for lacking corroboration.

## 3. Decision needed from the Captain
The `ESCALATE` rule depends on which sectors count as essential (`ESSENTIAL` in the module: retail/food supply, health,
telecom, aviation, energy, finance, cloud platforms, government, transport/water). On the preserved holdout the model escalates
a supermarket cyber incident, a supermarket freezer attack and a national-parks booking breach that the assistant labelled WATCH.
Whether those are "major operational consequence" is a policy decision, not a modelling one.

## 4. Results so far — DEVELOPMENT DATA ONLY (not release evidence)
Both sets were seen while building the model. Labels are the assistant's, from an older rubric on the 150-event set (it
treated KEV advisories and "AI as national-security challenge" as high materiality, which the new policy rejects).
| Measure | 150 dev set | 127 historical holdout (contaminated) |
|---|---|---|
| Candidate recall | 21/23 = 0.91 (CI 0.73–0.98) | 15/17 = 0.88 (CI 0.66–0.97) |
| High-materiality precision | 10/11 | 12/13 |
| High-materiality recall | 10/21 = 0.48 (labels from the older rubric) | 12/17 = 0.71 |
| Escalation recall (incident level) | 1/1 | 3/3 (CI 0.44–1.00) |
| Escalation precision | 1/7 | 3/6 (see §3) |
| Grouping recall | 10/13 = 0.77 | 17/19 = 0.89 |
| Grouping precision (excl. commentary) | 10/13 (3 "false merges" are unlabelled same-incident blackout reports) | 17/17 |
| Frozen b92c1b39 high-materiality P/R | 0.88 / 1.00 (tuned on it) | 0.83 / 0.59 |
None of this meets, or is evidence for, the release targets. The numbers show that the staged design generalises better than
vocabulary tuning on the same data and nothing more.

## 5. Evaluation methodology (independent review)
1. **Reference set** = the 150 dev events + the 127 historical events, relabelled under the new rubric by two independent
   reviewers (see below) with source evidence (publisher, URL, timestamps) in `docs/review/*_review_sheet.csv`. The 127-event
   original labels and fixture stay untouched.
2. **Fresh holdout** (~160 events, 12 Oct–2 Nov, before both existing windows): deterministic md5 sampling over five strata
   (top-ranked 30, random 40, keyword-enriched 40, primary advisories 25, routine 25). Sampled and written to disk by a worker
   that does not report titles; the model author does not read titles. Labelled blind by two reviewers who never see model
   code or output, using one written rubric for materiality (actual impact), priority, incident group membership and role
   (original, commentary, syndicated). Agreement reported as Cohen's kappa; disagreements are listed for the Captain, not
   resolved by the author. The model is run once, frozen, on the agreed labels.
3. **Metrics, reported separately with denominators and Wilson 95% intervals:** candidate recall; high-materiality precision
   and recall; escalation recall and precision (incident level); incident-grouping pairwise recall and precision; false-merge
   rate; per-stratum results; failure categories; comparison with legacy fields and the frozen b92c1b39.
4. **Thresholds.** Critical-event (escalation) recall ≥95%, high-materiality precision ≥85%, grouping recall ≥80% (as set).
   **Proposed:** grouping pairwise precision ≥95% and false-merge rate ≤5% of multi-report groups. Because intervals will be
   wide with ~20 positives, a release claim needs the lower 95% bound, not the point estimate, above the target, or the
   target stated as "not demonstrated".
5. **Limits:** the database holds roughly three weeks of events (pruned 11 Oct), so older high-impact outages, cyber incidents
   and critical vulnerabilities cannot be sampled from it. A curated historical set from public records is needed, ideally
   supplied by the Captain or a human researcher, and must be reported as a separate stratum, not mixed into the sample.

## 6. Status of the evaluation work
* Two data workers (fresh-holdout sampling; review-sheet evidence) are blocked on a permission prompt for read-only SQL in
  the Supabase tool, so neither file exists yet. The fresh-holdout result is therefore **not available**.
* Independent labelling has not started; it needs the sampled file.
