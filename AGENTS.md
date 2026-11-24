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

Two Supabase MCP servers, two trust models:

- **`mcp__supabase_ro__*` (read-only, standing approval).** `.claude/mcp/supabase_ro.mcp.json` defines `supabase_ro` with `read_only=true`, scoped to this
  project and to the `database,docs` tool groups (`.mcp.json` is gitignored: activate with
  `claude mcp add --transport http supabase_ro "<url in that file>"` or copy the entry into your own `.mcp.json`, then confirm the tool
  names are `mcp__supabase_ro__*`). The platform runs every query as `supabase_read_only_user`
  (`default_transaction_read_only=on`, no write privileges, cannot execute SECURITY DEFINER writers), so SQL text is irrelevant to write
  safety and is not parsed. `.claude/settings.json` allows only `execute_sql` and `list_tables` on that server. Use it for ALL research:
  SELECTs, CTEs (including column lists), aggregates, scorecards, metadata and `explain`. `.claude/hooks/supabase_ro_scope.py` (config:
  `supabase_ro_scope.json`) limits READS to an explicit list of intelligence relations (`permitted_relations`) and refuses everything else,
  credential/platform schemas, user-defined functions and SQL-executing builtins. That scope is application-level: the role can read every
  table and `postgres` cannot revoke that platform-granted membership. Verify the DB facts and scope drift with
  `tools/intelligence/ro_scope_verify.sql` (regenerate with `python tools/intelligence/ro_scope.py`); `tests/test_supabase_ro_access.py` proves
  the role cannot write (local Postgres).
- **Rule for every research agent and subagent:** use `mcp__supabase_ro__execute_sql` for every SELECT. Never use `mcp__Supabase__execute_sql`
  for reads: it prompts the Captain. If `supabase_ro` is not available in your session, do NOT fall back to the privileged connector; write the
  exact SELECT you need into your report and continue with other work. Activation steps: `docs/SUPABASE-READONLY-ACTIVATION.md`.
- **`mcp__Supabase__*` (write-capable, prompts).** `.claude/hooks/supabase_readonly_sql.py` still auto-approves a query only when it is
  provably read-only; every write, DDL, transaction and unknown function goes to the normal permission prompt, and `apply_migration` and
  every other tool on that server always prompt. Do not add a blanket `mcp__Supabase__*` allow rule
  (`tests/test_supabase_readonly_hook.py` enforces this) and do not keep widening the function allowlist: use the read-only server.
  Keep reads and writes in separate calls, and back up rows before any data fix.
