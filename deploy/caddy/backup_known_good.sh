#!/usr/bin/env bash
# SEC-01: save a dedicated copy of the CURRENT redacted Caddy v2 configuration
# before any v3 deployment. Dry-run by default; --apply writes the backup only.
# It never modifies the live file.
set -euo pipefail
V2_SHA="${CADDY_V2_SHA:-1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6}"
LIVE="${CADDY_LIVE:-/etc/caddy/Caddyfile}"
DEST_DIR="${DEST_DIR:-/root/.sec01-caddy-rollback}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1
sha() { sha256sum "$1" | cut -d' ' -f1; }
LIVE_SHA="$(sha "$LIVE")"
if [ "$LIVE_SHA" != "$V2_SHA" ]; then
  echo "REFUSED: live config is not the redacted v2 baseline (live=$LIVE_SHA)."; exit 3
fi
DEST="$DEST_DIR/Caddyfile.v2-redacted-${V2_SHA:0:8}"
echo "plan: copy live redacted v2 to $DEST (dir 0700, file 0600), then verify its hash"
[ "$APPLY" -eq 1 ] || { echo "dry-run: no changes made. Re-run with --apply."; exit 0; }
umask 077
mkdir -p "$DEST_DIR" && chmod 700 "$DEST_DIR"
install -m 0600 "$LIVE" "$DEST"
[ "$(sha "$DEST")" = "$V2_SHA" ] || { echo "ERROR: backup hash mismatch"; rm -f "$DEST"; exit 4; }
echo "backup saved and verified: $DEST"
