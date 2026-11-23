# Human-review plan for labels, evaluation separation, and third-holdout protocol

## 1. Status of the labels
The 437 rubric-v2 labels come from two AI reviewers of the same model family as the detector's author. They are **provisional development evidence**, not independent
ground truth. No release-grade performance claim is made or implied.

## 2. Possible systematic REFERENCE bias in Reviewer B
Measured on the 437 events: both reviewers called 358 events (81.9%) REFERENCE; A said non-R/B said R for 10 events and B said non-R/A said R for 10 events
(5/1/4 and 5/1/4 across the 150-, 127- and 160-event sets). **There is no asymmetry between A and B.** What the data cannot show is a *shared* bias toward REFERENCE:
both are the same model family under one rubric, and both leaned on default labels for unflagged headlines (B's most common REFERENCE note, "no relevant incident",
covers 235 events; A's, "no operational relevance", covers 269). Reviewer B's process also applied a default REFERENCE to headlines it did not individually flag, by its
own report. A shared false-negative rate for REFERENCE can be estimated only by human review of a stratified negative sample, below.

## 3. Human review queue (`docs/review/human_review_queue_v2.csv`, 98 events; the five Captain-adjudicated events are excluded)
| Group | Count | Reason |
|---|---|---|
| ESCALATE by at least one reviewer | 8 | every remaining positive (the 5 adjudicated cases are settled) |
| Other priority disagreements | 27 | all disputed non-E cases |
| Stratified REFERENCE sample | 63 | of 348 events both reviewers called REFERENCE; deterministic md5 selection stratified by set × source kind (aggregator / primary advisory / other) |
Each row has the AI labels, notes, source and URL, and empty `human_priority`, `human_materiality`, `human_notes` columns. Reviewers: two humans where possible, blind to the AI
labels for the REFERENCE sample (columns hidden), with disagreements adjudicated by the Captain. Outputs: human κ against the AI labels, the shared-false-negative rate for
REFERENCE with its interval, and corrected labels written to new files tagged `rubric_version` and `reviewed_by`, never over the originals.

## 4. Incident level, and enriched versus representative evaluation
* **Unit of evaluation is the incident, not the article.** Escalation recall/precision count incidents (gold unit = reviewed incident group or singleton; model unit = its
  incident group, commentary excluded). Article-level materiality figures are retained only as diagnostics. Grouping is reported separately (pairwise precision/recall and
  false merges).
* **Enriched critical-incident testing** (candidate recall, escalation recall, grouping) uses positives-enriched samples and the challenge set; it **cannot** estimate production
  false-positive rates or alert volume.
* **Representative estimation** uses only a uniformly random sample of all events. Using the 40 random events in holdout2, the model flagged 0 ESCALATE, 2 VERIFY (5.0%, 95% interval
  1.4–16.5%), 0 WATCH. Scaled to about 2,520 events per week (7,561 eligible events over the three-week window) that is roughly 35–416 VERIFY events per week: **far too imprecise to plan
  review load**; about 400 random events would narrow the interval to roughly ±2 points. Alert volume must also be reported after incident grouping, not per article.

## 5. Third-holdout protocol and readiness
| Prerequisite | Status |
|---|---|
| Rubric frozen | **Yes.** v2.1 frozen 2026-11-23 (`docs/rubrics/weekly-evidence-rubric-v2.1.md`). |
| Model frozen (hash + method version) | Not yet. `wk-detect/0.5.0-tiered-v2` is development-grade; freeze after the human review corrects labels. |
| Human-reviewed development labels | **No.** Review queue prepared, reviewers not yet assigned. |
| Adjudication of the five disputed cases | **Complete** (`docs/review/adjudication_v2_final_decisions.csv`). |
| Sampling window of untouched events | Available: only events after 2 Nov that no reviewer or developer has seen. The database holds about three weeks, so the window should be drawn from events collected after the freeze (forward collection) or an unused earlier slice. |
| Positives sufficient | **No.** About 10–13 ESCALATE positives exist in 437 events; 59 incident-level positives are needed for a zero-miss claim at 95% recall (93 with one miss). |
| Verified historical challenge set | In progress; unverified entries are excluded from ground truth. |
**Protocol once ready:** (1) freeze rubric and model, record hashes; (2) two-phase sample: a recall-oriented screen yields candidates, a random sample of screen-negatives estimates
what the screen misses, plus a separate uniformly random sample for representative false-positive and alert-volume estimation; (3) two blind human labellers, κ reported, disagreements
adjudicated by the Captain; (4) run once, report incident-level metrics with exact intervals and sample sizes; (5) no tuning on this set.
**Remaining limitations:** AI-correlated labels; tiny positive counts; one database and one time window; sector lexicons are hand-written; the representative alert-volume estimate has
not been measured at an adequate sample size.
