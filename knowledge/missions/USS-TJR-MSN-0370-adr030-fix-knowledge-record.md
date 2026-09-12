# Knowledge Record — USS-TJR-MSN-0370 (ADR-030 test/implementation mismatch fix)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0370 |
| Title | Resolve ADR-030 test/implementation mismatch |
| Follows | USS-TJR-MSN-0369 (filed ADR-030 as "Reconstructed — medium confidence (partially unimplemented)", flagged this exact mismatch as an open gap rather than fixing it) |
| Branch | msn-0370-adr030-fix |
| Date | 2026-09-12 |

## The mismatch, as handed off

`platform-runtime/test_build_router_alignment.py::TestEngineeringHandoffRouterMeta::test_handoff_includes_mission_id`
asserted `save_engineering_handoff_from_build_record()` in
`platform-runtime/commands/mission_brief.py` emits an "Engineering Router
Metadata" section citing `ADR-030`, with `router_mission_id` /
`router_backend` / `router_mode` fields. The real implementation does none
of this. MSN-0369 flagged it as an open gap without running the test or
deciding a fix.

## What running the test actually showed

Running the full file (it had never been run before this mission) surfaced
**12 of 23 tests failing**, not the single one cited — every failure traced
to the same root cause: the test file assumes a whole "mission ID input
routes through the Engineering Router with backend/mode selection; free
text uses Mistral Scribe" design (`_parse_router_args`,
`save_build_record(..., router_meta=...)`, an "Engineering Router Metadata"
section in build records and handoffs, a dict return from
`save_engineering_handoff_from_build_record()`) that is simply not present
anywhere in the current `commands/mission_brief.py`.

## Decision: the test was stale, not the code

Evidence gathered before fixing anything:

1. `git log --all -S "_parse_router_args" -- commands/mission_brief.py`
   (and unrestricted) returns **no commit** where that function ever
   existed in the source module — only in test fixtures, including the
   earliest commit that introduced this file into the (squash/sync-mangled)
   git history at all. There is no traceable point where this feature was
   "reverted" from `mission_brief.py`; the mismatch appears to predate any
   change visible in this repo's history.
2. A sibling test file testing the identical missing integration,
   `platform-runtime/tests/test_mission_brief_router_integration.py`, was
   already found and **deliberately deleted** on 2026-09-08 in commit
   `38e554352` ("Remove Slack integration platform-wide; Telegram is now
   the sole transport") as orphaned Slack-only test debt. That commit's own
   message audited dependencies file-by-file before deleting each one —
   this file (`test_build_router_alignment.py`) tests the exact same
   abandoned router integration and should have been caught in the same
   pass, but wasn't.
3. `grep -rn "save_engineering_handoff_from_build_record\|mission_brief"` across
   the whole repo (outside test files) returns **zero callers** — the
   module has no live caller anywhere post-Slack-removal, the same
   "confirmed dead, needs its own pass" category the 2026-09-08 commit
   explicitly called out for `commands/health_appointment_prep.py`.
4. `save_engineering_handoff_from_build_record()`'s own module-level public
   API docstring (top of `commands/mission_brief.py`) already documents
   `-> str` — matching the real implementation, contradicting the test's
   dict-return assumption.

Given no live caller depends on router metadata or a dict return, and no
evidence this integration was ever completed rather than only assumed by
tests, implementing the feature would mean building new, unrequested
behavior into dead code. The correct fix was to update the test to match
reality.

## What was changed

- `platform-runtime/test_build_router_alignment.py`: removed
  `TestParseRouterArgs` (4 tests), `TestBuildRecordRouterMeta` (2 tests),
  the two router-metadata assertions inside `TestEngineeringHandoffRouterMeta`
  and `test_router_meta_recovered_from_record` in
  `TestFindBuildRecordRouterMeta` — all asserted on functions/kwargs/sections
  that never existed in any live version of `mission_brief.py`. Each removal
  has an inline comment citing this evidence trail. Fixed the genuine
  NameError-regression test (`test_handoff_file_created_without_nameerror`)
  and the two "must return dict" tests
  (`TestSaveEngineeringHandoffReturnsDict`) to assert the function's real,
  documented `str` return contract instead.
- `core/governance/architecture-decision-records/ADR-030-engineering-router-execution-model.md`:
  added a "Resolution" section with the full evidence trail above, and
  updated the frontmatter status to reflect the mismatch is resolved. The
  load-bearing part of ADR-030 (plan/review-vs-apply backend boundary in
  `core/engineering/providers/gemini.py`) is untouched and still real —
  only the router-metadata handoff citation (the "Bad / open gap" item) was
  resolved.

## Verification

`/opt/starship-endeavour/platform-runtime/.venv/bin/pytest
platform-runtime/test_build_router_alignment.py -q` → **14 passed** (all
tests in the file now pass; note: this environment's system Python has no
usable pytest install — used the existing venv at
`/opt/starship-endeavour/platform-runtime/.venv` to run tests).

## Not done / explicitly out of scope

- Did not implement the "Engineering Router" integration into
  `mission_brief.py` (mission-ID routing, backend/mode selection, router
  metadata persistence) — no live caller needs it, and doing so would be
  resurrecting/inventing behavior for dead code, not fixing a real gap.
- Did not delete `commands/mission_brief.py` itself, despite confirming it
  has zero live callers — that's a separate "is this dead module worth
  reviving or removing" decision or its own follow-up mission, same as the
  2026-09-08 commit deliberately left `health_appointment_prep.py` alone
  for a future pass rather than deleting it inline.
