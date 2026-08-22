---
name: design-audit
description: Read-only UI audit that scores existing frontend code against a named list of AI-generated-slop patterns (generic layouts, contrast failures, token improvisation, mobile breakage) and returns a severity-ranked punch list. Use when reviewing LCARS Portal / workbench pages or components for design-quality drift, not when building new UI from scratch. Does not edit files.
---

# Design Audit

Ported from [obra/Nutlope's hallmark](https://github.com/Nutlope/hallmark) `audit` verb, trimmed to the gates that apply to an existing, live internal app (LCARS Portal / workbench UIs) instead of hallmark's own greenfield macrostructure/theme-catalog machinery. This skill only reads and scores — it never edits or redesigns. For net-new UI, use `frontend-design` instead.

## When to use

- User asks to audit, review, or score existing UI/CSS/component code for design quality, consistency, or "does this look AI-generated."
- Before/after a workbench build to catch drift (WCAG contrast regressions, mixed nav patterns, invented copy).
- NOT for building new pages — that's `frontend-design`'s job, and this skill has no theme catalog or macrostructure picker to hand off to.

## Procedure

1. **Scope check.** Confirm the target: file path(s), directory, or a whole workbench route. If unscoped ("audit the portal"), ask which pages/components, or default to the most recently changed files (`git diff --stat` against main).
2. **Read the target.** Do not edit. Read every file in scope fully — no excerpts, since several gates (token discipline, contrast pairs) require seeing the full `:root`/token block against every usage site.
3. **Score against the gate list** in [`references/slop-test.md`](references/slop-test.md) and the named tells in [`references/anti-patterns.md`](references/anti-patterns.md). Every gate answer must be "no" to pass.
4. **Report.** For each finding:
   - **Tell** — the named anti-pattern (cite the gate number or anti-pattern name).
   - **Where** — file path and line range.
   - **Severity** — `critical` (ships as slop / real defect — e.g. contrast failure, invented metric), `major` (looks AI-generated / inconsistent with rest of app), `minor` (small taste issue).
   - **Fix** — one-line concrete correction.

   Group by severity. End with a count: `N critical · M major · K minor` and a verdict line: `ships as slop | reads as AI-generated | close, fix the minors | clean`.

5. **Cross-reference known backlog.** Before finalizing, check whether findings overlap prior tracked issues (WCAG contrast gaps, mixed severity vocabularies, unreachable-nav items) — note the overlap explicitly rather than re-filing a duplicate.

## What this skill does NOT do

- Does not pick a macrostructure, theme, or run diversification/rotation logic — that machinery only makes sense for hallmark's own greenfield generation flow and has no equivalent concept in an existing, already-shipped app.
- Does not fix findings. Report only. If the user wants fixes applied, hand the punch list to a build/edit pass (or `code-review --fix` / a builder agent) as a separate step.
- Does not fabricate contrast numbers — compute or estimate OKLCH/hex lightness deltas from the actual values in the file; if a value can't be resolved statically (runtime-computed theme, CSS-in-JS with dynamic props), say so instead of guessing.
