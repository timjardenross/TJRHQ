# Knowledge Record — USS-TJR-MSN-0364

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0364 |
| Title | A "simple" scoped item can still surface a real, unrelated bug in the very tests meant to prove it safe |
| Date | 2026-09-08 |
| Lesson | LL-140 |

## Outcome

Delivered candidates A and B (core/coordination/command_bus.py + telegram-bots/xo/app.py) in one clean, green PR (#92, merged). Found and fixed the test-isolation gap in the same pass rather than pushing red or shipping a false-negative-prone test suite for someone else to hit later.

## Lesson

Both candidates A and B were deliberately picked as "easy" — small, unblocked, reusing already-tested functions rather than new logic. Re-running the full test suite before pushing (not just the new tests) caught a real, unrelated failure anyway: Missions/Engineering-Handoffs/ had gained real content on main via a concurrent session's PR while this work was in progress, and several pre-existing tests in test_number_one_brief.py were not actually hermetic against that — they patched _load_missions but not load_engineering_handoffs, so real handoff files with real PR URLs started leaking into supposedly-isolated unit tests and making live GitHub API calls. "Small and safe" work is not a reason to skip the full local test run before pushing — the size of a change and the size of what a full test run can catch are unrelated.

## Future Guidance

Always run the FULL relevant test suite before pushing, not just tests for the lines you touched — real repo state (file corpus, concurrent sessions' work landing on main) can silently invalidate a test's isolation assumptions between one run and the next, and the cheapest time to catch that is your own pre-push check, not CI or a future session.
