# Units into version control — VM audit (SID b7897aa6, 2026-11-03)

Six live systemd services and six timers existed only in `/etc/systemd/system`. This branch adds sanitized copies under `deploy/`. Nothing on the host was changed, and nothing here is deployed by it (none of the six services is in `auto-deploy-services.conf`).

## Services

| Unit | ExecStart | WorkingDirectory | User | Port | Depends on it | Code in git? | Venv / data |
|---|---|---|---|---|---|---|---|
| chatterbox-tts | `platform-runtime/run-with-infisical.sh core/voice/chatterbox-venv/bin/python core/voice/tts_chatterbox.py` | `/opt/starship-endeavour/core/voice` | root | 8893 (binds 0.0.0.0, proxied by Caddy at `reverse_proxy 127.0.0.1:8893`, public) | Caddy; `TTS_SERVICE_URL`/`TTS_SERVICE_SECRET` clients | `tts_chatterbox.py` tracked; `chatterbox-venv` untracked, gitignored, 6.3 GB | venv `core/voice/chatterbox-venv`; Hugging Face cache |
| command-bus | `platform-runtime/run-with-infisical-bot.sh xo -- platform-runtime/.venv/bin/python -m core.coordination.command_bus run` | `/opt/starship-endeavour` | root (unit default) | none | no other unit or deploy file references it | `core/coordination/command_bus.py` tracked | shared `platform-runtime/.venv`; three optional `EnvironmentFile=-` (.env files, may not exist) |
| command-centre | `/root/.nvm/versions/node/v24.18.0/bin/node app.js` | `/opt/starship-endeavour/core/command-centre/backend` | root | 5000 (`PORT=5000`, binds `*`) | Caddy (`/api/*`, `/health` to 127.0.0.1:5000, two site blocks); `deploy/docker-compose.watchlist.yml` | `app.js` tracked | Node from nvm (path pins v24.18.0); app loads its own dotenv |
| number-one-exporter | `/usr/bin/python3 core/coordination/number_one_exporter.py --watch --interval 300` | `/opt/starship-endeavour` | root | none | `deploy/mission-registry-sync.service` references it | `number_one_exporter.py` tracked | system python, no venv |
| ollama | `/usr/local/bin/ollama serve` | none (default) | ollama:ollama | 11434 (127.0.0.1) | `model-router.service`, `lcars-portal.service`, `platform-runtime/check-ollama-model-default.sh`, `auto-deploy.sh` | binary only, installed outside the repo | models under `/usr/share/ollama` |
| starship-meilisearch | `/usr/local/bin/meilisearch --master-key <redacted> --db-path /var/lib/meilisearch` | `/var/lib/meilisearch` | root (unit default) | 7700 (127.0.0.1 and ::1) | `core/search/meilisearch_client.py`, `tools/test_meilisearch.py`, `tools/supabase/retrieve_knowledge.py`, `core/quality/ragas_eval.py` | binary only, outside the repo | data `/var/lib/meilisearch`, log `/var/log/starship/meilisearch.log` |

## Timers (the `.service` files were already in `deploy/`)

`capture-enrichment` (every 15 min), `engineering-batch-sync` (5 min after boot, then every 30 min), `health-osint-collection` (02:00 UTC daily), `vm-processing` (every 10 min), `vm-processing-retry` (hourly), `vm-processing-healthcheck` (every 30 min). The `.timer` files are copied as-is; none contains a secret.

## Drop-ins captured

- `deploy/ollama.service.d/keep-alive-zero.conf`: sets `OLLAMA_KEEP_ALIVE=0`.

No drop-ins exist for the other five services or the six timers.

## Not captured (out of scope, listed so nothing is lost)

- `caddy.service.d/apikey.conf`: probably holds a secret. Not read into this PR.
- `auto-deploy.service.d/repair-git-perms.conf` and `sysstat-collect.timer.d/override.conf`: untracked, no secrets seen, not added.
- `human-systems-scheduler.service.d/capacity-bot-telegram.conf`: created today (2026-11-03) and is untracked. It should be added to `deploy/` in its own change.

## Could not sanitize / needs a human

- **starship-meilisearch**: the live unit passes the master key inline in `ExecStart`. The tracked copy uses `<set via Infisical or EnvironmentFile>`, so it is not deployable as-is. The same key literal is also hard-coded in `core/search/meilisearch_client.py`, already in this public repo. It is a weak, guessable value. Meilisearch listens on localhost only, which limits exposure, but the key should be rotated and moved to Infisical. I did not touch it.
- **command-centre**: the Node path is pinned to nvm v24.18.0 under `/root`, so an nvm upgrade breaks the unit.
- **command-bus**: the three `EnvironmentFile=-` lines of the live unit are commented out in the tracked copy (repo hook `no-raw-env-secrets` blocks active raw `.env` files). Before deploying, check whether the live `.env` files exist and are still needed. Also `After=starfleet-backend.service`, which does not exist (`LoadState=not-found`). Harmless but stale.

## Existing drift (not changed here)

The tracked `.service` files for the six timers have `After=... docker.service`, but the live copies do not. The repo is ahead of the host; none of them is on the auto-deploy restart list.

## Secret scans

`pre-commit run gitleaks` and `pre-commit run detect-secrets` (repo-pinned versions, staged files): both passed. The key literal does not appear anywhere under `deploy/`.

## Proposed backup change (tracked copy `deploy/starship-backup.sh` only; the live script is untouched)

The tracked copy was byte-identical to `/opt/starship-backup/backup.sh`. Today the backup takes only top-level `/etc/systemd/system/*.service` and `*.timer`, so drop-ins and enable symlinks are missed, and `/opt/deploy-guard`, `/etc/sysstat` and `/etc/systemd/journald.conf.d` are not covered at all. `chatterbox-venv` is already pruned from the `.env` find.

```diff
@@ -151,6 +151,10 @@ fi
 # --- small state captures
 ufw status numbered >"$STAGE/ufw-status.txt" 2>&1 || true
 crontab -l >"$STAGE/crontab-root.txt" 2>&1 || true
+# chatterbox-tts venv (core/voice/chatterbox-venv, ~6 GB, untracked + gitignored) is NOT backed up;
+# record its package set instead so it can be rebuilt.
+CB_PIP="$REPO_ROOT/core/voice/chatterbox-venv/bin/pip"
+if [ -x "$CB_PIP" ]; then "$CB_PIP" freeze >"$STAGE/chatterbox-venv-freeze.txt" 2>&1 || true; fi
 
 # --- 4. restic backup
 log "4/5 restic backup"
@@ -164,6 +168,10 @@ LIST="$STAGE/paths.txt"
     "$REPO_ROOT/.id-counters.json" \
     "$REPO_ROOT/platform-runtime/.infisical-auth.env" \
     /etc/caddy \
+    /etc/systemd/system \
+    /opt/deploy-guard \
+    /etc/sysstat \
+    /etc/systemd/journald.conf.d \
     /root/private-knowledge \
     /var/spool/cron/crontabs \
     /root/starship-branches-*.bundle; do
@@ -171,7 +179,7 @@ LIST="$STAGE/paths.txt"
   done
   find "$REPO_ROOT" -xdev \( -name node_modules -o -name .venv -o -name '.venv-*' -o -name .git -o -name .next -o -name chatterbox-venv \) -prune \
     -o -type f \( -name '.env' -o -name '.env.*' \) -print
-  find /etc/systemd/system -maxdepth 1 -type f \( -name '*.service' -o -name '*.timer' \) -print
+  # (/etc/systemd/system is now backed up whole above: units, timers, drop-ins and enable symlinks)
 } >"$LIST"
 log "paths to back up: $(wc -l <"$LIST") entries"
 
```

The chatterbox venv (6.3 GB, untracked) is deliberately not backed up. The change records `pip freeze` into each snapshot instead.

To apply: copy the tracked `deploy/starship-backup.sh` to `/opt/starship-backup/backup.sh` after review.

Note: backing up all of `/etc/systemd/system` also captures drop-ins that may hold secrets (e.g. `caddy.service.d/apikey.conf`). The restic repository is encrypted, and it already stores `.infisical-auth.env` and every `.env`, so this adds no new exposure class.
