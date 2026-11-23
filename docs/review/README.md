# Weekly-evidence review sheets

Human-review evidence sheets for two labelled evaluation fixtures: `dev150_review_sheet.csv` (150 development events, window 2026-11-17 to 2026-11-23 AEDT) and `holdout127_review_sheet.csv` (127 holdout events, window 2026-11-03 to 2026-11-16 AEDT). Each row carries database evidence (event id, title, publisher, url, collected_at, geography, a stored-summary excerpt of up to 300 chars, legacy rank and disposition) so you can judge without opening the source.

**The `proposed_materiality` / `proposed_priority` labels were written by an AI assistant and are unreviewed.** They were labelled from headline and source only, are copied unchanged from the fixtures, and must not be treated as ground truth until you have reviewed them.

How to review: fill `reviewer_materiality` (H/M/L) and `reviewer_priority` (E/W/V/R) for every row, and use `reviewer_notes` for disagreement reasons. Leave the `proposed_*` columns untouched. Use this rubric (copied from the fixtures' `_meta`):

- Materiality: H = a specific incident, advisory or policy event with direct implications for operational resilience of essential services, critical infrastructure or the financial sector, a significant cyber incident (AU-relevant), an actively exploited vulnerability, or AI/technology governance with direct operational implications. M = relevant context, analysis, routine advisory, or incident with weak operational relevance. L = not relevant to these domains.
- Priority (development set): E = needs the Captain's attention now (confirmed, material, fresh, essential-service or active-exploitation). W = monitor. V = material but only aggregator/secondary evidence: verify first. R = no action; reference.
- Priority (holdout set, applying the Captain's policy of 2026-11-23): E = a single credible report of a severe-consequence incident (essential services, emergency services, aviation, health systems, global platform outage) or exploited-and-exposed advisory; W = monitor; V = material but aggregator/secondary only; R = reference.

**The 127-event file is a preserved historical holdout and must not be tuned on.** FROZEN HOLDOUT. Labels are PROPOSED by the assistant and NOT yet reviewed by the Captain. They were written BEFORE the frozen model (commit b92c1b39, method wk-evidence/0.2.0-prototype) was run on these events. No tuning has been done on this set; any change made after viewing results contaminates it. Do not change prompts, vocabularies, thresholds or models after looking at its rows or results; use the 150-event development sheet for any tuning. Note also the labeller caveat: The labeller also wrote the vocabulary being tested, so rater and model are correlated; human review is required before these figures are treated as release evidence.

Legacy columns: `legacy_rank` is the stored `rank_score`; `legacy_disposition` is the stored `disposition` (blank = null). Excerpts are raw stored text (HTML entities left as stored).
