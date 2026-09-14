# Knowledge Record — USS-TJR-MSN-0388: Predictive Capacity Guardian (Capability Play A)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0388 |
| Title | Predictive Capacity Guardian — critical-slowing-down early warning for capacity |
| Date | 2026-09-14 |
| Priority | P1 |
| Source | TJR HQ Capability Brief (2026-09-14), Capability Play A. Cross-references **CAP-1 (rank 5/25)** and CAP-2 (rank 8/25) in that brief's Top 25. The Capability Brief is not an in-repo artifact — it is held by the Captain; this record is the in-repo counterpart to its CAP-1 entry. |
| Status | **STOPPED AT STREAM 0 KILL-GATE** — Streams 1, 2 and 3 deliberately not implemented |
| Outcome | The statistic is **not usable** at the Captain's real check-in cadence. This is the brief's own anticipated cheap-kill outcome, not a delivery failure. |

## Verdict in one line

Rolling lag-1 autocorrelation / rolling variance ("critical slowing down") cannot
produce a legible early-warning signal from 31 capacity readings over 21 days.
The observed signal is statistically indistinguishable from randomly shuffling
the same data, and its mean runs in the *wrong direction* for the method.

---

## Pre-flight verification (all four brief claims confirmed against current code)

Verified by reading both files in full, not by grep:

1. `core/health/burnout_trajectory.py` exists (498 lines), is the V3-doc-compliant
   deterministic 7-state threshold bucketer, and is the only early-warning module
   under `core/health/`. No CSD/CUSUM/EWMA module exists anywhere in first-party
   code (the only repo matches are inside `core/voice/chatterbox-venv/`, vendored
   third-party packages). **This mission would have extended it, not duplicated it.**
2. `MIN_CHECKINS_FOR_TRAJECTORY = 5` — **exactly line 52**, no drift.
3. `CapacityGate.evaluate(score, status, mission_queue, *, captain_override=False)`
   — **exactly line 69** of `core/health/capacity_gate.py`; every emitted
   `CapacityAction` carries `captain_override_available=True`. Untouched by this
   mission, as the brief requires.
4. The prohibition on a weighted numeric score is real and explicit — module
   docstring lines 17-20 cite V3 doc §14: *"Weight nothing numerically into a fake
   score — bucket into the 7 states via clear threshold rules."*

---

## Stream 0 — the kill-gate (DELIVERED)

Analysis script: `core/health/stability_statistic_validation.py`.
Read-only: creates no table, writes nothing, imported by no live code path.
Reproduce with `python3 -m core.health.stability_statistic_validation`.

### The Captain's actual cadence

| Measure | Value |
|---|---|
| Capacity readings (rows with a `capacity_state`) | **31** |
| Distinct check-in days | 18 |
| Calendar span | 21 days (2026-08-21 → 2026-09-10) |
| Day coverage | 85.7% |
| Readings per calendar day | 1.48 |
| Largest gap between days | 2 days |
| Staleness at analysis time | **4 days** (last reading 2026-09-10) |

Cadence *regularity* is actually good — 85.7% day coverage, no gap worse than
2 days. **Sparsity is not the problem. Total series length is.**

The CSD literature this play cites (van de Leemput & Wichers, PNAS 2014;
replicated Smit et al. 2024/25) uses experience-sampling designs: 3-10 prompts
per day for months, i.e. several hundred to several thousand observations, with
rolling windows of 100+ points. We have 31 observations total — fewer points in
the *entire history* than those studies put in a *single window*.

### Rolling AR(1) and variance on the `capacity_state` ordinal series

| Window | Usable estimates | AR(1) mean | AR(1) sd | AR(1) range | Approx SE/estimate | Shuffled-null p95 range | Verdict |
|---|---|---|---|---|---|---|---|
| 7  | 25 | **-0.112** | 0.347 | 1.000 | 0.378 | 1.321 | inside noise band |
| 10 | 22 | **-0.060** | 0.322 | 0.933 | 0.316 | 1.152 | inside noise band |
| 14 | 18 | **-0.078** | 0.242 | 0.779 | 0.267 | 0.906 | inside noise band |

Three independent reasons this fails, any one of which is disqualifying:

1. **Wrong sign.** CSD's entire premise is *rising positive* autocorrelation as a
   system approaches a transition. The Captain's measured AR(1) is **negative at
   every window** (-0.06 to -0.11). The series carries no persistence structure to
   detect slowing in — consecutive readings are mildly anti-correlated, which is
   what you expect from a self-correcting behavioural series (a red day prompts
   rest, which produces a greener next reading) rather than from a system with
   critical dynamics.
2. **Standard error swamps the effect.** The papers report pre-transition AR(1)
   rises of roughly 0.10-0.25. Per-estimate SE here is **0.267-0.378** — between
   1.8x and 2.5x the size of the effect the statistic is supposed to detect. Every
   individual estimate is noise-dominated.
3. **Indistinguishable from shuffled data.** A permutation null (2,000 shuffles,
   seeded, destroying all temporal structure by construction) produces a *larger*
   rolling-AR(1) range than the real series at every window tested — real 1.000 vs
   null p95 1.321 at w=7; real 0.779 vs null p95 0.906 at w=14. **The observed
   "signal" sits entirely inside the band that pure noise generates.** There is no
   temporal structure here to extract.

No larger `MIN_CHECKINS_FOR_TRAJECTORY`-style floor rescues this. Raising the
floor shrinks an already-31-point series further; the constraint is total history
length, and at ~1.5 readings/day the Captain would need roughly **6-12 months of
unbroken check-ins** before an AR(1)-based statistic became decision-grade.

**Stream 0 answer: NOT USABLE. Kill-gate triggered.**

---

## Streams 1, 2, 3 — not implemented (and why Stream 1 is killed too)

Per the brief's kill-gate instruction ("if it's a kill, stop and report honestly
rather than forcing the rest"), Streams 2 and 3 were skipped as the brief directs,
and **Stream 1 was stopped as well**. Stream 1's skip needs justifying, because the
brief does not pre-authorise it — so here is the evidence, discovered while
establishing the Stream 0 baseline:

**Stream 1 would have inverted the alerting it was meant to sharpen.** Personal
SPC/CUSUM control limits must be computed from an *in-control baseline period*.
The Captain's own history has no such period:

| Measure | Captain's own baseline | Existing population constant |
|---|---|---|
| `orange_red_pct` | **0.710** | `ACCUMULATING_ORANGE_RED_PCT` = 0.40 |
|  |  | `SUSTAINED_HIGH_ORANGE_RED_PCT` = 0.60 |
|  |  | `BURNOUT_LIKE_ORANGE_RED_PCT` = 0.75 |
| `red_pct` | **0.355** | `BURNOUT_LIKE_RED_PCT` = 0.40 |

(31 capacity readings: 9 green, 11 orange, 11 red. 11 evening rows, 3 with
`capacity_debt='yes'`.)

The Captain's personal baseline of 71% orange/red sits **above two of the three
population thresholds it was meant to replace**, and just under the most severe.
Control limits fitted to this history would therefore centre "normal" on a
genuinely strained state and set the alarm line *above* the current sustained-strain
level — silencing the `accumulating_strain` and `sustained_high_strain` buckets that
correctly fire today. That is the textbook SPC failure mode of fitting limits to an
out-of-control process, and it is the opposite of the mission's intent. Landing
Stream 1 on this data would have made the Captain's early warning worse while
looking like a personalisation upgrade.

**Stream 3 has no ground truth to backtest against either.** `burnout_profile` is
empty (0 rows — the V3 engine has never been run into storage), and no
crash/flare event table exists (`flare_events`, `crash_events` both 404). There is
nothing to replay a signal *against*, so the backtest could not have produced the
"where it would have fired vs where a crash actually occurred" comparison the
acceptance criteria demand, even had Streams 1+2 landed.

---

## What actually changed

| File | Change |
|---|---|
| `core/health/stability_statistic_validation.py` | **NEW** — Stream 0 read-only analysis. Not imported by any live path. |
| `knowledge/missions/USS-TJR-MSN-0388-knowledge-record.md` | **NEW** — this record. |
| `core/health/burnout_trajectory.py` | **UNCHANGED** — verified byte-identical in the diff. |
| `core/health/capacity_gate.py` | **UNCHANGED** — the mission never wires into `evaluate()`, per the brief. |

Because `burnout_trajectory.py` is untouched, the acceptance criterion "never
emits a weighted numeric score anywhere in output" holds trivially and was
confirmed by reading the diff (no hunks against that file). Its existing test
suite passes unchanged.

---

## Recommendation to the Captain

1. **Do not commission the CAP-1 follow-up that wires a predictive signal into
   `capacity_gate.py`.** There is no signal to wire. Re-run
   `python3 -m core.health.stability_statistic_validation` after ~6 months of
   sustained check-ins and revisit only if AR(1) turns positive and its range
   clears the shuffled-null band.
2. **The binding constraint is history length, not method choice.** Swapping AR(1)
   for another early-warning statistic does not help — 31 points is too few for
   any of them. The cheapest real uplift to CAP-1 is *check-in continuity*
   (the series is already 4 days stale), not a cleverer statistic.
3. **CAP-2 (contextual-bandit intervention personalisation) was out of scope here
   and remains so.** It was to be sequenced on Stream 2's live data, which does
   not exist. It needs its own data-sufficiency gate before commissioning —
   a bandit over 31 observations has the same problem.
4. **Reconsider whether personal control limits are wanted at all while the
   Captain's baseline is this strained.** The 71%-orange/red finding is itself
   the more actionable result of this mission: it says the current population
   constants are, if anything, *correctly* firing.

## Incidental finding — mission-ID minting drift root cause (recurrence)

`tools/mint_id.py MSN` first returned `USS-TJR-MSN-0377`, which **collides with an
existing mission** (`knowledge/missions/USS-TJR-MSN-0377-knowledge-record.md`,
2026-09-13). `id_registry.next_id()`'s collision self-heal is being defeated by a
test fixture: the repo scan finds the literal `MSN-9999` placeholder in

- `core/engineering/tests/test_engineering_router.py`
- `core/knowledge_navigation/tests/test_navigator.py`
- `knowledge/missions/USS-TJR-MSN-0368-knowledge-record.md`

so `scanned=9999` against `stored=377` exceeds `_MAX_SANE_DRIFT` (100), the
auto-bump is refused, and the minter falls back to the stale stored counter —
which is behind the true maximum in use (0384) and therefore mints collisions.
This is the durable root cause of the long-standing "mission ID minting drift"
issue, which has now recurred. **Not fixed here (out of scope).** The fix is for
`true_max_for_prefix()` to ignore IDs inside test files / obvious placeholder
sentinels rather than for `_MAX_SANE_DRIFT` to absorb them. Minting was advanced
to 0388 (first free ID above the true maximum) for this mission.
