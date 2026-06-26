# Advisor Intelligence — Live Deployment Runbook (MSN-0100)

What must exist on the live host before the MSN-0091→0099 advisor-intelligence
programme can be validated end-to-end. This is the production handoff: the code
is built and tested at the logic/build tier (see the per-mission reports); the
items below are the environment/config the deployed host must provide.

## Components & where they run

| Component | Path | Process |
|---|---|---|
| Advisory runtime (engines + products) | `core/advisory/` | imported by interfaces; CLI `core/advisory/cli.py` |
| Slack bot | `slack-bot/app.py` | Socket Mode service |
| Telegram bot | `telegram-bot/app.py` | polling service |
| XO bot | `xo-bot/app.py` | polling service (see `deploy/xo-bot.service`, `deploy/README-xo-bot.md`) |
| Portal | `lcars-portal/` | Next.js (`/intelligence`, `/advisory`, `/api/advisory`) |

## Required environment

### Advisory runtime (Python)
- `python3` available on the host (the portal `/api/advisory` route shells to it).
- `ADVISORY_DATA_ROOT` *(optional)* — overrides where advisory snapshots/outcomes
  are written (`logs/advisory/`, `knowledge/advisory-outcomes.jsonl`). Default is
  the repo root; set this only to relocate runtime data. **Used by tests for
  isolation; leave unset in production to use the repo paths.**
- Supabase: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (and `SUPABASE_SERVICE_ROLE_KEY`
  where persistence is used). Absent → the specialist retrieval path degrades to
  deterministic fallback (advice still produced, flagged `degraded`).
- Ollama (live Commander synthesis): `COMMANDER_SYNTHESIS_PROVIDER=ollama`,
  `OLLAMA_BASE_URL`, `OLLAMA_COMMANDER_MODEL` (e.g. `qwen3:8b`). **Fallback
  behaviour:** if the provider is not `ollama` or the call fails, synthesis uses
  the deterministic template — no outage, lower nuance.

### Slack bot (Socket Mode)
- `SLACK_BOT_TOKEN` (`xoxb-…`), `SLACK_APP_TOKEN` (`xapp-…`, Socket Mode).
- The 11 slash commands created in the Slack app config — see
  `MSN-0100-Slack-Command-Deployment-Checklist.md`.
- Optional: `BRIEF_CHANNEL` / `BRIEF_USER_ID` for any pushed briefs (no new push
  channels were added by this programme).

### Telegram bot
- `TELEGRAM_BOT_TOKEN`. Command menu auto-registers on startup (no manual step).
- Captain allowlist as already configured for the bot.

### XO bot
- Per `deploy/README-xo-bot.md`: `TELEGRAM_BOT_TOKEN` (XO bot token),
  `XO_ALLOWED_CHAT_IDS` (Captain's chat only). The XO advisory commands
  (`/advisory`, `/challenge`, `/evidence`) reuse `core/advisory` via
  `core/coordination/xo_advisory.py` — no extra env beyond the bot's own.

### Portal (`/api/advisory`)
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (build + runtime).
- `USSTJROS_ROOT` — path to the repo so the route can locate
  `core/advisory/cli.py` (defaults try `cwd/..`, `cwd`; set explicitly if the
  portal is deployed apart from the Python repo).
- `PYTHON_BIN` *(optional)* — python executable name/path (default `python3`).
- The route is **auth-gated** by `src/middleware.ts` (Supabase auth) — an
  authenticated session is required to call it; anonymous requests redirect to
  `/login`.

## Live validation steps (run on the host)

```bash
# 1. Advisory runtime (degraded vs live)
python3 core/advisory/cli.py --action advice --question "smoke test" --format markdown
COMMANDER_SYNTHESIS_PROVIDER=ollama python3 core/advisory/cli.py --action advice \
  --question "smoke test" --format markdown   # expect ollama synthesis + Supabase sources

# 2. Products / awareness
python3 core/advisory/cli.py --action awareness --format markdown
python3 core/advisory/cli.py --action products --format markdown

# 3. Portal (authenticated)
curl -s -X POST "$PORTAL_URL/api/advisory" -H 'Content-Type: application/json' \
  -H "Cookie: $AUTH_COOKIE" -d '{"action":"awareness"}' | jq .result.product

# 4. Slack / Telegram / XO — invoke the commands per the checklist and confirm replies.

# 5. Close a loop and confirm metrics move
python3 core/advisory/cli.py --action metrics --format markdown      # before
# …capture an outcome via any channel…
python3 core/advisory/cli.py --action metrics --format markdown      # after: counts +1
```

## Data dependency (why dashboards look quiet at first)

Calibration, forecasts, signals, triggers, wellness, the Operational Resilience
Watch and the Daily Awareness Brief are **wired but data-gated** — they honestly
report "insufficient data / no current signals" until real inputs accumulate:
- advisory outcomes closed via `/advisory-outcome`,
- health check-ins (`/health-check`) feeding `captains_log_entries`,
- the operational-resilience collection pipeline (`intelligence/`) running on the host.

This is by design (evidence before opinion); value grows as the loops are fed.

## Not reachable in CI/build environment

Live Slack/Telegram/XO transport, live Supabase/Ollama, the OR collection
pipeline, and authenticated portal calls cannot be exercised in a secret-free
build container. They are validated here only at the logic/build tier; the steps
above close the live tier on the deployed host.
