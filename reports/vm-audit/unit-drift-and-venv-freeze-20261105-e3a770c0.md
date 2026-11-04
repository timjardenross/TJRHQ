# Unit drift and venv freeze gap — 2026-11-05

Read-only audit; nothing restarted, installed, or changed on the VM. Repo side compared against `origin/main` @ `665edb1b8`. Secret values redacted (names only).

## 1. Unit drift

### self-improving-system.service

Drop-ins: `/etc/systemd/system/self-improving-system.service.d/` **does not exist** (VERIFIED).

Diff, repo (`<`) vs installed (`>`):

```
32c32,37
< ExecStart=/opt/starship-endeavour/scripts/self_improvement/run_daily_cycle.sh
---
> # 2026-09-18: heartbeat.py needs SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY to
> # record_heartbeat(); ... (comment only, names of env vars, no values)
> ExecStart=/opt/starship-endeavour/platform-runtime/run-with-infisical.sh /opt/starship-endeavour/scripts/self_improvement/run_daily_cycle.sh
```

No secret values in the installed unit (VERIFIED: grep for KEY/TOKEN/SECRET/PASSWORD hits only the comment naming two variables). Installed unit is *behind* the repo on nothing else; the repo was behind it by the wrapper. Fixed in #572.

### All `deploy/*.service` with an installed copy

42 repo units have an installed copy: **19 identical, 23 drifted** (VERIFIED). Not fixed, as instructed.

Installed side lacks `docker.service` in `After=` (repo ahead of installed; 17 units with only that difference):

capture-enrichment, context-service, daily-ops-cycle, engineering-batch-sync, health-osint-collection, intelligence-scheduler, lcars-portal, mission-registry-sync, model-router, self-improvement-dashboard, tg-capacitybot, tg-resiliencebot, tg-xo, verification-engine, vm-processing, vm-processing-retry, vm-processing-healthcheck. (human-systems-scheduler has this plus the items below.)

Installed side is *ahead* of / different from the repo (these matter more):

| Unit | Difference (names only) | Direction | Risk if repo file installed as-is |
|---|---|---|---|
| self-improving-system | Infisical wrapper on ExecStart | installed ahead | loses heartbeat secrets (fixed in #572) |
| governance-cache-sweep | ExecStart wrapped in `run-with-infisical.sh`; long comment about silent zero-credential runs | installed ahead | sweep runs without Supabase credentials and silently reports "Re-queued 0" |
| human-systems-scheduler | repo: `Environment=HS_DISABLED_JOBS=...` + `run-with-infisical-bot.sh capacitybot`; installed unit uses flat `run-with-infisical.sh` and relies on drop-in `human-systems-scheduler.service.d/capacity-bot-telegram.conf` which sets the same env + bot wrapper | repo ahead (2026-11-03 change folded in, installed still on drop-in) | Equivalent behaviour either way; drop-in would become redundant |
| auto-deploy | installed has `OnFailure=alert-on-failure@%n.service` active; repo has it commented out (`#OnFailure=`). Repo has `ExecStartPre=-+/opt/deploy-guard/repair-git-perms.sh` that installed lacks, but drop-in `auto-deploy.service.d/repair-git-perms.conf` supplies repair-git-perms + repair-tree-perms | mixed | installing repo file would silence failure paging and drop the tree-perms repair unless drop-in stays |
| command-bus | installed has 3 raw `EnvironmentFile=-` lines (`.env`, `platform-runtime/.env`, `telegram-bot/.env`); repo has them commented (hook forbids raw .env) | installed ahead | installing repo file drops those env files; effect depends on whether Infisical wrapper covers all vars: UNKNOWN |
| starship-meilisearch | installed passes `--master-key <value redacted>` inline in ExecStart; repo has a placeholder | installed ahead | repo file would start Meilisearch with a placeholder key. **Plaintext secret sits in a unit file in `/etc/systemd/system`, which `starship-backup` also copies into restic.** Not rotated or moved by me |

Identical (19): alert-on-failure@, chatterbox-tts, command-centre, deadmans-switch, delivery-reconciler, health-intelligence-weekly, hq-evolution, intelligence-source-validation, memory-nightly-consolidation, mint-server, mission-engineering-dispatch, number-one-exporter, ollama, phoenix, starship-backup, sync-self-improvement-state, watchlist-changedetection-webhook, watchlist-docker, watchlist-uptime-kuma-webhook.

Other drop-in directories under `/etc/systemd/system`: `auto-deploy.service.d`, `caddy.service.d`, `human-systems-scheduler.service.d`, `ollama.service.d`.

Reading across: nothing installs `deploy/*.service` automatically (auto-deploy only restarts). So the 17 "`After=` lacks docker" drifts are the repo's ahead-of-install guard (`tests/test_infisical_unit_ordering.py`) not yet applied; the 5-6 "installed ahead" rows are real hazards for anyone who copies repo units over the installed ones.

## 2. #572 update

- `deploy/self-improving-system.service` now equals the installed unit (wrapper included, no secrets) plus the `ExecStartPre` router wait. VERIFIED by `diff`.
- **Deviation from "only difference is ExecStartPre":** one more line differs, `After=network.target docker.service` (installed: `After=network.target`). `tests/test_infisical_unit_ordering.py` fails without it for any unit using the wrapper (1 failed before, 2 passed after). Flagged in the PR body; revert that line if you prefer, the test then fails.
- `systemd-analyze verify`: exit 0 (VERIFIED). `pytest tests/test_infisical_unit_ordering.py -q`: 2 passed (VERIFIED).
- Pushed to #572 (draft, unmerged). PR body rewritten.

## 3. Install

Awaiting the Captain's go-ahead and choice: drop-in vs replace. Nothing installed. Notes to inform the choice:
- Replace: the installed file would then equal the repo file; changes are the router wait + `After=docker.service`. `daemon-reload` needed; the unit is oneshot/timer-driven so no restart is required.
- Drop-in: only the router wait fits (`ExecStartPre=` list append), leaving the base file unchanged; but `After=` addition is a separate drop-in line, and it adds a fifth drop-in-managed unit to a system that already has drift from them.

## 4. Venv backup gap (report only; backup not changed)

### How the backup does chatterbox today

`deploy/starship-backup.sh` lines ~152-157:

```bash
# chatterbox-tts venv ... is NOT backed up; record its package set instead so it can be rebuilt.
CB_PIP="$REPO_ROOT/core/voice/chatterbox-venv/bin/pip"
if [ -x "$CB_PIP" ]; then "$CB_PIP" freeze >"$STAGE/chatterbox-venv-freeze.txt" 2>&1 || true; fi
```

`$STAGE` is the first entry in the restic file list, so the freeze is in each snapshot. The restic file list also excludes every `.venv`/`.venv-*`/`chatterbox-venv` from the `.env` find, so **no venv is backed up**. `/etc/systemd/system` is backed up whole (so installed units and drop-ins are covered, which reduces the unit-drift risk).

Whether the last snapshot actually contains `chatterbox-venv-freeze.txt`: UNKNOWN (the last run, 2026-11-05 02:41, logged "finished OK"; I did not open restic).

### Freeze size and Python version, measured now (`pip freeze` run read-only, output in scratchpad)

| Venv | Pins | Freeze size | Time | Python | pyvenv.cfg | Notes |
|---|---|---|---|---|---|---|
| `platform-runtime/.venv` | 388 | 7,625 B | 2.1s | 3.12.3 | home=/usr/bin, version 3.12.3 | torch 2.13.0 + CUDA-family packages (19 lines); extra index URL not captured by freeze |
| `core/infrastructure/vm-processing/.venv` | 126 | 2,409 B | 2.0s | 3.12.3 | same | 18 torch/nvidia lines |
| `scripts/self_improvement/.venv` | 9 | 141 B | 1.2s | 3.12.3 | same | tiny; matches `requirements.txt` scale |
| `tools/supabase/.venv` | 55 | 985 B | 0.9s | 3.12.3 | same | |
| `core/voice/chatterbox-venv` (existing step, for comparison) | 129 | 2,550 B | 1.0s | 3.12.3 | same | 2 git-URL pins (`chatterbox-tts`, `resemble-perth`) |

All five freezes exited 0 with empty stderr (VERIFIED). Total for the four new freezes: **~11 KB**, **~6s** added to a backup that already takes ~1 min.

### Python version

All five venvs are on system Python 3.12.3 (`home = /usr/bin`, `include-system-site-packages = false`), so a `pip freeze` alone rebuilds them on this OS (VERIFIED). Recording the version is still worth doing: the venvs link to `/usr/bin/python3.12`, which is part of the OS package, so an OS upgrade silently breaks every venv at once and the freeze says nothing about which interpreter to rebuild with. Cheapest: also write `python3 --version` and a copy of `pyvenv.cfg` next to each freeze.

### What adding it would take (not done)

In `deploy/starship-backup.sh`, replace the single chatterbox block with a loop over five venvs:

```bash
for v in platform-runtime/.venv core/infrastructure/vm-processing/.venv scripts/self_improvement/.venv tools/supabase/.venv core/voice/chatterbox-venv; do
  n=$(echo "$v" | tr '/' '_')
  if [ -x "$REPO_ROOT/$v/bin/pip" ]; then
    "$REPO_ROOT/$v/bin/pip" freeze >"$STAGE/venv-freeze-$n.txt" 2>"$STAGE/venv-freeze-$n.err" || true
    "$REPO_ROOT/$v/bin/python3" --version >"$STAGE/venv-freeze-$n.python" 2>&1 || true
    cp "$REPO_ROOT/$v/pyvenv.cfg" "$STAGE/venv-freeze-$n.pyvenv.cfg" 2>/dev/null || true
  fi
done
```

Points to decide:
1. **stderr:** the existing chatterbox line uses `2>&1`, so a pip error becomes the "freeze". Send stderr to a separate file as above.
2. **Silent failure:** `|| true` means a venv that is broken or missing produces an empty/absent file with no log line. Suggest `log "venv freeze: <name> N pins"` or a `fail` on empty output, so a vanished venv shows in the backup log (this is the failure mode of the llmsec outage).
3. **Rename:** keeping `chatterbox-venv-freeze.txt` unchanged avoids breaking anything that reads it: UNKNOWN whether anything does. A grep of tracked code found only the backup script itself.
4. **Not captured by freeze:** extra index URLs (torch/CUDA wheels in the two big venvs) and the apt packages the venvs depend on. The tracked `requirements.txt` files exist for all four (`platform-runtime`, `vm-processing`, `scripts/self_improvement`, `tools/supabase`), so rebuild is `requirements.txt` + freeze as the exact-version reference. Whether those requirements files are complete relative to the freeze: UNKNOWN.
5. A provisioning script per venv (like `deploy/provision-llmsec-venv.sh`) is the real fix; freezes only make the rebuild possible.
