#!/usr/bin/env bash
# Install the isolated store. Idempotent. Touches only its own users, paths, units and one container.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"
ROOT=/var/lib/tjrhq-intel; ETC=/etc/tjrhq-intel; OPT=/opt/tjrhq-intel; RUN=/run/tjrhq-intel
IMAGE=pgvector/pgvector:pg17
dpkg -s python3-asyncpg >/dev/null 2>&1 || NEEDRESTART_SUSPEND=1 DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-asyncpg
for g in tjrhq-intel tjrhq-intel-obj; do getent group "$g" >/dev/null || groupadd --system "$g"; done
mk() { id "$1" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin --gid tjrhq-intel "$1"; }
mk tjrhq-intel-db; mk tjrhq-intel-ingest; mk tjrhq-intel-read
usermod -aG tjrhq-intel-obj tjrhq-intel-ingest; usermod -aG tjrhq-intel-obj tjrhq-intel-read
install -d -m 0755 -o root -g root "$ROOT" "$ETC" "$OPT"
install -d -m 0700 -o tjrhq-intel-db -g tjrhq-intel "$ROOT/postgres"
install -d -m 2750 -o tjrhq-intel-ingest -g tjrhq-intel-obj "$ROOT/objects"
install -d -m 0700 -o tjrhq-intel-ingest -g tjrhq-intel "$ROOT/spool"
install -d -m 0700 -o root -g root "$ROOT/backup-stage"
printf 'd %s 2750 tjrhq-intel-db tjrhq-intel -\n' "$RUN" > /etc/tmpfiles.d/tjrhq-intel.conf
systemd-tmpfiles --create /etc/tmpfiles.d/tjrhq-intel.conf
install -m 0755 "$SRC"/guard.py "$SRC"/store.py "$SRC"/embed.py "$SRC"/fixtures.py "$SRC"/backup.py "$SRC"/restore.py "$SRC"/package_c.py "$SRC"/deletions.py "$SRC"/screen.py "$SRC"/validate_screening.py "$SRC"/names_worker.py "$OPT"/
install -m 0644 "$SRC"/schema.sql "$OPT"/
{ git -C "$SRC" rev-parse HEAD 2>/dev/null || echo unknown; git -C "$SRC" status --porcelain -- . 2>/dev/null | grep -q . && echo "uncommitted changes" || true; } > "$OPT/REVISION"
# the container sees only these accounts, so peer authentication maps host identities to database roles: no passwords exist
{ echo "root:x:0:0::/root:/bin/sh"; for u in tjrhq-intel-db tjrhq-intel-ingest tjrhq-intel-read; do echo "$u:x:$(id -u $u):$(id -g $u)::/nonexistent:/bin/sh"; done; } > "$ETC/passwd"
{ echo "root:x:0:"; echo "tjrhq-intel:x:$(getent group tjrhq-intel | cut -d: -f3):"; } > "$ETC/group"
echo "local all all peer map=intel" > "$ETC/pg_hba.conf"
cat > "$ETC/pg_ident.conf" <<'MAP'
intel tjrhq-intel-db     tjrhq-intel-db
intel root               tjrhq-intel-db
intel tjrhq-intel-ingest intel_ingest
intel tjrhq-intel-ingest intel_maint
intel tjrhq-intel-read   intel_read
MAP
chmod 0644 "$ETC"/*
[ -s "$ROOT/image" ] || { docker pull -q "$IMAGE" >/dev/null; docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}' > "$ROOT/image"; }
cp "$ROOT/image" "$ETC/image"
cat > /etc/systemd/system/tjrhq-intel-postgres.service <<UNIT
[Unit]
Description=TJRHQ isolated intelligence database (no network)
After=docker.service
Requires=docker.service

[Service]
ExecStartPre=-/usr/bin/docker rm -f tjrhq-intel-pg
ExecStart=/usr/bin/docker run --rm --name tjrhq-intel-pg --network none --user $(id -u tjrhq-intel-db):$(getent group tjrhq-intel | cut -d: -f3) \\
  --cpus 2 --memory 3g --memory-swap 3g --shm-size 256m --pids-limit 200 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \\
  -v $ROOT/postgres:/var/lib/postgresql/data -v $RUN:/var/run/postgresql -v $ETC/passwd:/etc/passwd:ro -v $ETC/group:/etc/group:ro -v $ETC:/etc/tjrhq-intel:ro \\
  -e PGDATA=/var/lib/postgresql/data/pgdata -e POSTGRES_USER=tjrhq-intel-db -e POSTGRES_DB=intel -e POSTGRES_HOST_AUTH_METHOD=trust \\
  $(cat "$ETC/image") postgres -c listen_addresses= -c hba_file=/etc/tjrhq-intel/pg_hba.conf -c ident_file=/etc/tjrhq-intel/pg_ident.conf \\
  -c unix_socket_permissions=0770 -c shared_buffers=1GB -c work_mem=4MB -c maintenance_work_mem=128MB -c max_connections=24
ExecStop=/usr/bin/docker stop -t 30 tjrhq-intel-pg
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/tjrhq-intel-backup.service <<UNIT
[Unit]
Description=TJRHQ intelligence store matched database and object backup
Requires=tjrhq-intel-postgres.service
After=tjrhq-intel-postgres.service
OnFailure=alert-on-failure@%n.service

[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
ExecStart=/usr/bin/python3 -I $OPT/backup.py run
UNIT
cat > /etc/systemd/system/tjrhq-intel-backup.timer <<'UNIT'
[Unit]
Description=Twice daily, so one missed run still leaves a snapshot under 24 hours old

[Timer]
OnCalendar=*-*-* 03:20:00
OnCalendar=*-*-* 15:20:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT
cat > /etc/systemd/system/tjrhq-intel-freshness.service <<UNIT
[Unit]
Description=Alert when the intelligence store has no off-host snapshot under 24 hours old
OnFailure=alert-on-failure@%n.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I $OPT/backup.py check-fresh
UNIT
cat > /etc/systemd/system/tjrhq-intel-freshness.timer <<'UNIT'
[Unit]
Description=Check intelligence store snapshot age

[Timer]
OnCalendar=*-*-* 04:30:00
OnCalendar=*-*-* 16:30:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable -q --now tjrhq-intel-postgres.service
for _ in $(seq 1 60); do docker exec -u "$(id -u tjrhq-intel-db)" tjrhq-intel-pg psql -qAt -U tjrhq-intel-db -d intel -c 'select 1' >/dev/null 2>&1 && break; read -t 1 <> <(:) || true; done
read -t 3 <> <(:) || true     # the image restarts the server once after first initialisation
for _ in $(seq 1 60); do docker exec tjrhq-intel-pg pg_isready -q && break; read -t 1 <> <(:) || true; done
docker exec -i -u "$(id -u tjrhq-intel-db)" tjrhq-intel-pg psql -q -v ON_ERROR_STOP=1 -U tjrhq-intel-db -d intel < "$OPT/schema.sql"
echo installed
