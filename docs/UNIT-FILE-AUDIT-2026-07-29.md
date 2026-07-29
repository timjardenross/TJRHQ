# Systemd Unit File Audit — 2026-07-29

Issue 13: does the repo's `deploy/*.service`/`systemd/*.service` set match what's
actually enabled and running on the VM (`vmi3371936`, 109.123.227.196)? Ran
directly on the VM (this session's shell is the VM itself, no SSH hop needed).

## Method

```bash
systemctl list-unit-files --state=enabled | grep -iE "usstjr|starship|xo|intelligence|context|brief|delivery|mint|model-router|improv"
```

then, for every `deploy/*.service` and `systemd/*.service`/`core/**/systemd/*.service`
file in the repo: `diff <(cat repo-file) <(systemctl cat unit-name)`.

## Enabled units found on VM

```
context-service.service                enabled
intelligence-scheduler.service         enabled
mint-server.service                    enabled
model-router.service                   enabled
self-improvement-dashboard.service     enabled
tg-xo.service                          enabled
delivery-reconciler.timer              enabled
health-intelligence-weekly.timer       enabled
self-improving-system.timer            enabled
```

(`self-improving-system.service`, `delivery-reconciler.service`,
`deadmans-switch.service`, `verification-engine.service`,
`capture-enrichment.service`, `vm-processing*.service` show `static` under
`is-enabled` — expected for oneshot units with no `[Install]` section, only
ever triggered by their own timer. Not a mismatch.)

## Unit-by-unit result

| Repo file | Live unit name | Match? | Notes |
|---|---|---|---|
| `deploy/context-service.service` | `context-service.service` | ✅ exact match | |
| `deploy/deadmans-switch.service` | `deadmans-switch.service` | ✅ exact match | |
| `deploy/intelligence-scheduler.service` | `intelligence-scheduler.service` | ✅ exact match | |
| `deploy/model-router.service` | `model-router.service` | ✅ exact match | |
| `deploy/self-improvement-dashboard.service` | `self-improvement-dashboard.service` | ✅ exact match | |
| `deploy/self-improving-system.service` | `self-improving-system.service` | ✅ exact match | See Issue 11 fix |
| `deploy/verification-engine.service` | `verification-engine.service` | ✅ exact match | |
| `core/infrastructure/vm-processing/systemd/vm-processing.service` | `vm-processing.service` | ✅ exact match | |
| `core/infrastructure/vm-processing/systemd/vm-processing-retry.service` | `vm-processing-retry.service` | ✅ exact match | |
| `core/infrastructure/vm-processing/systemd/vm-processing-healthcheck.service` | `vm-processing-healthcheck.service` | ✅ exact match | |
| `deploy/xo-bot.service` | **`tg-xo.service`** | ⚠️ **name mismatch, body matches** | Body identical (repo file's own header comment already documents this: renamed at deploy time 2026-07-05/07-12, file never renamed to match). Not a drift risk — anyone editing `deploy/xo-bot.service` and deploying it will correctly update `tg-xo.service`. Cosmetic only. |
| `deploy/mint-server.service` | `mint-server.service` | ❌ **mismatch** | `ExecStart` differs: repo says `/opt/starship-endeavour/.venv/bin/python`, live runs `/usr/bin/python3`. Repo file describes a venv that isn't what's actually invoked. |
| `deploy/telegram-build-executor.service` | `telegram-build-executor.service` | ❌ **mismatch** | Repo still references the retired `slack-bot/.venv` + `slack-bot/.env`; live uses `platform-runtime/.venv` + `platform-runtime/.env`. Service itself is `active` but shows `disabled` under `is-enabled` — won't restart on reboot until re-enabled. |
| `deploy/delivery-reconciler.service` | `delivery-reconciler.service` | ❌ **mismatch, behavior-significant** | Repo's `Description` and comments claim **read-only** reconciliation ("Does NOT write to the database"). Live unit runs **two** `ExecStart` passes: an `apply` pass that writes mechanical status corrections directly to Supabase, then the `report` pass the repo file alone describes. Repo also references the retired `slack-bot/.venv`; live uses `platform-runtime/.venv`. This is the most consequential drift found — the repo's own safety claim about this unit is false against what's actually running. |
| `core/capture/systemd/capture-enrichment.service` | `capture-enrichment.service` | ❌ **mismatch, severe** | Repo still describes the pre-migration layout: `User=ubuntu`, `WorkingDirectory=/opt/usstjros`, `/opt/usstjros/venv`, `/opt/usstjros/.env`. Live: `User=root`, `/opt/starship-endeavour`, `platform-runtime/.venv`, `platform-runtime/.env`. Repo file is a fossil from before the `/opt/usstjros` → `/opt/starship-endeavour` move. |
| — (no repo file) | `health-intelligence-weekly.service` + `.timer` | ❌ **undocumented** | Enabled and live (weekly RSS import + synthesis + article enrichment, Mondays 04:00 local), but has **no corresponding file anywhere in the repo** — not in `deploy/`, not in `systemd/`, not under any `core/**/systemd/`. `ExecStart=/bin/bash /opt/starship-endeavour/core/health/run_weekly_intelligence.sh` is the only trace. |
| `systemd/self_improving_loop.py`'s unit, `self-improving-loop.service`/`.timer` | *(none)* | N/A | Confirmed never installed on the VM at all (`systemctl cat` → not-found, not in root's crontab, no process). Deprecated under Issue 11, not a "live but undocumented" case — the opposite: documented but never live. |

## Follow-up items (one each, per the issue's success criteria)

1. **`deploy/mint-server.service` ExecStart drift** — repo references a venv
   path that isn't actually used; align repo to `/usr/bin/python3` or confirm
   intent and fix the live unit instead.
2. **`deploy/telegram-build-executor.service` venv/env drift** — repo still
   points at `slack-bot/`; live uses `platform-runtime/`. Also: live service
   is `active` but `disabled` (won't survive reboot) — separate from the file
   drift, worth its own fix.
3. **`deploy/delivery-reconciler.service` missing the `apply` pass** — repo
   undersells what this unit actually does (writes to Supabase, not read-only).
   Needs correcting for both accuracy and because anyone redeploying from the
   repo file today would silently lose the `apply` pass.
4. **`core/capture/systemd/capture-enrichment.service` stale pre-migration
   paths** — repo file predates the `/opt/usstjros` → `/opt/starship-endeavour`
   rename; would not work if redeployed as-is.
5. **`health-intelligence-weekly.service`/`.timer` has no repo file at all** —
   add `deploy/health-intelligence-weekly.service` + `.timer` matching the
   live units so the repo can redeploy this unit and so it shows up in any
   future "what's enabled" sweep run against the repo alone.
6. **`deploy/xo-bot.service` filename vs `tg-xo.service`** — lowest priority
   (bodies match, already self-documented in the file's own header), but
   rename the repo file to `deploy/tg-xo.service` for consistency, or add an
   explicit repo-wide note pointing at this fact so future automation doesn't
   assume filename == unit name.

None of items 1-6 were applied in this pass — this is the requested written
match/mismatch record only, each flagged for separate follow-up as the issue
specified. Item 11's fix (self-improving-loop retirement) was applied
directly since it was already fully scoped as its own issue.
