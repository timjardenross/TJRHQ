# Repository Governance Standard

Rewritten 2026-08-11 after a Chief Engineer review traced a live incident (33+3 files
committed to `main` with unresolved `<<<<<<< HEAD` conflict markers, breaking `tsc`/
`npm run build`) back to a structural gap: `main` had zero branch protection, and at
least one earlier incident (2026-07-30, parallel commit chains reconciled via
placeholder-message merges) shows the same failure mode recurring. The rules below
exist to close that gap, not as generic best-practice boilerplate.

## Branch protection on `main`

As of 2026-08-11, `main` requires:
- A pull request before merging (no direct push).
- The `check` status (`.github/workflows/lcars-portal-ci.yml`: typecheck + lint + test)
  to pass when it runs.
- No force-pushes, no branch deletion.

`enforce_admins` is deliberately `false` — the repo owner can still override via
GitHub's "merge without waiting for requirements" when the CI check's path filter
(`lcars-portal/**`) means it never triggers for a PR that only touches other parts of
the monorepo. This is a known gap in the current setup, not a design goal: if it
becomes a recurring annoyance, widen the workflow's trigger paths rather than
routinely reaching for the override.

## When a push is rejected

If `git push` fails because `main` has moved: **stop and look at what moved before
merging it in.** `git log HEAD..origin/main --oneline` first. Do not:
- Force-push over it.
- Merge and blindly resolve conflicts by picking one side without reading what the
  other side was actually trying to do (this repo's incident had a case where a
  script-based conflict resolution silently deleted an entire function body because it
  assumed every conflict block had non-empty content on both sides — verify with a
  diff against a known-good commit or a build/typecheck after any bulk resolution).
- Commit with literal conflict markers still in the file to "deal with it later." If a
  conflict can't be resolved with confidence in the moment, stop and surface it rather
  than landing broken code on a shared branch — that's the exact chain that produced
  this incident.

## Concurrent sessions on this repo

This repository is written to by more than one identity: interactive CLI sessions on
this VM, Anthropic's Cowork (a separate cloud product with its own local branch
state), a GitHub Actions bot, and the human owner directly. None of these currently
coordinate with each other in real time. With branch protection now requiring PRs,
this is structurally safer than a direct-push free-for-all, but it doesn't eliminate
concurrent-edit conflicts on the same PR/branch — the same "stop and look before
merging" discipline above still applies inside a PR, not just on `main` itself.

## Duplicate-surface / retirement policy

This platform went through a mid-2026 redesign that introduced a second page-shell
system (`WorkbenchShell`-based `*-workbench` routes, no LCARS app chrome) alongside
the original `(app)`-route-group pages. The migration was never finished for several
pages, leaving two live, independently-bug-fixed versions of the same feature
(`captains-chair` / `captains-chair-workbench`, `comms` / `content-workbench`) with
different nav files disagreeing about which one was canonical. Standing rule going
forward, per Captain direction 2026-08-11: **the `*-workbench` / `WorkbenchShell`
pattern is the current one.** A legacy `(app)`-group page that has a `*-workbench` (or
otherwise-canonical workbench) equivalent should be retired, not left running in
parallel indefinitely.

Retire, don't delete outright and don't leave silently broken:
1. **Parity-check first.** Confirm the surviving page is an actual superset — same
   data source, no feature/capability regression — before touching anything. If it
   isn't yet a superset, port the gap first or don't retire.
2. **Fix every live link** pointing at the page being retired (`grep` the route string
   across `lcars-portal/src/`) to point at the survivor, including nav files, hub
   tiles, and any other page's internal cross-links — not just the retired page
   itself.
3. **Replace the retired page's content** with a short "this page moved" notice
   linking to the survivor, rather than deleting the route or leaving old code live.
   An old bookmark or cross-link should land on an honest notice, not a 404 or stale
   functionality. See `lcars-portal/src/app/home/page.tsx`,
   `(app)/captains-brief/page.tsx`, and `(app)/comms/page.tsx` for the pattern.

**Not every `*-workbench`-adjacent page still linked from a hub should be assumed
dead.** `lcars-portal/src/lib/workbenches.ts`'s `LIVE_WORKBENCHES` registry only lists
what has a hub tile — several routes were deliberately delisted from the hub grid
while staying fully live and load-bearing (e.g. `comms-workbench`'s API routes remain
Content Workbench's only path from `approved` to `published`; `capture-workbench` and
`mission-workbench` were delisted "per direction" with an explicit note that neither
underlying feature was touched). Check the actual commit history for *why* a page was
delisted before treating "not in the registry" as "safe to remove" — those are
different things.

## Standards (unchanged from the original short version)

- Clear folder structure.
- Source of truth defined per domain — don't let two files independently claim to be
  canonical for the same thing (see the nav-vs-registry disagreement above for what
  happens when this slips).
- No duplicate documents.
- Consistent naming.
- Git hygiene: meaningful commit messages (a placeholder like `"1"` or `"11"` is a
  signal something was rushed past review, not a style choice), no accidental
  whole-directory imports (this repo's history has one merge that added 2,358 files
  in a single commit, including a stray macOS app bundle — still on `main`, not yet
  cleaned up).
