# Fresh holdout (holdout2) — staged detector wk-detect/0.3.0 (commit d9413291), run once

**Result: the staged detector fails the release targets on unseen data.** Targets are not met and the design as built should not
proceed to shadow comparison without the changes in §4.

## Design and independence
* 160 events, 12 Oct–2 Nov 2026 (before both earlier sets), deterministic md5 sampling, five strata (30 top-ranked, 40 random,
  40 keyword-enriched, 25 primary-advisory, 25 routine). Sampled by a worker that reported counts only.
* Two reviewers labelled blind (headline, source, time, geography only), working in opposite row orders, against one written
  rubric: materiality (H/M/L), priority (E/V/W/R), incident group, role. **Both reviewers are instances of the same model family
  as the detector's author, so their errors are correlated with the author's.** Human review remains required before these are
  treated as ground truth. Files: `tests/fixtures/labels_holdout2_reviewer{A,B}.json`, merged fixtures `..._labelled_{A,B,either}.json`.
* Agreement (`scripts/label_agreement.py`): materiality κ=0.79, priority κ=0.84, role κ=0.79; high-materiality κ=0.78 (96.9% raw);
  escalate κ=0.79 (97.5% raw). Group pairs: 21 and 21, identical. Disagreements on escalate: 4 events; on high materiality: 5.
* Blindness disclosure: while checking reviewer B's process I read a script that contained short paraphrases of about 60 events.
  The model was already frozen and committed (`d9413291`), was run once, and was not changed afterwards.
* The 'either' variant counts a positive if either reviewer marks it (recall-conservative); A and B are reported separately.

## Results (Wilson 95% intervals; denominators shown)
| Measure | Reviewer A | Reviewer B | Either |
|---|---|---|---|
| Candidate recall (H or E/V events found) | 3/10 = 0.30 (0.11–0.60) | 5/15 = 0.33 (0.15–0.58) | 5/15 = 0.33 |
| High-materiality precision | 3/7 = 0.43 | 5/7 = 0.71 | 5/7 = 0.71 |
| High-materiality recall | 3/10 = 0.30 | 5/15 = 0.33 | 5/15 = 0.33 |
| **Escalation recall (incident level)** | 1/8 = 0.13 (0.02–0.47) | 1/10 = 0.10 (0.02–0.40) | 1/11 = 0.09 |
| Escalation precision | 1/1 | 1/1 | 1/1 |
| Grouping pairwise recall | 0/21 | 0/21 | 0/21 |
| Grouping false merges | 0 | 0 | 0 |
| Frozen b92c1b39 high-materiality P / R | 0.22 / 0.20 | 0.33 / 0.20 | 0.33 / 0.20 |
| Legacy "confidence = HIGH" P / R | 0.13 / 0.40 | 0.13 / 0.27 | 0.13 / 0.27 |
Candidate pool share 10.6% of events; model priorities: 1 ESCALATE, 8 VERIFY, 7 WATCH, 144 REFERENCE. Only 8–11 positives, so every
interval is wide, but the point estimates are far below target and the upper bounds (0.47, 0.40) are also below 95%.
It beats the frozen b92c1b39 and the legacy label on high-materiality precision/recall only modestly, and the frozen model also fell
to ~0.20 recall here, which confirms the earlier holdout result was not an outlier.

## Failure categories (14 reviewer-marked high-impact events, 5 found)
1. **Cyber breach at an organisation whose sector is not in the lexicon (5):** cosmetics company (340,000 clients), Federal Court,
   Origin Energy customer/card data, a crypto exchange after an apparent hack, Japanese firms compensating users. The candidate rule
   requires a sector, a scale cue or a stated-compromise word, and a plain "data breach"/"hack" is not in the compromise list.
2. **Physical/kinetic infrastructure events (2):** a fire at an oil hub after an attack; a ship sunk in the Strait of Hormuz. The
   detector has no physical-event class at all.
3. **SaaS/platform outage reported by a status page (1):** "Users unable to access <product>"; the product is not in the lexicon and
   "unable to access" is not an outage term.
4. **Exploited advisory with wide reach but no stated exposure (2):** reviewers marked E under the rubric ("plausibly affects widely
   used products"), which conflicts with the Captain's rule (exposure to our estate required). **That is a rubric defect on my side**,
   not necessarily a model miss; it needs the Captain's ruling.
5. **Found but under-ranked (3):** an outage reported by an aggregator or status page was VERIFY, not ESCALATE (policy-consistent,
   reviewers differ); a telecom AGM story is commentary-like.
6. **Grouping 0/21:** the 21 gold pairs are 15 in one advisory cluster (advisories are never grouped by prose, by design), 5 in
   non-incident political/crime follow-up groups that the detector never groups, and 1 in a court-breach pair whose members were never
   candidates (category 1). None is an in-scope grouping success or false merge, so grouping is **not measured** by this set. A grouping
   test needs a fresh set with many multi-report incidents.

## What this means
* Replacing one hand-written vocabulary with a larger hand-written lexicon repeated the failure on new data: the entity and event
  lexicons are still the bottleneck. Further lexicon patching would again be tuned to what I have now seen.
* The retained principle is sound but not implemented broadly enough: uncertain high-impact candidates must be kept. A strong event
  signal (breach, hack, attack, fire, sunk, unable to access, outage) should make an event a candidate for VERIFY whatever the sector.
  Cost: more VERIFY items; this must be measured as review load (events/week) alongside recall.
* Holdout2 is now a development set (it has been inspected). Any change requires a **new, third holdout** before a result is claimed.

## 4. Proposed next iteration (needs approval; offline only)
1. Candidate rule: event-type signal alone makes a candidate (routed to VERIFY unless consequence is established); add a physical/
   kinetic class and status-page outage forms. Measure VERIFY volume per week as a first-class metric.
2. Replace the fixed sector lexicon with a small local-model extraction step (entity, sector, event type, actual/potential) whose output
   is validated by deterministic rules and falls back to the lexicon when the model is unavailable or disagrees — evaluated before use.
3. Resolve the advisory rubric with the Captain (is wide reach enough, or is known exposure required?).
4. Build a grouping test set from multi-report incidents; today's sets contain too few.
5. Draw a third untouched holdout and have a human review the labels.
