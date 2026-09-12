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

## Working in this repo

- Prefer the existing skill for a task over writing new persona/process instructions from
  scratch — see if `chief-engineer`, `xo`, or `design-audit` already covers what's being
  asked.
- Keep pull requests scoped to what was asked; this repo's PR template
  (`.github/pull_request_template.md`) has the expected shape (summary, test plan, scope,
  breaking changes).
- When in doubt about platform-wide conventions or existing capabilities, check
  `knowledge/` and any registry/CMDB-style docs before adding something new — see the
  Chief Engineer skill for why.
