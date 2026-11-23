# Agent Notes

Solo, at-home project — not a production team system. Keep process light: no mission briefs,
approval gates or knowledge-records unless the Captain asks for one. Prefer a small change, a
quick check, and a commit over ceremony.

## Skills in `.claude/skills/`

- **`chief-engineer/`**, **`xo/`** — optional personas for architecture / capacity questions.
  Use only when asked.
- **`design-audit/`** — read-only UI audit against AI-slop patterns.
- **`resilience-crosswalk/`** — Operational Resilience Advisor crosswalk mode.
- **`bot-reviews/`** — kept only because code comments cite `bot-reviews/fixes-2026-08-09/`
  for design rationale. Reference material, not a process to follow.

Older persona workspaces, workbench reviews and the chief-of-staff / number-one skills were removed
in the 2026-11 process peel-back; see git history before that commit if you need them.

## Working in this repo

- Keep changes scoped to what was asked. PRs are for risky changes (secrets, privacy boundaries,
  deploy path); small docs/script/UI fixes can go straight to the working branch.
- CI is deliberately minimal: ruff, gitleaks, pytest on changed paths, and three small repo
  gates. Don't add new CI jobs, scanners or schedulers without asking.
- ADRs (when a decision really needs one): `core/governance/architecture-decision-records/TEMPLATE-madr.md`.
- Before adding to a registry (intelligence `SOURCES`, ADR numbers, specialist roster in
  `platform-runtime/prompt_loader.py`), grep for the name first.

### Supabase tool permissions

`.claude/settings.json` wires a `PreToolUse` hook (`.claude/hooks/supabase_readonly_sql.py`) to
`mcp__Supabase__execute_sql`. It auto-approves only provably read-only queries; everything else
goes to the normal permission prompt. Keep reads and writes in separate calls, do not add a blanket
`mcp__Supabase__*` allow rule (`tests/test_supabase_readonly_hook.py` enforces this), and back up
rows before any data fix.
