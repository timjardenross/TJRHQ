# Rubric v2 relabelling (437 events) and model 0.5.0 on those labels — DEVELOPMENT EVIDENCE ONLY

Rubric 2.0 (`docs/rubrics/weekly-evidence-rubric-v2.md`) was frozen and committed (`fad77804`) before any v2 label was written.
The 150-event dev set, the 127-event historical holdout and the 160-event holdout2 were merged into one md5-ordered, label-free input
and labelled by two blind reviewers (A in order, B in reverse order; model-family reviewers, so correlated with the author).
Original v1 labels and fixtures are unchanged for audit history. v2 files: `tests/fixtures/labels_v2_reviewer{A,B}.json`,
`weekly_evidence_v2_{dev150,hist127,h2_160}_{either,both}.json`.

## Agreement (437 events)
| Field | κ | raw |
|---|---|---|
| priority (E/V/W/R) | 0.765 | 0.927 |
| materiality | 0.724 | 0.938 |
| impact status | 0.802 | 0.899 |
| event type | 0.917 | 0.961 |
| sector tier | 0.803 | 0.888 |
| role | 0.939 | 0.995 |
| evidence | 0.719 | 0.860 |
| urgency | 0.716 | 0.924 |
| escalate vs not | 0.756 | 0.989 |
Incident-group pairs: A 134, B 134, both 132 (agreement on 98%). Priority disagreements: 32; **escalate disagreements: 5**.
Escalate counts: A 10, B 11 (dev150 0 / 3, hist127 8 / 7, holdout2 2 / 1).

## Adjudication (transparent)
No disagreement was resolved by the model's author. The five escalate disagreements are listed with both reviewers' notes in
`docs/review/adjudication_v2_escalate_disagreements.csv` with empty `captain_decision` columns. Until the Captain decides, results are
reported for two label sets: **either** (positive if either reviewer says high/ESCALATE) and **both** (positive only if both do).

## Model 0.5.0 against v2 labels (development sets; all seen during development)
| Set (n) | Variant | Candidate recall | Escalation recall | Escalation precision | Grouping recall / precision |
|---|---|---|---|---|---|
| dev150 | either | 9/9 | 1/1 | 1/4 | 13/33 / 13/13 |
| dev150 | both | 4/4 | 0/0 | 0/4 | 13/33 / 13/13 |
| hist127 | either | 13/14 | 2/3 | 2/3 | 31/43 / 31/31 |
| hist127 | both | 10/10 | 2/2 | 2/3 | 31/43 / 31/31 |
| holdout2 | either | 4/7 | 1/2 | 1/2 | 0/10 / n/a |
| holdout2 | both | 3/5 | 1/1 | 1/2 | 0/10 / n/a |
**Positive counts are 0–3 per set, so no interval is informative** (e.g. 2/3 has a 95% interval of roughly 0.21–0.94). The only thing these
numbers show is behaviour: grouping precision is high where groups exist; recall is limited by wording differences; and the model
escalates events the reviewers rated medium, e.g. a roughly 20,000-customer regional blackout (reviewers: medium/WATCH under the "regional
or partial disruption is medium" rule; the model has no way to know a disruption is regional from the headline). Whether a
20,000-customer power cut is "severe" is a calibration decision for the Captain.

## Not claimed
No release threshold is supported: there are about 10 ESCALATE events across all 437, against the 59 needed. A fresh holdout drawn after
this rubric and model are frozen, with a two-phase enriched design, is still required (plan in
`docs/WEEKLY-EVIDENCE-TIERED-POLICY-AND-VALIDATION-PLAN.md`). Reviewer B applied a default REFERENCE label to unflagged headlines
(358 of 437); reviewer A reports labelling each by hand. Review sheets for the 150- and 127-event sets: `docs/review/*.csv`.
