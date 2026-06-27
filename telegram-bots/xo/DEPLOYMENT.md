# XO Bot — Production Deployment Notes

## Environment (telegram-bots/xo/.env)

Copy `.env.example` and fill in all values:

```
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<your chat ID — send /start to discover>
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<anon or service-role key>
LCARS_PORTAL_URL=https://<your-portal>.vercel.app   # required for /mission_create
```

## Python Dependencies

```bash
cd telegram-bots/xo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pinned versions:
```
python-telegram-bot==20.7
apscheduler==3.10.4
supabase==2.3.4
python-dotenv==1.0.0
httpx<0.28
```

## Scheduler — AsyncIOScheduler Required

The bot uses `AsyncIOScheduler` from `apscheduler.schedulers.asyncio` (NOT `BackgroundScheduler`).
`BackgroundScheduler` does not work with an async event loop — it raises a threading conflict at runtime.
APScheduler 3.x ships both; always import `AsyncIOScheduler`.

If you see `RuntimeError: There is no current event loop` or `PythonicJobStore error`, the bot is likely
running with the wrong scheduler class. Confirm with:

```bash
grep "AsyncIOScheduler" telegram-bots/xo/app.py
```

## Systemd Service (tg-xo.service)

```ini
[Unit]
Description=XO Telegram Bot — @Starship_endeavour_xO_bot
After=network.target

[Service]
WorkingDirectory=/opt/starship-endeavour
EnvironmentFile=/opt/starship-endeavour/telegram-bots/xo/.env
ExecStart=/opt/starship-endeavour/telegram-bots/xo/.venv/bin/python -m telegram_bots.xo.app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Post-Deploy Verification

```bash
systemctl status tg-xo.service
journalctl -u tg-xo.service -n 50

# In Telegram:
/mission_list
/mission_status 0173
/mission_create Test mission from Telegram
```

## Supabase Schema Notes (MSN-0173)

The `missions` table has NO `owner` column. Use `created_by` for mission attribution.
Valid `status` values (CHECK constraint):
- `Idea`, `Designed`, `Implemented`, `Tested`
- `Awaiting Number One Review`, `Validated`, `Awaiting XO Approval`
- `Closed`, `Blocked`, `Archived`

`Active` is NOT a valid status value and will be rejected by Supabase.
The XO bot `/mission_list active` maps to `['Implemented', 'Tested', 'Awaiting Number One Review', 'Validated', 'Awaiting XO Approval']`.

## Backfill Tool (MSN-0173 WP2)

To backfill missing missions into Supabase:

```bash
python3 tools/backfill_missions_to_supabase.py --dry-run   # preview
python3 tools/backfill_missions_to_supabase.py             # execute
```

This is idempotent — existing mission_ids are skipped.
