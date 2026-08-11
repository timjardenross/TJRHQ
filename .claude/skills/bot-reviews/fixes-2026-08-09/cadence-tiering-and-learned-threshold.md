---
title: Downdetector tiered cadence (banking/telco priority sources) + LLM-learned per-source report-count threshold
date: 2026-08-10
author: Chief Engineer, USS-TJR-003, Engineering Division — Advisory + implementation (Captain-directed)
scope: Implements both Captain decisions from the outage-pipeline review chain
  (chief-engineer-intelligence-pipeline-review.md Finding 3 + Finding 4,
  xo-review-of-ce-intelligence-pipeline-review.md §3/§4). Design + real code,
  verified against the live registry and quota accounting, not asserted.
status: Implemented. Migration applied live. Tests pass. Not yet observed
  through a real 07:00-19:00 AEST business-hours cycle or a real nightly
  recompute run (both first fire on their own schedule after this lands).
---

# Mission Summary

Two Captain decisions from tonight's review chain, both implemented:

1. **Tiered cadence** — the Big 4 banks (NAB/ANZ/CBA/Westpac) and top 2
   telcos (Telstra/Optus) get extra Downdetector checks during 07:00-19:00
   AEST business hours, on top of (not instead of) the existing once-daily
   06:00 check every registered source already gets.
2. **LLM-learned per-source report-count threshold** — replaces the flat
   `_REPORT_COUNT_FLOOR = 150` constant in `downdetector_adapter.py` with a
   per-source value the platform learns from real accumulated history,
   with an explicit bootstrap period, a sanity guard on the LLM's output,
   and a disclosed interim per-sector default for banking/government while
   history accumulates.

# Decision 1 — Tiered Cadence

## The real quota math

Confirmed live against `intelligence_source_registry` (2026-08-10), not
assumed:

**Firecrawl path** (7 active sources: AEMO Market Notices, Fastly Status, +
5 active telecom Downdetector sources — Telstra, Optus, TPG, Vodafone, NBN
Co; iiNet/Dodo/Aussie Broadband/Superloop/Activ8me remain inactive).
Existing committed baseline, recomputed fresh: 7 × 1×/day × 30 = 210, +
fortnightly full-brief job (7 × 2) = 14 → **224/month**, unchanged from
`firecrawl-production-provisioning.md`'s original math — confirmed still
accurate, not stale.

**Bright Data path** (9 active sources: all 6 banking + all 3 government
Downdetector sources, all confirmed `active=true` live). Existing baseline:
9 × 1×/day × 30 = 270, + fortnightly (9 × 2) = 18 → **288/month**.

**Interval chosen: every 120 minutes (2 hours) during 07:00-19:00 AEST.**
The 12-hour window and the 120-minute period divide evenly, so exactly 6 of
the day's 12 total ticks always land inside the window, regardless of
scheduler restart phase — 6 extra real checks/day per tiered source, not
"roughly."

Hourly was computed and explicitly rejected: 12 extra checks/day × 2
Firecrawl-path sources (Telstra, Optus) × 30 days = 720/month additional,
on top of the 224 baseline = **944/month — over the 850 safe ceiling**.
Real math, not guesswork, ruled it out.

At 120 minutes:

| Provider | Existing baseline | Tiered addition | New total | Ceiling | Headroom |
|---|---|---|---|---|---|
| Firecrawl (Telstra + Optus, 2 sources) | 224/month | 2 × 6/day × 30 = **360/month** | **584/month** | 850 | **266/month (31.3%)** |
| Bright Data (NAB/ANZ/CBA/Westpac, 4 sources) | 288/month | 4 × 6/day × 30 = **720/month** | **1,008/month** | 4,500 | **3,492/month (77.6%)** |

Both leave genuine headroom, not a barely-under margin — and the existing
DB-backed hard-cap circuit breaker (`external_fetch_budget.py`) is still
the real backstop if this math is ever wrong in practice (a new source
added, a cron misfire, etc.), consistent with how it was built to be used.

XO's review flagged that Bright Data's headroom could absorb more than
Firecrawl's — true, but a single shared interval for all 6 sources was
kept for implementation simplicity (one job, one interval, scoped by exact
source name) rather than two separate cadences per provider; 120 minutes
already clears both budgets with real margin, so the added complexity of a
split cadence wasn't justified by the math.

## Implementation

`intelligence/scheduler.py`:
- `_PRIORITY_TIERED_SOURCE_NAMES` — exact 6 source names, confirmed live
  (`Downdetector AU — NAB`, `— ANZ Bank`, `— Commonwealth Bank`,
  `— Westpac`, `— Telstra`, `— Optus`). Bendigo/UBank and TPG/Vodafone/NBN
  Co/small-ISPs deliberately excluded, per the Captain's brief.
- `_within_priority_tiered_window(hour)` — pure function, 07:00 ≤ hour <
  19:00, directly unit-tested.
- `_priority_tiered_collection_job()` — new `IntervalTrigger(minutes=120)`
  job, `next_run_time=now`. No-ops (skips collection entirely, doesn't just
  skip the push) outside the window using the same Brisbane-timezone
  hour-gate pattern `_wellness_reminder_job()` already uses — deliberately
  `Australia/Brisbane` (AEST, no DST), not `SCHEDULE_TZ`
  (`Australia/Melbourne`, which shifts with DST), per the mission brief's
  explicit instruction. Scoped by exact source NAME, not category — has
  zero effect on the other 13 Downdetector sources or any non-Downdetector
  source, and is entirely independent of `_intraday_status_collection_job`
  (which already excludes ALL downdetector-type sources via
  `_excluding_firecrawl_fetch_sources`).
- Same collect → classify → dedup → filter → rank → save_event pipeline
  every other collection job here uses; same dedup keys, so this can never
  double-save an event another job already collected today.

# Decision 2 — LLM-Learned Per-Source Threshold

## Design

**New table `downdetector_baseline_history`** (migration 0121) — every real
Downdetector fetch logs its parsed `(status, report_count)` here,
unconditionally, regardless of whether the two-layer push-alert gate
passed. Written from `DowndetectorAdapter.collect()` via
`intelligence_store.save_downdetector_observation()`, best-effort (a
logging failure can never break real collection). This is the accumulation
ledger — and Decision 1 directly feeds it faster: the 6 tiered sources now
generate up to ~7 real observations/day (1 daily + 6 business-hours) instead
of 1.

**New table `downdetector_learned_thresholds`** — one row per source, the
current threshold in force plus `threshold_source` recording exactly how it
got there (never a silent transition):
- `bootstrap_default_insufficient_history` — cold start
- `bootstrap_default_llm_unavailable` — all 3 LLM providers failed/unparseable
- `bootstrap_default_after_llm_reject` — LLM answered, sanity guard rejected it
- `llm_learned` — LLM recommendation passed the sanity guard, adopted

**Cold-start bootstrap defaults** (`intelligence/ingestion/downdetector_thresholds.py::bootstrap_default()`),
judgment call, disclosed:

| Sector | Default | Basis |
|---|---|---|
| telecom | 150 | Unchanged — the one evidence-grounded number this platform has (Telstra's real 2026-07-07/08 outage: 230-354 peak reports vs. 1-42 quiet baseline) |
| banking | 30 | Interim. CE review Finding 4: live banking baselines (~3) are ~10x lower than telecom's (~34); a proportional spike (6-10x baseline, matching Telstra's real ratio) would plausibly land 20-70 — 30 sits inside that range with margin above the quiet baseline |
| government | 20 | Interim, same reasoning, even lower observed baselines (~1-2) |
| other | 150 | No evidence yet for any non-telecom/banking/government source; falls back to the proven number rather than guessing lower |

**Minimum history: 21 distinct calendar days** (`_MIN_HISTORY_DAYS`),
judgment call disclosed — the middle of the mission brief's own suggested
14-30 day range. Measured in distinct days, not raw rows, specifically
because Decision 1 means a tiered source can log 7 rows in a single day —
a threshold learned from one unusually busy/quiet day's repeated samples
would not be a real baseline.

**LLM call** (`_call_threshold_llm()`) — same never-raise,
try-gemini-then-mistral-then-ollama fallback pattern as
`intelligence_store.py::_call_blast_radius_llm()` (shared pattern, not
shared code — different prompt, different task_type, different caller).
Given real structured data: distinct-day count, quiet-day distribution
(min/mean/p95/max), and up to 5 most recent known "problems"-tier spike
events with their real report counts. Required strict output format
(`THRESHOLD: <int>` / `REASONING: <text>`), parsed the same strict way the
blast-radius guard parses its `ANSWER:` line — an unparseable response is
treated as a provider failure, falls through to the next provider.

**Sanity guard** (`sanity_check()`), judgment call disclosed:
- Reject `<= 0`.
- Reject `<=` the highest real quiet-day count ever observed (would misfire
  on an ordinary day).
- Upper bound: if a real "problems"-tier spike exists in history, reject
  above `3× the highest real spike ever seen`; if none exists yet, reject
  above `20× max(quiet_max, sector_bootstrap)` — generous enough not to
  punish a source with a tiny quiet baseline, but bounded so the LLM cannot
  set a number that makes the gate effectively impossible to trigger.
- Any rejection falls back to the bootstrap default, logged with the exact
  reason and the LLM's rejected candidate — never silent.

**Nightly recompute** (`intelligence/scheduler.py::_downdetector_threshold_recompute_job`,
`CronTrigger(hour=5, minute=0)` AEST) — before `_daily_collection_job`
(06:00) so a freshly recomputed threshold is in force for the very next
real collection cycle. Iterates every registered Downdetector source
(active or not — an inactive source can still hold real pre-deactivation
history, and recomputing costs nothing extra), calls
`recompute_threshold_for_source()` per source, upserts the result. Never
raises — a per-source failure is logged and skipped, same discipline as
every other job in this module.

**Gate wiring** (`downdetector_adapter.py::get_report_count_floor()`) —
replaces the flat `_REPORT_COUNT_FLOOR` constant. Short-TTL (10 min)
in-process cache over `downdetector_learned_thresholds` (a live Supabase
read on every single gate check would be wasteful now that tiered sources
can be checked ~7x/day); falls back to the sector bootstrap default —
the same one the recompute job itself uses — whenever no row exists yet or
the cache refresh fails. Never raises, never blocks a real fetch on a
Supabase hiccup.

`slug_from_url()`/`sector_for_slug()` were pulled out of
`DowndetectorAdapter` as module-level functions so both the live gate and
the nightly recompute job agree on sector classification for a given
registry row, without the recompute job reaching into adapter-instance
internals.

## Verification

`python3 -m py_compile` clean on all four touched/new files (`scheduler.py`,
`downdetector_adapter.py`, `downdetector_thresholds.py`,
`intelligence_store.py`).

**`tests/test_downdetector_thresholds.py`** (20 tests) — synthetic data, no
live Supabase/LLM call, no 30-day wait:
- Bootstrap defaults (telecom=150, banking/government lower, unknown sector
  falls back to "other").
- `summarize_history()`: quiet/spike split, percentile math, null
  `report_count` excluded from the distribution (never fabricated), distinct
  days measured by calendar day not row count.
- Sanity guard: rejects 0, negative, `None`, at-or-below quiet max, and an
  absurdly high value (`100000` against a cap of `600`) with no spike
  history; accepts a reasonable value; correctly derives the cap from real
  spike history when one exists.
- `recompute_threshold_for_source()`: cold-start (5 days) → bootstrap,
  logged as `bootstrap_default_insufficient_history`; sufficient history
  (25 days) + mocked LLM returning a sane value → `llm_learned`; mocked LLM
  returning `0` or `999999` → rejected by the sanity guard, falls back to
  bootstrap, logged as `bootstrap_default_after_llm_reject`; all providers
  unavailable → `bootstrap_default_llm_unavailable`; malformed observation
  shapes never raise.

**`tests/test_downdetector_priority_cadence.py`** (16 tests):
- `_within_priority_tiered_window()` tested directly at 6 (before), 7
  (start, inclusive), 13 (mid), 18 (last hour inside), 19 (end, exclusive),
  22 (after), 0 (midnight).
- `_PRIORITY_TIERED_SOURCE_NAMES`: exactly 6 entries; Big 4 banks present,
  Bendigo/UBank absent; Telstra/Optus present, TPG/Vodafone/NBN Co absent.
- `_priority_tiered_collection_job()` wiring: gated off →
  `collect_all()` never called; gated on with a mixed registry → calls
  `collect_all()` with exactly the 2 matching fake sources, excluding a
  Bendigo row and an AEMO row present in the same registry; empty
  intersection (none of the 6 currently active) → skips collection
  entirely rather than calling with an empty list.

All 36 new tests pass. Ran the full existing `tests/test_intelligence_*.py`
suite (199 tests) before and after this change (`git stash`/`pop`) to
confirm no regression: 3 failures present identically both before and
after (`test_media_source_low_relevance_suppressed`,
`test_load_returns_sorted_list`, `test_trends_stable`) — pre-existing,
unrelated to this work (live-data-dependent tests, not touched by any file
this mission changed).

Migration `0121_downdetector_learned_thresholds.sql` applied live via
Supabase MCP (`downdetector_learned_thresholds`), confirmed both tables
exist with RLS enabled and the expected `service_all`/`auth_read` policies.

## Not yet observed live

Both pieces are wired but neither has fired on its own real schedule yet:
the tiered job's first real business-hours tick and the recompute job's
first 05:00 AEST run both happen after this lands. Every source starts in
`bootstrap_default_insufficient_history` state — genuine `llm_learned`
values won't appear until 21 real distinct days of history accumulate per
source (faster now for the 6 tiered sources, unchanged pace for the other
13). Worth a live health-row / heartbeat check
(`downdetector_priority_tiered_collection`, `downdetector_threshold_recompute`)
after the next scheduler restart and after 05:00/07:00 AEST next pass —
same "code merged is not code running" lesson this review chain's Finding 1
already surfaced once tonight.

## Disclosed judgment calls (no Captain sign-off sought on these specifics)

1. Single 120-minute interval shared across all 6 sources, rather than a
   tighter cadence on the Bright Data side alone (XO's flagged option) —
   simplicity over squeezing extra headroom that wasn't needed.
2. Interim bootstrap defaults of 30 (banking) / 20 (government) — derived
   from CE's live baseline ratios, not independently evidence-grounded the
   way telecom's 150 is.
3. 21-day minimum history threshold — middle of the suggested 14-30 day range.
4. Sanity-guard multipliers (3x observed spike / 20x quiet-or-bootstrap
   ceiling) — reasoned but not independently validated against a second
   real historical event; telecom's 150 vs. Telstra's real 230-354 spike is
   the only calibration data point this platform has.
5. No `LLMCostGovernance` wiring for the threshold-recompute call
   (unlike the blast-radius guard) — this is a bounded nightly batch (≤19
   calls, once/day), not a per-event call site; added complexity judged
   unnecessary at this volume, but flagged here in case that changes.
