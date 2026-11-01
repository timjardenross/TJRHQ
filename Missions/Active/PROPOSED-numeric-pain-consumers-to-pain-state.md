# Mission Brief — Move the remaining numeric-pain consumers to pain state

**Status: PROPOSED — brief only. Nothing in this brief is approved to start.** The PO approved
writing it (2026-10-15) as a separate follow-up to the R2 alignment (TJRHQ PR #381). No code,
database or live change is made by this document.

## Mission Header

- **Mission ID:** (to be minted with `python3 tools/mint_id.py MSN` when the PO starts the mission — not minted here)
- **Priority:** PO to set
- **Source:** TJRHQ PR #381 open item "numeric-pain consumers outside the approved rules"; PO decision 2026-10-15 (approved as a separate follow-up mission, "not now")

## Why

Pain is now captured as "pain compared with your usual baseline" (`capacity_checkins.pain_state`:
low / baseline / elevated / high). CapacityBot no longer asks the 0–10 question (PR #381, step 2), so
new check-ins carry **no number**. Several consumers still read `pain_score`; they will go quiet or
mis-read as old numeric history ages out of their windows. The recovery-score function and the pain
red flag are already on pain state (migration `0234`, `lcars-portal/src/lib/painSignal.ts`).

## Pre-flight

1. [x] **Existing-entry check.** This mission adds no row to any registry. N/A — no list is extended.
2. [x] **Premise verification** (run 2026-10-15 on `main` at `234aae0`; `-`/line numbers are from these greps):
   ```
   grep -nE "pain" core/health/capacity_score.py            -> WEIGHTS["pain_max_deduction"]=35 (l.28); deduction = pain/10 x 35 (l.101-104)
   grep -nE "PAIN_SPIKE" core/health/readiness_score.py     -> PAIN_SPIKE_THRESHOLD = 8; -8 pts if pain_score >= 8 (l.15, 70, 151-155)
   grep -nE "pain_avg" core/health/weekly_synthesis.py      -> acute if pain_avg >= 7 (l.648-664); 3+ days >= 7 (l.1073); avg >= 6 (l.1086); >= 7 (l.1257)
   grep -nE "pain" core/intelligence/operating_picture.py   -> pain >= 7 (l.246)
   grep -nE "pain" core/intelligence/health_mission_correlation.py -> high_pain_days: pain >= 7 (l.285)
   grep -nE "avg_pain" platform-runtime/commands/health_appointment_prep.py -> avg >= 6 / >= 4 labels (l.216); topic when avg >= 5 (l.279)
   grep -n "painStateToScore" lcars-portal/src/lib/human-systems.ts -> maps low/baseline/elevated/high -> 2/4/7/9 (l.365-368); used at l.383
   ```
   **Finding that changes the risk of Stream 1:** `painStateToScore()` is not display-only. Its pseudo-number
   becomes `pain_score` on the merged row (l.383), which `interpretCapacity` turns into a physical-domain
   penalty of `min(25, pain x 2.5)` (l.219-220). So "around usual" (4) already costs the portal's capacity
   snapshot 10 points. Removing the mapping changes portal numbers and needs the comparison below.
3. [x] **Explicitly not in scope** — see next section.

## Explicitly Not In Scope

- Anything already done in PR #381: the recovery-score pain modifier (`0234`), the red flag, the readers' wording, the CapacityBot question removal.
- "Pain trend elevated" (state-based alert) — its own small PR (PO-approved, separate).
- Retiring the dormant `commands/health_check.py` writer — its own small PR (PO-approved, separate).
- Governance documents (Phase 3, USSTJROS PR) and Phase 4 (posture rule version / golden vectors — not approved).
- Deleting or converting any stored pain data. Columns and history stay; the old number is shown only as labelled history.
- Any live change without the PO's go.

## Method (same as migration 0234)

Additive only; rollback saved before anything is applied; for any change that moves a score, an
**aggregate-only** before/after comparison (counts and distributions, no row contents or health values)
is reported and the **PO's go** is obtained before it goes live. State is used where it exists; the
old number is used only for pre-change history days; a number is **never invented** from a state and a
missing value is never read as zero or as "no pain". Small PRs, tests for each pain state, a missing
state and an old numeric-only day. No independent review unless the PO engages one.

## Streams (in the PO's order)

1. **Remove `painStateToScore()`** (`lcars-portal/src/lib/human-systems.ts`) and replace the portal's
   physical-domain pain drag with a pain-state rule (none for low/baseline, half for elevated, full for
   high — scaled to the existing 25-point drag, PO to confirm the scale). Moves portal capacity numbers →
   aggregate before/after on the same days, PO go first. No database change.
2. **`weekly_synthesis.py` and `operating_picture.py`** — replace "pain_avg ≥ 7 / ≥ 6 / pain ≥ 7" with
   state counts (e.g. check-ins at "higher than usual" / "much higher than usual" over the window;
   "much higher" as the acute trigger, matching the red flag). User-visible wording only; tests per state.
3. **`capacity_score.py` and `readiness_score.py`** — these **change scores**: a pain-state deduction
   (replacing `pain/10 x 35` and the ≥ 8 spike) calibrated so "much higher than usual" is not loosened and
   lower/around usual is not penalised. Each needs its own aggregate before/after comparison and the PO's
   go before it ships. Check callers first (`daily_ops_cycle.py`, `capacity_gate.py`, schedulers).
4. **`health_mission_correlation.py` and the `health_appointment_prep.py` thresholds** — high-pain days
   become days with a "much higher than usual" check-in; the appointment-prep topic fires on a count of
   "higher than usual" or above across the period instead of `avg ≥ 5`.

Order of work inside each stream: tests first (old numeric-only day, new state, missing), then the change,
then the comparison where scores move.

## Acceptance

- No consumer in the list reads `pain_score` for a *new* check-in; each handles state, old numeric history
  and missing value, with tests for all three.
- `painStateToScore()` is gone and nothing synthesises a number from a state.
- Every score-changing stream has a recorded aggregate before/after, the PO's go, and a saved rollback.
- A missing value never reads as zero or as "no pain" anywhere in the list.
- Grep shows no remaining numeric-pain threshold (`>= 6/7/8`, `x 2.5`, `/ 10 x 35`) in the listed files.
- Columns and history untouched (row counts before = after).

## Reporting

One knowledge record in `knowledge/missions/` with the per-stream comparison results (aggregate only),
the rollbacks, and the open decisions. No SUOC Platform Registry change expected.
