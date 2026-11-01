# Knowledge Record — SD-FND-003 / USS-TJR-MSN-1788922470456

| Field | Value |
|---|---|
| Mission ID | SD-FND-003, USS-TJR-MSN-1788922470456 |
| Title | A system that writes to its own working tree outside of commits will eventually block its own deploy pipeline |
| Date | 2026-09-10 |
| Lesson | LL-142 |

## Outcome

`data/self-improvement/review/decisions.jsonl`, `opportunities.jsonl`, and `.evolution_cycle.lock` were tracked in git but rewritten live by the self-improvement engine outside of any deliberate commit, repeatedly dirtying the VM's working tree and tripping `deploy/auto-deploy.sh`'s dirty-tree safety check — confirmed blocking `auto-deploy.timer` for over an hour on 2026-09-09. Three separate records converged on the same fix: self-improvement's own `governance_violation` finding (SD-FND-003), a duplicate auto-dispatched mission handoff (USS-TJR-MSN-1788922470456, dispatched twice 15 minutes apart), and an independently-authored PR (#99) that actually shipped it — `git rm --cached` on the three files plus `.gitignore` entries. PR #100 landed the same day as a complementary hardening of `auto-deploy.sh` itself so untracked files can't block a pull either way.

## Lesson

None of the three auto-generated handoffs for this finding (SD-FND-003 and its two MSN-1788922470456 duplicates) resulted in a batch-coded PR being opened — all three logged "no PR opened (GitHub not configured or no new files to add)". The fix that actually landed was authored independently, outside the auto-dispatch pipeline, days after the findings were first raised. The auto-dispatch path silently produced nothing actionable three times over for the same real, conclusive-evidence finding, and nothing surfaced that failure loudly enough to prompt a human or a differently-routed fix sooner.

## Future Guidance

A live-mutated state file living inside a git-tracked directory is a recurring category, not a one-off: any new per-cycle counter, lock, or live-decision file a background process writes should be `.gitignore`d at the moment it's introduced, not discovered after it blocks a deploy. Separately, when an auto-dispatch handoff's batch result says "no PR opened," that is itself a signal worth escalating (or re-attempting via a different path) rather than leaving the handoff sitting at `DELIVERED` indefinitely — three consecutive dispatches producing no PR for the same finding should have triggered a fallback, not a fourth identical dispatch.
