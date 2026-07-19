# Telegram → engineering auto-pipeline

Closes the loop: **approve a build in Telegram → review-only patch / draft PR, hands-off.**

## Components

| Piece | File | Privilege |
|---|---|---|
| `/build` (existing) | `telegram-bot/app.py` | append-only: logs a `PENDING_TRIAGE` BREQ |
| `/approve` + Approve button (new) | `telegram-bot/app.py`, `telegram-bot/approval.py` | append-only: INSERTs an *approval marker* row (`source=telegram-approval`, `status=approved`) — **no new DB privilege** |
| Executor (new) | `core/coordination/telegram_build_executor.py` | **service_role**: polls markers → writes ENG-HANDOFF → `run_sync_one` (Mistral, FULL_FILE → draft PR, new-files-only) → stamps row → notifies the chat |

The Telegram bot never gains write/PR power; the executor supplies it, separately.

## Flow

```
/build            → BREQ-*.md  + inbox row (pending_triage)
/approve <id>     → inbox row  (source=telegram-approval, status=approved)
executor (poll)   → claim (approved→engineering_running)   [atomic, dedup]
                  → ENG-HANDOFF-*.md (APPROVED_FOR_ENGINEERING / Batch Status: PENDING)
                  → run_sync_one()  → patch artifact + draft PR (new files only)
                  → status engineering_delivered | engineering_failed
                  → Telegram message with the PR / artifact
```

## Marker row status vocabulary (inbox.status)

`approved` → `engineering_running` → `engineering_delivered` | `engineering_failed`
(No migration needed — reuses the existing `build_request_inbox` columns from 0015.)

## Install

```bash
# 1) unit
sudo cp /opt/starship-endeavour/deploy/telegram-build-executor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-build-executor.service

# 2) pick up the new /approve handlers in the live bot
sudo systemctl restart telegram-chief-engineer.service
```

### Required env (already present for the Slack path)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (executor DB access)
- `MISTRAL_API_KEY` / `MISTRAL_BATCH_API_KEY` (codegen)
- `GITHUB_TOKEN`, `GITHUB_REPO` (draft PR)
- `TELEGRAM_BOT_TOKEN` (notify) — in `telegram-bot/.env`

The executor self-loads `.env` + `slack-bot/.env` + `telegram-bot/.env`.

## Manual one-shot (for the first supervised run)

```bash
cd /opt/starship-endeavour
slack-bot/.venv/bin/python -m core.coordination.telegram_build_executor once
```

## Tests (offline, no network)

```bash
cd /opt/starship-endeavour && slack-bot/.venv/bin/python -m unittest core.coordination.tests.test_telegram_build_executor
cd /opt/starship-endeavour/telegram-bot && .venv/bin/python -m unittest tests.test_approval
```

## Safety

- Review-only: patch is an artifact, any PR is a **draft**, nothing merges.
- New-files-only auto-commit (`AUTO_ENGINEER_ALLOW_EXISTING_EDITS` default false); edits to
  existing files are deferred to the PR body for manual review.
- `engineering_failed` is terminal for that marker — re-approve (new `/approve`) to retry.
