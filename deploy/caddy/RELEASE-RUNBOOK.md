# SEC-01 Production Release Runbook (Caddy v3 and secret rotation)

## 0. Scope and status

- **PRODUCTION NOT AUTHORISED.** Every step needs the Captain's explicit go, given per step.
- This document is not approval. Reading it authorises nothing.
- Scope: Caddy v2 to v3 (self-improvement write containment), rotation of `SELF_IMPROVEMENT_API_SECRET`, G4 activation, G5 validation.
- Companions: `deploy/caddy/README-v3.md` (gate, rollback, drift), `rollback_v2.sh`, `backup_known_good.sh`, `g5_validate.sh`, `validate_v3.sh`.
- Hosts: `109-123-227-196.sslip.io`, `109.123.227.196`.
- Hashes and identifiers:
  - Live redacted v2 baseline: `1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6`
  - v3 candidate `deploy/caddy/Caddyfile.v3`: `a90ce2d7890086a5fdb8a3a59bd9ec9e9f71baceb558d09ed9d9513fc40f267e`
  - Captain key fingerprint: `6E5C773E0397E30F8EA620C907B59F541DB268BE`
- Forbidden rollback source: `/etc/caddy/Caddyfile.bak.pre-sec01*` (pre-redaction; restoring re-enables secret-header logging).
- `<...>` marks a placeholder filled at authorisation. Secret values never appear in argv, output, logs or this file. `STOP` = halt and report to the Captain.

## 1. Preconditions (all must pass, or STOP)

```bash
# 1.1 PR #605 head and CI green (record head as <PR605_HEAD>)
gh pr view 605 --json headRefOid,state,statusCheckRollup    # all conclusions SUCCESS
# 1.2 live Caddyfile is the redacted v2 baseline
sha256sum /etc/caddy/Caddyfile                              # 1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6
# 1.3 PR #604 markers on main
git -C <repo-clone> show origin/main:tools/alert_on_systemd_failure.py | grep -c _state_lock   # >= 1
# 1.4 alert-state file untouched (compare with baseline hash in authorisation record)
sha256sum <alert-state-file>
# 1.5 no concurrent deploys
vercel ls | grep -ci building                                # 0
# 1.6 Captain runs on the Mac and reports:
gpg --show-keys --fingerprint <captain-key-id>               # 6E5C773E0397E30F8EA620C907B59F541DB268BE
# 1.7 v3 offline gate (README-v3 deployment gate items 4 and 6)
cd <repo-clone> && bash deploy/caddy/validate_v3.sh
sha256sum deploy/caddy/Caddyfile.v3                          # a90ce2d7890086a5fdb8a3a59bd9ec9e9f71baceb558d09ed9d9513fc40f267e
```

## 2. Backup redacted v2

```bash
cd <repo-clone>
deploy/caddy/backup_known_good.sh                # dry-run, writes nothing
sudo deploy/caddy/backup_known_good.sh --apply
sha256sum /root/.sec01-caddy-rollback/Caddyfile.v2-redacted-1a309347
```

Pass: prints `1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6`. STOP on refusal or mismatch. Source is `/etc/caddy/Caddyfile` only.

## 3. Rotation phase (one maintenance window, owners notified)

Write routes are unavailable from 3d until section 4 passes.

3a. Encrypted rollback backup of the CURRENT secret, before any write.

```bash
install -d -m 0700 /root/.sec01-secret-rollback
umask 077
<infisical-read-command-value-to-stdout-only> \
  | gpg --batch --yes --encrypt -r 6E5C773E0397E30F8EA620C907B59F541DB268BE \
      --output /root/.sec01-secret-rollback/self-improvement-secret.pre-rotation.gpg
chmod 0600 /root/.sec01-secret-rollback/self-improvement-secret.pre-rotation.gpg
```

Expiry timer needs separate authorisation. Without it, the ciphertext persists until `shred -u <file>` on Captain instruction.

3b. New secret from a CSPRNG into a 0600 file. Never printed, never in argv.

```bash
umask 077
python3 -I -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(48))' > /root/.sec01-secret-rollback/new.tmp
chmod 0600 /root/.sec01-secret-rollback/new.tmp
```

3c. Infisical prod root `SELF_IMPROVEMENT_API_SECRET` via API PATCH. Value on stdin; auth in a 0600 curl config, not argv. Then readback equality in memory (boolean only).

```bash
python3 -I -c 'import json,sys; v=open(sys.argv[1]).read(); sys.stdout.write(json.dumps({"workspaceId":"<WS_ID>","environment":"prod","secretPath":"/","secretValue":v}))' \
  /root/.sec01-secret-rollback/new.tmp \
  | curl -sS --config /root/.sec01-secret-rollback/infisical.curl -X PATCH --data-binary @- \
      "<INFISICAL_API_BASE>/api/v3/secrets/raw/SELF_IMPROVEMENT_API_SECRET" -o /dev/null -w '%{http_code}\n'
curl -sS --config /root/.sec01-secret-rollback/infisical.curl \
  "<INFISICAL_API_BASE>/api/v3/secrets/raw/SELF_IMPROVEMENT_API_SECRET?workspaceId=<WS_ID>&environment=prod&secretPath=%2F" \
  | python3 -I -c 'import json,sys; got=json.load(sys.stdin)["secret"]["secretValue"]; print("readback_equal", got==open(sys.argv[1]).read())' \
      /root/.sec01-secret-rollback/new.tmp
```

Pass: PATCH `200`; `readback_equal True`. STOP otherwise.

3d. Vercel production and preview. Value on stdin only. STOP if the installed CLI rejects stdin for `env update`.

```bash
vercel env update SELF_IMPROVEMENT_API_SECRET production --sensitive -y < /root/.sec01-secret-rollback/new.tmp
vercel env update SELF_IMPROVEMENT_API_SECRET preview --sensitive -y < /root/.sec01-secret-rollback/new.tmp
```

3e. Production redeploy from the CURRENT production deployment's source commit; poll until `READY`. STOP on `ERROR` or `CANCELED`.

```bash
vercel redeploy <current-production-deployment-url> --target production --no-wait
vercel inspect <new-deployment-url>              # repeat until READY
```

3f. Immediately on READY, restart ONLY these two services. Both must be `active`.

```bash
/opt/deploy-guard/scoped-restart.sh restart self-improvement-dashboard.service
/opt/deploy-guard/scoped-restart.sh restart lcars-portal.service
systemctl is-active self-improvement-dashboard.service lcars-portal.service
```

3g. Bulk_decide operator re-exports the value at run time (never printed). Then destroy staging.

```bash
infisical run --env=prod -- <bulk_decide-operator-invocation>
shred -u /root/.sec01-secret-rollback/new.tmp
```

## 4. Propagation verification (no secret printed)

```bash
# 4.1 dashboard runtime env equals Infisical (boolean only; use child PID via pgrep -P if the unit uses infisical run)
PID="$(systemctl show -p MainPID --value self-improvement-dashboard.service)"
<infisical-read-command-value-to-stdout-only> | python3 -I -c '
import sys
env = open(f"/proc/{sys.argv[1]}/environ", "rb").read().split(b"\0")
got = [e.split(b"=", 1)[1].decode() for e in env if e.startswith(b"SELF_IMPROVEMENT_API_SECRET=")]
print("runtime_env_matches_infisical", got == [sys.stdin.read()])
' "$PID"                                          # True
# 4.2 loopback GET, no header
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8892/api/status          # 401
# 4.3 loopback OPTIONS with the NEW value (child env only; never -v, set -x or echo)
infisical run --env=prod -- sh -c 'curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 -X OPTIONS -H "X-Self-Improvement-Secret: $SELF_IMPROVEMENT_API_SECRET" http://127.0.0.1:8892/api/decide'   # 200
# 4.4 Vercel alias resolves to the new READY deployment
vercel alias ls | grep -F "<production-domain>"  # alias -> <new-deployment-url>
vercel inspect <production-domain>               # READY
# 4.5 public GETs with no header, both hosts
for h in 109-123-227-196.sslip.io 109.123.227.196; do
  curl -sk -o /dev/null -w "$h %{http_code}\n" --max-time 10 "https://$h/self-improvement/api/status"   # 401
done
```

4.6 Owner browser checks by the Captain, both accounts: findings, evolution tile, handoffs. Record PASS/FAIL per account.

Section 5 starts only when 4.1 to 4.6 all pass.

## 5. G4 activation (only after section 4 passes)

```bash
cd <repo-clone>
sha256sum deploy/caddy/Caddyfile.v3              # a90ce2d7890086a5fdb8a3a59bd9ec9e9f71baceb558d09ed9d9513fc40f267e
sudo caddy validate --config deploy/caddy/Caddyfile.v3
sudo install -m 0644 deploy/caddy/Caddyfile.v3 /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo caddy reload --config /etc/caddy/Caddyfile --force
```

- Never reload before validate passes. Both validates must pass.
- If the second validate fails after install, do NOT reload. Disk holds v3; running Caddy still serves v2. Recover with 8(a).

## 6. G5 validation

```bash
cd <repo-clone>
deploy/caddy/g5_validate.sh                      # dry-run, sends nothing
deploy/caddy/g5_validate.sh --live               # only when authorised; expect every line PASS, exit 0
```

The live mode sends GET, HEAD, OPTIONS and a POST with a synthetic wrong value. It never sends a valid secret.

6.1 Owner browser checks by the Captain, both accounts, after cutover.

6.2 Journal count since cutover (counts only; nothing printed). Pass: `new_value_occurrences 0`. The old-value count is open item 10.

```bash
umask 077
journalctl --since "<CUTOVER_UTC>" -u self-improvement-dashboard.service -u lcars-portal.service -o cat \
  | infisical run --env=prod -- python3 -I -c 'import os,sys; d=sys.stdin.read(); n=os.environ["SELF_IMPROVEMENT_API_SECRET"]; print("new_value_occurrences", d.count(n))'
```

## 7. Stop conditions (immediate stop, then rollback decision)

- Any HTTP 503 from the dashboard.
- Owner 403, or any 5xx, on a read route.
- Public unauthenticated GET returns 200 on either host.
- Public OPTIONS returns anything other than 403.
- Any `caddy validate` failure.
- `self-improvement-dashboard.service` not `active`.
- Vercel alias not on a `READY` deployment.
- Any secret value found in new logs (6.2 count above 0 for either value).

## 8. Rollback (in order)

Caveat: restoring any previous secret REACTIVATES an exposed credential, so it requires a fresh rotation afterwards. Preferred path: forward fix (rotate again).

8(a). Caddy back to redacted v2.

```bash
cd <repo-clone>
V3=a90ce2d7890086a5fdb8a3a59bd9ec9e9f71baceb558d09ed9d9513fc40f267e
sudo env CADDY_BACKUP=/root/.sec01-caddy-rollback/Caddyfile.v2-redacted-1a309347 V3_SHA=$V3 deploy/caddy/rollback_v2.sh          # dry-run
sudo env CADDY_BACKUP=/root/.sec01-caddy-rollback/Caddyfile.v2-redacted-1a309347 V3_SHA=$V3 deploy/caddy/rollback_v2.sh --apply
sudo caddy validate --config /etc/caddy/Caddyfile
sudo caddy reload --config /etc/caddy/Caddyfile --force   # only after validate PASS
```

The script refuses on drift and never reloads.

8(b). Secret back to the previous value. Captain instruction only; followed by a fresh rotation. Decryption needs the Captain's private key (Mac only), so the Captain streams from the Mac, value on stdin only:

```bash
gpg --decrypt /root/.sec01-secret-rollback/self-improvement-secret.pre-rotation.gpg \
  | ssh <vm-user>@<vm-host> '<same stdin-based PATCH, readback and Vercel update as 3c and 3d>'
```

Then repeat 3e and 3f (the same two restarts only). Do NOT promote the previous production deployment (`dpl_A2s7xZipN5hbGvWKD2GUZpftr9wz`): it carries the compromised credential (see section 10, risk acceptance). Then schedule a fresh rotation through section 3.

8(c). Drift at any point: follow the drift procedure in `deploy/caddy/README-v3.md`. Do not overwrite.

```bash
sudo cp -p /etc/caddy/Caddyfile /root/.sec01-caddy-rollback/Caddyfile.drift-$(date -u +%Y%m%dT%H%M%SZ)
```

Compare with `diff -u` against the redacted v2 backup and the deployed v3. Decide the end state with the Captain.

## 9. Out of scope, tracked

- Journal cleanup of historical secret-bearing lines is a SEPARATE authorisation.
- It does not block G4 once rotation is complete, because the old values are then invalid.

## 10. Blockers and open items

- Captain's private key is on the Mac only. Decryption and rollback 8(b) run there.
- Vercel sensitive values are not readable. Verification is by alias, deployment status and owner browser checks.
- The 24h backup expiry timer needs approval.
- Preview deployments built before rotation keep the old value. Do not promote them.
- Not in the repo; confirm before authorisation:
  - Infisical read and PATCH endpoints, workspace ID, curl config (3a, 3c, 4.1).
  - `/opt/deploy-guard/scoped-restart.sh` existence and arguments (3f).
  - `bulk_decide` operator invocation (3g).
  - `<alert-state-file>` path (1.4).
  - `vercel env update` stdin behaviour on the installed CLI (3d).
  - Old-value journal count (6.2): needs the old value in memory, so the Captain decrypts on the Mac and runs the count there.
- Owner browser checks (4.6, 6.1) are Captain-only.

### Risk acceptance: historical journal exposure (recorded 2026-11-07)

- **Historical exposure:** 34 journal lines contain the previous `SELF_IMPROVEMENT_API_SECRET` value. This is the Captain-reported count, from a Mac-side GPG decryption and SSH journal count on 2026-11-07. The VM itself cannot decrypt the value, so this count was not reproduced on the VM.
- **Mitigation:** the previous credential was rotated. Captain-reported: Mac-side verification returned HTTP 401 for one read-only GET (2026-11-07). Verified on the VM (2026-11-07): the new credential returns HTTP 200 on the dashboard.
- **Prevention:** Caddy access-log redaction is active (header-delete filter in both site blocks). Verified on the VM (2026-11-07), count-only check since cutover: 0 new-value occurrences in the dashboard, portal and Caddy journals, and 0 `X-Self-Improvement-Secret` header keys in the Caddy journal.
- **Decision (Captain):** retain historical journals without cleanup. Residual risk accepted: the revoked credential remains readable in retained logs. This record does not close open item 10 or any gate.
- **Compromised deployment:** `dpl_A2s7xZipN5hbGvWKD2GUZpftr9wz` carries the compromised credential. Never promote or restore it.
- **Current production deployment:** `dpl_Cs6u7WzNG6oZwbDp2q21pG3D3y5X` (READY, alias `usstjros.vercel.app`; verified on the VM, 2026-11-07).
