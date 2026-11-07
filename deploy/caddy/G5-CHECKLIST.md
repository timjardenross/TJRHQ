# SEC-01 G5 validation checklist (non-executing)

Run only after G3 and G4 are separately authorised and deployed. Every probe below is
non-mutating: GET, HEAD or OPTIONS, or a POST with a synthetic header that is refused before any handler runs.

## Preconditions
- [ ] Secret rotated; old credential retired (see rotation runbook).
- [ ] Caddy log redaction live: no new access-log line contains the secret header value.
- [ ] PR #604 alert-state locking present on main (`grep -c _state_lock tools/alert_on_systemd_failure.py`).
- [ ] Caddy config sha256 matches the approved candidate; `caddy validate` passes.

## Both public hostnames (run for each of 109-123-227-196.sslip.io and 109.123.227.196, `-k` for the internal CA)
- [ ] GET /self-improvement/api/{findings,opportunities,evolution-summary,mission-dispatch-status,engineering-handoffs,status} with no header -> 401
- [ ] GET the same with a synthetic wrong header -> 401
- [ ] OPTIONS on each write path, with and without a header -> 403
- [ ] POST on a write path with no header -> 403 (Caddy); with a synthetic wrong header -> 401 (Flask)
- [ ] PUT/PATCH/DELETE on a write path -> 403

## Loopback (on the VM, non-mutating)
- [ ] GET http://127.0.0.1:8892/api/status with no header -> 401
- [ ] OPTIONS /api/decide with a synthetic wrong header -> 401

## Owner accounts (browser, read-only, separate authorisation required)
- [ ] outlook.com: findings, evolution tile, handoffs tab load data
- [ ] outlook.sg: the same three checks
- [ ] No decision, approve or reject control is pressed

## Logs and integrity
- [ ] Journal since cutover: no 503 responses, no tracebacks, no secret value (checked in memory, count only)
- [ ] PR #604 alert-state file unchanged by probes (mtime and owner unchanged)

## Rollback readiness (verify, do not execute)
- [ ] Redacted v2 backup saved outside the repo by backup_known_good.sh; sha256 is 1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6
- [ ] Rollback is NOT sourced from any Caddyfile.bak.pre-sec01* file (pre-redaction)
- [ ] Deployed v3 sha256 recorded and passed as V3_SHA; rollback_v2.sh dry-run shows the plan
- [ ] Drift procedure understood: a mismatched live file is copied for review, never overwritten
- [ ] caddy validate passes before any reload
- [ ] Previous Vercel production deployment ID recorded
- [ ] Scoped restart commands recorded for self-improvement-dashboard.service and lcars-portal.service
