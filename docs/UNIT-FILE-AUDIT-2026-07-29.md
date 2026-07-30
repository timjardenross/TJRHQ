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

## Follow-up items — status 2026-07-29 (same session, after initial audit)

1. ✅ **FIXED** — `deploy/mint-server.service` ExecStart drift. Confirmed the
   repo's referenced venv (`/opt/starship-endeavour/.venv`) doesn't exist on
   the VM at all; repo file corrected to `/usr/bin/python3` (live truth).
2. ✅ **FIXED** — `deploy/telegram-build-executor.service` venv/env drift.
   Repo corrected to `platform-runtime/`. Also re-enabled the live service
   (`systemctl enable telegram-build-executor.service`) — it was `active` but
   `disabled` (preset says `enabled`), meaning it would not have survived a
   reboot. Confirmed still `active` after enabling.
3. ✅ **FIXED** — `deploy/delivery-reconciler.service` now documents and
   includes the `apply` pass (was silently missing from the repo file, which
   also falsely claimed read-only behavior).
4. ✅ **FIXED** — `core/capture/systemd/capture-enrichment.service` updated
   from the pre-migration `/opt/usstjros` / `ubuntu` layout to live
   `/opt/starship-endeavour` / `root` / `platform-runtime`.
5. ✅ **FIXED** — added `deploy/health-intelligence-weekly.service` +
   `.timer`, copied verbatim from the live units. Note: the live timer's own
   `Description=` says "every Monday 06:00" while its `OnCalendar=` comment
   and value say 04:00 Melbourne local — a pre-existing inconsistency in the
   *live* unit's own text, copied faithfully rather than silently corrected.
   Worth a follow-up to fix live if 04:00 is in fact correct.
6. **Not fixed — deferred.** `deploy/xo-bot.service` filename vs live
   `tg-xo.service`. Bodies match exactly; only the filename differs, and the
   file already self-documents this in its header. Left as-is — a rename is
   cosmetic and not urgent.

All 6 repo files (`mint-server.service`, `telegram-build-executor.service`,
`delivery-reconciler.service`, `capture-enrichment.service`,
`health-intelligence-weekly.service`, `health-intelligence-weekly.timer`)
verified byte-for-byte matching their live `systemctl cat` output after the
fix.
