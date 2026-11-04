# Unit installs — 2026-11-05 (second batch, no restarts)

Source: clean worktree of `origin/main` @ `09ace768b` (#583). No service or timer was started, stopped or restarted by me. Rollback copies preserve path, mode, owner and mtime (`cp -a --parents`) under `/root/unit-rollback-2026-11-05b/etc/systemd/system/`. VERIFIED = observed this session.

## 0. Pull and check

| Check | Result | Status |
|---|---|---|
| #572, #575, #576, #578, #580, #582 | all MERGED | VERIFIED |
| `deploy/self-improving-system.service` has the `ExecStartPre` router wait | 1 match for `ExecStartPre=.*8891/health` | VERIFIED |
| `deploy/command-bus.service` has no `EnvironmentFile=` | 0 active lines | VERIFIED |
| `tests/test_timer_units_no_requires.py` exists | yes (#581) | VERIFIED |

The live checkout `/opt/starship-endeavour` was already at `09ace768b` (auto-deploy pulls); I read from a separate worktree to keep it clean.

## 1. The 17 `After=docker.service` units

List from `unit-drift-and-venv-freeze-20261105-e3a770c0.md`: capture-enrichment, context-service, daily-ops-cycle, engineering-batch-sync, health-osint-collection, intelligence-scheduler, lcars-portal, mission-registry-sync, model-router, self-improvement-dashboard, tg-capacitybot, tg-resiliencebot, tg-xo, verification-engine, vm-processing, vm-processing-retry, vm-processing-healthcheck (17).

Test applied: strip ` docker.service` from the repo file's `After=` line; the result must be byte-identical to the installed file. **All 17 passed; none skipped.** None was a symlink. Installed with `install -m 644 -o root -g root` (the installed mode/owner), then `cmp` repo == installed.

## 2. Reconciled units

| Unit | Expected | Observed | Action |
|---|---|---|---|
| auto-deploy | identical | identical (`cmp`) | none needed |
| self-improving-system | identical | identical (`cmp`) | none needed |
| governance-cache-sweep | only `After=` differs | only `After=network-online.target` -> `... docker.service` | installed |

## 3. command-bus

Diff, installed vs repo, non-comment lines: exactly the three `EnvironmentFile=-` lines removed (`/opt/starship-endeavour/.env`, `.../platform-runtime/.env`, `.../telegram-bot/.env`); the repo adds only a comment. Installed. **Not restarted**: pid **2800257** before and after, `active`, `NRestarts=0`, running since 2026-11-01 13:14:38 (VERIFIED). It keeps its current environment and the new unit applies at its next natural restart.

## 4. The 11 timers (only `Requires=` removed from the installed copy)

Method: `sed -i '/^Requires=/d'` on the installed file; no repo file was copied over. After each: `grep -c '^Requires='` = 0 and `diff` against the rollback copy shows exactly one deleted line (the `Requires=` line).

| Timer | Differences vs repo file other than `Requires=` | Requires removed | diff vs backup |
|---|---|---|---|
| capture-enrichment | none | yes | 1 line |
| daily-ops-cycle | none | yes | 1 line |
| deadmans-switch | none | yes | 1 line |
| engineering-batch-sync | none | yes | 1 line |
| hq-evolution | comment-only: header comments describe the 07:00 collision differently (installed older wording). No schedule difference | yes | 1 line |
| **self-improving-system** | **schedule differs**: installed `OnCalendar=*-*-* 07:00:00`; repo `OnCalendar=*-*-* 04:30:00` (HQ V1 QA §23 change, plus a long comment). **Installed schedule left at 07:00; repo not copied.** | yes | 1 line |
| verification-engine | none | yes | 1 line |
| vm-processing-healthcheck | none | yes | 1 line |
| vm-processing-retry | none | yes | 1 line |
| vm-processing | none | yes | 1 line |
| mission-engineering-dispatch | none (see below) | already absent | not touched |

**mission-engineering-dispatch.timer is a symlink** (`/etc/systemd/system/... -> /opt/starship-endeavour/deploy/mission-engineering-dispatch.timer`). `sed -i` would have replaced the symlink with a regular file, or (with `--follow-symlinks`) edited a git-tracked file. The target is the live checkout, which is already at the merged `main`, so it already has no `Requires=` (count 0, VERIFIED). Nothing to do; left as is. It stays inactive/paused as intended.

**Schedule drift for the Captain:** `deploy/self-improving-system.timer` says 04:30 but the VM runs 07:00 (next run Fri ~07:03). Installing the repo timer would move it; I did not. Decide which is right and update either the repo or the VM.

## 5. Reload and verification

| Check | Result | Status |
|---|---|---|
| `systemctl daemon-reload` | once, 09:35:17-09:35:19 | VERIFIED |
| `NeedDaemonReload=no` for every touched unit | 32 units checked (19 services replaced, 2 identical services, 10 timers sed-ed, mission-engineering-dispatch.timer); 0 with `yes` | VERIFIED |
| `systemctl cat` | tg-xo `After=network.target docker.service`; model-router `After=network.target ollama.service docker.service`; governance-cache-sweep `After=network-online.target docker.service`; command-bus 0 `EnvironmentFile=`; hq-evolution.timer 0 `Requires=`; self-improving-system.timer still `OnCalendar=*-*-* 07:00:00` | VERIFIED |
| Timers listed | 38 before, 38 after. All 11 present and `active` except mission-engineering-dispatch (`inactive`, next `-`, last 2026-10-28, as intended) | VERIFIED |
| Next-run times | same dates and slots; moved by seconds to ~2 min, e.g. self-improving-system Fri 07:04:25 -> **07:02:46**, hq-evolution 03:02:49 -> 03:02:50, daily-ops-cycle 06:51:34 -> 06:52:28. Cause: reload re-rolled each timer's `RandomizedDelaySec` (capture-enrichment/vm-processing 30s, retry 120s, daily-ops/hq 3 min, self-improving 5 min). Not identical, as you asked "same"; all inside their delay windows | VERIFIED (times) / explanation inferred from `RandomizedDelaySec` values |
| `pytest tests/test_infisical_unit_ordering.py tests/test_timer_units_no_requires.py -q` | **3 passed** | VERIFIED |

### Restarts that were not mine

Several services show start times around 09:28-09:29 (context-service, intelligence-scheduler, model-router, self-improvement-dashboard, tg-capacitybot, tg-resiliencebot, human-systems-scheduler, tg-xo, mint-server). Those were **auto-deploy** (`deploy` user, `scoped-restart.sh`) after #583 merged: "is stale (running since before the newest repo commit)", 09:28:44-09:28:58. My installs landed at 09:35:06 and the reload at 09:35:17, i.e. after, so they did not cause any restart and those services restarted with the old unit text. All are `active`; router `/health` = 200 (VERIFIED). Because of this, the units are running with definitions that now match disk (no restart needed for the `After=` change; it only affects ordering at boot).

Unrelated and pre-existing: `systemd-networkd-wait-online.service` is failed (since 2026-10-21, boot-time); the only failed unit.

## Table: unit, action, result, rollback

Rollback root: `/root/unit-rollback-2026-11-05b/etc/systemd/system/<file>`; to roll back copy the file back (`cp -a`) and run `systemctl daemon-reload`.

| Unit | Action | Result | Rollback file |
|---|---|---|---|
| capture-enrichment.service | installed | `After=` +docker | `capture-enrichment.service` |
| context-service.service | installed | same | `context-service.service` |
| daily-ops-cycle.service | installed | same | `daily-ops-cycle.service` |
| engineering-batch-sync.service | installed | same | `engineering-batch-sync.service` |
| health-osint-collection.service | installed | same | `health-osint-collection.service` |
| intelligence-scheduler.service | installed | same | `intelligence-scheduler.service` |
| lcars-portal.service | installed | same | `lcars-portal.service` |
| mission-registry-sync.service | installed | same | `mission-registry-sync.service` |
| model-router.service | installed | same | `model-router.service` |
| self-improvement-dashboard.service | installed | same | `self-improvement-dashboard.service` |
| tg-capacitybot.service | installed | same | `tg-capacitybot.service` |
| tg-resiliencebot.service | installed | same | `tg-resiliencebot.service` |
| tg-xo.service | installed | same | `tg-xo.service` |
| verification-engine.service | installed | same | `verification-engine.service` |
| vm-processing.service | installed | same | `vm-processing.service` |
| vm-processing-retry.service | installed | same | `vm-processing-retry.service` |
| vm-processing-healthcheck.service | installed | same | `vm-processing-healthcheck.service` |
| governance-cache-sweep.service | installed | `After=` +docker | `governance-cache-sweep.service` |
| command-bus.service | installed (no restart) | 3 `EnvironmentFile=` removed | `command-bus.service` |
| auto-deploy.service | skipped: already identical | none | n/a |
| self-improving-system.service | skipped: already identical | none | n/a |
| *.timer x10 (capture-enrichment, daily-ops-cycle, deadmans-switch, engineering-batch-sync, hq-evolution, self-improving-system, verification-engine, vm-processing-healthcheck, vm-processing-retry, vm-processing) | sed (`Requires=` deleted) | 0 `Requires=`; 1-line diff each | `<name>.timer` |
| mission-engineering-dispatch.timer | skipped: symlink into live checkout, already no `Requires=` | untouched | n/a |

29 files backed up (19 services + 10 timers). Mode and owner of every replaced file: 644 root:root (VERIFIED on a sample of six).

## Skipped / open

1. mission-engineering-dispatch.timer: symlink, already compliant (above).
2. self-improving-system.timer: 07:00 on the VM vs 04:30 in the repo; not changed.
3. Still-untouched drift from the earlier report: human-systems-scheduler (repo ahead, installed uses a drop-in), starship-meilisearch (inline master key on the VM), and the units not on this list.
4. Pending from the previous brief: `/root/verify-backup-after-0245.sh` after 02:45 Fri, and the self-improving-system check after its next run (now ~07:03 Fri, not 07:04).
