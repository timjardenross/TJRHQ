# llmsec venv restore — 2026-11-05

Cause: the 2026-11-03 disk clean-up removed `platform-runtime/.venv-llmsec` (gitignored, referenced by path from `core/security/llm_guardrails.py`). The model-router fails cloud dispatch closed when the venv is missing, so every Gemini/Mistral/`:cloud` route returned HTTP 500.

## Steps

| # | Step | Command | Result | Status |
|---|------|---------|--------|--------|
| 1 | Create venv | `python3 -m venv platform-runtime/.venv-llmsec` | created (Python 3.12.3) | VERIFIED |
| 2 | Install deps | `.venv-llmsec/bin/pip install -r core/security/requirements-llmsec.txt` | exit 0 | VERIFIED |
| 3 | Install spaCy small model | `pip install .../en_core_web_sm-3.8.0-py3-none-any.whl` | exit 0 | VERIFIED |
| 4 | Import + model load | `.venv-llmsec/bin/python3 -c "import presidio_analyzer, spacy; spacy.load('en_core_web_sm'); print('ok')"` | printed `ok` | VERIFIED |
| 5 | Restart router | `systemctl restart model-router` | active; takes ~7s before listening; `/health` = 200 | VERIFIED |
| 6 | Start self-improving-system | `reset-failed` + `start` | **1st attempt failed**: router not yet listening ("Connection refused"). 2nd start was a no-op: unit sat in its 5-min `auto-restart` wait. `stop` + `reset-failed` + `start` ran a real cycle | VERIFIED (after retry) |
| 7 | Self-improvement result | `journalctl -u self-improving-system` | 07:56:23 start, Phases 1-5 ran, `"success": true`, "Finished" 07:57:13, Result=success. Phase 5 skipped (model confidence / remediation disabled) — normal, not an error | VERIFIED |
| 8 | Guardrails request through router | `POST /api/model/intelligence-brief` (Gemini route, prompt contained a fake email + phone) | **HTTP 200**, `success: true`; router log: `llm_guardrails: redacted 6 PII/identifier finding(s)` (EMAIL_ADDRESS, PHONE_NUMBER, ...) then output rail `guardrail-check-output` ran. Took 46s (local qwen input/output rails). | VERIFIED |

Note on step 8: the model reply was `<ORGANIZATION>`, not "PONG" — Presidio redacted part of the test prompt. Plumbing works; the reply content is not meaningful.

## Outage window

- Last known good: self-improving-system run 2026-11-03 07:00 (Finished OK).
- First observed failure: **2026-11-04 03:01:05 AEDT** (model-router, task `hq-evolution-external-fit`).
- Last observed failure: **2026-11-05 07:24:09** (self-improving-system retry); intelligence-scheduler last error 2026-11-05 06:04:34.
- Fixed: 2026-11-05 ~07:51 (venv built), router restarted 07:53.
- Exact removal time: **UNKNOWN**. No callers hit the guardrails between the clean-up and 2026-11-04 03:01, so the first failure is only an upper bound on when the venv vanished.
- ~28h of observed failure.

## Self-improvement runs lost

| Run | Result |
|-----|--------|
| 2026-11-03 07:00 | OK (before outage) |
| 2026-11-04 07:03 (timer) + retries 07:08, 07:13, 07:18, 07:23, 07:28 | all failed; daily run **missed** |
| 2026-11-05 07:03 (timer) + retries 07:08, 07:13, 07:19, 07:24, 07:29 | all failed; daily run **missed** |
| 2026-11-05 07:56 (manual) | OK — today's cycle recovered. 11-04's cycle was not re-run |

## Affected services (journal count of `llmsec venv not found`, since 2026-11-03)

| Service | Count | Last error | Now |
|---------|-------|-----------|-----|
| model-router (20 distinct failed calls: hq-evolution-external-fit, hq-evolution-investigate, intelligence-brief, self-improvement-analyse) | 20 | 11-05 07:24 | healthy; test call 200 — VERIFIED |
| self-improving-system | 30 | 11-05 07:24 | success — VERIFIED |
| intelligence-scheduler (via `core/llm/provider_chain.py`; brief LLM + downdetector thresholds fell back/failed) | 66 | 11-05 06:04 | **no errors since router restart**, but no guarded call observed since either — UNKNOWN until next scheduled run |
| hq-evolution | 13 | 11-05 03:01 | next run not yet observed — UNKNOWN |

Other files referencing the guardrails (`core/content/draft_worker.py`, `core/engineering/*`, `mission-engineering-dispatch`, `engineering-batch-sync`): units inactive, 0 llmsec errors in journal. `phoenix.service`: 0 errors. No cron callers.

Only model-router, and self-improving-system were (re)started. Nothing else restarted. Nothing else removed.

## Follow-ups (not done)

1. The venv has no provisioning/health check; the clean-up will recur if nothing records it. Suggest a `scripts/` setup step plus a startup assertion or a `check-*.sh` health check for `.venv-llmsec`.
2. Other gitignored dirs referenced by path (e.g. the isolated garak venv used by `core/quality/garak_gate.py`) were not checked for the same clean-up; worth auditing. I did not touch them.
3. 2026-11-04's self-improvement cycle was not backfilled.
4. Router needs ~7s to listen after restart; units that health-check it on start (self-improving-system) fail if started inside that window.
5. `systemctl start` on a unit in `auto-restart` wait does nothing — use `stop` first.
