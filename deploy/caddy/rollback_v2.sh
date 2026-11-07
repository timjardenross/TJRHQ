#!/usr/bin/env bash
# SEC-01 guarded rollback to the known-good REDACTED Caddy v2 configuration.
#
# DEFAULT IS DRY-RUN: this script reads and reports. Nothing is written unless
# --apply is given. It never reloads Caddy; reload is a separate, explicit step
# that must follow a successful `caddy validate` of the restored file.
#
# Required environment:
#   CADDY_BACKUP  path to the saved redacted v2 copy (outside the repo)
#   V3_SHA        sha256 of the v3 file that is currently deployed
# Optional:
#   CADDY_LIVE    live config path (default /etc/caddy/Caddyfile)
#   CADDY_BIN     caddy binary (default caddy)
#   CADDY_V2_SHA  expected redacted v2 hash. Tests only; production must not set it.
#
# Refuses to act if: the backup is a pre-redaction file; the backup hash is not the
# redacted v2 hash; the live file no longer matches the deployed v3 hash (drift);
# validation of the staged file fails.
set -euo pipefail

V2_SHA="${CADDY_V2_SHA:-1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6}"
LIVE="${CADDY_LIVE:-/etc/caddy/Caddyfile}"
BACKUP="${CADDY_BACKUP:?set CADDY_BACKUP to the saved redacted v2 copy}"
V3_SHA="${V3_SHA:?set V3_SHA to the sha256 of the v3 file currently deployed}"
CADDY_BIN="${CADDY_BIN:-caddy}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

sha() { sha256sum "$1" | cut -d' ' -f1; }

# Guard 1: the pre-redaction backup is forbidden as a rollback source.
case "$BACKUP" in
  *Caddyfile.bak.pre-sec01*) echo "REFUSED: $BACKUP predates log redaction and must not be used."; exit 2 ;;
esac

# Guard 2: the backup must be exactly the redacted v2 baseline.
[ -f "$BACKUP" ] || { echo "REFUSED: backup not found: $BACKUP"; exit 3; }
if [ "$(sha "$BACKUP")" != "$V2_SHA" ]; then
  echo "REFUSED: backup hash $(sha "$BACKUP") != expected redacted v2 hash $V2_SHA"; exit 3
fi

# Guard 3: refuse to overwrite a live file that is not the deployed v3 (drift).
LIVE_SHA="$(sha "$LIVE")"
if [ "$LIVE_SHA" != "$V3_SHA" ]; then
  echo "STOP: live config has drifted (live=$LIVE_SHA, deployed v3=$V3_SHA)."
  echo "Nothing was overwritten. Follow the drift procedure in README-v3.md."
  exit 4
fi

echo "plan: restore redacted v2 ($V2_SHA) from backup to $LIVE, validating first"
if [ "$APPLY" -ne 1 ]; then
  echo "dry-run: no changes made. Re-run with --apply to restore."
  exit 0
fi

# Stage in the same directory, validate, then rename atomically.
STAGE="$LIVE.rollback-stage.$$"
install -m 0644 "$BACKUP" "$STAGE"
if ! "$CADDY_BIN" validate --config "$STAGE" >/dev/null 2>&1; then
  rm -f "$STAGE"; echo "REFUSED: staged file failed caddy validate. Live file untouched."; exit 5
fi
mv -f "$STAGE" "$LIVE"
if [ "$(sha "$LIVE")" != "$V2_SHA" ]; then
  echo "ERROR: post-restore hash mismatch on $LIVE"; exit 6
fi
"$CADDY_BIN" validate --config "$LIVE" >/dev/null 2>&1 || { echo "ERROR: restored file failed validate"; exit 7; }
echo "restored and validated. Reload is NOT performed here. To reload, run explicitly:"
echo "  caddy reload --config $LIVE --force"
