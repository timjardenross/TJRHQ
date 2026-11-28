#!/usr/bin/env python3
# ruff: noqa: SIM115  (small single-user command-line tools)
"""Restore the latest intel-b snapshot into a freshly installed, empty store and reconcile it with its manifest. Run as root: restore.py WORKDIR
Run the copy in the repository checkout (the installed one is removed by a purge)."""
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup
import store


async def reconcile(manifest):
    con = await store.connect("tjrhq-intel-db")
    try:
        counts = dict(await con.fetchrow(backup.COUNTS))
        lineage = await con.fetchval(backup.LINEAGE)
        objects = [[r["domain"], r["sha256"]] for r in await con.fetch("select domain, sha256 from intel.object order by sha256")]
        checked = await store.verify(con)
        stray, unused = await store.orphans(con)
    finally:
        await con.close()
    return {"counts_match": counts == manifest["counts"], "lineage_match": lineage == manifest["lineage_md5"], "object_set_match": objects == manifest["objects"],
            "objects": checked, "orphan_files": len(stray), "orphan_rows": len(unused), "counts": counts}


def main(work):
    t0 = time.monotonic()
    os.makedirs(work, mode=0o700, exist_ok=False)
    backup.restic("restore", "latest", "--tag", backup.TAG, "--target", work)
    t_fetch = time.monotonic() - t0
    stage = work + backup.STAGE
    manifest = json.load(open(f"{stage}/manifest.json"))
    if hashlib.sha256(open(f"{stage}/db.dump", "rb").read()).hexdigest() != manifest["db_dump_sha256"]:
        raise SystemExit("database dump does not match the manifest")
    uid = str(os.stat("/var/lib/tjrhq-intel/postgres").st_uid)
    with open(f"{stage}/db.dump", "rb") as dump:
        subprocess.run(["docker", "exec", "-i", "-u", uid, "tjrhq-intel-pg", "pg_restore", "-U", "tjrhq-intel-db", "-d", "intel", "--clean", "--if-exists",
                        "--exit-on-error"], stdin=dump, check=True)
    shutil.copytree(work + store.ROOT, store.ROOT, dirs_exist_ok=True)
    subprocess.run(["chown", "-R", "tjrhq-intel-ingest:tjrhq-intel-obj", store.ROOT], check=True)
    subprocess.run(["find", store.ROOT, "-type", "d", "-exec", "chmod", "2750", "{}", "+"], check=True)
    result = asyncio.run(reconcile(manifest))
    result.update({"snapshot_taken_at": manifest["taken_at"], "fetch_seconds": round(t_fetch, 1), "total_seconds": round(time.monotonic() - t0, 1)})
    print(json.dumps(result))


if __name__ == "__main__":
    main(sys.argv[1])
