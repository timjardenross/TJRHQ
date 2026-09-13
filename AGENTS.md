# Agent Notes

This repo is developed with the help of AI coding agents (Claude Code and others). If you're
an agent working in here, the main thing to know is that most of the standing process,
persona, and review guidance already lives under `.claude/skills/` rather than in this file —
check there before improvising your own conventions.

This file is intentionally a short pointer, not a full contributor guide.

## What's in `.claude/skills/`

- **`chief-engineer/`** — the Chief Engineer persona: architecture reviews, technical debt
  assessment, security oversight, repo governance, and platform capability planning for the
  USS TJR platform.
- **`xo/`** — the Executive Officer (XO) persona: a recovery-first capacity gatekeeper and
  mission-governance reviewer, used both for day-to-day capacity questions and for
  structured gatekeeper passes on other specialists' recommendations.
- **`design-audit/`** — a read-only UI audit skill that scores existing frontend code against
  a named list of AI-generated-slop patterns (generic layouts, contrast failures, token
  improvisation, mobile breakage) and returns a severity-ranked punch list. It doesn't edit
  files or design new UI.
- **`chief-engineer-workspace/`** and **`xo-workspace/`** — eval and benchmark iterations for
  the `chief-engineer` and `xo` skills (benchmark configs, scoring, and sample review
  transcripts used to tune those personas over time).
- **`bot-reviews/`** and **`workbench-reviews/`** — archived Chief Engineer / XO review
  write-ups produced against specific bots and workbenches, kept as a historical record of
  past findings and decisions.

## Writing a new decision record (ADR)

If you're about to write up an architectural decision, start from the MADR
template at `docs/decisions/TEMPLATE-madr.md` (Markdown Architectural
Decision Records format, adopted format-only under USS-TJR-MSN-0366 Stream
10 — no new tool or dependency, just a target shape) instead of inventing
a one-off structure. See
`docs/decisions/EXAMPLE-ADR-001-model-router-cloud-escalation-degrade-chain.md`
for a filled-out real example, and `platform-runtime/adr_conflict_detector.py`
for the (currently separate) tool that scans an older, plainer ADR shape
elsewhere in the repo — consolidating the two is scoped to a later
ADR-consolidation mission, not something to improvise now.

## Working in this repo

- Prefer the existing skill for a task over writing new persona/process instructions from
  scratch — see if `chief-engineer`, `xo`, or `design-audit` already covers what's being
  asked.
- Keep pull requests scoped to what was asked; this repo's PR template
  (`.github/pull_request_template.md`) has the expected shape (summary, test plan, scope,
  breaking changes).
- Starting a new mission brief? Start from `knowledge/MISSION-BRIEF-TEMPLATE.md` rather than
  inventing a structure — its Pre-flight section is the enforcement point for the
  "check first" rule below (USS-TJR-MSN-0372).

### Check-first registries

The same failure mode has hit this repo twice for real: a mission adds a row to an
existing list without checking whether it's already there (`SOURCES` duplicate rows that
took down a 163-row upsert batch; up to 4 separate ADR registries before consolidation).
Before adding to any of these, grep the exact name/key first — "check `knowledge/` and be
careful" isn't enough, run the actual grep:

- **Intelligence sources** — `tools/intelligence/seed_source_registry.py` (`SOURCES` list).
  Check `source_name`/`url` before adding; the file already dedupes+warns on a collision,
  but that's a safety net, not a substitute for checking first.
- **ADR citations** — `core/governance/architecture-decision-records/` is the canonical
  filed-ADR directory. Check the number isn't already filed or reserved before citing or
  writing a new one. (`docs/decisions/` holds the MADR *template* and worked example, not
  the filed registry itself — don't confuse the two.)
- **Scheduled jobs (APScheduler)** — consolidation is in progress (USS-TJR-MSN-0368 Stream
  6); real count as of that stream is 2 live instances (`intelligence/scheduler.py`,
  `telegram-bots/revs/scheduler.py`). Ask before adding a new scheduler instance rather than
  assuming one doesn't already cover your use case.
- **Specialist registry** — `platform-runtime/prompt_loader.py`'s `SPECIALISTS` dict and
  `specialists/SPECIALIST-INVENTORY.md` (narrative, not code-loaded) both describe the same
  specialist roster from two angles; check both before adding a specialist so the two don't
  drift apart.

This list will go stale as registries get added or consolidated — that's expected and fine;
update it when the next instance of this pattern turns up rather than treating it as final.

### Concurrent session git safety

Many interactive sessions and scheduled services can share one checkout at
`/opt/starship-endeavour` at once (observed live: 74 concurrent peer sessions,
USS-TJR-MSN-0382). This has already caused real commit corruption once —
diagnosed in `LL-146`, fixed for one caller in `LL-149`, and given a dedicated
fix in `USS-TJR-MSN-0377` (`self-improving-system.service`'s own worktree).
Generalized rule for any session or service doing real git work here:

1. **Never `git checkout`/`switch` on the shared interactive checkout** if
   you're about to do real work — create an isolated worktree first:
   `git worktree add <path> -b <branch>`.
2. **Path and branch names must include a unique identifier** (session ID or
   mission ID) — a generic worktree/branch name just relocates the collision,
   it doesn't remove it.
3. **Prune after merge.** Run `git worktree list` / `git worktree prune` once
   a worktree's branch is merged — undocumented accumulation is exactly how
   74 concurrent sessions turns into 740 stale worktrees.
4. **The shared checkout is reference-only for interactive sessions.** Treat
   it as read space. Anything that must run from a canonical, always-current
   location (systemd services) gets its own dedicated worktree, per
   `USS-TJR-MSN-0377`'s precedent — not a claim on the shared checkout.

Enforcement tooling (a pre-flight check, a lint rule) is a legitimate future
follow-up; this section documents the convention only.
