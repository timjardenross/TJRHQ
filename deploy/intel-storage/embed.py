#!/usr/bin/env python3

"""Embed substantive passages with the local model, one request at a time. Run as tjrhq-intel-ingest: embed.py [MAX_PASSAGES]
Pauses at brief times and stops when the guard's stop file appears. Planted fixtures are always embedded first."""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard
import store

BATCH = 16


async def main(limit):
    con = await store.connect("intel_ingest")
    stop = os.environ.get("INTEL_STOP_FILE")
    done, start = 0, time.monotonic()
    while done < limit and not (stop and os.path.exists(stop)) and not guard.quiet_now():
        rows = await con.fetch("select p.document_id, p.ordinal, p.body from intel.passage p left join intel.passage_embedding e using (document_id, ordinal) "
                               "where p.substantive and e.document_id is null order by (p.document_id not in (7, 11)), p.document_id, p.ordinal limit $1",
                               min(BATCH, limit - done))
        if not rows:
            break
        vectors = store.embed(["search_document: " + r["body"] for r in rows])
        await con.executemany("insert into intel.passage_embedding values ($1,$2,$3,$4::vector)",
                              [(r["document_id"], r["ordinal"], store.MODEL, store.vec(v)) for r, v in zip(rows, vectors, strict=True)])
        done += len(rows)
    secs = time.monotonic() - start
    print(json.dumps({"embedded": done, "seconds": round(secs, 1), "per_second": round(done / secs, 2) if secs else None,
                      "pending": await con.fetchval("select count(*) from intel.passage p where substantive and not exists "
                                                    "(select 1 from intel.passage_embedding e where (e.document_id, e.ordinal) = (p.document_id, p.ordinal))")}))
    await con.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10**9))
