# Knowledge Record — USS-TJR-MSN-1788844167855

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-1788844167855 |
| Title | A metric's denominator must be discovered with the same scope as its numerator |
| Date | 2026-09-08 |
| Lesson | LL-135 |

## Outcome

_find_test_files() now uses the same _find_prune_args()-pruned, repo-wide find scope as _count_python_files(), matching test_*.py/*_test.py across the whole tree and returning relative paths. Added a regression test (TestFileSystemAuditReconciliation) asserting test-file count never exceeds python-file count and that files outside tests/ are found. Verified against the real tree: 220 test files / 976 total python files, matching the original finding.

## Lesson

Two counts meant to be compared (or where one is meant to be a subset of the other) must be discovered with matching scope and matching directory-exclusion rules, or they silently drift apart and any consumer trusting both numbers together draws a wrong conclusion. Same defect class as the vendored-directory exclusion bug already fixed for _count_python_files()/_find_todos() (2026-08) — the fix pattern (shared prune-args helper) existed but was never applied to _find_test_files().

## Future Guidance

When a self-improvement/audit collector adds a new file-discovery method, default it to the same shared prune/scope helper the rest of the collector already uses rather than a fresh ad hoc glob() — and pair any two counts meant to be compared with a reconciliation assertion in tests, not just a non-emptiness check.
