# Telegram Bot Deployment Task

This file contains deployment instructions for Claude Code to execute on the VM.

## Context

Three Telegram bots are deployed and running. All code is on branch
`claude/sweet-shannon-npafr5`. Tokens, Supabase credentials, and chat ID are in the
local `.env` files on the VM (not committed). The only value to add after a fresh pull
is `OLLAMA_API_KEY` — the Ollama Cloud key from Vercel Environment Variables.

## Bots

| Bot | Username | Directory |
|-----|----------|-----------|
| XO | @Starship_endeavour_xO_bot | `telegram-bots/xo/` |
| Chief Engineer | @Starship_ChiefEngineer_bot | `telegram-bots/engineer/` |
| Engineering Dept | @starship_endeavour_bot | `telegram-bots/engineering-dept/` |

## Step 1 — Pull the branch

```bash
git fetch origin
git checkout claude/sweet-shannon-npafr5
git pull origin claude/sweet-shannon-npafr5
```

## Step 2 — Get the Captain's Telegram chat ID

The chat ID is not yet in any `.env` file. Discover it by starting the XO bot
temporarily, then instruct the Captain to send `/start` to @Starship_endeavour_xO_bot
in Telegram. The bot will reply with the chat ID.

```bash
cd telegram-bots/xo
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
cd ../..
python -m telegram_bots.xo.app
```

Once the Captain sends `/start` and the chat ID appears in the bot reply, note it,
then stop the bot with Ctrl+C.

## Step 3 — Fill in Ollama API key in all three .env files

The chat ID (`643108092`) is already set. Add the Ollama Cloud API key
(same key used by LCARS portal AI Console — retrieve from Vercel env vars):

```bash
# In each of these files, set OLLAMA_API_KEY=<your-key>
telegram-bots/xo/.env
telegram-bots/engineer/.env
telegram-bots/engineering-dept/.env
```

Each file already contains:
```
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=glm-5.2
OLLAMA_API_KEY=        ← paste key here
```

Do not commit these files. They are already covered by `.gitignore`.

## Step 4 — Start all three bots

Run each in a separate terminal, screen, or tmux pane so they run concurrently:

```bash
bash telegram-bots/xo/start.sh
bash telegram-bots/engineer/start.sh
bash telegram-bots/engineering-dept/start.sh
```

Each script will:
- Create a `.venv` if one does not exist
- Install requirements
- Validate the `.env` file
- Start the bot with polling

## Step 5 — Update BotFather command menus

Open a chat with @BotFather in Telegram. For each bot, send `/setcommands`, select
the bot, then paste the command list below.

**@Starship_endeavour_xO_bot (XO)**
```
start - Executive Officer online
help - Available commands
recovery_status - Today's recovery confidence and pulse status
recovery_pulse - Log a recovery pulse (tap buttons — no portal)
dispatch - Manual dispatch check
```

**@Starship_ChiefEngineer_bot (Chief Engineer)**
```
start - Chief Engineer online
help - Available commands
recovery_status - Today's recovery confidence (read-only)
engineering_status - Active engineering missions
```

**@starship_endeavour_bot (Engineering Dept)**
```
start - Engineering Dept noticeboard online
help - Available commands
recovery_status - Today's recovery confidence (read-only)
operations_status - All active missions across departments
```

## Step 6 — Verify

Send `/recovery_status` to XO — should reply with today's confidence bar from Supabase.
Send `/recovery_pulse` to XO — should show inline tap buttons (energy → mood → stress).
Send a plain message to XO (e.g. "What's my capacity today?") — should get an LLM response.
Send `/engineering_status` to Chief Engineer — should list engineering missions.

## Step 7 — Confirm and report back

Once all three bots are responding correctly, report:
- Which bots are running
- Whether XO inline pulse logging works (button taps)
- Whether XO conversational responses work (LLM via Ollama Cloud)
- Any errors encountered and how they were resolved

## Constraints

- Do not commit `.env` files
- Do not modify any files outside `telegram-bots/`
- Do not change bot tokens
- If a bot fails to start, diagnose the error and fix it before moving on
- The Supabase anon key and bot tokens are already in the `.env` files — do not
  replace or regenerate them
