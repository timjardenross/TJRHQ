# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0382
- **Priority:** P2 — real, observed collision risk (74 concurrent peer sessions on one shared checkout), not hypothetical
- **Source:** live observation (this session, 2026-09-13) — a concurrent session hit shared-checkout contention and self-corrected to an isolated worktree "per past lesson." No general convention exists to generalize that.

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -n "worktree|concurrent session|shared checkout" AGENTS.md
   → no matches. No documented convention for concurrent-session git safety exists.
   ```

2. **Real precedent already in this repo, generalize it rather than reinvent it:**
   `LL-146`/`LL-149` (2026-09-12) diagnosed and fixed this exact failure mode for one specific
   caller (`hq-evolution.timer`'s cycle-artifact commit): a scheduled process sharing a working
   tree with interactive use produced orphan commits on whatever branch happened to be checked
   out. `MSN-0377` then gave `self-improving-system.service` its own dedicated worktree as the
   fix. The pattern is proven; it has never been written as a standing rule for *sessions*
   generally, only applied once to one *service*.

3. **Explicitly not in scope:**
   - Rewriting any individual session/service's existing worktree fix (MSN-0377's is done).
   - Building tooling/automation to enforce this — this mission documents the convention;
     enforcement (a pre-flight check, a lint rule) is a legitimate future follow-up, not bundled here.

## Scope

Add a short, generalized "Concurrent Session Git Safety" section to `AGENTS.md` (or the
nearest equivalent cross-session convention doc) covering:
1. **Never `git checkout`/`switch` on the shared interactive checkout** if doing real work —
   create an isolated worktree first (`git worktree add <path> -b <branch>`).
2. **Path and branch names must include a unique identifier** (session ID or mission ID) —
   a generic worktree/branch name just relocates the collision, it doesn't remove it.
3. **Prune after merge.** `git worktree list` / `git worktree prune` once a worktree's branch
   is merged — undocumented accumulation is exactly how 74 sessions turns into 740 stale
   worktrees.
4. **The shared checkout itself is reference-only for interactive sessions** — treat it as
   read space; anything that must run from a canonical, always-current location (systemd
   services) gets its own dedicated worktree, per `MSN-0377`'s precedent, not a claim on the
   shared one.

## Acceptance

- The convention is written once, in the place other sessions actually read (`AGENTS.md`),
  citing `LL-146`/`LL-149`/`MSN-0377` as the precedent rather than restating the diagnosis
  from scratch.
- Concrete enough that a new session can follow it without re-deriving the reasoning —
  the four points above, not an essay.

## Reporting

A short knowledge record (`knowledge/missions/USS-TJR-MSN-0382-knowledge-record.md`) noting
the `AGENTS.md` diff and citing the precedent chain.
