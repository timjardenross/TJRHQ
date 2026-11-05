# llmsec follow-ups — 2026-11-05

Follows `reports/vm-audit/llmsec-venv-restore-20261105-d66b83db.md`. Read-only except for the Item 3 PR (#572, separate). Nothing restarted, installed or removed. Snapshot taken ~08:17 AEDT, main at `665edb1b8`.

## Item 1 — unchecked callers (read-only)

| Check | Result | Status |
|---|---|---|
| `deploy/provision-llmsec-venv.sh --check` | `llmsec venv OK: /opt/starship-endeavour/platform-runtime/.venv-llmsec`, exit 0 | VERIFIED |
| model-router `llmsec venv not found` since 07:53 | **0** | VERIFIED |
| intelligence-scheduler `llmsec venv not found` since 07:53 | **0** | VERIFIED |
| intelligence-scheduler: guarded call since 07:53 | **None has happened.** Only ingestion/collection jobs and the 5-min brief-readiness poll ran. No LLM provider-chain call logged. | VERIFIED (none yet) |
| hq-evolution: run since 07:53 | **None.** Last run 03:00:31-03:01:30 today (Finished OK, but that was before the fix; its guarded calls in that run failed, see restore report). | VERIFIED (none yet) |

Notes:
- **intelligence-scheduler was restarted twice, not by me:** 08:02:19 and 08:12:22. The 08:12 one is auto-deploy ("stale, running since before the newest repo commit", after #571 merged). It is running now (since 08:12:32).
- Next guarded calls (from `intelligence/scheduler.py` cron triggers; I did not see these fire):

| Caller | Next due | Path |
|---|---|---|
| intelligence-scheduler `_downdetector_threshold_recompute_job` | **Fri 2026-11-06 05:00** | `downdetector_thresholds.py` -> `core/llm/provider_chain.py` |
| intelligence-scheduler `_eod_brief_job` | **Thu 2026-11-05 18:00** (earliest brief LLM call) | brief `llm_provider` |
| intelligence-scheduler `_morning_brief_job` | Fri 2026-11-06 07:00 | brief `llm_provider` |
| hq-evolution.timer | **Fri 2026-11-06 03:00:53** | router `hq-evolution-*` tasks |

Both stay **UNKNOWN** until those runs. Neither had a failure after 07:53, so the STOP condition was not triggered.

## Item 2 — gitignored directories referenced by path (read-only)

`git status --ignored` shows 178 ignored entries; table covers directories >50 MB, named `.venv*`/`node_modules`, or referenced from tracked code. `__pycache__`, `.pytest_cache`, `logs/`, `outputs/` etc. are not path dependencies and are omitted.

### Garak venv (asked first)

`platform-runtime/.venv-garak` **does not exist** (no copy anywhere on disk to depth 4). **VERIFIED missing.** Whether it ever existed on this VM, or was removed by the 11-03 clean-up: **UNKNOWN**.

- Used by: `core/quality/garak_gate.py` (`VENV_PYTHON`, `VENV_GARAK`), `tools/garak_sweep.sh`.
- Callers: no systemd unit, timer or cron in `/etc/systemd/system` or crontab invokes garak/ragas/deepteam. `python-ci.yml` only mentions them in comments (CI builds no `.venv-garak`). So the gate is **manual-only**; nothing is failing today. Last gate run artefacts: `reports/garak/gate-20260913*` (12-13 Sept).
- `import garak` health check: not possible, venv absent.
- Provisioned? **UNPROVISIONED.** Only docs (`platform-runtime/README.md`, mission record) and the error text of `garak_sweep.sh` describe how to build it.
- What breaks: the pre-activation gate for the model-router cannot run (exits with "dedicated garak venv not found").

### Table

Status: PROVISIONED = a tracked script/CI builds it; UNPROVISIONED = referenced, built only by hand/docs; UNREFERENCED = nothing in tracked code points at it.

| Directory | Size | Referenced by | Exists & healthy | What breaks if missing | Provisioned? |
|---|---|---|---|---|---|
| `platform-runtime/.venv-llmsec` | 580 MB | `core/security/llm_guardrails.py` (model-router cloud dispatch) | yes; `--check` OK — VERIFIED | all guarded cloud routes 500 (the 11-03 outage) | **PROVISIONED** `deploy/provision-llmsec-venv.sh` (+ CI step in `python-ci.yml`) |
| `platform-runtime/.venv-garak` | n/a | `core/quality/garak_gate.py`, `tools/garak_sweep.sh` | **NO** — VERIFIED | garak gate/sweep cannot run (manual-only) | **UNPROVISIONED** |
| `platform-runtime/.venv-docling` | n/a | `core/knowledge/docling_processor.py`, `tools/supabase/docling_ingest.py` | **NO** — VERIFIED | docling PDF ingest (on-demand only). `scripts/self_improvement/collector.py` only names it in a find-prune comment | **UNPROVISIONED** (README only) |
| `platform-runtime/.venv-ragas` | n/a | `core/quality/ragas_eval.py` | **NO** — VERIFIED | RAGAS eval (manual) | **UNPROVISIONED** (README only) |
| `.venv-deepteam` (name only) | n/a | `core/quality/deepteam_scan.py` | **NO** (not on disk) — VERIFIED | deepteam scan (manual) | **UNPROVISIONED** |
| `platform-runtime/.venv` | 6.7 GB | 76 files incl. most units (`intelligence-scheduler`, etc.) | yes; python 3.12.3, `import anthropic` OK — VERIFIED | most platform services | **UNPROVISIONED** (no script found; created by hand; README steps only). Biggest single risk. |
| `core/voice/chatterbox-venv` | 6.4 GB | `deploy/chatterbox-tts.service` | yes; python 3.12.3 — full import UNKNOWN | TTS service | **UNPROVISIONED**; `deploy/starship-backup.sh` states it is **not backed up** |
| `core/infrastructure/vm-processing/.venv` | 5.6 GB | `vm-processing*.service` (3 units) | yes; python 3.12.3 — deps UNKNOWN | vm-processing + retry + healthcheck (memory notes this was already "stuck") | **UNPROVISIONED** (README only) |
| `telegram-bots/xo/.venv` | 957 MB | `deploy/tg-xo.service` | yes; python 3.12.3 | XO bot | **PROVISIONED** `telegram-bots/xo/start.sh` creates it if missing |
| `telegram-bots/capacitybot/.venv` | 77 MB | `deploy/tg-capacitybot.service` | yes; python 3.12.3 | Capacitybot | **PROVISIONED** `start.sh` |
| `telegram-bots/resiliencebot/.venv` | 38 MB | `deploy/tg-resiliencebot.service` | yes; python 3.12.3 | Resiliencebot | **PROVISIONED** `start.sh` |
| `scripts/self_improvement/.venv` | 24 MB | `deploy/hq-evolution.service` (ExecStart + PATH), `self-improvement-dashboard.service` (4 tracked refs total) | yes; python 3.12.3; `evolution_orchestrator` imports OK — VERIFIED | hq-evolution + dashboard + self-improvement | **UNPROVISIONED** (`requirements.txt` exists, no builder found) |
| `tools/supabase/.venv` | 266 MB | `tools/supabase/commander_synthesis.py`, README | yes; python 3.12.3 | dual-commander run (manual) | **UNPROVISIONED** (README: "create first with python3 -m venv") |
| `lcars-portal/node_modules` | 830 MB | `lcars-portal.service`, CI | yes; `.bin/next` present — VERIFIED | portal build/run | **PROVISIONED** `auto-deploy.sh` runs `npm ci`; `lcars-portal-ci.yml` |
| `lcars-portal/.next` | 540 MB | `lcars-portal.service` | yes; `BUILD_ID` present — VERIFIED | portal serves nothing until rebuilt | **PROVISIONED** `auto-deploy.sh` runs `npm run build` |
| `core/command-centre/backend/node_modules` | 5 MB | not path-referenced | yes | n/a | UNREFERENCED (by path) |
| `outputs/` | 38 MB | none by path found | yes | n/a | UNREFERENCED |
| `core/voice/cache/` | 31 MB | none by path found | yes | n/a | UNREFERENCED (cache) |
| `deploy/watchlist-data/` | 15 MB | none by path found | yes | n/a | UNREFERENCED |
| `.cortex/apigraph/` | 12 MB | none by path found | yes | n/a | UNREFERENCED |

UNREFERENCED means no tracked `.py/.sh/.service/.ts/.yml` hit for the path. It is **not** a recommendation to remove anything; that is the Captain's call and nothing was deleted or moved.

### Findings

1. **Three venvs are referenced but absent** (`.venv-garak`, `.venv-docling`, `.venv-ragas`, plus `.venv-deepteam`): all manual/on-demand tools, so nothing live is failing. Cause (never built vs removed 11-03) is UNKNOWN.
2. **Highest-risk UNPROVISIONED directories, all live:** `platform-runtime/.venv` (6.7 GB, most services), `core/voice/chatterbox-venv` (6.4 GB, not in backups), `core/infrastructure/vm-processing/.venv` (5.6 GB), `scripts/self_improvement/.venv` (hq-evolution). A clean-up of any of these takes down running services, the same shape as the llmsec outage. Suggest the same `provision-*.sh --check` treatment, starting with `platform-runtime/.venv`.
3. Only the llmsec venv, the three telegram bot venvs and the portal build are rebuilt by tracked code.

## Item 3 — wait for router

Separate draft PR: **#572** (`deploy/self-improving-system.service`, +8 lines, one `ExecStartPre`).

| Check | Result | Status |
|---|---|---|
| `systemd-analyze verify deploy/self-improving-system.service` | exit 0; only repo-wide "marked executable" warnings | VERIFIED |
| `python -m pytest tests/test_infisical_unit_ordering.py -q` (platform-runtime/.venv; system python has no pytest) | 2 passed | VERIFIED |
| Snippet vs live router | exit 0, 0.03s | VERIFIED |
| Snippet vs dead port | 31s, one warning line, exit 0 | VERIFIED |
| Fix works against a real router restart | not exercised; unit not installed, nothing restarted | UNKNOWN |

Flags raised in the PR:
- **Installed unit has drifted from the repo file** (installed ExecStart is wrapped in `run-with-infisical.sh`; repo is not). Installing the repo file verbatim would drop the wrapper. Not changed here.
- The unit had no `After=`/`Wants=` on model-router, so there was nothing to preserve and none was added.
- Same race exposure (not changed): `hq-evolution` (oneshot, `Persistent=true` timer, 03:00; moderate), `intelligence-scheduler` (long-running, `Restart=always`; low).

## Summary

- Item 1: provisioning check OK, zero new llmsec failures anywhere since 07:53. Both callers UNKNOWN until 18:00 today / 03:00-05:00 tomorrow.
- Item 2: garak venv missing (manual tool, nothing failing); 3 more absent tool venvs; 4 big live venvs unprovisioned.
- Item 3: PR #572 open (draft, unmerged).
