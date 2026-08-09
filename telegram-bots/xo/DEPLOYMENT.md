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

`SUPABASE_KEY` security note: an anon key leaves Postgres RLS as a backstop if
the bot's own chat-ID auth gate ever has a gap. A `service_role` key bypasses
RLS entirely for every table this bot touches — if you use one, the bot-level
auth gate (see below) becomes the *only* access control standing between an
unauthorized caller and full read/write access to those tables. Treat the two
as materially different security postures, not interchangeable options.

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
gotrue==1.3.1
python-dotenv==1.0.0
httpx<0.26
```

`apscheduler` is listed but not currently imported anywhere in `app.py`,
`voice_capture.py`, or `pulse_time.py` — see the scheduling note below. It's a
dead dependency left over from an earlier version of this bot.

## Scheduling — this process does not self-schedule

This bot only responds to inbound Telegram updates (commands, free text, voice
notes, button taps). It does **not** run `AsyncIOScheduler`, `BackgroundScheduler`,
or any other in-process scheduler — there is no `apscheduler` import anywhere in
`telegram-bots/xo/`.

Proactive pushes advertised in `/help` (07:00 Daily Operating Picture, 21:00
Evening Recovery Reflection, Monday Weekly Human Systems Review, etc.) are owned
by the separate `intelligence-scheduler.service` unit, which calls into this
bot's Telegram chat independently. If a scheduled push isn't arriving, check
that service (`systemctl status intelligence-scheduler.service`,
`journalctl -u intelligence-scheduler.service`) — not this one.

`XO_SCHEDULED_BRIEFS_ENABLED` (see `.env.example`) exists only as a local-testing
escape hatch for when `intelligence-scheduler.service` isn't running. Leaving it
on in production alongside that service causes duplicate messages.

## Systemd Service (tg-xo.service)

The live unit is installed as `/etc/systemd/system/tg-xo.service`, sourced from
`deploy/xo-bot.service` in this repo (the destination filename differs from the
source filename — that's expected, not a typo). Current content:

```ini
[Unit]
Description=Starship XO Telegram bot (new architecture)
After=network.target

[Service]
WorkingDirectory=/opt/starship-endeavour
EnvironmentFile=-/opt/starship-endeavour/platform-runtime/.env
EnvironmentFile=-/opt/starship-endeavour/telegram-bots/xo/.env
ExecStart=/opt/starship-endeavour/telegram-bots/xo/.venv/bin/python -m telegram_bots.xo.app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Two `EnvironmentFile` directives are required, in this order —
`platform-runtime/.env` first (shared provider config: `EMBEDDING_PROVIDER`,
`OLLAMA_*`, `SUPABASE_*`, etc.), then `telegram-bots/xo/.env` second so
bot-specific values (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) win on any
overlapping key. A single-file unit that only loads `telegram-bots/xo/.env` was
a real production bug: without the `platform-runtime/.env` line,
`EMBEDDING_PROVIDER` was unset and fell back to the code's 1024-dim default
against a database schema migrated to 768-dim, silently degrading `/advise` and
`/challenge`. Don't reintroduce a single-`EnvironmentFile` version of this unit.

Install/update:

```bash
sudo cp deploy/xo-bot.service /etc/systemd/system/tg-xo.service
sudo systemctl daemon-reload
sudo systemctl restart tg-xo.service
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

## Known gaps (as of 2026-08-09)

- `telegram_bots.xo.debrief_engine` is imported by five call sites in `app.py`
  but does not exist in this repo or its git history. All five sites guard the
  import with `try/except ImportError` and degrade gracefully (plain
  quick-capture / plain LLM reply, or an honest "unavailable" message) rather
  than crashing — but debrief session functionality itself is not available
  until that module is rebuilt or recovered.
- `app.py` (~2,300 lines, the bulk of this bot) has no automated test coverage.
  Only `voice_capture.py` is covered, via `test_voice_capture.py` (run directly
  with `python test_voice_capture.py`, not via `pytest`/`unittest discover` —
  the tests are plain asserts, not `unittest.TestCase` classes).
