#!/usr/bin/env python3
# ruff: noqa: SIM115, ASYNC221, ASYNC230  (small single-user command-line tools)
"""Matched database and object backup to the existing encrypted off-host repository (tag intel-b). Run as root: backup.py run|check-fresh"""
import asyncio
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

STAGE = "/var/lib/tjrhq-intel/backup-stage"
TAG = "intel-b"
CEILING_BYTES, MIN_REMOTE_FREE_BYTES = 15 * 10**9, 2 * 2**30
COUNTS = ("select (select count(*) from intel.object) objects, (select count(*) from intel.document) documents, (select count(*) from intel.passage) passages, "
          "(select count(*) from intel.rebuild_priority) rebuild_priority")
LINEAGE = ("select md5(coalesce(string_agg(id || ':' || object_sha256 || ':' || coalesce(previous_id, 0) || ':' || md5(body), ',' order by id), '')) "
           "from intel.document")


def restic_env():
    """Repository location and password file as the existing nightly job defines them; neither is copied or changed."""
    env = dict(os.environ, HOME="/root")
    for line in open("/opt/starship-backup/backup.sh"):
        m = re.match(r'export (RESTIC_REPOSITORY|RESTIC_PASSWORD_FILE)="\$\{\1:-([^}]+)\}"', line) or re.match(r"export (RESTIC_REPOSITORY|RESTIC_PASSWORD_FILE)=(\S+)", line)
        if m:
            env[m.group(1)] = m.group(2).strip('"')
    return env


def restic(*args, **kw):
    return subprocess.run(["restic", "-o", "rclone.program=/usr/local/bin/rclone", *args], env=restic_env(), check=True, capture_output=True, text=True, **kw).stdout


def code_hashes(folder="/opt/tjrhq-intel"):
    """SHA-256 of every installed program and schema file, so a snapshot names the exact code that made it."""
    out = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith((".py", ".sql")):
            with open(os.path.join(folder, name), "rb") as fh:
                out[name] = hashlib.sha256(fh.read()).hexdigest()
    return out


def remote_free():
    out = subprocess.run(["/usr/local/bin/rclone", "about", "gdrive2:", "--json"], env=restic_env(), check=True, capture_output=True, text=True).stdout
    return json.loads(out)["free"]


async def dump():
    con = await store.connect("tjrhq-intel-db")
    try:
        async with con.transaction(isolation="repeatable_read", readonly=True):
            snapshot = await con.fetchval("select pg_export_snapshot()")
            counts = dict(await con.fetchrow(COUNTS))
            lineage = await con.fetchval(LINEAGE)
            objects = [[r["domain"], r["sha256"]] for r in await con.fetch("select domain, sha256 from intel.object order by sha256")]
            uid = str(os.stat("/var/lib/tjrhq-intel/postgres").st_uid)
            with open(f"{STAGE}/db.dump", "wb") as out:
                subprocess.run(["docker", "exec", "-u", uid, "tjrhq-intel-pg", "pg_dump", "-U", "tjrhq-intel-db", "-d", "intel", "-Fc",
                                "--snapshot", snapshot, "--exclude-table-data=intel.passage_embedding"], stdout=out, check=True)
    finally:
        await con.close()
    return counts, lineage, objects


def run():
    started = time.monotonic()
    taken = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    free = remote_free()
    if free < MIN_REMOTE_FREE_BYTES:
        raise SystemExit(f"refused: only {free} bytes free off-host")
    with open("/run/starship-backup.lock", "a") as nightly, open(store.MAINT_LOCK, "a") as maint:
        fcntl.flock(nightly, fcntl.LOCK_EX)         # never concurrent with the existing nightly backup
        fcntl.flock(maint, fcntl.LOCK_EX)           # no object removal between the dump and the copy
        counts, lineage, objects = asyncio.run(dump())
        if not counts["documents"]:
            raise SystemExit("refused: the store is empty, so this snapshot must not become the latest recoverable one")
        manifest = {"taken_at": taken, "counts": counts, "lineage_md5": lineage, "objects": objects,
                    "db_dump_sha256": hashlib.sha256(open(f"{STAGE}/db.dump", "rb").read()).hexdigest(),
                    "image": open("/etc/tjrhq-intel/image").read().strip(),
                    "revision": open("/opt/tjrhq-intel/REVISION").read().strip(), "code_sha256": code_hashes()}
        json.dump(manifest, open(f"{STAGE}/manifest.json", "w"))
        out = restic("backup", "--tag", TAG, "--json", f"{STAGE}/db.dump", f"{STAGE}/manifest.json", store.ROOT, "/etc/tjrhq-intel", "/opt/tjrhq-intel")
    summary = next(j for j in map(json.loads, out.splitlines()) if j.get("message_type") == "summary")
    restic("forget", "--tag", TAG, "--group-by", "host,tags", "--keep-daily", "7", "--keep-weekly", "4")     # no prune: the nightly job prunes
    size = json.loads(restic("stats", "--mode", "raw-data", "--json"))["total_size"]
    result = {"taken_at": taken, "snapshot": summary["snapshot_id"][:8], "seconds": round(time.monotonic() - started, 1), "counts": counts,
              "bytes_processed": summary["total_bytes_processed"], "bytes_added": summary["data_added"], "repository_bytes": size,
              "remote_free_bytes": remote_free()}
    json.dump(result, open(f"{STAGE}/last-success.json", "w"))
    print(json.dumps(result))
    if size > CEILING_BYTES:
        raise SystemExit("repository exceeds the provisional ceiling")


def check_fresh():
    try:
        last = json.load(open(f"{STAGE}/last-success.json"))
    except (OSError, ValueError):
        print(json.dumps({"snapshot": None, "within_24h": False, "reason": "no successful backup recorded on this installation"}))
        return 1
    age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last["taken_at"])).total_seconds() / 3600
    print(json.dumps({"snapshot": last["snapshot"], "age_hours": round(age, 2), "within_24h": age <= 24}))
    return 0 if age <= 24 else 1


if __name__ == "__main__":
    sys.exit(run() if sys.argv[1] == "run" else check_fresh())
