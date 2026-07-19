# Recovery Officer — Telegram Engagement Dispatcher

D-055 WP3: Active Engagement & Escalation

Dispatches recovery pulse reminders and escalation alerts via Telegram.
Bot-agnostic — wire into any of the three existing bots.

## Existing bots

| Bot | Username | Role |
|-----|----------|------|
| Starship Endeavour | @starship_endeavour_bot | Primary crew bot |
| XO | @Starship_endeavour_xO_bot | Executive Officer |
| Chief Engineer | @Starship_ChiefEngineer_bot | Engineering |

## Wiring into an existing bot

Add to your bot's scheduled jobs (e.g. APScheduler):

```python
from telegram_bots.recovery_officer.engagement_dispatcher import run_dispatch_check

# Morning window (07:00) — morning pulse reminder
scheduler.add_job(
    lambda: run_dispatch_check(bot, CAPTAIN_CHAT_ID),
    'cron', hour=7, minute=0,
)

# Midday window (12:30)
scheduler.add_job(
    lambda: run_dispatch_check(bot, CAPTAIN_CHAT_ID),
    'cron', hour=12, minute=30,
)

# End of workday (16:00)
scheduler.add_job(
    lambda: run_dispatch_check(bot, CAPTAIN_CHAT_ID),
    'cron', hour=16, minute=0,
)

# Evening (20:00) — final reminder + daily summary if all done
scheduler.add_job(
    lambda: run_dispatch_check(bot, CAPTAIN_CHAT_ID),
    'cron', hour=20, minute=0,
)
```

Add a `/recovery` command handler:

```python
@bot.message_handler(commands=['recovery'])
def handle_recovery_command(message):
    from telegram_bots.recovery_officer.engagement_dispatcher import (
        get_recovery_status, build_daily_summary, build_pulse_reminder
    )
    status = get_recovery_status()
    if status.next_suggested_pulse:
        bot.reply_to(message, build_pulse_reminder(status), parse_mode='Markdown')
    else:
        bot.reply_to(message, build_daily_summary(status), parse_mode='Markdown')
```

## Escalation levels

| Level | Trigger | Message |
|-------|---------|---------|
| 0 | Confidence ≥ 75% | No action |
| 1 (L1) | Next pulse window open | Friendly reminder |
| 2 (L2) | Confidence ≤ 50% | Recovery Officer notification |
| 3 (L3) | 0 pulses by afternoon | Critical alert |

## Environment variables

```
SUPABASE_URL=https://cjvrpjwewsrumnbdydgg.supabase.co
SUPABASE_KEY=<anon-key>
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<captain-chat-id>
```

## Standalone test

```bash
cd /path/to/USSTJROS
python -m telegram_bots.recovery_officer.engagement_dispatcher
```
