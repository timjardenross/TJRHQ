# TJRHQ orientation (Graphify-assisted) and local build notes

Written 2026-11-19. Built from a local Graphify v0.9.112 merged graph of this repo at commit
`128e67e` plus direct reading of source. Evidence is labelled **Graph** (from the Graphify
output), **Source** (read in the file), or **Inference** (not verified).

This complements `graphify-maintenance.md`, which still describes the older USSTJROS-era
layout. The commands in the second half were run on the VM and worked as written.

## 1. What this repo is

**Source** (`README.md`): TJRHQ is the operational workbench and evidence-control system for the
TJR ecosystem. Runtime code, Telegram/Slack bots, cron jobs, systemd services, AI pipelines,
migrations and deploy scripts live here. Main components named in the README:
`platform-runtime/` (Commander runtime, "Number One"), `lcars-portal/` (Next.js command
dashboard), `telegram-bots/`, `core/`, `intelligence/`, `specialists/`, `deploy/`.

## 2. One real entry point: the XO Telegram bot

- **Source:** a systemd unit under `deploy/` runs `python -m telegram_bots.xo.app`
  (`telegram_bots` is a symlink to `telegram-bots/`).
- **Graph + Source (agree):** `main()` at `telegram-bots/xo/app.py` L2351 registers an auth gate
  (`_global_auth_gate`, group -1), command handlers (`cmd_brief` L2371, `cmd_signals` L2363, ...)
  and callback handlers (`handle_mission_approval_callback` L2381, ...). Graph id:
  `telegram-bots::xo_app_main`, 30 `indirect_call` edges, all `INFERRED 0.85`.

Other `main()` entry points in the graph include `telegram-bots/capacitybot/app.py`,
`telegram-bots/resiliencebot/app.py`, `core/infrastructure/vm-processing/worker.py`,
`core/capture/enrichment_worker.py`, `core/content/draft_worker.py`,
`core/context-assembly/context_service.py`, `scripts/daily_ops/run_daily_ops_cycle.py`.

## 3. Flow traced: mission-approval button

1. **Source (comments only):** `core/platform/approval_router.py` documents the flow as
   `send_approval_notification()` -> XO bot callback -> `mark_event_status()`, with `event_id`
   embedded in `callback_data`. The body of `send_approval_notification` was not read.
2. **Source:** button data format is `ms|action|mission_id[|event_id]`
   (`telegram-bots/xo/app.py` L2225-2256).
3. **Graph + Source:** `main()` registers `handle_mission_approval_callback`
   (`xo/app.py` L2225, graph id `telegram-bots::xo_app_handle_mission_approval_callback`).
4. **Source:** the handler checks the chat allowlist (`_chat_is_allowed`), edits the Telegram
   message, then calls `core.platform.event_bus.mark_event_status(event_id, "acknowledged" |
   "dismissed")`. Failures are logged and swallowed.
5. **Graph + Source:** `mark_event_status` (`core/platform/event_bus.py` L227) validates the
   status and id, then updates `core_events.status` in Supabase through
   `CommanderSupabaseClient` and records a bus heartbeat.

In this path "approval" means acknowledging or dismissing a notification. The handler does not
change the mission itself (**Source**).

## 4. Known limits of the graph

- **Lazy and aliased imports produce no call edges.** The handler's calls to `mark_event_status`
  are function-local imports; the graph shows no edge from it and reports one caller
  (`interrupt_dispatcher.py` L143) where the source has at least two call sites. The Supabase
  write inside `mark_event_status` is also a lazy import and has no edge. `_chat_is_allowed`
  (an `import ... as` alias) has none either. For callers and side effects, grep as well.
- **`query` is keyword-seeded.** "Which depends on X" returns loose name matches (including
  tests and stdlib nodes). It is good for locating names; use `explain` for real edges.
- **Tests are not modelled.** Files like `*.test.ts(x)` yield no symbols, so test linkage
  questions will not work for `lcars-portal`.
- **Parse error:** `lcars-portal/src/app/(app)/delivery/page.tsx` L22 reported a syntax error
  (1 symbol extracted). Not yet checked whether this is a parser limit or a real defect.

## 5. Building the local graph (VM, verified)

Size measured 2026-11-19: **18,430 nodes, 41,231 edges** across 26 graphs (20 MB merged),
under the hosted free plan's 25,000-node limit before adding `tests/`.

```bash
# from a dedicated worktree, never the shared checkout (see AGENTS.md)
export GRAPHIFY_BACKEND=none      # avoids naming communities via the `claude` CLI

for d in core/advisory core/capture core/content core/context-assembly core/coordination \
         core/engineering core/exec-assistant core/governance core/health core/inbox \
         core/infrastructure core/intelligence core/knowledge core/knowledge_navigation \
         core/platform core/quality core/security core/voice \
         platform-runtime/lib platform-runtime/commands telegram-bots lcars-portal/src \
         intelligence tools services scripts; do
  nice graphify "./$d" --code-only
done

# persist outside the worktree, then merge
mkdir -p /var/lib/graphify/tjrhq
find . -path '*/graphify-out/graph.json' -not -path './.git/*' | cpio -pdm /var/lib/graphify/tjrhq/
cd /var/lib/graphify/tjrhq && mkdir -p graphify-out
graphify merge-graphs $(find . -path '*/graphify-out/graph.json' -not -path './graphify-out/*' | sort) \
  --out graphify-out/merged-graph.json
```

Notes:
- `--code-only` is required for folders containing docs or fonts, otherwise Graphify demands an
  LLM API key.
- Query examples: `graphify explain "telegram-bots::xo_app_main" --graph $GRAPH --all` and
  `graphify explain "xo/app.py::handle_mission_approval_callback()" --graph $GRAPH --all`
  (use `path::symbol` or the full node id; a bare `main` is ambiguous across 141 nodes).
- `graphify claude install` edits `AGENTS.md` and `.claude/settings.json` (adds search/read
  hooks and a rebuild-after-change hook). Do not commit those edits, and do not run it in the
  shared `/opt/starship-endeavour` checkout.
- `graphify-out/` is gitignored; generated graphs are not committed. Rebuild when needed.

## 6. Evidence missing

- No hosted-Graphify verification: the starter task failed with "no indexed graph yet".
- `tests/` and loose `.py` files at the `platform-runtime/` root are not in the local graph.
- The doc's flow was traced for one callback only; other bots and the portal were not traced.
