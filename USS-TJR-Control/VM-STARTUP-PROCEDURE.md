# VM Startup & Recovery Procedure
# USS-TJR-MSN-0181 — Established 2026-06-28

## Boot recovery (automatic)

All production services start automatically on boot via systemd.
No manual intervention required for core services.

| Service | Unit | Auto-starts |
|---|---|---|
| Slack Commander | `starfleet-slack-bot.service` | Yes |
| Command Bus | `command-bus.service` | Yes |
| XO Telegram Bot | `tg-xo.service` | Yes |
| Telegram Build Executor | `telegram-build-executor.service` | Yes |
| Number One Exporter | `number-one-exporter.service` | Yes |
| LCARS Portal | `lcars-portal.service` | Yes |
| Mission Mint Server | `mint-server.service` | Yes |
| Caddy (reverse proxy) | `caddy.service` | Yes |
| Ollama | `ollama.service` | Yes |
| Command Centre API (Node) | pm2 via `pm2-root.service` | Yes |
| Delivery Reconciler | `delivery-reconciler.timer` (15-min) | Yes |
| Engineering Batch Sync | `engineering-batch-sync.timer` (30-min) | Yes |

## Verification after boot

```bash
# Check all systemd services
systemctl is-active starfleet-slack-bot command-bus tg-xo telegram-build-executor \
  number-one-exporter lcars-portal mint-server pm2-root

# Check pm2 (Command Centre API)
pm2 status

# Check Slack bot startup
tail -20 /opt/starship-endeavour/USS-TJR-Control/logs/slack-bot.log
# Expect: [startup] Supabase connectivity OK — missions table readable

# Check Caddy
systemctl is-active caddy
curl -sk https://localhost/health | python3 -m json.tool
```

## Manual restart procedures

### Slack bot (ONLY use systemd — never start manually alongside systemd)
```bash
systemctl restart starfleet-slack-bot
journalctl -u starfleet-slack-bot -f
```

### Command Centre API
```bash
cd /opt/starship-endeavour && git pull origin main
pm2 restart command-centre
pm2 logs command-centre --lines 20
```

### LCARS Portal
```bash
systemctl restart lcars-portal
journalctl -u lcars-portal -f
```

### XO Telegram Bot
```bash
systemctl restart tg-xo
journalctl -u tg-xo -f
```

### Full stack restart after git pull
```bash
cd /opt/starship-endeavour && git pull origin main
systemctl restart starfleet-slack-bot lcars-portal tg-xo
pm2 restart command-centre
# Verify
systemctl is-active starfleet-slack-bot lcars-portal tg-xo
pm2 status
tail -5 /opt/starship-endeavour/USS-TJR-Control/logs/slack-bot.log
```

## Architecture (as of MSN-0182, 2026-06-28)

```
Browser → Caddy (:443)
  /api/* /health  → Node Command Centre (:5000, pm2)
  /*              → LCARS Portal (:3100, systemd lcars-portal)
```

LCARS Portal is the primary command interface. Dashy and Control Engine are decommissioned.

## Decommissioned components

- **Dashy** (`lissy93/dashy` Docker container) — removed. Config preserved at
  `core/command-centre/dashy-config.yml` for reference only.
- **Control Engine** (Flask :8888) — Caddy route removed. Dashboard data now
  served by Node Command Centre API at `/api/v1/console/dashboard`.

## Critical rules

1. NEVER start `python app.py` manually for the Slack bot while systemd service is active.
   This creates duplicate Socket Mode connections and splits command handling.

2. Command Centre API is managed by pm2, NOT systemd directly.
   Use `pm2 restart command-centre`, not `systemctl`.

3. All .env files must be chmod 600. Check after any git pull that introduces new env files.

4. Repo root: /opt/starship-endeavour (github: timjardenross/USSTJROS, branch: main)
   USS-TJR-Control/config/services.conf REPO_ROOT is correct for VM — do not revert to macOS path.
