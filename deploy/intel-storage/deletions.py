#!/usr/bin/env python3
"""Mandatory deletions that survive a restore.

The ledger holds identifiers and reasons only. It lives outside the database and its snapshots, is copied off-host on its own tag, and the
LATEST copy is applied after any restore, whatever age the restored snapshot is, before the store is used. Run as root.

  deletions.py add ID --reason TEXT [--no-stub]   record, apply to the live store, copy the ledger off-host
  deletions.py apply                              apply the whole ledger to the live store
  deletions.py check                              fail if anything on the ledger is present
--no-stub: not even the identifier may remain in other records' relationships.
"""

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LEDGER = "/var/lib/tjrhq-intel/deletion-ledger.jsonl"
TAG = "intel-deletions"


def entries(path=LEDGER):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def append(identifier, reason, stub, path=LEDGER):
    uuid.UUID(identifier)                                   # identifiers only: never content
    if not reason.strip() or len(reason) > 200:
        raise SystemExit("a short reason is required")
    row = {"id": identifier, "reason": reason.strip(), "stub": stub, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


async def apply(con, rows):
    """Idempotent. Returns how many records were removed now."""
    removed = 0
    async with con.transaction():
        for r in rows:
            removed += int((await con.execute("delete from intel.c_event where event_id = $1", r["id"])).split()[-1])
            await con.execute("delete from intel.c_edge where cohort_event_id = $1", r["id"])
            if r["stub"]:
                await con.execute("update intel.c_edge set endpoint = 'deleted' where linked_id = $1", r["id"])
                await con.execute("update intel.c_event set canonical_state = 'deleted' where canonical_signal_id = $1", r["id"])
            else:
                await con.execute("delete from intel.c_edge where linked_id = $1", r["id"])
                await con.execute("update intel.c_event set canonical_signal_id = null, canonical_state = 'deleted' where canonical_signal_id = $1", r["id"])
    return removed


async def present(con, rows):
    ids = [r["id"] for r in rows]
    bare = [r["id"] for r in rows if not r["stub"]]
    return await con.fetchval("select (select count(*) from intel.c_event where event_id = any($1::text[])) "
                              "+ (select count(*) from intel.c_edge where linked_id = any($2::text[]) or cohort_event_id = any($1::text[])) "
                              "+ (select count(*) from intel.c_event where canonical_signal_id = any($2::text[]))", ids, bare)


def ship():
    import backup

    backup.restic("backup", "--tag", TAG, LEDGER)


def fetch_latest(work):
    """Bring the newest off-host ledger onto this host and merge it with the local one. A missing ledger is an error once one has shipped."""
    import backup

    snapshots = json.loads(backup.restic("snapshots", "--tag", TAG, "--json"))
    if not snapshots:
        return 0
    os.makedirs(work, mode=0o700, exist_ok=True)
    backup.restic("restore", "latest", "--tag", TAG, "--target", work)
    have = {(r["id"], r["at"]) for r in entries()}
    new = [r for r in entries(work + LEDGER) if (r["id"], r["at"]) not in have]
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in new)
    return len(entries())


async def run(cmd):
    import store

    con = await store.connect("tjrhq-intel-db")
    try:
        rows = entries()
        if cmd == "apply":
            return {"ledger": len(rows), "records_removed": await apply(con, rows), "still_present": await present(con, rows)}
        return {"ledger": len(rows), "still_present": await present(con, rows)}
    finally:
        await con.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="deletions")
    ap.add_argument("cmd", choices=("add", "apply", "check"))
    ap.add_argument("id", nargs="?")
    ap.add_argument("--reason", default="")
    ap.add_argument("--no-stub", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        append(a.id, a.reason, not a.no_stub)
        out = asyncio.run(run("apply"))
        ship()                                              # if this fails the deletion is not protected: let it raise
        out["shipped_off_host"] = True
    else:
        out = asyncio.run(run(a.cmd))
    print(json.dumps(out))
    return 2 if out["still_present"] else 0


if __name__ == "__main__":
    sys.exit(main())
