# Knowledge Record — USS-TJR-MSN-1788844175339

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-1788844175339 |
| Title | Retire duplicate config formats immediately, not just fix the loader bug |
| Date | 2026-09-08 |
| Lesson | LL-134 |

## Outcome

Deleted config/self_improvement_policy.yaml; repointed policy.py's self-test at the canonical .json file; config/self_improvement_policy.json is now the single source of truth. Full self-improvement test suite (28 tests) verified green after the change.

## Lesson

A loader bug caused by "which of two config files wins" is a symptom; leaving both files in place after fixing the loader just re-arms the same class of bug for the next person who edits the wrong one.

## Future Guidance

When investigating a "which file is actually read" bug, check for a duplicate/shadow config file as part of the fix, not just the code path that reads it — and require the fix to name a single canonical source.
