# USS-TJR-MSN-0389 — EOS Blueprint Tier 0 Completion

**Parent:** USS-TJR-MSN-0347 (Executive Operating System Blueprint V2.0)
**Type:** Implementation, scoped to Tier 0 structural preconditions only.
**Status:** Active — opened 2026-09-15 during a Chief-of-Staff planning/validation pass.

## Why this mission exists

MSN-0347 specified a 5-item Tier 0 ("structural preconditions, before any UI investment")
and never had implementation commissioned against it. Its own report was also found
never committed to this repo (recovered 2026-09-15, commit `2b6a27f5b` — see that
mission's own record; the "committed c4796952" claim in prior memory was false).

Before writing this brief, all 5 Tier 0 items were re-validated against live code
(not the 2-month-old doc, not memory) on 2026-09-15. Two are already done — the
actual fix for the real historical near-miss (Telstra outage, root-caused to a
schema mismatch + unscheduled reasoning cycle) is live. This mission scopes only
the remaining 4.

## Already done — do not re-build

- **Heartbeat / internal self-health monitoring** — `core/platform/heartbeat.py` +
  `core/platform/verification_engine.py` (systemd timer) + `core/platform/deadmans_switch.py`
  (watches the watcher, independent Telegram alert path). Confirmed live, firing ~every 10min.
- **INTERRUPT_NOW drill/certification** — `core/platform/attention_drill.py`, scheduled
  weekly inside `intelligence/scheduler.py` (job `attention_engine_weekly_drill`), real
  end-to-end synthetic drill through Telegram, tagged `[DRILL]`, feeding the heartbeat
  system above for a scorecard trail.

## Remaining scope (this mission)

1. **Wire Priority Engine into the Decisions Inbox.** Core scoring (`core/platform/priority_engine.py`)
   is real and already wired into the Captain's Brief Workbench
   (`lcars-portal/src/app/captains-brief-workbench/_components/ItemRow.tsx`). The Decisions
   Inbox (`lcars-portal/src/lib/decisions.ts`) still runs its own separate, unrelated
   `priorityRank` heuristic from P0/P1 labels + age — never touched by the fix. This is
   the specific surface MSN-0347 §1.4's structural ranking gate was actually about.
   Task: replace or bridge `decisions.ts`'s heuristic with `priority_engine.py`'s real
   score, respecting §1.4's own gate (unranked/attention-grouped rendering until Priority
   Engine's confidence tier clears Emerging — check current confidence tier before wiring
   ranked display).

2. **Instrument the shrinking-Stream metric + anti-gaming guardrail.** Confirmed not built —
   zero hits for `stream_size`/`override_rate`/`false_suppression` anywhere in code or SQL.
   `NEVER_INTERRUPT` already exists as a live suppression category
   (`core/platform/attention_engine.py`) — this task instruments *that*, it doesn't build
   a new suppression mechanism. Needs: per-domain Stream-size tracking over time with a
   named owner, plus a paired override-rate/false-suppression-rate guardrail so a shrinking
   Stream from earned trust is distinguishable from one shrinking via quietly-raised
   thresholds.

3. **Build the thin delegation record.** Confirmed not built as specified — existing
   `delegat*` code (`core/exec-assistant/delegation_router.py`, task-delegation columns
   in migrations 0056/0145) is task-routing to specialists, not this. Needs: a thin Event
   Bus record (not a new subsystem) supporting silent checkpoint → proxy nudge →
   Captain-escalation-with-default → non-response-default-fires.

4. **LCARS retirement — DECIDED 2026-09-15: retire.** Captain sign-off obtained during
   this mission's own planning pass. LCARS stops being the platform's primary visual
   identity. Per MSN-0347 §13.3's corrected sequencing: the **decision** and the
   **skin-agnostic token abstraction** land here at Tier 0/1 (so the shared renderer
   this mission's item 1 touches isn't built coupled to LCARS-specific color/chrome
   conventions); the **actual visual reskin execution** is deferred to Tier 4, a
   separate future mission. Note: the 2026-09-13 tooling decision
   (`lcars-portal/docs/design-tokens/STYLE-DICTIONARY-LEONARDO-DECISION.md`) declined
   Style Dictionary/Leonardo and called LCARS colors "governance-locked brand values" —
   that was a tooling-choice call made before this identity decision and will need
   revisiting now that LCARS itself is being retired as primary identity, not just its
   tooling.

## Out of scope

Tier 1-4 of MSN-0347's roadmap (Brief object, trust infrastructure, autonomy rungs,
visual execution) — those depend on this Tier 0 work landing first and are separate,
larger missions.

## Next action

Item 4 blocks nothing else and costs nothing but a decision — surface it to the Captain
directly rather than treating it as engineering work. Items 1-3 can proceed in parallel;
item 1 is the smallest, most contained, and closes the specific gate MSN-0347 cared about
most (Fix Now/Enterprise Leadership's finding).
