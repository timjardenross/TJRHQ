# VM Startup & Recovery Procedure
# USS-TJR-MSN-0181 — Established 2026-06-28, rewritten 2026-09-26

> **2026-09-26:** the original version of this file listed a Slack bot,
> pm2-managed Command Centre API, and a much smaller service list — all
> stale. Rewritten from a live audit of the production host
> (`systemctl list-units`, `docker ps`), not from memory. See
> `USS-TJR-Control/README.md` for the narrative version of this same
> topology; this file is the operational runbook (verification commands,
> restart procedures).

## Boot recovery (automatic)

Every service below is systemd-managed and auto-starts on boot. No manual
intervention required.

| Service | Unit | Notes |
|---|---|---|
| Reverse proxy | `caddy.service` | Owns 80/443 directly |
| LCARS Portal | `lcars-portal.service` | `:3200` |
| Command Centre API | `command-centre.service` | `:5000` — systemd, **not pm2** since 2026-09-26 |
| Command Bus | `command-bus.service` | |
| Context Assembly | `context-service.service` | `:5001` |
| Model Router | `model-router.service` | `:8891` |
| Ollama | `ollama.service` | `:11434` |
| XO Telegram Bot | `tg-xo.service` | Action-capable, Captain-only |
| REVS Telegram Bot | `tg-revs.service` | Public check-in, no action capability |
| CapacityBot Telegram Bot | `tg-capacitybot.service` | Capacity check-ins |
| Human Systems Scheduler | `human-systems-scheduler.service` | |
| Intelligence Scheduler | `intelligence-scheduler.service` | |
| Number One Exporter | `number-one-exporter.service` | |
| Mission Mint Server | `mint-server.service` | `:5052` |
| Meilisearch | `starship-meilisearch.service` | `:7700` |
| Chatterbox TTS | `chatterbox-tts.service` | `:8893` |
| Arize Phoenix | `phoenix.service` | `:6006`/`:4317` |
| Self-Improvement Dashboard | `self-improvement-dashboard.service` | `:8892` |
| Self-Improving System | `self-improving-system.timer` | Runs from a dedicated worktree |
| Officer Daily-Ops Cycle | `daily-ops-cycle.timer` | Daily 06:50 Australia/Sydney |
| Delivery Reconciler | `delivery-reconciler.timer` | |
| Mission Registry Sync | `mission-registry-sync.timer` | |
| Engineering Auto-Dispatch | `mission-engineering-dispatch.timer` | Every 15min |

Plus docker-managed: **Infisical** (secrets, `127.0.0.1:8446`), **Uptime Kuma**
(fronted by Caddy at `/uptime/*`), **changedetection.io** (fronted by Caddy at
`/changedetection/*`).

**Not present** (decommissioned — do not expect these, do not chase them
during an incident): Slack bot (any variant), Chief Engineer bot, Engineering
Dept bot, `control-engine.service`, Coolify, Dashy, `pm2-root.service`.

## Verification after boot

```bash
# Core services
systemctl is-active caddy lcars-portal command-centre command-bus \
  context-service model-router ollama tg-xo tg-revs tg-capacitybot

# Check for anything failed
systemctl --failed

# Docker stack
docker ps --format "table {{.Names}}\t{{.Status}}"

# End-to-end through Caddy
curl -sk https://109.123.227.196/health
curl -sk -o /dev/null -w "%{http_code}\n" https://109.123.227.196/
```

## Manual restart procedures

### Any systemd service (this is now uniform — nothing is pm2-managed)
```bash
systemctl restart <unit-name>
journalctl -u <unit-name> -f
```

### Full stack restart after a git pull
```bash
cd /opt/starship-endeavour && git pull origin main
systemctl restart lcars-portal command-centre command-bus context-service model-router
systemctl is-active lcars-portal command-centre command-bus context-service model-router
```

Secrets come from Infisical via `platform-runtime/run-with-infisical.sh` for
every wrapped unit — check `systemctl cat <unit>`'s `ExecStart` before
assuming a `.env` file is what a given service actually reads.

## Critical rules

1. Every backend process is systemd-managed. There is no pm2 anymore — if
   you find yourself reaching for `pm2 restart`, that's a sign this doc (or
   your assumption) is stale; use `systemctl` instead.
2. All `.env` files must be `chmod 600`. Check after any git pull that
   introduces new env files.
3. Repo root: `/opt/starship-endeavour` (github: `timjardenross/TJRHQ`,
   branch: `main`). The `self-improvement` branch runs from a **separate git
   worktree** at `/opt/starship-endeavour-self-improvement` — do not confuse
   the two checkouts.
