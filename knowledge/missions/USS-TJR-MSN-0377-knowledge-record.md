# Knowledge Record — USS-TJR-MSN-0377: self-improvement cycle-artifact commit path

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0377 |
| Title | Self-improvement cycle-artifact commit path silently refusing since LL-149 |
| Date | 2026-09-13 |
| Status | **DONE** — root cause confirmed structurally, fixed at the deployment layer, alerting added |

## Pre-flight was right: the fix, not the mechanism, was broken

LL-149 (2026-09-12) fixed `AutoRemediationExecutor.git_commit()` to fail closed
on a branch mismatch and push on success — a real, correct fix for LL-146's
diagnosed bug (commits landing silently on whatever branch happened to be
checked out, never reaching origin). But `git log --all --grep="self-improvement:
cycle"` shows the last real cycle-artifact commit landed **2026-09-12** (cycle
`2026-09-11-210230`, the same day LL-149 shipped) — zero cycle commits in the
~24h+ since. ~64 cycles of `data/self-improvement/runs/*/evidence.json` piled
up uncommitted until a human noticed by hand and committed them manually
(separate commit on this branch, `chore(self-improvement): commit durable
evolution-engine run evidence`).

## Root cause: which timer, which branch

Two separate systemd units run two separate scripts here, easy to conflate:

- `hq-evolution.timer` (03:00 daily) → `evolution_orchestrator.py` — the newer
  HQ Evolution pipeline. Its own service file states explicitly: "Never
  applies a remediation, never creates a Mission, never touches git." Not
  the culprit.
- `self-improving-system.timer` (04:30 daily) → `orchestrator.py` →
  `SelfImprovementOrchestrator.run_full_cycle()` → `AutoRemediationExecutor.
  git_commit()`. **This** is the one LL-149 fixed, and the one that's been
  silently refusing.

`AutoRemediationExecutor.__init__` hardcodes `self.expected_branch =
"self-improvement"` by design — the class docstring explains why: cycle
artifacts and auto-remediation commits are meant to land on a dedicated
branch, isolated from human-authored `main`, for periodic human
review/fast-forward. That's a reasonable design. The bug: `self-improving-
system.service`'s `WorkingDirectory` was `/opt/starship-endeavour` — the
**same shared checkout** every interactive Claude session on this host also
uses for its own feature-branch work (confirmed live: this session's own
checkout was on `msn-0368-stage-2b-existing-capability-fixes` while
investigating). Per existing memory (`git-shared-worktree-collision-2026-08-12`,
`hq-evolution-timer-commits-to-whatever-branch-is-checked-out`), that shared
checkout is routinely left on whatever branch a human/session was last
using — essentially never `self-improvement` at 04:30. LL-149's fail-closed
check was correct in isolation; the deployment never guaranteed its
precondition. Post-fix, "correct" and "never fires" turned out to be the
same outcome.

**Ground truth caveat:** no SSH/journalctl access from this sandbox (same
limitation as MSN-0374/0375's Stream 0) — this finding rests on git-history
timestamps (`git log --all --grep`) and reading the fail-closed logic
directly, not a live `journalctl` confirmation of the exact refusal message
firing on the real VM. The git-history evidence is strong and unambiguous
(a hard stop in commit cadence exactly at LL-149's ship date, no drift),
but it is inference from artifacts, not a live log line witnessed directly.

## Fix: dedicated worktree, not a weaker check

The mismatch was fixed at the deployment layer, not by loosening LL-149's
check (which stays intact and correct):

- New `scripts/self_improvement/run_daily_cycle.sh`: ensures a dedicated git
  worktree at `/opt/starship-endeavour-self-improvement`, permanently
  checked out on `self-improvement` (created via `git worktree add` on
  first run, idempotent after). Fast-forwards from `origin/main` first (best
  effort — a failed fetch/merge logs a warning and does not block the
  cycle) so evidence collection still reflects live code, then execs
  `orchestrator.py --repo-root <worktree> --data-root <worktree>/data/
  self-improvement`, reusing the main checkout's existing venv (Python venvs
  don't care what directory the script being run lives in).
- `deploy/self-improving-system.service`'s `ExecStart` now points at this
  wrapper instead of calling `orchestrator.py` directly.
- Net effect: `git_commit()`'s branch check now passes **by construction**
  every day, because nothing but this service ever touches that worktree —
  not by trusting that whatever's checked out on the shared repo happens to
  be right.

**Known follow-on inconsistency, flagged not fixed here:** the manual
catch-up commit for the ~64-cycle backlog landed on
`msn-0368-stage-2b-existing-capability-fixes` (this session's own working
branch), not on `self-improvement` — it was a one-off recovery of data that
existed nowhere else, done before this mission's root-cause fix was in
place. Going forward, all new cycle-artifact commits land on
`self-improvement` via the dedicated worktree, per original design. A human
should decide whether/how to reconcile the one-off backlog commit into
`self-improvement`'s own history (the run directories are uniquely
timestamped, so there's no real merge conflict risk — just duplicate
history across two branches until someone merges).

## Alerting

`orchestrator.py`'s `run_full_cycle()` already logged
`"Cycle artifacts commit failed or had nothing to commit"` on a `None`
return from `git_commit()` — a log line nobody was reading, which is
exactly how ~64 refusals went unnoticed. Now also calls
`core/platform/notification_service.py`'s `notify()` (`Severity.WARNING`,
`template="alert"`) with the current branch and expected branch in the
message body, routed through the existing Telegram transport — no new
notification mechanism, per this pipeline's own existing convention
(`auto_remediation.py`'s cycle-summary notify already uses the same
service).

## Verification: what was actually checked, and what wasn't

- **Verified for real:** `orchestrator.py` and the new
  `run_daily_cycle.sh` both pass a Python syntax check
  (`ast.parse`/`bash -n`); the new/modified files are internally consistent
  with the existing `AutoRemediationExecutor`/`SelfImprovementOrchestrator`
  APIs (`--repo-root`, `--data-root` were already real CLI flags on
  `orchestrator.py`, not invented for this fix).
- **Not run end-to-end:** a full live cycle was not triggered from this
  sandbox — `run_full_cycle()` makes real Model Router LLM calls
  (`router_client.py`) as part of evidence analysis, which this mission's
  scope (commit-path and alerting only) does not license spending on/side-
  -effecting for a verification pass. The dedicated worktree's creation
  (`git worktree add`) and the wrapper's fetch/merge/exec sequence were
  **not executed against the real repo from this session** for the same
  reason a full cycle wasn't: doing so here would create the worktree
  against this sandbox's own checkout state, not the production VM's,
  which is a materially different action than what the real systemd timer
  will do on next fire. **This is the honest gap**: the fix is code-complete
  and internally consistent, but the actual "a real `hq-evolution.timer`
  run after the fix produces an actual pushed cycle-artifact commit"
  acceptance bar from the mission brief requires the real VM's next 04:30
  fire (or a deliberate manual dry run on that host) — not yet observed.
  Flagging this plainly rather than asserting a live-fire verification that
  didn't happen.

## Registry

`SUOC-Platform-Registry.md`'s Notification capability: added this mission's
new consumer (the commit-failure alert) and flagged, under Technical Debt,
that no capability currently owns self-improvement's own operational health
(heartbeat staleness, cycle-commit success) — consistent with the
already-tracked "wire the remaining 23 silent `domain_heartbeats` domains"
backlog item. Did not invent a new capability entry for this; the gap is
real but this mission's fix (one point notification) doesn't close it, so
claiming ownership would overstate what was actually done.

## Scope discipline

Did not touch `.secrets.baseline`/detect-secrets exclusions (separate
MSN-0376). Did not touch classification/remediation/decision logic in
`auto_remediation.py`, `decision_processor.py`, `policy.py`, or any
`Strategy` class — only the commit-path deployment wiring and one
notification call were changed.
