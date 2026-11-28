#!/usr/bin/env python3

"""Embed substantive passages with the local model, one request at a time. Run as tjrhq-intel-ingest: embed.py [MAX_PASSAGES] [RECENT_HOURS]
Order: documents of active investigations (intel.rebuild_priority), then newest evidence first. With RECENT_HOURS, only those two groups
(recent measured back from the newest document). Pauses at brief times and stops when the guard's stop file appears."""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard
import store

BATCH = 16


SCOPE = """from intel.passage p join intel.document d on d.id = p.document_id
left join intel.rebuild_priority r on r.document_id = p.document_id
left join intel.passage_embedding e on (e.document_id, e.ordinal) = (p.document_id, p.ordinal)
where p.substantive and e.document_id is null
  and ($1::int is null or r.document_id is not null
       or d.retrieved_at > (select max(retrieved_at) from intel.document) - make_interval(hours => $1::int))"""


async def main(limit, hours):
    con = await store.connect("intel_ingest")
    stop = os.environ.get("INTEL_STOP_FILE")
    done, start = 0, time.monotonic()
    while done < limit and not (stop and os.path.exists(stop)) and not guard.quiet_now():
        rows = await con.fetch(f"select p.document_id, p.ordinal, p.body {SCOPE} "
                               "order by (r.document_id is null), d.retrieved_at desc, p.document_id, p.ordinal limit $2", hours, min(BATCH, limit - done))
        if not rows:
            break
        vectors = store.embed(["search_document: " + r["body"] for r in rows])
        await con.executemany("insert into intel.passage_embedding values ($1,$2,$3,$4::vector)",
                              [(r["document_id"], r["ordinal"], store.MODEL, store.vec(v)) for r, v in zip(rows, vectors, strict=True)])
        done += len(rows)
    secs = time.monotonic() - start
    print(json.dumps({"embedded": done, "seconds": round(secs, 1), "per_second": round(done / secs, 2) if secs else None,
                      "pending_in_scope": await con.fetchval(f"select count(*) {SCOPE}", hours), "coverage": await store.coverage(con)}))
    await con.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10**9, int(sys.argv[2]) if len(sys.argv) > 2 else None))
