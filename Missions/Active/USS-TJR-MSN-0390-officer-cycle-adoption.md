# USS-TJR-MSN-0390 — Officer Daily-Operations Cycle: Formal Adoption

**Parent context:** MSN-0210L/M (Officer & Experience Convergence, design-only, 2026-07-05).
**Type:** Implementation — scheduling + ownership, not new feature design.
**Status:** Active — opened 2026-09-15 during a Chief-of-Staff Tier-2 decision review.

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
