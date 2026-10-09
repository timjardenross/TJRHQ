#!/bin/bash
# starship-backup.sh - nightly encrypted off-box backup (USS-TJR-MSN-0412, Stream 2).
#
# What it does
#   1. Dumps the Supabase database (public, auth, storage, supabase_migrations,
#      plus the cron.job rows). To save Supabase egress (Free plan cap 5 GB), the
#      dump runs every SUPABASE_DUMP_EVERY_HOURS (default 72, i.e. every 3rd night),
#      skips the DATA of the regenerable log tables (schema is kept), and the last
#      good dump is cached on the VM and re-added to every nightly snapshot, so each
#      snapshot is self-contained (restic de-duplicates the unchanged file).
#   2. Dumps the Infisical Postgres and records the Infisical containers'
#      definitions (docker inspect), which hold keys the compose files do not.
#   3. Bundles every local git branch.
#   4. Backs those up, with VM-only state, to an encrypted restic repository on
#      Google Drive (through rclone).
#   5. Applies retention (7 daily / 4 weekly / 3 monthly) and prunes.
#
# Safety properties
#   * Never prints secrets and never uses `set -x`.
#   * The Supabase connection string comes from Infisical at runtime, only for
#     step 1, is passed to a throwaway container by variable NAME, and is never
#     written to disk. Steps 2-5 do not depend on the Infisical API being up.
#   * Dumps are staged in a private temp directory that is removed on exit,
#     success or failure.
#   * A component failure is recorded and the remaining components still run, so
#     one bad night does not lose the others. Any failure makes the script exit
#     non-zero, which fires the unit's OnFailure= alert.
#   * Pruning only runs after a successful backup.
#
# DRY_RUN=1  does all the dumps, but makes restic only report what it would add
#            or remove (nothing is written to the repository).
set -uo pipefail
umask 077

RCLONE=/usr/local/bin/rclone      # explicit: the apt rclone is too old for Drive auth
RESTIC=/usr/bin/restic
REPO_ROOT="${BACKUP_REPO_ROOT:-/opt/starship-endeavour}"
INFISICAL_WRAPPER="$REPO_ROOT/platform-runtime/run-with-infisical.sh"
export RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-rclone:gdrive:starship-backups}"
export RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/root/.restic-pass}"
export HOME="${HOME:-/root}"
DRY="${DRY_RUN:-0}"
TAG=starship-nightly

# Append-only operational logs that are pruned to 30 days by migration 0221 (and heartbeats by an
# earlier job). Their rows are regenerable/low value, about 30% of the data; the table definitions
# are still dumped. audit_events is deliberately NOT here (evidentiary).
EXCLUDE_DATA_TABLES=(public.domain_heartbeats public.core_events public.verification_state public.intelligence_source_health)
EXCLUDE_DATA_ARGS=()
for t in "${EXCLUDE_DATA_TABLES[@]}"; do EXCLUDE_DATA_ARGS+=("--exclude-table-data=$t"); done

CACHE_DIR="${BACKUP_CACHE_DIR:-/var/lib/starship-backup}"
DUMP_EVERY_H="${SUPABASE_DUMP_EVERY_HOURS:-72}"
DUMP_GRACE_H=1            # nights drift by seconds; due = age >= interval - grace

redact() { sed -E 's#(postgres(ql)?://)[^[:space:]]+#\1<redacted>#g'; }

# --- sub-mode: runs UNDER the Infisical wrapper so SUPABASE_DB_URL is in the
# --- environment. Must come before the lock below (the parent holds it).
if [ "${1:-}" = "--supabase-dump" ]; then
  out="${2:?output path}"
  [ -n "${SUPABASE_DB_URL:-}" ] || { echo "SUPABASE_DB_URL is not set" >"$out.err"; exit 2; }
  docker run --rm --network host -e SUPABASE_DB_URL postgres:17 \
    sh -c 'exec pg_dump "$SUPABASE_DB_URL" --no-owner --no-privileges --format=custom --schema=public --schema=auth --schema=storage --schema=supabase_migrations "$@"' sh "${EXCLUDE_DATA_ARGS[@]}" \
    >"$out" 2>"$out.err"
  rc=$?
  # cron.job definitions (data only); best effort, never fails the dump.
  docker run --rm --network host -e SUPABASE_DB_URL postgres:17 \
    sh -c 'exec pg_dump "$SUPABASE_DB_URL" --no-owner --no-privileges --data-only --table=cron.job' \
    >"$out.cron-job.sql" 2>>"$out.err" || true
  exit "$rc"
fi

FAILED=()
log() { printf '%s [starship-backup] %s\n' "$(date +%FT%T%z)" "$*"; }
fail() { FAILED+=("$1"); log "FAILED: $1"; }

exec 9>/run/starship-backup.lock
flock -n 9 || { log "another run holds the lock - exiting"; exit 0; }

STAGE="$(mktemp -d /var/tmp/starship-backup.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
RESTIC_CMD=("$RESTIC" -o "rclone.program=$RCLONE")

log "start (dry_run=$DRY, stage=$STAGE)"

# --- preflight
[ -s "$RESTIC_PASSWORD_FILE" ] || { log "restic password file missing or empty"; exit 1; }
[ -x "$RCLONE" ] || { log "$RCLONE not found"; exit 1; }
"${RESTIC_CMD[@]}" cat config >/dev/null 2>&1 \
  || { log "cannot open the restic repository (Drive authorisation or password problem)"; exit 1; }

# --- 1. Supabase (every DUMP_EVERY_H hours; otherwise re-use the cached dump, no Supabase egress)
mkdir -p "$CACHE_DIR" && chmod 700 "$CACHE_DIR"
CACHE_DUMP="$CACHE_DIR/supabase.dump"
CACHE_CRON="$CACHE_DIR/supabase.dump.cron-job.sql"
now=$(date +%s)
cache_age_h=-1
[ -s "$CACHE_DUMP" ] && cache_age_h=$(( (now - $(stat -c %Y "$CACHE_DUMP")) / 3600 ))
if [ "${FORCE_SUPABASE_DUMP:-0}" = "1" ] || [ "$cache_age_h" -lt 0 ] || [ "$cache_age_h" -ge $((DUMP_EVERY_H - DUMP_GRACE_H)) ]; then
  log "1/5 supabase dump (cached dump age: $([ "$cache_age_h" -lt 0 ] && echo none || echo "${cache_age_h}h"); data skipped for ${#EXCLUDE_DATA_TABLES[@]} log tables)"
  if "$INFISICAL_WRAPPER" "$0" --supabase-dump "$STAGE/supabase.dump" >"$STAGE/supabase.wrapper.log" 2>&1; then
    size=$(stat -c %s "$STAGE/supabase.dump" 2>/dev/null || echo 0)
    toc=$(docker run -i --rm postgres:17 pg_restore --list <"$STAGE/supabase.dump" 2>/dev/null | wc -l)
    log "supabase dump: $((size / 1048576)) MB, $toc table-of-contents entries"
    if [ "$size" -ge 1048576 ] && [ "$toc" -ge 100 ]; then
      cp "$STAGE/supabase.dump" "$CACHE_DUMP.tmp" && mv -f "$CACHE_DUMP.tmp" "$CACHE_DUMP"
      [ -f "$STAGE/supabase.dump.cron-job.sql" ] && cp "$STAGE/supabase.dump.cron-job.sql" "$CACHE_CRON"
    else
      fail "supabase dump is empty or unreadable ($size bytes, $toc entries)"
    fi
  else
    fail "supabase dump failed: $(head -c 300 "$STAGE/supabase.dump.err" 2>/dev/null | redact | tr '\n' ' ')"
  fi
  rm -f "$STAGE/supabase.wrapper.log"
else
  log "1/5 supabase dump skipped: cached dump is ${cache_age_h}h old (next due at ${DUMP_EVERY_H}h); re-using it, no Supabase egress"
  cp "$CACHE_DUMP" "$STAGE/supabase.dump"
  [ -f "$CACHE_CRON" ] && cp "$CACHE_CRON" "$STAGE/supabase.dump.cron-job.sql"
fi
# A due-but-failed dump is already recorded by fail() above and retried the next night (the cache
# stays old, so it stays due). Re-using the old cached dump meanwhile is not done: only a good dump is cached.
[ -s "$STAGE/supabase.dump" ] || log "no supabase dump in this snapshot"

# --- 2. Infisical
log "2/5 infisical database and container definitions"
if docker exec infisical-db-1 sh -c 'exec pg_dump -U "$POSTGRES_USER" --format=custom "$POSTGRES_DB"' \
     >"$STAGE/infisical-db.dump" 2>"$STAGE/infisical-db.err"; then
  size=$(stat -c %s "$STAGE/infisical-db.dump")
  toc=$(docker exec -i infisical-db-1 pg_restore --list <"$STAGE/infisical-db.dump" 2>/dev/null | wc -l)
  log "infisical dump: $((size / 1024)) KB, $toc entries"
  { [ "$size" -ge 20480 ] && [ "$toc" -ge 20 ]; } || fail "infisical dump is empty or unreadable ($size bytes, $toc entries)"
else
  fail "infisical dump failed: $(head -c 300 "$STAGE/infisical-db.err" | tr '\n' ' ')"
fi
docker inspect infisical-infisical-1 infisical-db-1 infisical-redis-1 >"$STAGE/infisical-containers-inspect.json" 2>/dev/null \
  || fail "docker inspect of the infisical containers failed"

# --- 3. git bundle of every local branch
log "3/5 git bundle"
if git -C "$REPO_ROOT" bundle create "$STAGE/branches.bundle" --branches >/dev/null 2>&1 \
   && git -C "$REPO_ROOT" bundle verify "$STAGE/branches.bundle" >/dev/null 2>&1; then
  log "bundle: $(( $(stat -c %s "$STAGE/branches.bundle") / 1048576 )) MB, $(git -C "$REPO_ROOT" bundle list-heads "$STAGE/branches.bundle" | wc -l) refs"
else
  fail "git bundle failed or did not verify"
fi

# --- small state captures
ufw status numbered >"$STAGE/ufw-status.txt" 2>&1 || true
crontab -l >"$STAGE/crontab-root.txt" 2>&1 || true

# --- 4. restic backup
log "4/5 restic backup"
LIST="$STAGE/paths.txt"
{
  echo "$STAGE"
  for p in \
    "$REPO_ROOT/data/self-improvement/review" \
    "$REPO_ROOT/outputs/delivery_ledger.txt" \
    "$REPO_ROOT/Missions/Engineering-Handoffs" \
    "$REPO_ROOT/.id-counters.json" \
    "$REPO_ROOT/platform-runtime/.infisical-auth.env" \
    /etc/caddy \
    /root/private-knowledge \
    /var/spool/cron/crontabs \
    /root/starship-branches-*.bundle; do
    if [ -e "$p" ]; then echo "$p"; else log "note: $p does not exist, skipped"; fi
  done
  find "$REPO_ROOT" -xdev \( -name node_modules -o -name .venv -o -name '.venv-*' -o -name .git -o -name .next -o -name chatterbox-venv \) -prune \
    -o -type f \( -name '.env' -o -name '.env.*' \) -print
  find /etc/systemd/system -maxdepth 1 -type f \( -name '*.service' -o -name '*.timer' \) -print
} >"$LIST"
log "paths to back up: $(wc -l <"$LIST") entries"

BACKUP_OK=1
# --group-by host,tags: the path set changes every run (random staging dir, new .env files), so
# the default host,paths grouping would give every snapshot its own group: no parent
# snapshot for speed-up and, worse, retention would never prune anything.
BK=("${RESTIC_CMD[@]}" backup --files-from "$LIST" --tag "$TAG" --group-by host,tags --exclude-caches)
[ "$DRY" = "1" ] && BK+=(--dry-run)
"${BK[@]}" 2>&1 | grep -vE 'NOTICE: gdrive: This remote uses rclone.s shared Google Drive client_id'
rc=${PIPESTATUS[0]}   # must be read immediately after the pipeline: it is restic's own exit code
if [ "$rc" -ne 0 ]; then BACKUP_OK=0; fail "restic backup exited $rc"; fi

# --- 5. retention (only after a good backup)
log "5/5 retention"
if [ "$BACKUP_OK" = "1" ]; then
  FG=("${RESTIC_CMD[@]}" forget --tag "$TAG" --group-by host,tags --keep-daily 7 --keep-weekly 4 --keep-monthly 3)
  if [ "$DRY" = "1" ]; then FG+=(--dry-run); else FG+=(--prune); fi
  "${FG[@]}" 2>&1 | grep -vE 'NOTICE: gdrive: This remote uses rclone.s shared Google Drive client_id' | tail -15
  [ "${PIPESTATUS[0]}" -eq 0 ] || fail "restic forget/prune failed"
else
  log "skipping prune because the backup failed"
fi

if [ "${#FAILED[@]}" -gt 0 ]; then
  log "finished WITH ${#FAILED[@]} FAILURE(S): ${FAILED[*]}"
  exit 1
fi
log "finished OK"
