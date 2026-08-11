# XO Telegram bot (@Starship_endeavour_xO_bot)

Command-driven Executive Officer you talk to over Telegram — Captain intelligence
narratives, mission governance, health/recovery logging, and free-text conversation
with the platform's LLM (aware of live recovery/wellness/mission context). This is
**not** a general shell-agent: there is no planner/executor/action-registry layer,
no per-step Approve/Skip/Cancel flow, and no arbitrary host/shell control. That
architecture (`xo-bot/` — `planner.py`, `executor.py`, `actions.py`, `shellrun.py`)
was superseded on 2026-07-05 and no longer exists on this platform; what's
documented below is the bot that is actually deployed.

## Pieces (`telegram-bots/xo/`)

| File | Role |
|---|---|
| `app.py` | Telegram app — ~40 command/callback handlers, global auth gate, main() |
| `voice_capture.py` | Voice note transcription (faster-whisper) + quick-capture save |
| `pulse_time.py` | Recovery pulse time-window helpers |
| `test_voice_capture.py` | Plain-assert test suite for `voice_capture.py` (run directly, not via pytest/unittest discovery) |

`telegram_bots/xo/debrief_engine.py` is imported by five call sites (voice-note
routing, free-text routing, `/debrief_close`, and the voice-capture "Start Debrief"
callback) but does not exist in this repo or its git history — it was lost between
environments before ever being committed. Every import site guards this with
`try/except ImportError` and degrades gracefully (plain quick-capture / plain LLM
reply, or an honest "Debrief is unavailable" reply) rather than crashing. Debrief
session functionality itself (`/debrief_close`, voice-triggered debrief sessions)
is not currently available on this deploy.

## Security model

- **Global auth gate**: `_global_auth_gate` (`app.py`) is registered as a
  `TypeHandler(Update, ...)` at `group=-1`, so it runs before every other handler
  for every update type. It calls the shared `_chat_is_allowed()` check
  (`core/platform/telegram_access.py`) and raises `ApplicationHandlerStop` — with
  no reply sent — on any chat ID not on the allowlist. This closes the bot
  platform-wide in one place rather than relying on each of the ~40 handlers to
  remember to check individually (an earlier version of this bot had that
  per-handler pattern, and most handlers didn't call it — a real gap, fixed).
- **Allowlist source**: `telegram_access.allowed_chat_ids()`, driven by
  `TELEGRAM_ALLOWED_CHAT_IDS` if set, otherwise falling back to the single
  bootstrap Captain chat ID (`TELEGRAM_CHAT_ID`). In practice this is currently
  just the Captain's chat.
- **No shell execution, no action registry, no approval flow.** The bot only
  calls Supabase, the LCARS Portal API (via `X-Bot-Secret`), the local LLM
  gateway, and the advisory CLI as a subprocess with a fixed, non-user-controlled
  argument list (`cmd_restart_bots` resolves the target service through a
  hardcoded dict lookup, never raw user text).
- Runs as its own systemd unit (not root-shell-capable by design); `.env` is
  `chmod 600`.

## Commands

Grouped roughly as registered in `app.py`'s `main()` / advertised via `/help`:

- **Captain intelligence** — `/captain`, `/learning`, `/patterns [category]`, `/pending`
- **Intelligence** — `/brief`, `/signals`, `/themes`, `/source_status`, `/operating_picture`, `/daily [morning|eod|weekly]`
- **Missions** — `/missions` (alias for `/mission_list`), `/mission_list [active|idea|blocked|completed|all]`, `/mission_status <id>`, `/mission_create <title>`
- **Captain governance** — `/captain_approve <id>`, `/captain_reject <id> <reason>`, `/mission_submit <id>`, `/handoff_engineering <id>`
- **Advisory** — `/advise <question>`, `/challenge <plan>`
- **Debrief** — `/debrief_close`, `/debrief_weekly` (session start/routing depends on `debrief_engine.py`, currently unavailable — see above)
- **Health & recovery** — `/recovery_status`, `/recovery_pulse` (+ `/pulse_check` alias), `/log_activity`, `/log_weight`
- **Capture** — `/note <content>`, voice notes (any voice message)
- **Ops** — `/dispatch`, `/db_status`, `/restart_bots [slack|telegram|all]`
- **Meta** — `/start`, `/help`
- Free text (not a command) — routed to the LLM with live recovery/wellness/mission context
- Inline button callbacks — pulse logging, outcome capture, voice-capture actions, voice-debrief decisions

Proactive pushes (07:00 Daily Operating Picture, 21:00 Evening Recovery Reflection,
etc.) are **not** sent by this process — they're owned by the separate
`intelligence-scheduler.service`. This bot only replies to inbound messages/commands.

## Config (`telegram-bots/xo/.env`, 0600)

See `telegram-bots/xo/.env.example` for the full documented list:
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SUPABASE_URL`, `SUPABASE_KEY`,
`LCARS_PORTAL_URL` (required for `/mission_create` and other governance
commands). `TELEGRAM_ALLOWED_CHAT_IDS` (comma/space-separated, optional — see
`core/platform/telegram_access.py`) is also read but not yet in `.env.example`;
if unset, the allowlist falls back to the single `TELEGRAM_CHAT_ID`.
`platform-runtime/.env` supplies shared provider config (embedding provider,
Ollama, etc.) — see Install below for why both are needed.

## Install

The live systemd unit is named **`tg-xo.service`** (not `xo-bot.service`, though
the source file in this repo is still named `deploy/xo-bot.service` — the install
step renames it on copy):

```bash
sudo cp /opt/starship-endeavour/deploy/xo-bot.service /etc/systemd/system/tg-xo.service
sudo systemctl daemon-reload
sudo systemctl enable --now tg-xo.service
journalctl -u tg-xo.service -f
```

The unit loads **two** `EnvironmentFile`s, in this order — `platform-runtime/.env`
first, then `telegram-bots/xo/.env` second (later file wins on any overlapping
key). Dropping the first file previously caused `/advise` and `/challenge` to
silently run against the wrong embedding dimension — see `deploy/xo-bot.service`'s
own header comment for the incident this fixed.

## Tests

```bash
cd /opt/starship-endeavour/telegram-bots/xo
.venv/bin/python test_voice_capture.py
```

This only exercises `voice_capture.py`. `app.py` (the bulk of this bot's logic —
command routing, auth gate, mission/governance calls) has no automated test
coverage yet.
