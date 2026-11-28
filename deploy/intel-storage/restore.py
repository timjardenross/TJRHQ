#!/usr/bin/env python3
# ruff: noqa: SIM115  (small single-user command-line tools)
"""Restore the latest intel-b snapshot into a freshly installed, EMPTY store and reconcile it with its manifest.
Run as root from the repository checkout (a purge removes the installed copy): restore.py WORKDIR [SNAPSHOT_ID]
Refuses a destination that holds anything. Exits non-zero unless every reconciliation check passes."""
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
        semantic = await store.coverage(con)
    finally:
        await con.close()
    return {"counts_match": counts == manifest["counts"], "lineage_match": lineage == manifest["lineage_md5"], "object_set_match": objects == manifest["objects"],
            "objects": checked, "orphan_files": len(stray), "orphan_rows": len(unused), "counts": counts, "semantic_search": semantic}


CHECKS = ("counts_match", "lineage_match", "object_set_match")


async def destination_contents():
    con = await store.connect("tjrhq-intel-db")
    try:
        held = {k: v for k, v in dict(await con.fetchrow(backup.COUNTS)).items() if v}
        vectors = await con.fetchval("select count(*) from intel.passage_embedding")
    finally:
        await con.close()
    held.update({"vectors": vectors} if vectors else {})
    files = sum(len(names) for _d, _s, names in os.walk(store.ROOT))
    held.update({"object_files": files} if files else {})
    return held


def failures(result):
    bad = [k for k in CHECKS if not result[k]]
    bad += [k for k in ("missing_or_unreadable", "digest_mismatch") if result["objects"][k]]
    return bad + [k for k in ("orphan_files", "orphan_rows") if result[k]]


def main(work, snapshot="latest"):
    t0 = time.monotonic()
    held = asyncio.run(destination_contents())
    if held:
        raise SystemExit(f"refused: the destination is not empty: {held}")
    os.makedirs(work, mode=0o700, exist_ok=False)
    backup.restic("restore", snapshot, "--tag", backup.TAG, "--target", work)
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
    here = backup.code_hashes(os.path.dirname(os.path.abspath(__file__)))
    result.update({"snapshot_revision": manifest.get("revision"), "code_differs_from_snapshot": sorted(k for k, v in manifest.get("code_sha256", {}).items() if here.get(k) != v),
                   "failed_checks": failures(result)})
    result.update({"snapshot_taken_at": manifest["taken_at"], "fetch_seconds": round(t_fetch, 1), "total_seconds": round(time.monotonic() - t0, 1)})
    print(json.dumps(result))
    return 2 if result["failed_checks"] else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
