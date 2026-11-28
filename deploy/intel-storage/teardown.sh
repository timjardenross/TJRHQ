#!/usr/bin/env bash
# Stop and remove the store. --purge also removes its data, configuration, code, users and groups. Nothing else is touched.
set -uo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
systemctl disable -q --now tjrhq-intel-backup.timer tjrhq-intel-postgres.service 2>/dev/null
docker rm -f tjrhq-intel-pg >/dev/null 2>&1
rm -f /etc/systemd/system/tjrhq-intel-postgres.service /etc/systemd/system/tjrhq-intel-backup.service /etc/systemd/system/tjrhq-intel-backup.timer
systemctl daemon-reload
if [ "${1:-}" = "--purge" ]; then
  rm -rf --one-file-system /var/lib/tjrhq-intel /etc/tjrhq-intel /opt/tjrhq-intel /run/tjrhq-intel
  rm -f /etc/tmpfiles.d/tjrhq-intel.conf
  for u in tjrhq-intel-db tjrhq-intel-ingest tjrhq-intel-read; do userdel "$u" 2>/dev/null; done
  for g in tjrhq-intel-obj tjrhq-intel; do groupdel "$g" 2>/dev/null; done
fi
echo removed
