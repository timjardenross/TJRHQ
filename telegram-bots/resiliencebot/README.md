# Resilience Crosswalk Bot

The Operational Resilience Advisor (USS-TJR-OR-001) on Telegram. It's a thin
front-end over the grounded crosswalk pipeline in `platform-runtime/lib/resilience/`.
It takes no host or shell actions; XO stays the only bot that can.

## Using it

| Command | What it does |
|---|---|
| `/crosswalk <request>` | Starts a crosswalk. Tap target frameworks, cycle the source and intended use, then **Run**. |
| `/coverage` | Shows what `knowledge/regulatory-corpus/` actually holds for each framework. |
| `/pending` | Lists crosswalks still waiting for your review, with review buttons. |
| `/changes` | Lists new APRA/BIS publications that may affect stored clauses, with **Dismiss** and **Re-ingested** buttons. |
| `/help` | Lists the commands. |

The full four-part crosswalk arrives as a `.md` document, because Telegram doesn't
render Markdown tables. A short summary follows it with **Accepted / Edited / Rejected**
buttons, which write to the pipeline's audit log
(`data/resilience-crosswalk/audit.jsonl`, gitignored).

Input passes through `lib/resilience/guardrails.py` before any model sees it, so customer
identifiers and requests for regulator responses or legal advice are refused up front.

## Deploying (host)

1. Create the bot with BotFather.
2. Put its `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Infisical folder `/bots/resiliencebot`.
3. Create the venv and install the unit:
   ```bash
   cd /opt/starship-endeavour/telegram-bots/resiliencebot
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   sudo cp /opt/starship-endeavour/deploy/tg-resiliencebot.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now tg-resiliencebot
   ```
4. Make sure the Model Router (`model-router.service`) is up. The bot uses the
   platform's `llm.try_generate_response`.

For local runs, copy `.env.example` to `.env` and run `bash telegram-bots/resiliencebot/start.sh`.

## Code layout

- `conversation.py`: the intake session, keyboards, callback parsing and summaries. It has
  no Telegram imports, so it's unit-testable.
- `app.py`: handler wiring, the chat allowlist gate (`core/platform/telegram_access.py`),
  and running the pipeline off the event loop.
