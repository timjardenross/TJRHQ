# Holdout evaluation — frozen model wk-evidence/0.2.0-prototype (commit b92c1b39)

Run once on `tests/fixtures/weekly_evidence_holdout_set.json` (127 events, 3–16 Nov 2026, two weeks before the
development set). Labels were written by the assistant before the run and are **not yet human-reviewed**. No tuning
followed. Because the sample is stratified and enriched with keyword-matched events (28) and primary advisories (15),
precision here is not a population estimate. 17 positives only; intervals are wide (Wilson 95%).

| High-materiality detection | TP | FP | FN | Precision (CI) | Recall (CI) |
|---|---|---|---|---|---|
| Proposed v0.2 | 10 | 2 | 7 | 0.83 (0.55–0.95) | **0.59 (0.36–0.78)** |
| Legacy: osint confidence = HIGH | 9 | 30 | 8 | 0.23 (0.13–0.38) | 0.53 (0.31–0.74) |
| Legacy: ESCALATE/WATCH disposition | 12 | 37 | 5 | 0.25 (0.15–0.38) | 0.71 (0.47–0.87) |

Development set (tuned on it): precision 0.875 / recall 1.0. **The development figure was optimistic: recall fell from
1.0 to 0.59 on unseen data.** The release target of ≥95% critical-event recall is NOT met.

Priority exact match 0.906 (mostly REFERENCE). Of 3 gold ESCALATE events, 0 were escalated (2 WATCH, 1 REFERENCE).

## Failure modes (seven misses)
Six of seven misses are events whose headline names an organisation and a cyber/breach/outage word the vocabulary does
not combine with the essential-service cue: "cybersecurity incident" (Coles), "cybersecurity breach … major incident"
(NSW Health), "personal data stolen … hacked" (National Parks booking), "shop freezers hit by cyber-attack",
"ongoing cyber threat to industrial refrigeration", and "Microsoft ‘deeply sorry’ for global disruption" (no "outage").
The seventh (Bloomberg Microsoft outage) scored medium. Two false positives were commentary on the Microsoft outage.

## Incident grouping
Pairwise recall 0.316 (6 of 19 gold pairs); all 4 two-report incidents stayed split and the 6-report Microsoft outage
split into 3 groups. One false merge: two commentary items were merged into the Microsoft outage group. Grouping v2 was
tuned on the development set and does not generalise (different wording, no shared stems/entities). Proposed threshold
remains ≥0.80 pairwise on reviewed groups; **not met**.

## Consequence
Do not tune further on this set. Next iteration needs (a) human review of both sets, (b) a fresh holdout, and
(c) design changes (entity+event-class matching rather than title-term overlap), not vocabulary patches.
