# Weekly Intelligence Report redesign — 2026-08-10

**File:** `intelligence/captains_brief.py` — `generate_weekly_report()`

## What changed

Captain's explicit direction: the weekly report was built entirely on
`_get_latest_ori_brief()` (a single latest-row snapshot from
`intelligence_briefs`) plus an `ACTIVE MISSIONS` block. Both are gone.
Redesigned to:

1. **Tech OSINT weekly roll-up** — 7-day aggregation over `intelligence_events`
2. **Health OSINT weekly roll-up** — 7-day aggregation over `health_signals`
3. **Content this week** — published/review/ready_to_publish/approved items, windowed by `updated_at`
4. **Decisions this week** — `decision_records` rows from the last 7 days
5. **Capacity this week** — `captains_log_entries` Green/Amber/Red trend across the 7-day window
6. **Missions removed entirely** — no `_get_active_missions()` call, no `ACTIVE MISSIONS` block

`_get_active_missions()` itself was deleted from the module — after removing
its only call site (this function), it was unused dead code (confirmed via
repo-wide grep; the only other hit was an unrelated `command_memory_interface`
test with a same-named function).

## Data sources investigated and reused

- **Tech OSINT**: `lcars-portal/src/app/api/intelligence-workbench/intelligence-summary/route.ts`
  (made the default landing tab tonight). It queries `intelligence_events`,
  buckets on `osint_confidence_level` (HIGH/MEDIUM/LOW), orders by
  `rank_score desc`, and joins `intelligence_source_registry` for source name.
  New `_get_weekly_tech_signals()` reuses the same table + confidence field,
  windowed to `collected_at >= now-7d` instead of that route's single fetch.
  Live check 2026-08-10: 590 non-suppressed rows in the trailing 7 days
  (16 HIGH / 9 MEDIUM / 211 LOW / 354 unscored) — set `limit=1000` so the
  weekly counts are real totals, not the UI's 150-row display cap.

- **Health OSINT**: `lcars-portal/src/app/api/health-osint/intelligence-summary/route.ts`.
  Queries `health_signals`, buckets on `confidence_level`. New
  `_get_weekly_health_signals()` mirrors it, same 7-day window. Live check:
  322 rows (3 HIGH / 149 MEDIUM / 170 LOW).

- **Content**: extended `_get_content_review_queue()`'s pattern
  (`comms_content`) to include `published` and `approved` in the status set
  (previously only `draft,review,ready_to_publish`) and filter by
  `updated_at >= now-7d` instead of returning the standing pending-queue
  snapshot. `comms_content` has no dedicated status-change timestamp, so
  `updated_at` is the best available proxy — noted in the docstring as a
  known approximation.

- **Decisions**: confirmed via `platform-runtime/lib/build_learning_loop.py`
  (comment added there tonight, 2026-08-10, "Chief Engineer decisions-heartbeat
  follow-up") that `decision_records` is the canonical write path — most
  historical rows carry `metadata.source="build-learning-loop"` and the
  `DEC-REC-<ts>-<hex>` id format it generates. `governance_service.py` also
  reads from the same table. New `_get_weekly_decisions()` filters
  `decision_timestamp >= now-7d`, selecting `mission_id, recommendation_text,
  human_decision, decision_maker, decision_timestamp`.

- **Capacity/health trend**: `_get_weekly_capacity()` pulls
  `captains_log_entries` across the 7-day window (not the daily briefs'
  single-day snapshot) and `_format_weekly_capacity_block()` renders a
  Green/Amber/Red count summary plus an emoji trend sequence in date order,
  reusing the existing `_rating_emoji()` helper (the same one fixed earlier
  tonight for the `captain_capacity_rating` text-column bug).

## Decisions made during implementation

- **Dropped the ORI-brief-based risk section entirely** rather than keeping
  it alongside the new OSINT roll-up — the Captain's direction said "replace
  this with a real WEEKLY aggregation," and the two weekly OSINT blocks
  already carry equivalent HIGH/MEDIUM/LOW risk framing, so a parallel ORI
  section would have been redundant. `_get_latest_ori_brief()` itself was
  **not** deleted — `generate_morning_brief()` still uses it.
- **`limit=1000` instead of the workbench UI's `limit=150`** for the two
  weekly signal fetches — the UI's cap exists for on-screen display size;
  the brief needs an accurate weekly count, and 1000 comfortably covers the
  ~600/~320 rows/week observed live without needing a second exact-count
  query.
- **Added an "unscored" (⚪) bucket** to the weekly OSINT block whenever
  `HIGH + MEDIUM + LOW` doesn't account for every row (354/590 tech rows
  this week have no `osint_confidence_level` set) — showing `(590)` next to
  three buckets that only summed to 236 would have silently misrepresented
  the data; this makes the scoring-coverage gap visible instead.
- **Headline items fall back to top-ranked-overall if nothing is HIGH-tier**
  this week, so the block never renders as "0 high / N medium / M low" with
  no example signals shown.
- Added `from collections import Counter` at module level — the only new
  import needed.

## Verification

- `python3 -m py_compile intelligence/captains_brief.py` — passes.
- Ran `generate_weekly_report()` live (env sourced from
  `telegram-bots/xo/.env`, no Telegram send — printed to stdout only).
  Output is well-formed, non-empty, 1531 chars (well under Telegram's 4096
  limit even with every section populated).
- Confirmed `decision_records` and `captains_log_entries` genuinely have no
  rows in the trailing 7 days (most recent `decision_records` row is
  2026-06-14; most recent `captains_log_entries` row with a rating is
  2026-06-20) — the "No decisions logged this week" / "No capacity logs this
  week" output is a real data-freshness finding, not a query bug. Flagging
  for the Captain: both pipelines look stale against a genuinely weekly
  cadence.

## Sample output (live, 2026-08-10)

```
📊 WEEKLY INTELLIGENCE REPORT
04 Aug – 10 Aug 2026

🛰 TECH OSINT — WEEKLY (590)
  🔴 16 high  ·  🟡 9 medium  ·  🟢 211 low  ·  ⚪ 354 unscored
  🔴 Connectivity issues affecting access to some website from certain networks in Egypt
  🔴 Worker's Observarbility Issues
  🔴 Network Performance Issues in Istanbul

🩺 HEALTH OSINT — WEEKLY (322)
  🔴 3 high  ·  🟡 149 medium  ·  🟢 170 low
  🔴 Large RCT confirms updated mRNA booster reduces severe outcomes 71%
  🔴 Remote Multicomponent Rehabilitation in Intensive Care Unit Survivors: A Randomized Clinical Trial.
  🔴 Updated seasonal influenza strain shows 12% higher transmissibility

✍️ CONTENT THIS WEEK (6)
  2 published  ·  3 review  ·  1 ready to publish
  ✅ Resilience by Design.  [published · operational resilience]
  ✅ McGill Method Physiotherapy Investigations  [published · —]
  📝 ADHD Work Systems - how do Neuro Spicy Employees work better with work insturctions, pr…  [review · personal operating systems]
  🟢 The Telstra outage is a stark reminder of the widespread effects of single-system failures  [ready_to_publish · operational resilience]
  📝 The power of data from Businss Impact Assesments if used correctly - hot spots in your …  [review · —]
  📝 Critical Infrastructure Resilience Management Plan (CIRMP) alignment.  [review · operational resilience]

📋 DECISIONS THIS WEEK
  No decisions logged this week.

⚡ CAPACITY THIS WEEK
  No capacity logs this week.

🤖 XO · Starship Endeavour
```

## Not done / open items

- No live Telegram test push — Captain will trigger that themselves.
- `comms_content.updated_at` as a proxy for "published/moved to review this
  week" will also catch rows that were merely edited (e.g. re-QA'd) without
  a genuine status transition. A dedicated status-change timestamp/history
  table would be more precise if this becomes a recurring complaint.
- Did not add an exact-count (`Prefer: count=exact`) query for the OSINT
  roll-ups; `limit=1000` is a pragmatic cap that covers current volume with
  margin, not a guaranteed-exact total if weekly volume grows substantially.
