# USS-TJR-MSN-0390 — Officer Daily-Operations Cycle: Formal Adoption

**Parent context:** MSN-0210L/M (Officer & Experience Convergence, design-only, 2026-07-05).
**Type:** Implementation — scheduling + ownership, not new feature design.
**Status:** Active — opened 2026-09-15 during a Chief-of-Staff Tier-2 decision review.
Reconciliation + scheduling (items 1-3) DELIVERED 2026-09-26 (see "Convergence update"
below); item 4 (readiness re-verify) also closed out same date. Remaining: coordinating
session to review/merge `deploy/daily-ops-cycle.service`+`.timer` and enable on the host.

## Convergence update (2026-09-26)

A same-session investigation resolved every open item below:

- **Item 1 (reconcile the two files) — not actually a conflict.** `daily_ops_cycle.py`
  (1600 lines) is not a competing design against `daily_operations_cycle.py` (524 lines) —
  it *calls into* it. `daily_ops_cycle.py`'s step 7.2 (`_step_autonomous_officers`) imports
  `run_officer_cycle`/`format_officer_cycle_summary` directly from
  `lib.officers.daily_operations_cycle` and runs it as EXEC-010A, after all 6 preceding
  officer/review steps have populated the shared `CycleContext`. There is one real cycle
  (`daily_ops_cycle.py`'s `run_daily_cycle()`), and the smaller file is a component of it,
  not an alternative to it. Nothing needed retiring.
- **Item 2 (owner)** — assigned. See `knowledge/SUOC-Platform-Registry.md`.
- **Item 3 (live scheduler)** — built. `deploy/daily-ops-cycle.service` + `.timer` (oneshot,
  06:50 Australia/Sydney daily, modeled on `self-improving-system.service`/`.timer`'s
  Restart/logging/circuit-breaker conventions) invoke a new entry point,
  `scripts/daily_ops/run_daily_ops_cycle.py`, which gathers real missions (via
  `context_service.py`'s live Number One mission overlay) and today's `capacity_checkins`
  row, then calls `run_daily_cycle()`. No dedicated worktree needed (unlike
  self-improving-system.service) — this cycle only reads and prints a brief, it never
  git-commits.
  **Authority-gate coverage, checked as this item required:** every officer this cycle
  touches (`human_systems`, `research`, `knowledge`, `number_one`, `medical`, `engineering`,
  `xo`) has a manifest file in `governance/authority/`, so the cycle will not hit the
  fail-closed `ManifestGapError` MSN-0326 Wave 3 introduced. However, coverage is only
  structural, not substantive: every one of those manifests is the deliberately
  **baseline-permissive** placeholder from `governance/authority/_template_notes.md`
  (empty `allowed_actions`/`disallowed_actions`/`requires_*` lists) — no real policy has
  ever been set for any officer action. Worse, of the two write paths this cycle actually
  exercises, only one is authority-gated at all: `_step_number_one()` calls
  `core/coordination/execution_engine.py::NumberOneExecutionEngine`, which does invoke
  `core/governance/authority_validator.py` (against the permissive `number_one.yaml`).
  The newer EXEC-010A autonomous-officer layer (`daily_operations_cycle.py`'s
  `run_officer_cycle()`, which calls `assign_mission()` and `advance_escalation()` — real
  mutating writes) never calls `enforce_authority()`/`can_officer()` at all — confirmed by
  a repo-wide grep for those names, which returns only `execution_engine.py` and
  `platform-runtime/command_memory_integration.py`. **Closed 2026-09-26** (Captain's call:
  wire it in before enabling, not enable-then-fix): both write calls in
  `daily_operations_cycle.py` are now wrapped in `AuthorityContext`, same pattern as
  `execution_engine.py`'s Number One step — `AuthorityError`/`ManifestGapError` both skip
  the write (fail-closed) instead of proceeding ungated. Verified directly (mocked
  dependencies, no network): the `assign_mission` path proceeds correctly under
  `number_one`'s existing permissive manifest; the `advance_escalation` path correctly
  fail-closes when `esc.officer` has no matching manifest file (e.g. a literal
  `chief_engineer` — no `governance/authority/chief_engineer.yaml` exists, only
  `engineering.yaml`). That fail-close is currently inert either way: `create_escalation()`
  has zero production callers anywhere in the repo, so `get_overdue_escalations()` returns
  empty and this loop has nothing to iterate over yet — a separate, smaller gap (nothing
  ever populates the escalation queue) worth flagging for whoever wires that up for real.
- **Item 4 (Medical Officer duplication) — re-verified stale, confirmed not a real
  problem.** `daily_operations_cycle.py`'s `_step_readiness_assessment()` (its own
  "Medical Officer" step) does not collect any capacity data itself — it only reads
  `ctx.capacity_status`/`ctx.capacity_score` (already computed upstream, in the same
  cycle, by `_step_human_systems()` from the real `capacity_checkins` pipeline via
  `capacity_zone_from_checkin()`) and logs a one-line summary signal. There is no second,
  competing readiness/capacity data path here to reconcile against the live
  `telegram-bots/wellness_officer/`/`recovery_officer/` bots — it's a downstream consumer
  of the same single source of truth, not a duplicate collector. Safe to wire as-is.

## Captain decision (2026-09-15)

Formally adopt the officer daily-operations cycle rather than retire it. This mission
scopes what "adopt" actually requires: a real owner, a live scheduler, and closing the
authority-semantics question this code has been blocked on since MSN-0210L.

## Verified live state (2026-09-15, re-checked before writing this brief — do not trust
## the 2026-07-05 dormancy finding without re-verifying if this mission stalls and gets
## picked up much later)

- **Two similarly-named files exist**, both dormant:
  - `platform-runtime/lib/officers/daily_operations_cycle.py` (524 lines) — the original
    8-step cycle MSN-0210L found dormant.
  - `platform-runtime/lib/daily_ops_cycle.py` (1600 lines, `EXEC-001` through `EXEC-010A`)
    — a substantially larger, more recent orchestrator sequencing Human Systems → Strategic
    Planning → ORI → Engineering → Communications → Number One, plus 7 more sub-steps
    (Investigation/Learning/Strategic-Outcomes/Program-Coordination/Portfolio-Optimisation/
    Enterprise-Architecture/Investment-Governance review stages).
  - **Neither has a real caller anywhere in the repo.** The only 2 files mentioning
    `daily_ops_cycle` (`platform-runtime/lib/improvement/framework.py`,
    `platform-runtime/lib/strategy/portfolio_queries.py`) do so in docstring comments
    only — zero actual `import` statements found for either module, repo-wide. No
    systemd unit, timer, or crontab entry references either.
  - **This is worth flagging on its own**: real engineering effort has gone into growing
    this code (524 → 1600 lines) while it has never once executed against real data.
    That's a bigger red flag than plain dormancy — it means "adopt" needs to include
    reconciling *which* of the two files is actually meant to be the real cycle before
    scheduling anything, not just flipping a switch on existing code.

- **Authority-duplication blocker is RESOLVED, not still pending.** MSN-0210L flagged
  `platform-runtime/lib/officers/officer_actions.py`'s own `AUTHORITY_MAP` as a third
  instance of authority-checking duplication, "blocked on the same still-pending
  canonical-semantics Captain decision." Verified 2026-09-15: MSN-0326 Wave 5 already
  consolidated `AUTHORITY_MAP` onto `core/governance/authority_validator.py`'s manifest
  loader (`officer_actions.py:23,80,85,115` — "AUTHORITY_MAP (Mechanism 2, now retired)").
  This mission does not need to solve that question — it's already solved.

## Scope

1. **Reconcile the two cycle files first.** Determine whether `daily_ops_cycle.py`
   (1600 lines) is the intended successor to `daily_operations_cycle.py` (524 lines) or
   a separate, competing design. Read both, check git blame/history for which one recent
   work actually targeted, and either retire the superseded one or document why both are
   needed. Do not schedule a cycle without first knowing which cycle it is.
2. **Assign a real owner.** Per the platform's own registry convention (see
   `knowledge/SUOC-Platform-Registry.md`), every live capability needs a named owner —
   this one currently has none.
3. **Build the live scheduler.** Wire whichever cycle is adopted into a real
   systemd timer or cron entry, following the pattern already established for
   `self-improving-system.service`/`.timer` (dedicated worktree if this needs
   filesystem writes; direct invocation if read-only). Confirm the officer authority
   gate (`core/governance/authority_validator.py`, now fail-closed by default per Wave 3)
   actually covers whatever real actions this cycle would take once live — this is
   where [[chief-of-staff-action-register]]'s downgraded "authority_validator reach"
   item re-opens.
4. **Verify the Medical Officer duplication before wiring readiness data.** MSN-0210L
   found the dormant cycle's readiness step is a second, non-unified implementation
   alongside the LIVE `telegram-bots/wellness_officer/`/`recovery_officer/` bots.
   Re-verify this is still true before this mission wires the dormant cycle's readiness
   step to anything — don't build a second live readiness path if one already exists.

## Out of scope

Building any of the "Operations/Content/Finance Officers" MSN-0210L confirmed are
doc-only aspirations with zero code — those stay correctly unbuilt.

## Next action

Start with item 1 (reconcile the two files) — everything else depends on knowing which
cycle is actually being adopted, and it's the cheapest item to resolve (reading + git
history, not new code).
