#!/usr/bin/env python3
# ruff: noqa: ASYNC230  (small single-user command-line tools)
"""Content-addressed, Zstandard-compressed evidence objects and the checks that tie them to the database.

  store.py verify              (intel_read)   every referenced object present, decompresses, matches its digest
  store.py orphans             (intel_read)   files without a row, rows without a document
  store.py gc                  (intel_maint)  remove orphans
  store.py search TEXT         (intel_read)   full-text search
  store.py similar TEXT        (intel_read)   nearest embedded passages, with how much of the corpus that covers
  store.py coverage            (intel_read)   share of substantive passages searchable by meaning
"""
import asyncio
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

import asyncpg

ROOT = "/var/lib/tjrhq-intel/objects"
SOCKET = "/run/tjrhq-intel"
OLLAMA = "http://127.0.0.1:11434/api/embed"
MODEL = "nomic-embed-text"
MAINT_LOCK = "/var/lib/tjrhq-intel/spool/maintenance.lock"


async def connect(role):
    return await asyncpg.connect(host=SOCKET, port=5432, user=role, database="intel")


def path_for(domain, digest):
    return os.path.join(ROOT, domain, "sha256", digest[:2], digest + ".zst")


def put_object(domain, data):
    """Write once. Returns (digest, stored_bytes). The file is durable before the caller records it."""
    digest = hashlib.sha256(data).hexdigest()
    final = path_for(domain, digest)
    if not os.path.exists(final):
        folder = os.path.dirname(final)
        os.makedirs(folder, mode=0o2750, exist_ok=True)
        packed = subprocess.run(["zstd", "-q", "-10", "-c"], input=data, capture_output=True, check=True).stdout
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
        with os.fdopen(fd, "wb") as fh:
            fh.write(packed)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o440)
        os.replace(tmp, final)
        dir_fd = os.open(folder, os.O_RDONLY)
        os.fsync(dir_fd)
        os.close(dir_fd)
    return digest, os.path.getsize(final)


def read_object(domain, digest):
    out = subprocess.run(["zstd", "-q", "-d", "-c", path_for(domain, digest)], capture_output=True, check=True).stdout
    if hashlib.sha256(out).hexdigest() != digest:
        raise ValueError("digest mismatch " + digest)
    return out


def files():
    for folder, _dirs, names in os.walk(ROOT):
        for n in names:
            if n.endswith(".zst"):
                yield n[:-4], os.path.join(folder, n)


async def verify(con):
    rows = await con.fetch("select domain, sha256 from intel.object")
    missing = corrupt = 0
    for r in rows:
        try:
            read_object(r["domain"], r["sha256"])
        except subprocess.CalledProcessError:
            missing += 1
        except ValueError:
            corrupt += 1
    return {"objects": len(rows), "missing_or_unreadable": missing, "digest_mismatch": corrupt}


async def orphans(con):
    known = {r["sha256"] for r in await con.fetch("select sha256 from intel.object")}
    unused = await con.fetch("select domain, sha256 from intel.object o where not exists (select 1 from intel.document d where d.object_sha256 = o.sha256)")
    return [p for h, p in files() if h not in known], [(r["domain"], r["sha256"]) for r in unused]


def embed(texts):
    req = urllib.request.Request(OLLAMA, data=json.dumps({"model": MODEL, "input": texts, "options": {"num_thread": 2}}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:  # nosec B310 - fixed loopback address
        return json.load(resp)["embeddings"]


COVERAGE = """
select count(*) filter (where p.substantive) as substantive, count(e.document_id) filter (where p.substantive) as embedded,
       count(*) filter (where p.substantive and r.document_id is not null) as priority,
       count(e.document_id) filter (where p.substantive and r.document_id is not null) as priority_embedded
from intel.passage p left join intel.passage_embedding e using (document_id, ordinal) left join intel.rebuild_priority r using (document_id)"""


async def coverage(con):
    """What semantic search can currently see. Anything short of all substantive passages is stated as degraded."""
    c = dict(await con.fetchrow(COVERAGE))
    c["percent"] = round(100 * c["embedded"] / c["substantive"], 2) if c["substantive"] else 100.0
    c["degraded"] = c["embedded"] < c["substantive"]
    if c["degraded"]:
        c["notice"] = (f"Semantic search is degraded: {c['percent']}% of substantive passages are searchable by meaning. "
                       "A missing result is not evidence of absence; use full-text search.")
    return c


def vec(values):
    return "[" + ",".join(f"{v:.7f}" for v in values) + "]"


async def main(argv):
    cmd = argv[0]
    con = await connect("intel_maint" if cmd == "gc" else "intel_read")
    try:
        if cmd == "verify":
            print(json.dumps(await verify(con)))
        elif cmd == "orphans":
            stray, unused = await orphans(con)
            print(json.dumps({"files_without_row": len(stray), "rows_without_document": len(unused)}))
        elif cmd == "gc":
            with open(MAINT_LOCK, "a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)           # never while a backup is copying objects
                stray, unused = await orphans(con)
                for domain, digest in unused:
                    await con.execute("delete from intel.object where sha256 = $1", digest)
                    stray.append(path_for(domain, digest))
                removed = 0
                for p in stray:
                    if os.path.exists(p):
                        os.unlink(p)
                        removed += 1
                print(json.dumps({"rows_removed": len(unused), "files_removed": removed}))
        elif cmd == "search":
            rows = await con.fetch("select id, ts_rank(search, q) r from intel.document, websearch_to_tsquery('english', $1) q where search @@ q order by r desc limit 5", argv[1])
            print(json.dumps([r["id"] for r in rows]))
        elif cmd == "similar":
            v = vec(embed(["search_query: " + argv[1]])[0])
            rows = await con.fetch("select document_id from intel.passage_embedding order by embedding <=> $1::vector limit 5", v)
            print(json.dumps({"documents": [r["document_id"] for r in rows], "coverage": await coverage(con)}))
        elif cmd == "coverage":
            print(json.dumps(await coverage(con)))
    finally:
        await con.close()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(main(sys.argv[1:]))
