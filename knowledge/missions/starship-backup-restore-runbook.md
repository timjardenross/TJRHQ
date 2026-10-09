# Starship backup: restore runbook

Written for USS-TJR-MSN-0412 (Stream 2). Public-safe on purpose: it names files and
commands, never values. Everything secret lives in the Captain's password manager.

## What the nightly backup contains

A restic repository on Google Drive (`rclone:gdrive:starship-backups`), written by
`deploy/starship-backup.sh` at 02:40 Australia/Melbourne. Each snapshot (tag `starship-nightly`) holds:

| Item | Where in a restored tree |
|---|---|
| Supabase dump (`public`, `auth`, `storage`, `supabase_migrations`), custom format | `var/tmp/starship-backup.*/supabase.dump` |
| `cron.job` rows (data-only SQL) | `.../supabase.dump.cron-job.sql` |

The Supabase dump is taken every 3rd night (to save Supabase egress on the Free plan). On the other nights the
last good dump is re-added from a VM cache, so every snapshot still contains one; its age is in the run log
(`supabase dump skipped: cached dump is Nh old`). The DATA of four regenerable log tables
(`domain_heartbeats`, `core_events`, `verification_state`, `intelligence_source_health`) is not in the dump;
their definitions are. After a restore those tables start empty and refill from the running services.
| Infisical Postgres dump, custom format | `.../infisical-db.dump` |
| Infisical containers' definitions (`docker inspect`) | `.../infisical-containers-inspect.json` |
| Git bundle of every local branch | `.../branches.bundle` (and a dated `starship-branches-*.bundle`) |
| Machine-identity auth file used by every service to log in to Infisical | `opt/starship-endeavour/platform-runtime/.infisical-auth.env` |
| All `.env*` files, Caddy config, systemd units and timers, root crontab, `ufw` status | under their original paths |
| Self-improvement review state, handoffs, ID counters, the private-knowledge directory | under their original paths |

Not in the backup: the `vault` schema (its secrets cannot be decrypted in another project),
the rclone token, the restic password, Ollama models, Docker images.

## You need (from the password manager)

1. The restic repository password.
2. Infisical `ENCRYPTION_KEY` and `AUTH_SECRET`.
3. A machine with Docker, `restic` 0.16+ and `rclone` **1.75+** (the Ubuntu apt rclone 1.60 cannot authorise Drive).

## 1. Reach the repository

On a machine with a browser: `rclone authorize "drive" "$(printf '{"scope":"drive.file"}' | base64)"`
(the second argument is just the base64 of `{"scope":"drive.file"}`, which limits rclone to files it creates).
On the target machine: `rclone config create gdrive drive scope drive.file token '<json>'`.

**Caveat:** with the `drive.file` scope, rclone only sees files created by the *same OAuth client*.
If the client ID is ever changed (for example from rclone's shared client to your own), the
existing `starship-backups` folder is invisible to the new client. Plan a switch as: new
client, new folder, `restic init`, one fresh backup, then retire the old folder.

Check access: `restic -o rclone.program=$(command -v rclone) -r rclone:gdrive:starship-backups snapshots`.

## 2. Restore the files

`restic ... restore latest --tag starship-nightly --target ./restore` (the target holds secrets: mode 700, delete when done).

## 3. Git

`git clone ./restore/var/tmp/starship-backup.*/branches.bundle repo && cd repo && git checkout main`.
The bundle is made with `--branches`, so it has no HEAD; the checkout step is required.

## 4. Infisical

1. Recreate the stack from the saved compose directory in the restored private-knowledge tree
   (compose file plus its env files). Start only `db` and `redis` first.
2. `docker exec -i <db container> pg_restore -U infisical -d infisical --no-owner --no-privileges < infisical-db.dump`.
3. Start the app. If the recovery env file is missing, set `ENCRYPTION_KEY` and `AUTH_SECRET` from the password manager.
4. Put `.infisical-auth.env` back in `platform-runtime/`. Services log in with it.
5. Verify: log in with the CLI and export the `prod` environment; the secret count should match what you expect.

Tested 2026-10-09: all 100 secrets decrypted to values identical to live.

## 5. Supabase

1. Create a project (any plan). Enable extensions: `vector` (schema `public`), `uuid-ossp` and `pgcrypto`
   (schema `extensions`), `pg_cron`, `pgmq`, `supabase_vault`.
2. Create the custom roles first (names only; grants come from the repo's migrations): `xo_bot`,
   `revs_bot`, `telegram_engineer_ro`, plus the usual Supabase roles if the project lacks them.
3. Use a Postgres 17 client: `pg_restore --no-owner --no-privileges -d <db> supabase.dump`.
   The only expected error is `schema "public" already exists`.
4. Re-create the cron jobs from `supabase.dump.cron-job.sql`.
5. Re-enter vault secrets from Infisical.

Tested 2026-10-09 against a throwaway container: 166 tables, 163 with identical row counts
(3 high-churn tables were 2-4 rows behind live), `auth.users` 3 of 3, 7 cron jobs.

## 6. Services

Copy units back to `/etc/systemd/system/`, Caddy to `/etc/caddy/`, the `.env*` files to their
original paths, then `systemctl daemon-reload` and start services in dependency order
(Infisical first).
