# Knowledge Record — USS-TJR-MSN-0371 (Stream 1: pilot + runbook)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0371 |
| Title | Retire .env as a production secret source — Stream 1 (pilot) |
| Date | 2026-09-12 |
| Follows | Stream 0 audit (`USS-TJR-MSN-0371-stream0-secrets-audit-knowledge-record.md`) |
| Pilot service | `verification-engine.service` (oneshot, timer-triggered every 5 min, no user-facing impact) |

## Pre-req: wrapper fix (before any pilot could safely run)

`run-with-infisical.sh` originally passed the minted access token via
`infisical run --token="$TOKEN"` — visible in plain `ps aux` /
`/proc/<pid>/cmdline` to any local user, no root needed. Confirmed this CLI
build (`0.42.6`) accepts the same value via the `INFISICAL_TOKEN` env var
instead (string literal present in the binary; tested directly — works
identically). Changed the wrapper to `export INFISICAL_TOKEN=...` and drop
`--token=` from the `infisical run` call. Token now only reachable via
`/proc/<pid>/environ` (root/same-UID only) — same exposure level as every
other secret on this host, not worse. This fix applies to every future
migrated service, not just the pilot; already covers `chatterbox-tts` and
`intelligence-scheduler`, which use this same script.

## Cutover procedure (the reusable runbook)

1. In `deploy/<service>.service`, comment out the `EnvironmentFile=` line
   (don't delete — this is the rollback path) and wrap `ExecStart` through
   `run-with-infisical.sh`:
   ```
   # EnvironmentFile=/opt/starship-endeavour/platform-runtime/.env
   ExecStart=/bin/sh -c '/opt/starship-endeavour/platform-runtime/run-with-infisical.sh <original command> ...'
   ```
   Note the exact quoting if `ExecStart` is already a `/bin/sh -c '...'`
   wrapper (as most oneshots here are) — the infisical wrapper goes
   *inside* that string, before the original binary, not around the whole
   `sh -c`.
2. Copy to `/etc/systemd/system/<service>.service`, then
   `systemctl daemon-reload`.
3. `systemctl start <service>` (works for oneshots; for long-running
   services use `restart`).
4. Check `systemctl status` for `code=exited, status=0/SUCCESS` (oneshot)
   or `active (running)` (long-running), and check the service's own log
   for errors. No missing-env-var errors = pass.
5. Prove live sourcing, not a cached read: push a throwaway probe key to
   Infisical prod (`infisical secrets set PILOT_PROBE=v1 --env=prod`),
   confirm the wrapper surfaces it
   (`run-with-infisical.sh sh -c 'echo $PILOT_PROBE'`), rotate it
   (`set PILOT_PROBE=v2`), confirm the new value shows on the next
   invocation with no restart of anything needed to "pick it up" — the
   wrapper does a fresh `infisical login` + `infisical run` every
   invocation, so there is no cache to bust. **Delete the probe key
   afterward** (`infisical secrets delete PILOT_PROBE --type=shared
   --env=prod`) — don't leave test junk in the prod project.
   For a service whose own code doesn't read arbitrary env vars (like this
   pilot — it only reads one URL var, unset, code-default), the probe
   check validates the wrapper mechanism directly rather than through the
   service's business logic; that's sufficient, since the mechanism is
   what's shared across every future migration.

## Pilot results — verification-engine.service

| Check | Result |
|---|---|
| ExecStart wraps run-with-infisical.sh | done, `deploy/verification-engine.service` + live unit |
| Old EnvironmentFile= preserved, commented | done (rollback = revert this diff + daemon-reload + restart) |
| daemon-reload + manual start | `code=exited, status=0/SUCCESS` |
| No missing-env-var errors | confirmed, log wrote its normal JSON output (verification_state row, capacity check-ins) same as before |
| Live-not-cached proof | `PILOT_PROBE` v1→v2 rotation both confirmed via direct wrapper invocation |
| Unattended timer fire (not manually triggered) | **not yet observed this pass** — timer fires every 5 min; next natural fire will exercise this without any Claude intervention. Flagging as the one box not literally ticked this session — recommend a quick `journalctl -u verification-engine.service --since -10min` check before calling the pilot fully closed. |

## Note: repo file briefly appeared reverted mid-session

A `<system-reminder>` fired saying `deploy/verification-engine.service`
"changed on disk" back to the pre-edit content, right after the edit was
made. Checked immediately: `git diff` and a direct re-read both showed the
edit intact — false alarm, not an actual revert by a concurrent session.
Worth noting because this repo has 5 concurrent root SSH sessions active
right now (`w` showed 5 logged-in root sessions besides this one) and this
exact shared-checkout collision risk is already a known issue here (see
memory: git shared-worktree collision, 2026-08-12). This time nothing was
actually lost, but the next stream's execution should watch for it for
real, not assume it's always a false alarm.

## Not done this pass

- Did not confirm the pilot's *unattended* timer-triggered run (only the
  manually-triggered one) — see table above.
- Did not touch any other service. Streams 2-5 are still blocked on: (a)
  this runbook being reviewed, and (b) the Stream 0 scope revision
  (real 38-service inventory, not the brief's 21) being confirmed before
  picking which services go in which group.
- Did not yet commit `intelligence-scheduler.service`'s pre-existing live
  drift back to the repo (flagged in Stream 0, still open).
- Did not fix `chatterbox-tts.service`'s token-on-cmdline exposure
  specifically — the wrapper fix above covers it going forward since that
  service already uses the same script, but its live process (PID 455997)
  won't inherit the fix until it's restarted.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KTwCophMNST95DQdnh4nQU
