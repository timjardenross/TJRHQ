---
status: "Reconstructed — high confidence (test/implementation mismatch resolved USS-TJR-MSN-0370: stale test, not a missing feature)"
date: 2026-09-12
decision-makers: {unknown — reconstructed from code, not from a governance-log entry}
consulted: {unknown}
informed: {unknown}
---

# Engineering Router Execution Model: cloud backends plan/review, never auto-apply

## Context and Problem Statement

The `/build` and `/mission-brief` flows route engineering work to different
backends (Gemini, Mistral, GLM, …) depending on whether the request came in
as a Mission ID (routed through the Engineering Router) or as free text
(handled by a separate "Mistral Scribe" path with no router involved). ADR-030
is cited as the decision governing which backends are trusted to do what —
specifically, that a backend suitable for "plan, review, architecture
assessment, mission decomposition" is explicitly **not** trusted to
"auto-apply or directly modify files."

## Decision Drivers

* Not all engineering backends should be allowed to write to the repository
  directly — some are advisory/planning-only.
* Build records and engineering handoffs need traceable router metadata
  (which mission, which backend, which mode) so a human/engineer reviewing a
  handoff can see how a change was routed and why.

## Decision Outcome

Chosen option (as far as the evidence shows): backends are split into
plan/review-only vs. apply-capable, with the boundary made explicit in the
backend's own module docstring. `core/engineering/providers/gemini.py`
states this directly: "Suitable for: plan, review, architecture assessment,
mission decomposition. NOT for: auto-apply or direct file modification
(ADR-030 governs this)."

### Consequences

* Good, because a reviewer can trust that a Gemini-routed plan/review output
  was never silently auto-applied to the codebase.
* Bad / open gap found during this reconstruction: the test suite
  (`platform-runtime/test_build_router_alignment.py`,
  `TestEngineeringHandoffRouterMeta.test_handoff_includes_mission_id`)
  asserts that `save_engineering_handoff_from_build_record()` in
  `platform-runtime/commands/mission_brief.py` emits an "Engineering Router
  Metadata" section containing the literal string `"ADR-030"` alongside the
  router mission ID/backend/mode — but the current implementation of
  `save_engineering_handoff_from_build_record()` does not build that
  section or reference `router_mission_id`/`router_backend`/`router_mode`
  at all. Either this test is one of the repo's known pre-existing failures
  (see `starship-endeavour-46-preexisting-test-failures` in prior mission
  notes) or the handoff-metadata feature this test documents was reverted/
  never finished. This mission did not run the test to confirm pass/fail
  status (Stream 3 is governance-docs-only, no code changes), so the gap is
  flagged here rather than fixed.

### Confirmation

Run `platform-runtime/test_build_router_alignment.py::TestEngineeringHandoffRouterMeta::test_handoff_includes_mission_id`.
If it fails against current `mission_brief.py`, that confirms the
"Engineering Router Metadata" / `ADR-030` handoff citation is aspirational,
not live — worth its own follow-up mission to either implement the missing
section or update the test to match the real, current handoff format.

## Pros and Cons of the Options

### Backend docstring boundary (plan/review vs. apply) — adopted

* Good, because it is cheap, explicit, and colocated with the backend code
  it constrains.
* Neutral, because it is currently enforced only by convention/docstring, not
  by a runtime check visible in this reconstruction — no gate was found in
  `gemini.py` or its callers that would refuse an apply-style operation at
  runtime.

## More Information

## Resolution (USS-TJR-MSN-0370, 2026-09-12)

Follow-up mission to reconstruct the confirmation above and resolve the
flagged gap. Verdict: **the test's expectations were stale, not
`mission_brief.py`'s implementation.** Fixed `platform-runtime/test_build_router_alignment.py`
to match the real, current code rather than adding the missing feature to
`mission_brief.py`.

Evidence gathered:

* Running the test file (previously never run — see "Confirmation" above)
  showed **12 of 23 tests failing**, not just the one cited. All 12 failures
  traced to one root cause: a "mission ID routes through the Engineering
  Router with backend/mode selection, free text uses Mistral Scribe" design
  that the test file assumes throughout (`_parse_router_args`,
  `save_build_record(..., router_meta=...)`, a `## Engineering Router
  Metadata` section in build records/handoffs, a dict return from
  `save_engineering_handoff_from_build_record()`).
* Searched this repo's full git history (`git log --all -S`) for
  `_parse_router_args` in `commands/mission_brief.py`: it has **never
  existed** in that file at any point in history. It only ever appears in
  test fixtures — including the earliest commit where the file was
  introduced into this history at all, meaning the mismatch predates any
  traceable change here (consistent with this repo's git history being
  squash/sync-mangled, per prior missions' notes).
* Found the actual precedent: `platform-runtime/tests/test_mission_brief_router_integration.py`
  — a *sibling* test file exercising the exact same missing
  `_parse_router_args`/router-integration surface — was already found and
  **deliberately deleted** on 2026-09-08 (commit `38e554352`, "Remove Slack
  integration platform-wide; Telegram is now the sole transport") as
  orphaned Slack-only test debt. `test_build_router_alignment.py` tested the
  identical abandoned integration but was overlooked in that same cleanup
  pass — this mission is the belated other half of that cleanup.
* Confirmed `commands/mission_brief.py` (and specifically
  `save_engineering_handoff_from_build_record()`) has **zero live callers
  anywhere in the repo** (`grep -rn` for both the module and the function
  found none outside test files and the module's own docstring). The module
  is dead code left behind by the Slack removal, in the same category the
  2026-09-08 commit message explicitly flagged for `commands/health_appointment_prep.py`
  ("real generation logic behind dead Slack Bolt command handlers... needs
  its own pass").
* `save_engineering_handoff_from_build_record()`'s own module-level public
  API docstring already documents `-> str`, matching its real
  implementation — the dict-return and router-metadata assumptions in the
  test were never true of any live version of this function.

Because there is no live caller anywhere depending on router metadata or a
dict return, and no evidence this integration was ever completed (only
assumed by tests), implementing the missing feature would mean building
unrequested new behavior for dead code rather than fixing a real gap. Fixed
`test_build_router_alignment.py` instead: removed the assertions/tests that
depended on the non-existent `_parse_router_args`, `router_meta` kwarg, and
"Engineering Router Metadata"/`ADR-030` handoff section (documented inline
in the test file with this same evidence trail), and updated the
NameError-regression and dict-return tests to assert the function's real,
current `str` contract. All 14 remaining tests in the file pass.

This does not change the load-bearing part of this ADR: the plan/review-vs-apply
backend boundary in `core/engineering/providers/gemini.py` is real, current,
and unaffected by this resolution — only the router-metadata handoff
citation (always the "Bad / open gap" item above) has been resolved, as
stale test debt.

Evidence: `core/engineering/providers/gemini.py` (direct governance citation),
`platform-runtime/test_build_router_alignment.py` (describes intended
router-metadata behaviour, currently not matched by
`platform-runtime/commands/mission_brief.py`'s
`save_engineering_handoff_from_build_record()`). Also referenced (title-only,
"ADR-030-Engineering-Router-Execution-Model") in a `temporal_entities`
ghost-table dump (`core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`,
status `UNKNOWN`, zero owning application code) and several
`data/self-improvement/runs/*/evidence.json` retrieval-fixture path lists
that reference a file
(`core/governance/architecture-decision-records/ADR-030-Engineering-Router-Execution-Model.md`)
that never existed on disk before this mission. The ghost-table title matches
the code-derived topic closely enough to corroborate the title, but
contributed no additional decision content — this document's body content
comes from the two real code citations above. Given the confirmed
implementation gap, this ADR is filed as **medium confidence**: the
governance boundary itself (plan/review-only backends must not auto-apply)
is real and load-bearing in `gemini.py`; the router-metadata handoff behaviour
it's also associated with in tests appears to be unimplemented or reverted.
