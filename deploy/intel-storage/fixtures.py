#!/usr/bin/env python3
# ruff: noqa: SIM905  (small single-user command-line tools)
"""Deterministic synthetic documents only (fictional providers and places). Run as tjrhq-intel-ingest: fixtures.py COUNT"""
import asyncio
import datetime as dt
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

WORDS = ("outage service network power water payment exchange regulator notice restoration supplier region failover capacity alert "
         "maintenance incident customers operator disruption backup settlement fibre substation telemetry advisory review control "
         "obligation resilience dependency recovery monitoring degraded elevated errors latency authentication storage").split()
PLACES = ("Karrabin", "Wollumba", "Teyvale", "Port Ashcombe", "Merrinook", "Dunsford Ridge")
FIRMS = ("Quillon Telecom", "Verdant Grid", "Orrery Pay", "Halcyon Water", "Bluegum Cloud")
PLANTED = {7: ("zephyrine interchange", "A beekeeper cooperative reported that its hive sensors stopped sending temperature readings after frost."),
           11: ("quokkaline relay", "Ferry ticketing kiosks at the harbour refused cards because a certificate had expired overnight.")}


def paragraph(rng):
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(40, 110))).capitalize() + f" near {rng.choice(PLACES)}."


def document(i):
    rng = random.Random(i)
    firm = rng.choice(FIRMS)
    paras = [paragraph(rng) for _ in range(rng.randint(2, 9))]
    title = f"Synthetic notice {i}: {firm} {rng.choice(WORDS)} {rng.choice(WORDS)}"
    if i in PLANTED:
        term, sentence = PLANTED[i]
        paras = [f"{sentence} {term}. {sentence}"] + paras[:1]
    return title, paras


async def main(count):
    con = await store.connect("intel_ingest")
    start, done = time.monotonic(), await con.fetchval("select coalesce(max(id), 0) from intel.document")
    stop = os.environ.get("INTEL_STOP_FILE")
    base = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    raw = stored = 0
    for i in range(done + 1, count + 1):
        if stop and i % 200 == 0 and os.path.exists(stop):
            print("stopped by guard", file=sys.stderr)
            break
        previous = i - 20 if i > 20 and i % 10 == 0 else None          # every tenth is a newer version of an earlier one
        copy = i - 1 if not previous and i % 25 == 0 else None         # byte-identical republication: one object, two documents
        title, paras = document(previous or copy or i)
        if previous:
            paras = paras + [f"Update {i}: restoration reported."]
        body = "\n\n".join(paras)
        data = f"<html><title>{title}</title><body>{body}</body></html>".encode()
        digest, size = store.put_object("synthetic", data)
        raw, stored = raw + len(data), stored + size
        async with con.transaction():
            await con.execute("insert into intel.object values ($1,'synthetic',$2,$3) on conflict do nothing", digest, len(data), size)
            await con.execute("insert into intel.document (id, source_key, uri, title, body, origin, object_sha256, previous_id, retrieved_at) "
                              "values ($1,$2,$3,$4,$5,'synthetic',$6,$7,$8)", i, f"synthetic-{i % 37}", f"https://example.invalid/{i}", title, body,
                              digest, previous, base + dt.timedelta(minutes=3 * i))
            await con.executemany("insert into intel.passage values ($1,$2,$3,$4)", [(i, n, p, len(p) >= 400 or i in PLANTED) for n, p in enumerate(paras)])
    print(json.dumps({"documents": await con.fetchval("select count(*) from intel.document"), "seconds": round(time.monotonic() - start, 1),
                      "raw_mb": round(raw / 1e6, 1), "stored_mb": round(stored / 1e6, 1)}))
    await con.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
