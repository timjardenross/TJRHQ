# Activating the read-only Supabase connector (`supabase_ro`)

The repo ships the standing allow rule and the scope guard (`.claude/settings.json`, `.claude/hooks/supabase_ro_scope.*`). They apply to a server
named exactly `supabase_ro` (tool names `mcp__supabase_ro__execute_sql` and `mcp__supabase_ro__list_tables`). The server itself is registered per
user, because `.mcp.json` is gitignored and the Supabase server needs an OAuth login. The definition is `.claude/mcp/supabase_ro.mcp.json`.

URL (read-only, this project only, database and docs tools only):
`https://mcp.supabase.com/mcp?project_ref=cjvrpjwewsrumnbdydgg&read_only=true&features=database,docs`

## Local Claude Code (your own machine)
Run in a terminal, in the repository directory (so the project hooks and settings are loaded):

    claude mcp add --transport http supabase_ro "https://mcp.supabase.com/mcp?project_ref=cjvrpjwewsrumnbdydgg&read_only=true&features=database,docs"

Then start Claude Code in that directory, run `/mcp`, choose `supabase_ro` and complete the Supabase login (pick the organisation that owns the
project). Restart the session so the tools and the project settings are loaded.

## Claude on the web / cloud sessions (claude.ai/code)
Cloud sessions load their MCP servers from your account connectors when the session starts, so a server cannot be added to a running session.
In claude.ai: Settings, Connectors, Add custom connector. Name it exactly `supabase_ro`, paste the URL above, and authenticate with Supabase. Then
start a NEW session on this repository (settings and hooks come from the repository checkout, so merge to the default branch first).

## Check it worked (first message in the new session)
1. `/mcp` (or the tool list) shows tools named `mcp__supabase_ro__execute_sql` and `mcp__supabase_ro__list_tables`. If the names differ, the allow
   rule and the scope guard do not apply: tell the agent, who will adjust `.claude/settings.json`.
2. Run three queries with no approval prompt: a CTE with a column list over `intelligence_events`; a latency query over
   `llm_call_metrics` (named columns); a scorecard-style join of `intelligence_events` and `intelligence_source_registry`.
3. Confirm refusals: `select * from health_daily_logs` is denied by the scope guard; `select * from captains_daily_briefs` is denied
   (list columns); an INSERT or DELETE fails at the database.

The privileged `mcp__Supabase__*` connector keeps its approval prompts and must not be used for reads.

## If the privileged connector is set to "Always Allow"
That setting approves every call to the tool by name, whatever the SQL says, and the connector connects as `postgres`. The repo hooks are the only
remaining control: `supabase_readonly_sql.py` answers "allow" for provably read-only SQL and an explicit "ask" for everything else, and
`supabase_privileged_guard.py` answers "ask" for every mutating tool (migrations, edge-function deploys and secrets, branches, project
pause/restore/create, notebooks, feedback). Whether a hook "ask" overrides Always Allow depends on the client, so verify it once in a new session
with this harmless probe on the privileged connector; it must prompt (decline it, or approve it: it writes nothing):

    begin; select 1 as probe; rollback;

If it does NOT prompt, set the connector's tools back to "Needs approval" (or block the mutating ones) in claude.ai connector settings and use
`supabase_ro` for reads.
