# USS TJR HQ — Service & Bot Topology

Canonical, current description of what actually runs TJR HQ. Consolidates and
replaces `VM-STARTUP-PROCEDURE.md`, `deploy/README-xo-bot.md`,
`telegram-bots/DEPLOY.md`, and `lcars-portal/README.md`'s old architecture
section, all of which had drifted to describe a decommissioned Slack bot
and/or a pre-activation LCARS portal (see git history for what each said).

**Last verified:** 2026-09-26, via a live audit of the production host
(`systemctl`, `docker ps`, direct HTTP checks) — not from memory or an older doc.

## Production host

One VM, everything supervised by systemd + Infisical for secrets (via
`platform-runtime/run-with-infisical.sh`). No Slack, no pm2, no Coolify, no
Dashy, no "Control Engine" — all retired. `git tag -l 'archive/*'` has the
history if any of that needs to be reconstructed.

### Front door
- **Caddy** (`caddy.service`) owns ports 80/443 directly. Reverse-proxies
  everything below by path. See `/etc/caddy/Caddyfile` for the live routing
  table — that file is the source of truth for exact paths, not this doc.

### Captain-facing surfaces
- **LCARS Portal** (`lcars-portal.service`, Next.js, `:3200`) — the primary
  command interface. Real Supabase-backed data, all API endpoints activated.
  Includes the Decisions Inbox, Captain's Chair, workbenches fleet.
- **Command Centre backend** (`command-centre.service`, Node/Express, `:5000`)
  — API gateway LCARS Portal and other consumers call.
- **Self-Improvement Dashboard** (`self-improvement-dashboard.service`, `:8892`)
  — review/approval UI for the HQ Evolution autonomous-improvement pipeline.

### Telegram bots (all systemd-managed, Telegram-polling — no inbound ports)
- **XO** (`tg-xo.service`) — the *only* bot with host/shell action capability.
  Captain-only allowlist, plan-then-approve gate on anything destructive.
- **REVS** (`tg-revs.service`) — public check-in bot, no action capability.
- **CapacityBot** (`tg-capacitybot.service`) — capacity check-ins
  (`capacity_checkins` table), no action capability.

None of these are Slack. Slack notification-sending and the Slack-only
Chief Engineer / Engineering Dept bots were fully retired — see
`xo-only-telegram-bot-policy` in the project's memory for the real scope of
that policy (action-capability, not "only bot that may exist").

### Intelligence / coordination
- **Command Bus** (`command-bus.service`) — coordination hub.
- **Context Assembly Service** (`context-service.service`, gunicorn, `:5001`)
  — Captain's Brief + recommendations HTTP bridge.
- **Model Router** (`model-router.service`, `:8891`) — shared LLM gateway,
  task-type routing across cloud + local models.
- **Ollama** (`ollama.service`, `:11434`) — local inference backing the router.
- **Officer Daily-Operations Cycle** (`daily-ops-cycle.service`+`.timer`,
  06:50 Australia/Sydney) — the executive-staff orchestrator (EXEC-001..010A).
- **Mission Minting Server** (`mint-server.service`, `:5052`).
- **Meilisearch** (`starship-meilisearch.service`, `:7700`) — unified search.
- **Chatterbox TTS** (`chatterbox-tts.service`, `:8893`).
- **Arize Phoenix** (`phoenix.service`, `:6006`/`:4317`) — LLM call tracing.

### Self-improvement / HQ Evolution
Runs from a dedicated git worktree at `/opt/starship-endeavour-self-improvement`
(branch `self-improvement`), not the main checkout — see
`agent-worktree-isolation-manual-fallback` in memory for why. Scheduled via
`self-improving-system.service`+`.timer`, state synced back via
`sync-self-improvement-state.service` on its own 3-min cycle.

### Monitoring
- **Uptime Kuma** (docker, fronted by Caddy at `/uptime/*`) — up/down probing.
- **changedetection.io** (docker, fronted by Caddy at `/changedetection/*`) —
  page-diff watching, feeds the intelligence watchlist pipeline.
- Both were exposed directly on raw ports until 2026-09-26 (fixed — see
  `deploy/docker-compose.watchlist.yml`).

### Secrets
**Infisical** (self-hosted, docker, `127.0.0.1:8446`) is the real secret
source for every service wrapped by `run-with-infisical.sh`. Plain `.env`
files are stale/inert for anything migrated onto that wrapper — check the
unit's own `ExecStart` before assuming a `.env` file is what a service
actually reads (a small number of older units, e.g. some `mission-*`
one-shots, still read a plain `.env` directly — verify per-unit, don't
assume).

## What this replaces

If you're looking at an older doc that mentions any of: a Slack bot, `pm2`,
Dashy, a "Control Engine" on port 8888, Coolify, LCARS Portal on port 3100
with placeholder/mock data, or `/recovery_pulse` — that doc is describing a
retired system. This file is the one kept current going forward.
