# DEPRECATED — 2026-07-29

Retired. This was a second, parallel self-improvement implementation
(`scripts/self_improving_loop.py` + `systemd/self-improving-loop.{service,timer}`)
that duplicated `scripts/self_improvement/orchestrator.py`. Two independently
loaded self-improvement systems violated the "canonical over convenient"
governance principle (Issue 11, VM audit 2026-07-29).

## Why this one, not orchestrator.py

- **Never actually deployed.** `systemctl cat self-improving-loop.service` on the
  VM returns not-found — no unit file was ever copied to `/etc/systemd/system/`,
  despite `docs/self-improvement/VM-DEPLOYMENT.md` and `README.md` describing it
  as the production path. Not in root's crontab either. Zero risk of duplicate
  or conflicting writes with the canonical system — it has never run outside a
  developer's local invocation.
- **Stale.** Last touched 2026-07-12 (`e39751e`, `3b07892`). `orchestrator.py`
  has commits through 2026-07-17 (run-dir fix, `classify_finding` API fix),
  reflecting live production use this file never got.
- **Canonical system is live and active.** `self-improving-system.service`
  (runs `scripts/self_improvement/orchestrator.py`) is triggered daily 07:00
  local by `self-improving-system.timer` (enabled), writes real findings to
  `/tmp/usstjros-findings/runs/<run_id>/`, and is fronted by
  `self-improvement-dashboard.service` (port 8892, enabled+active). Confirmed
  a real run completed 2026-07-29 07:01 with 4 findings, 100% model confidence.

## Shared module directory — not touched

Both implementations imported from `scripts/self_improvement/` (`collector.py`,
`router_client.py`, `policy.py`, `decision_processor.py`, `auto_remediation.py`,
`dashboard.py`). That directory is the canonical orchestrator's own module set
and stays in place. This file's import (`policy.classify_findings`, plural) is
a different/older entry point than what `orchestrator.py` now calls
(`PolicyEngine.classify`, per the 2026-07-12 `classify_finding` singular fix) —
another sign this path had drifted out of sync with the live implementation.

**Not deleted outright** — quarantined (renamed, not removed) to preserve a
recovery window, matching repo convention (see `telegram-bot.DEPRECATED-2026-07-12/`).
