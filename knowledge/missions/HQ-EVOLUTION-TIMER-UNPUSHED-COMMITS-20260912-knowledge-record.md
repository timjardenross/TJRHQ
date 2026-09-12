# Knowledge Record — hq-evolution.timer commits pollute whatever branch is checked out, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | none (diagnosed during PR #110 review cleanup, not an auto-dispatched finding) |
| Title | hq-evolution.timer's cycle-artifact commit never pushes, so it silently pollutes any branch checked out at 03:00 |
| Date | 2026-09-12 |
| Lesson | LL-146 |

## Outcome

PR #109 and PR #110 (unrelated feature work — Phoenix tracing, cortex_suite
structural context) both shipped with 11 unrelated
`data/self-improvement/review/*` and `data/self-improvement/runs/*` files in
their diffs on first push. Both times this was cleaned up by hand without
first finding out why it kept happening. This record is that diagnosis, done
during #110's cleanup, so the next occurrence doesn't require re-deriving it.

**Confirmed root cause:** `hq-evolution.timer` fires daily at 03:00 →
`hq-evolution.service` → `scripts/self_improvement/orchestrator.py`, which is
invoked with a hardcoded `--repo-root` of `/opt/starship-endeavour` (see its
`argparse` default). At the end of a cycle it calls
`AutoRemediationExecutor.git_commit()` (`scripts/self_improvement/auto_remediation.py:446`)
to persist that cycle's artifacts:

```python
add_cmd = ["git", "-C", str(self.repo_root), "add"]
add_cmd += paths if paths else ["-A"]
subprocess.run(add_cmd, check=True, capture_output=True)
subprocess.run(["git", "-C", str(self.repo_root), "commit", "-m", message],
                check=True, capture_output=True)
```

This has two properties that combine into the bug:

1. **No branch check.** It commits onto whatever branch is checked out in
   `/opt/starship-endeavour` at exactly 03:00 — main, or any feature branch a
   human or agent happened to leave checked out overnight.
2. **No `git push` anywhere in `git_commit()`.** The commit is created
   locally and never sent to `origin`. Nothing else in the codebase pushes it
   later either — `git log --oneline --all --grep` for
   `self-improvement: cycle` commits followed by a push of the same sha turns
   up nothing.

**Evidence, reproducible with this exact command:**

```
git log --oneline origin/main..main
```

On 2026-09-12 this returned:

```
aa4dfefe Merge origin/main into main
bbf8e1a0 self-improvement: cycle 2026-09-11-210230 artifacts
34d19399 self-improvement: cycle 2026-09-10-210005 artifacts
```

Two orphan cycle-artifact commits sitting on local `main`, never in
`origin/main`, created by the timer while `main` was checked out on two
separate nights. Any branch cut from local `main` with `git branch <name>
main` (rather than from `origin/main`) silently inherits whatever local-only
commits are sitting there. When that branch is later opened as a PR against
`origin/main`, git's diff shows those inherited files as if the branch
author had changed them — usually appearing as a *revert* of whatever
origin/main had moved on to in the meantime, since the branch's copy is
older. That misleading diff is what showed up in both #109 and #110.

**Not fixed as part of this record** — this is shared automation
(`orchestrator.py` / `auto_remediation.py`), out of scope for the feature
work both PRs were doing, and deserves its own reviewed change rather than a
drive-by patch. Two directions worth considering when someone does pick it
up:

- Make `git_commit()` branch-aware: only commit when `main` is checked out,
  or `git push` immediately after every commit so `origin/main` never falls
  behind local `main`.
- Stop having the timer operate on the same working tree that engineers and
  agents interactively check branches out in at all — give it a dedicated
  worktree or clone it owns exclusively, so no shared HEAD state exists to
  collide with in the first place.

## Lesson

A scheduled job that commits to a shared, interactively-used working tree
without also pushing creates commits that are invisible to `origin` but
still fully "real" to any local branch built from that tree afterward. The
bug doesn't announce itself at commit time — `git status` after the timer
fires looks clean, because the commit succeeded. It only surfaces much
later, on a completely unrelated PR, as a confusing diff that looks like the
PR's author changed files they never touched.

## Future Guidance

Before cutting any new branch on a VM that also runs scheduled write-jobs
against the live working tree, run `git fetch origin` and branch from
`origin/main`, never from local `main` directly — local `main` can be
silently ahead of `origin/main` with commits a background job made and never
pushed. `git log --oneline origin/main..main` is the fast way to check
whether local main carries any such orphan commits before trusting it as a
base. If a PR's diff shows files nobody touched, especially files owned by
another automated process (self-improvement artifacts, generated reports,
timer output), suspect this pattern first rather than assuming a merge
mistake in the PR's own history — rebasing/cherry-picking the real commit(s)
onto a branch cut from `origin/main` is the fix, not manually reverting the
unrelated files forward.
