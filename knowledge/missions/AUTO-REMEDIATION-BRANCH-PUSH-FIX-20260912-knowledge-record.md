# Knowledge Record — auto_remediation.py's git_commit() now refuses the wrong branch and pushes, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0365 (Stream A) |
| Title | LL-146's diagnosed-but-unfixed root cause is fixed: git_commit() fails closed on branch mismatch and pushes on success |
| Date | 2026-09-12 |
| Lesson | LL-149 |

## Outcome

LL-146 (PR #111, merged) diagnosed but explicitly did not fix
`scripts/self_improvement/auto_remediation.py`'s `git_commit()`
(`hq-evolution.timer` → `orchestrator.py` → this method): no check on which
branch was checked out, no `git push`, so cycle-artifact commits landed
silently on whatever branch the VM happened to have checked out at 03:00 and
never reached `origin`.

Fixed in PR #118 (https://github.com/timjardenross/TJRHQ/pull/118, merged):

- `AutoRemediationExecutor.__init__` now sets
  `self.expected_branch = "self-improvement"` — a judgment call made for
  this mission: a dedicated branch, not `main`, so autonomous nightly
  cycle-artifact commits stay isolated from human-authored history until a
  human reviews and merges them on their own schedule, rather than landing
  directly in `main` unreviewed.
- `git_commit()` now runs `git rev-parse --abbrev-ref HEAD` before touching
  anything. On a mismatch it logs an error naming both the expected and
  actual branch, skips `add`/`commit` entirely, and returns `None` — fails
  closed, exactly as LL-146 recommended.
- On a successful commit, it now runs `git push origin <branch>`. A push
  failure is logged at `error` level with the commit sha called out
  explicitly ("this needs manual attention or it will dangle exactly like
  LL-146"), but does not raise or undo the local commit — the function still
  returns the sha.

**Evidence:** `pytest tests/test_auto_remediation.py -v` → 21 passed (18
pre-existing + 3 new: refuses on wrong branch with zero add/commit calls
made; commits and pushes on the expected branch; a push failure still
returns the sha but logs loudly). All git/subprocess calls mocked — no real
git or network operations in the test suite, per this file's existing
convention.

While rebasing onto latest `main`, the implementing agent found an unrelated
upstream change (merged since this stream's instructions were written) had
added a `paths` parameter to `git_commit()` for scoped `git add`. The
branch-check/push logic was merged cleanly alongside it rather than
clobbering it — both behaviors coexist in the final version.

## Lesson

Diagnosing a bug and writing it up (LL-146) is not the same as it being
fixed — a knowledge record that says "not fixed here" needs a tracked
follow-up or it can sit indefinitely while the underlying automation keeps
producing the exact failure mode already documented. This record closes
that loop explicitly rather than leaving LL-146 as a dangling diagnosis.

## Future Guidance

Before any daily/scheduled write-job's commit method ships, ask two
questions LL-146 and this fix both had to answer the hard way: (1) does it
verify *which* branch it's about to commit to, or does it trust whatever
happens to be checked out at fire time; (2) does it push, or does it leave a
local-only commit that `origin` never sees. A scheduled job sharing a
working tree with interactive/human use is the specific shape of risk here
— isolating its target branch (as done here) is one fix; giving it a
dedicated worktree/clone it owns exclusively (LL-146's other suggested
direction) is the other, not yet taken.
