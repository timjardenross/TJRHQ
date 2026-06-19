# Telegram Bot Deployment Task

This file contains deployment instructions for Claude Code to execute on the VM.

## Context

Three Telegram bots have been built and are ready to deploy. All code is on branch
`claude/sweet-shannon-npafr5`. All tokens and Supabase credentials are already in the
`.env` files. The only missing value across all three bots is `TELEGRAM_CHAT_ID` —
the Captain's personal Telegram user ID.

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

## Step 3 — Write the chat ID into all three .env files

Edit the following files and set `TELEGRAM_CHAT_ID=<id>` in each:

- `telegram-bots/xo/.env`
- `telegram-bots/engineer/.env`
- `telegram-bots/engineering-dept/.env`

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

## Step 5 — Verify

Send `/recovery_status` to each bot in Telegram. Each should reply with today's
recovery confidence bar and pulse count pulled live from Supabase.

Send `/start` to confirm the chat ID is correctly set (the bot echoes it back).

## Step 6 — Confirm and report back

Once all three bots are responding correctly, report:
- Which bots are running
- The chat ID that was used
- Any errors encountered and how they were resolved

## Constraints

- Do not commit `.env` files
- Do not modify any files outside `telegram-bots/`
- Do not change bot tokens
- If a bot fails to start, diagnose the error and fix it before moving on
- The Supabase anon key and bot tokens are already in the `.env` files — do not
  replace or regenerate them
