#!/usr/bin/env python3
"""Mandatory deletions that survive a restore.

The ledger holds identifiers and reasons only. It is a numbered hash chain starting from a genesis entry, so absence, truncation and
alteration are all detectable; `init` creates it and copies it off-host before any record can be protected. It lives outside the database and its snapshots, is copied off-host on its own tag, and the
LATEST copy is applied after any restore, whatever age the restored snapshot is, before the store is used. Run as root.

  deletions.py init                           create the ledger and copy it off-host (once per installation lineage)
  deletions.py add ID --reason TEXT [--no-stub]   record, apply to the live store, copy the ledger off-host
  deletions.py apply                              apply the whole ledger to the live store
  deletions.py check                              fail if anything on the ledger is present
--no-stub: not even the identifier may remain in other records' relationships.
"""

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LEDGER = "/var/lib/tjrhq-intel/deletion-ledger.jsonl"
TAG = "intel-deletions"


class LedgerError(SystemExit):
    """The deletion ledger is absent or cannot be trusted: nothing restored may be handed back."""


def entries(path=LEDGER):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def seal(row):
    return hashlib.sha256(json.dumps({k: v for k, v in row.items() if k != "hash"}, sort_keys=True).encode()).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def genesis():
    row = {"seq": 0, "id": None, "reason": "ledger started", "stub": True, "at": now(), "prev": ""}
    return {**row, "hash": seal(row)}


def entry(previous, identifier, reason, stub):
    uuid.UUID(identifier)                                   # identifiers only: never content
    if not reason.strip() or len(reason) > 200:
        raise SystemExit("a short reason is required")
    row = {"seq": previous["seq"] + 1, "id": identifier, "reason": reason.strip(), "stub": stub, "at": now(), "prev": previous["hash"]}
    return {**row, "hash": seal(row)}


def verify_chain(rows, at_least=0):
    """at_least: how many deletions the thing being restored already knew of; a shorter ledger is a truncated one."""
    if not rows or rows[0].get("seq") != 0 or rows[0].get("id") is not None:
        raise LedgerError("deletion ledger: absent or without its first entry")
    previous = ""
    for n, row in enumerate(rows):
        if row.get("seq") != n or row.get("prev") != previous or row.get("hash") != seal(row):
            raise LedgerError(f"deletion ledger: broken at entry {n}")
        previous = row["hash"]
    if len(rows) - 1 < at_least:
        raise LedgerError(f"deletion ledger: {len(rows) - 1} deletion(s) but at least {at_least} were known")
    return rows


def write(row, path=LEDGER):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def append(identifier, reason, stub, path=LEDGER):
    rows = verify_chain(entries(path))
    write(entry(rows[-1], identifier, reason, stub), path)


def scan_sql(tables):
    """Count rows, in any column of any table of the store, that mention one of the identifiers in $1."""
    return " + ".join(f'(select count(*) from "{s}"."{t}" x where exists (select 1 from unnest($1::text[]) i where position(i in x::text) > 0))'
                      for s, t in tables)


async def apply(con, rows):
    """Idempotent. Returns how many records were removed now."""
    removed = 0
    async with con.transaction():
        for r in (x for x in rows if x.get("id")):
            removed += int((await con.execute("delete from intel.c_event where event_id = $1", r["id"])).split()[-1])
            if not r["stub"]:                               # the batch's own record of what was held is metadata too
                await con.execute("update intel.c_batch set held = held - $1 where held ? $1", r["id"])
            await con.execute("delete from intel.c_edge where cohort_event_id = $1", r["id"])
            if r["stub"]:
                await con.execute("update intel.c_edge set endpoint = 'deleted' where linked_id = $1", r["id"])
                await con.execute("update intel.c_event set canonical_state = 'deleted' where canonical_signal_id = $1", r["id"])
            else:
                await con.execute("delete from intel.c_edge where linked_id = $1", r["id"])
                await con.execute("update intel.c_event set canonical_signal_id = null, canonical_state = 'deleted' where canonical_signal_id = $1", r["id"])
    return removed


async def present(con, rows):
    """Rows still carrying something prohibited: a deleted record itself, or, where no stub may remain, any mention anywhere."""
    ids = [r["id"] for r in rows if r.get("id")]
    bare = [r["id"] for r in rows if r.get("id") and not r["stub"]]
    found = await con.fetchval("select count(*) from intel.c_event where event_id = any($1::text[])", ids)
    if bare:
        tables = [(t["table_schema"], t["table_name"]) for t in await con.fetch(
            "select table_schema, table_name from information_schema.tables where table_schema = 'intel' and table_type = 'BASE TABLE'")]
        found += await con.fetchval("select " + scan_sql(tables), bare)
    return found


def ship():
    import backup

    backup.restic("backup", "--tag", TAG, LEDGER)


def off_host_snapshots():
    import backup

    return json.loads(backup.restic("snapshots", "--tag", TAG, "--json") or "[]")


def fetch_latest(work, at_least=0):
    """Bring the newest off-host ledger onto this host and verify it. No off-host ledger, or an unverifiable one, is an error."""
    import backup

    if not off_host_snapshots():
        raise LedgerError("deletion ledger: none is held off-host")
    os.makedirs(work, mode=0o700, exist_ok=True)
    backup.restic("restore", "latest", "--tag", TAG, "--target", work)
    remote = verify_chain(entries(work + LEDGER), at_least)
    local = entries()
    if local:
        verify_chain(local)
        shorter, longer = sorted((local, remote), key=len)
        if [r["hash"] for r in longer[: len(shorter)]] != [r["hash"] for r in shorter]:
            raise LedgerError("deletion ledger: the local and off-host copies disagree")
        remote = longer
    for row in remote[len(local):]:
        write(row)
    return len(remote) - 1


def init():
    if entries() or off_host_snapshots():
        raise SystemExit("refused: a deletion ledger already exists")
    write(genesis())
    ship()


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
    ap.add_argument("cmd", choices=("init", "add", "apply", "check"))
    ap.add_argument("id", nargs="?")
    ap.add_argument("--reason", default="")
    ap.add_argument("--no-stub", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "init":
        init()
        print(json.dumps({"started": True, "shipped_off_host": True}))
        return 0
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
