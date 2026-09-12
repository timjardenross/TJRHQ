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
