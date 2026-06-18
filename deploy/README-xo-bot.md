# XO Telegram bot (@Starship_endeavour_xO_bot)

Action-capable Executive Officer you converse with over Telegram. **Full host/shell
control**, governed by **plan-then-approve-each**: the XO proposes a plan and
NOTHING runs until you tap **✅ Approve** on that specific step. Every executed
step is written to an append-only audit log.

## Flow

```
You (plain language)  →  planner (LLM) returns one of:
   • reply            → just an answer (no actions)
   • clarification    → a question back to you
   • a numbered plan  → per-step approval:
        Step i/N + risk + the exact command/action
        [✅ Approve] [⏭ Skip] [🛑 Cancel]
        approve → execute (shell or registered action) → result posted → next step
```

## Pieces (`xo-bot/`)

| File | Role |
|---|---|
| `app.py` | Telegram app + per-chat plan/approve-each state machine |
| `planner.py` | NL → strict-JSON Plan (steps: shell or named action; risk/reversible) |
| `executor.py` | runs ONE approved step; append-only audit log (`logs/xo-actions.log`) |
| `actions.py` | hybrid "known ops" registry (service status/restart/logs, git, host stats, run-engineering-once) |
| `shellrun.py` | shared subprocess runner (timeout/capture) |
| `config.py` | env + closed-by-default allowlist + shell timeout/workdir |
| `llm.py` | loads slack-bot/llm.py (Gemini auto) by file path |

## Security model

- **Closed-by-default allowlist** (`XO_ALLOWED_CHAT_IDS`, currently the Captain's
  chat only) gates every message AND every button. This is the primary control —
  guard the token and the chat.
- **No execution without per-step approval.** The planner is forbidden from acting;
  only `executor.execute_step` runs anything, and only on an Approve tap.
- **Audit log**: `xo-bot/logs/xo-actions.log` (JSONL) — ts, chat, command/action,
  exit, output head. `/audit [n]` shows recent entries in chat.
- Runs as root (full control by design). `.env` is `chmod 600`.

## Commands

- (plain text) — make a request
- `/cancel` — abandon the active plan
- `/audit [n]` — last n executed actions (default 10)
- `/start`, `/help`

## Config (`xo-bot/.env`, 0600)

- `XO_BOT_TOKEN` (secret), `XO_ALLOWED_CHAT_IDS=643108092`
- `XO_SHELL_TIMEOUT=300`, `XO_WORKDIR` (default repo root)
- Provider keys (`GEMINI_API_KEY`, …) inherited from repo-root `.env`.

## Install

```bash
sudo cp /opt/starship-endeavour/deploy/xo-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now xo-bot.service
journalctl -u xo-bot.service -f
```

## Tests (offline)

```bash
cd /opt/starship-endeavour/xo-bot && .venv/bin/python -m unittest tests.test_xo
```
