# Knowledge Record — USS-TJR-MSN-0382: Concurrent Session Git Safety convention

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0382 |
| Priority | P2 |
| Date | 2026-09-13 |
| Status | **DONE** — convention documented, no code/enforcement changes |

## What triggered this

Live observation this session: 74 concurrent peer sessions on the one shared
`/opt/starship-endeavour` checkout. One peer session hit shared-checkout
contention and self-corrected to an isolated worktree "per past lesson" — but
no such lesson existed as a general, citable convention. `AGENTS.md` had
nothing under `worktree`/`concurrent session`/`shared checkout` (confirmed via
grep before starting).

## Precedent generalized, not reinvented

- `LL-146` (2026-09-12) diagnosed the failure mode: a scheduled process
  sharing a working tree with interactive use lands orphan commits on
  whatever branch happens to be checked out.
- `LL-149` (2026-09-12) fixed the one caller it covered
  (`AutoRemediationExecutor.git_commit()`): fail closed on branch mismatch,
  push on success.
- `USS-TJR-MSN-0377` (2026-09-13) found LL-149's fix silently never fired in
  practice, because `self-improving-system.service`'s `WorkingDirectory` was
  the same shared checkout every interactive session also uses — the fix's
  precondition (being on the right branch) was never guaranteed by the
  deployment. Real fix: give the service its own dedicated worktree.

That chain fixed one service. This mission writes the same pattern as a
standing rule for *any* session or service, in `AGENTS.md` (where other
sessions actually read it), rather than restating the diagnosis.

## Change made

Added a "Concurrent Session Git Safety" section to `AGENTS.md`, under
"Working in this repo" / after "Check-first registries" (same shape: short,
citing precedent, four concrete rules):

1. Never `checkout`/`switch` on the shared interactive checkout for real
   work — create an isolated worktree first.
2. Worktree path and branch names must carry a unique identifier (session or
   mission ID) — a generic name just relocates the collision.
3. Prune worktrees after merge (`git worktree list` / `git worktree prune`) —
   undocumented accumulation is how 74 sessions becomes 740 stale worktrees.
4. The shared checkout is reference-only for interactive sessions; anything
   needing a canonical always-current location (systemd services) gets its
   own dedicated worktree, per `USS-TJR-MSN-0377`'s precedent.

## Explicitly not done (by design, per mission brief)

- No rewrite of `USS-TJR-MSN-0377`'s existing worktree fix — it's done.
- No enforcement tooling (pre-flight check, lint rule). Flagged in the
  `AGENTS.md` section itself as a legitimate future follow-up, not bundled
  here.

## Meta note: dogfooded the rule while writing it

While applying this mission's own edit, found the shared checkout dirty and
checked out to an unrelated stale branch (`msn-0368-stage-2b-...`) with
~60 untracked `data/self-improvement/runs/*` dirs and a modified CI workflow
belonging to other concurrent sessions — live confirmation of the exact
collision risk this mission documents. Followed the new rule instead of
committing there: created an isolated worktree
(`/tmp/wt-msn-0382`, branch `msn-0382-concurrent-session-git-safety`) off
`origin/main`, made the edit there, and left the shared checkout untouched.
