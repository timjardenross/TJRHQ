# Intelligence reference incident set (DRAFT, window 2026-09-01 to 2026-11-24)

A small, human-reviewable set of incidents used to measure intelligence performance without
marking TJRHQ's own homework. **Nothing here is ground truth until a human has reviewed it**
(`reviewed_by_human: false` on every record).

## Files

| File | Purpose |
|---|---|
| `reference_set.json` | Working copy of the 27 records. Edit this during review. |
| `baseline-2026-11-24.json` | Frozen copy plus the baseline scorecard. Do not edit; create a new dated file instead. |
| `captain_ratings_template.csv` | Optional Captain CSV (brief usefulness 1-5, noise count, verification minutes). |
| `../../tools/intelligence/performance_scorecard.py` | Offline scorecard (see below). |

## How the set was built

1. Incidents were found by public web search (standard mode, US-indexed) across Australian banks,
   telcos, payments, cloud/SaaS, government, energy and cyber, **independent of `intelligence_events`**.
2. Each record was then looked up in production `intelligence_events` / `captains_daily_briefs`
   (SELECT only, project `cjvrpjwewsrumnbdydgg`) by title regex and publication window to fill `tjr_detection`.
3. Records TJR found that web search could not confirm are marked `discovered_via: tjr_events_only`
   and `verification_status: unverified_independently`.

## Composition

27 records: 8 scored material incidents (RS-001/002/003/004/005/008/009/011; RS-005 is a follow-up development), 2 further material records that are `unverified` (RS-006, RS-007) and so are not scored, and 17 negative examples (`is_negative_example: true`) of these types: routine notice noise, status-page noise, foreign events with no Australian effect, retrospective or out-of-window stories resurfacing, statistics releases, local outages, and 4 `correlation_trap` pairs (PAIR-A to PAIR-D) that look related but are expected to be unrelated. Discovered via web search: 22; found only in TJR data: 5 (RS-012, 013, 014, 026, 027).
Negative classifications marked "provisional" need a human decision.

## Things that could not be verified (read before trusting a record)

- **Telstra Stockton outage (12 Nov)**: web search found nothing; only a TJR-collected Google News headline exists (RS-012).
- **Telstra/AWS outage (31 Oct)**: not found; probably a stale or re-dated Mashable item (RS-013).
- **AWS me-central-1 "15 Sep" disruption**: the outage began in March; the Sep item is an update (RS-016).
- **AEMO "notices"**: no material AEMO notice (lack of reserve, directions, load shedding) was found for Sep-Nov; only routine notices (RS-014).
- **CBA 22-23 Oct and Westpac 10 Nov**: single weak sources each; kept as `unverified` and excluded from detection scoring (RS-006, RS-007).
- Many start/end times are approximate; each time field carries its source and, for starts, a confidence.
- The set is thinner than the requested ~30 because the search tool surfaces few dated Australian items.

## Timestamp caveat

`intelligence_events.published_at` was repaired (+10h for RSS rows) on 2026-11-24 ~00:40Z. An initial pass was
made before the repair and **every timestamp was re-pulled afterwards**; all `tjr_detection` times here are post-repair.
`collected_at` is batch time, so "time to detection" includes feed and collection lag.

## Running the scorecard (offline)

```bash
# frozen baseline (uses each record's embedded tjr_detection)
python3 tools/intelligence/performance_scorecard.py --reference knowledge/intelligence-reference-set/baseline-2026-11-24.json

# weekly run from exported rows
python3 tools/intelligence/performance_scorecard.py \
  --reference knowledge/intelligence-reference-set/reference_set.json \
  --events events.json --briefs briefs.json --ratings ratings.csv \
  --week-start 2026-11-17 --week-end 2026-11-24 --out scorecard-week.json
```

Export the inputs yourself with a read-only SELECT (the script never connects). Events need
`event_id, source_name, raw_title, published_at, collected_at` and optionally `brief_id, suppressed, risk_rating, canonical_signal_id`.

## Metric notes

- Do not read time to first detection alone: the scorecard also reports, per source, first report,
  confirmation, restoration evidence and chronology roles.
- Independent corroboration excludes aggregators and counts one organisation once (`intelligence.weekly_evidence` semantics).
- A detection is a regex title match; it can over-match (opinion pieces) or under-match. Review `n_events`
  with suspicion.
- Brief surfacing from `brief_text` is a regex match and is weaker evidence than `intelligence_events.brief_id`.

## v1 (draft)

`reference_set_v1.json` (53 records, statuses per record) supersedes v0 for scoring; v0 files stay frozen. See
`CHANGELOG.md` for counts, the unresolved-is-not-negative rule, targets not met (15 of 25 material) and the
measured-vs-unverified split. Run:

```bash
python3 tools/intelligence/performance_scorecard.py \
  --reference knowledge/intelligence-reference-set/reference_set_v1.json \
  --events knowledge/intelligence-reference-set/events_export_2026-11-24.json
```

The output has three views (`all`, `v0_subset`, `v1_new_only`).
