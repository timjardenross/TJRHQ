# Slack Slash-Command Deployment Checklist — Advisor Intelligence (MSN-0100)

Registers the 11 advisory slash commands added across MSN-0092 → MSN-0099 in the
Slack app configuration. **The handlers already exist in `slack-bot/app.py`** —
this checklist is the Slack-side configuration required before they are invokable.

## Important: the bot runs in **Socket Mode**

`slack-bot/app.py` uses `SocketModeHandler` with `SLACK_APP_TOKEN` (`xapp-…`).
In Socket Mode, slash-command payloads are delivered over the WebSocket — the
**Request URL is NOT used for routing**. You must still *create* each command in
the app config (Slack requires the Request URL field to be non-empty), but any
placeholder works and is ignored. **Do not assume a production HTTP URL — there
isn't one for slash commands in this setup.**

- Request URL placeholder (unused in Socket Mode): `https://example.com/slack/commands`
- Required app-level token: `SLACK_APP_TOKEN` (`xapp-…`, Socket Mode enabled)
- Required bot token: `SLACK_BOT_TOKEN` (`xoxb-…`)
- Required OAuth scope: `commands`

## Commands to create

Create each under **Slack app → Features → Slash Commands → Create New Command**.

| Command | Short description (Slack) | Usage hint | Handler (verify) |
|---|---|---|---|
| `/advisor` | Multi-officer, evidence-based advisory | `<question>` | `handle_advisor` |
| `/challenge` | Red-team a decision before committing | `<question>` | `handle_challenge` |
| `/lessons` | Prior lessons for a topic | `<topic>` | `handle_lessons` |
| `/evidence` | Historical evidence + related decisions | `<question>` | `handle_evidence` |
| `/advisory-outcome` | Close the loop on prior advice | `<id\|last> <success\|failure\|partial> [note]` | `handle_advisory_outcome` |
| `/advisor-metrics` | Advisory metrics / calibration | `[calibration]` | `handle_advisor_metrics` |
| `/advisor-scan` | Proactive scan — what the system noticed | _(none)_ | `handle_advisor_scan` |
| `/timeline` | Temporal query (what changed / preceded / began / next) | `<question>` | `handle_timeline` |
| `/intel` | Intelligence views | `[brief\|picture\|wellness\|strategic\|forecast\|trust]` | `handle_intel` |
| `/awareness` | Daily Awareness Brief (or another product) | `[product]` | `handle_awareness` |
| `/products` | Intelligence product catalogue | _(none)_ | `handle_products` |

All eleven are registered as `@app.command(...)` in `slack-bot/app.py` (verify with
`grep -oE '@app.command\("/[a-z-]+"\)' slack-bot/app.py`).

## Steps

1. [ ] Confirm Socket Mode is **enabled** (Settings → Socket Mode) and an app-level
       token with `connections:write` exists → that is `SLACK_APP_TOKEN`.
2. [ ] Confirm the bot has the `commands` OAuth scope (Features → OAuth & Permissions).
3. [ ] For each row above: create the slash command, paste the description and usage
       hint, set Request URL to the placeholder.
4. [ ] **Reinstall the app** to the workspace (required after adding commands/scopes).
5. [ ] Ensure the runtime host has the env from the runbook
       (`MSN-0100-Advisor-Intelligence-Runbook.md`) and restart the Slack bot service
       so the handlers connect over Socket Mode.
6. [ ] Verify each command in Slack (see below).

## Verification

For each command, run it in a channel/DM where the bot is present and confirm a
formatted reply (not a `dispatch_failed` / "command not recognised" error):

```
/advisor Should we prioritise the portal or the Telegram bot next?
/awareness
/products
/intel brief
/advisor-scan
/timeline what changed recently?
/advisory-outcome last success
```

Expected: each returns advisory/awareness output carrying the standard
"Advisory only — Captain decides" note. A non-response usually means (a) the
command was not created in the app config, (b) the app was not reinstalled, or
(c) the bot service is not running / `SLACK_APP_TOKEN` is missing.

## Note

Telegram requires **no** equivalent manual step — `telegram-bot/app.py` registers
its command menu automatically via `set_my_commands` in `_post_init` on startup.
