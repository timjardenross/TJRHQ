#!/usr/bin/env python3
"""Package C pilot: copy one fixed historical cohort into the isolated store, prove it, and be able to take it out again.

The source stays authoritative and is only ever read. Existing links are copied as recorded; nothing is inferred, matched or repaired.
An export is a folder: events.jsonl, edges.jsonl, sources.jsonl, manifest.json.

  package_c.py synthetic DIR                    write a synthetic export with the cohort's shape (fictional content)
  package_c.py plan DIR --holds F               check files, digests and holds; write nothing           (any user)
  package_c.py import DIR --holds F --batch B   load in one transaction                                 (tjrhq-intel-ingest)
  package_c.py verify DIR --holds F --batch B   compare the store with the export, field by field       (tjrhq-intel-read)
  package_c.py compare OLD NEW                  what changed at the source between two exports          (any user)
  package_c.py rollback --batch B               remove exactly that batch                               (tjrhq-intel-ingest as intel_maint)

A holds file lists every record that must not be copied: JSON {"event_id": {"disposition": "held"|"review", "rules": [...]}}. It is
required; {} states that screening held none. Recorded links of held records are still kept, as identifiers only.
Importing anything that is not marked synthetic needs --authorised "<the principal's execution authority>".
"""
# ruff: noqa: SIM115  (small single-user command-line tool)
import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import random
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EVENT_FIELDS = ("event_id", "source_id", "raw_title", "raw_summary", "canonical_url", "geography", "collected_at", "published_at",
                "published_at_basis", "signal_status", "suppressed", "suppression_reason", "publisher_domain", "publisher_family",
                "published_at_precision", "published_at_confidence")
TIME_FIELDS = ("collected_at", "published_at")
EDGE_FIELDS = ("cohort_event_id", "relation", "linked_id")
SOURCE_FIELDS = ("source_id", "source_name", "licence_url", "attribution")
EVENT_RELATIONS = ("canonical_of_this", "has_this_as_canonical", "corroborated_by", "corroborates")
LICENCE = {"APRA": ("https://www.apra.gov.au/copyright", "© Australian Prudential Regulation Authority"),
           "RBA": ("https://www.rba.gov.au/copyright/", "Source: Reserve Bank of Australia")}


def norm_time(value):
    if value in (None, ""):
        return None
    when = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    return (when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat(timespec="microseconds")


def canonical(row, fields):
    out = {}
    for f in fields:
        v = row.get(f)
        out[f] = norm_time(v) if f in TIME_FIELDS else str(v) if isinstance(v, uuid.UUID) else v
    return out


def digest_rows(rows, fields):
    lines = sorted(json.dumps(canonical(r, fields), sort_keys=True, ensure_ascii=False) for r in rows)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_export(folder, events, edges, sources, *, as_of, synthetic):
    os.makedirs(folder, mode=0o750, exist_ok=False)
    manifest = {"as_of": as_of, "synthetic": synthetic, "counts": {}, "digests": {}}
    for name, rows, fields in (("events", events, EVENT_FIELDS), ("edges", edges, EDGE_FIELDS), ("sources", sources, SOURCE_FIELDS)):
        with open(f"{folder}/{name}.jsonl", "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(canonical(r, fields), sort_keys=True, ensure_ascii=False) + "\n" for r in rows)
        manifest["counts"][name] = len(rows)
        manifest["digests"][name] = digest_rows(rows, fields)
    json.dump(manifest, open(f"{folder}/manifest.json", "w"), indent=1)
    return manifest


def load_export(folder):
    """The export, or SystemExit: every file must match the manifest and be internally consistent."""
    manifest = json.load(open(f"{folder}/manifest.json"))
    data = {n: read_jsonl(f"{folder}/{n}.jsonl") for n in ("events", "edges", "sources")}
    fields = {"events": EVENT_FIELDS, "edges": EDGE_FIELDS, "sources": SOURCE_FIELDS}
    bad = [f"{n}: count or digest differs from the manifest" for n, rows in data.items()
           if len(rows) != manifest["counts"][n] or digest_rows(rows, fields[n]) != manifest["digests"][n]]
    ids = [e["event_id"] for e in data["events"]]
    sources = {s["source_id"] for s in data["sources"]}
    if len(set(ids)) != len(ids):
        bad.append("duplicate event ids")
    if {e["source_id"] for e in data["events"]} - sources:
        bad.append("an event names a source outside the cohort")
    if {e["cohort_event_id"] for e in data["edges"]} - set(ids):
        bad.append("an edge starts outside the cohort")
    if len({tuple(e[f] for f in EDGE_FIELDS) for e in data["edges"]}) != len(data["edges"]):
        bad.append("duplicate edges")
    if bad:
        raise SystemExit("export refused: " + "; ".join(bad))
    return manifest, data


def load_holds(path, events):
    holds = json.load(open(path))
    unknown = set(holds) - {e["event_id"] for e in events}
    good = all(isinstance(v, dict) and v.get("disposition") in ("held", "review") and v.get("rules") for v in holds.values())
    if unknown or not good:
        raise SystemExit(f"holds refused: every entry needs a cohort event id, a disposition and the rules matched ({len(unknown)} unknown id(s))")
    return holds


def date_evidence(event):
    """About the publication date only, never factual accuracy. Labels are copied untouched; a backfilled date is not verified."""
    verified = str(event.get("published_at_confidence") or "").lower() == "verified" and "backfill" not in str(event.get("published_at_basis") or "").lower()
    return "verified" if verified else "unverified"


def organisation(event):
    return "RBA" if "rba.gov.au" in str(event.get("canonical_url") or "") else "APRA"


def not_independent_because(edge, by_id):
    """Why a recorded corroboration link may not count as independent support; None for links that are not corroboration. In this pilot no
    link can count: independent underlying evidence origins are not recorded anywhere, and unestablished means not counted."""
    if edge["relation"] not in ("corroborates", "corroborated_by"):
        return None
    a, b = by_id.get(edge["cohort_event_id"]), by_id.get(edge["linked_id"])
    if not a or not b:
        return "an end is not a copied record"
    if date_evidence(a) != "verified" or date_evidence(b) != "verified":
        return "publication date unverified"
    if organisation(a) == organisation(b):
        return "same organisation"
    if any(x.get("suppressed") or x.get("signal_status") == "DUPLICATE" for x in (a, b)):
        return "an end is duplicate or suppressed"
    return "independent evidence origin not established"


def expected(data, holds):
    """What the store must contain. Held records are left out; every recorded link is kept as identifiers, saying whether its origin was
    held and where its other end is. Nothing is added."""
    events = [e for e in data["events"] if e["event_id"] not in holds]
    by_id = {e["event_id"]: e for e in events}
    edges = []
    for e in data["edges"]:
        endpoint = "not_event" if e["relation"] not in EVENT_RELATIONS else "held" if e["linked_id"] in by_id else "external"
        edges.append({**{f: e[f] for f in EDGE_FIELDS}, "endpoint": endpoint, "origin_held": e["cohort_event_id"] not in by_id,
                      "not_independent_because": not_independent_because(e, by_id)})
    linked = {e["cohort_event_id"]: e for e in edges if e["relation"] == "canonical_of_this"}
    rows = []
    for e in events:
        edge = linked.get(e["event_id"])
        state = edge["endpoint"] if edge else "not_recorded"
        rows.append({**canonical(e, EVENT_FIELDS), "canonical_signal_id": edge["linked_id"] if edge else None, "canonical_state": state,
                     "date_evidence": date_evidence(e)})
    return rows, edges


def summary(manifest, data, holds):
    rows, edges = expected(data, holds)
    dup = [e for e in data["events"] if e.get("signal_status") == "DUPLICATE"]
    linked = {e["cohort_event_id"] for e in data["edges"] if e["relation"] == "canonical_of_this"}
    per_source = {}
    for e in data["events"]:
        c = per_source.setdefault(e["source_id"], {"eligible": 0, "held": 0, "review": 0})
        c[holds.get(e["event_id"], {}).get("disposition", "eligible")] += 1
    return {"as_of": manifest["as_of"], "synthetic": manifest["synthetic"], "export_counts": manifest["counts"], "per_source": per_source,
            "to_copy": {"events": len(rows), "edges": len(edges)}, "edges_from_held_records": sum(e["origin_held"] for e in edges),
            "duplicates": len(dup), "duplicates_without_recorded_canonical": sorted(e["event_id"] for e in dup if e["event_id"] not in linked),
            "external_edges": sum(e["endpoint"] == "external" for e in edges), "date_verified": sum(r["date_evidence"] == "verified" for r in rows),
            "links_counting_as_independent": 0}


EDGE_STORE = EDGE_FIELDS + ("endpoint", "origin_held", "not_independent_because")
STORE_FIELDS = EVENT_FIELDS + ("canonical_signal_id", "canonical_state", "date_evidence")


async def do_import(folder, holds_path, batch, authorised):
    import store

    manifest, data = load_export(folder)
    if not manifest["synthetic"] and not authorised:
        raise SystemExit("refused: this export is not synthetic and no execution authority was given")
    holds = load_holds(holds_path, data["events"])
    rows, edges = expected(data, holds)
    con = await store.connect("intel_ingest")
    try:
        async with con.transaction():
            await con.execute("insert into intel.c_batch (batch_id, source_as_of, synthetic, authority, export_digests, held) values ($1,$2,$3,$4,$5,$6)",
                              batch, manifest["as_of"], manifest["synthetic"], authorised, json.dumps(manifest["digests"]), json.dumps(holds))
            await con.executemany("insert into intel.c_source (batch_id, source_id, source_name, licence_url, attribution) values ($1,$2,$3,$4,$5)",
                                  [(batch, *(s[f] for f in SOURCE_FIELDS)) for s in data["sources"]])
            cols = ", ".join(("batch_id", *STORE_FIELDS))
            marks = ", ".join(f"${i}" for i in range(1, len(STORE_FIELDS) + 2))
            await con.executemany(f"insert into intel.c_event ({cols}) values ({marks})",
                                  [(batch, *(dt.datetime.fromisoformat(r[f]) if f in TIME_FIELDS and r[f] else r[f] for f in STORE_FIELDS)) for r in rows])
            await con.executemany("insert into intel.c_edge (batch_id, cohort_event_id, relation, linked_id, endpoint, origin_held, not_independent_because) values ($1,$2,$3,$4,$5,$6,$7)",
                                  [(batch, *(e[f] for f in EDGE_STORE)) for e in edges])
            failed = await compare_store(con, batch, data, holds)
            if failed:
                raise SystemExit("import abandoned and rolled back, reconciliation failed: " + ", ".join(failed))
    finally:
        await con.close()
    return {**summary(manifest, data, holds), "batch": batch, "committed": True}


async def compare_store(con, batch, data, holds):
    """Names of the checks that fail; empty when the batch is exactly what the export and holds call for."""
    rows, edges = expected(data, holds)
    got = [dict(r) for r in await con.fetch(f"select {', '.join(STORE_FIELDS)} from intel.c_event where batch_id = $1", batch)]
    got_edges = [dict(r) for r in await con.fetch(f"select {', '.join(EDGE_STORE)} from intel.c_edge where batch_id = $1", batch)]
    got_sources = [dict(r) for r in await con.fetch("select source_id, source_name, licence_url, attribution from intel.c_source where batch_id = $1", batch)]
    per_source = lambda rs: sorted((s, sum(str(r["source_id"]) == s for r in rs)) for s in {str(r["source_id"]) for r in rs})
    checks = {"event_count": len(got) == len(rows), "per_source_counts": per_source(got) == per_source(rows),
              "event_fields": digest_rows(got, STORE_FIELDS) == digest_rows(rows, STORE_FIELDS),
              "edges": digest_rows(got_edges, EDGE_STORE) == digest_rows(edges, EDGE_STORE),
              "sources_and_attribution": digest_rows(got_sources, SOURCE_FIELDS) == digest_rows(data["sources"], SOURCE_FIELDS)}
    return [k for k, ok in checks.items() if not ok]


async def do_verify(folder, holds_path, batch):
    import store

    manifest, data = load_export(folder)
    holds = load_holds(holds_path, data["events"])
    con = await store.connect("intel_read")
    try:
        failed = await compare_store(con, batch, data, holds)
    finally:
        await con.close()
    return {**summary(manifest, data, holds), "batch": batch, "failed_checks": failed}


async def do_rollback(batch):
    import store

    con = await store.connect("intel_maint")
    try:
        async with con.transaction():
            n = await con.fetchval("select count(*) from intel.c_event where batch_id = $1", batch)
            if await con.fetchval("select count(*) from intel.c_batch where batch_id = $1", batch) != 1:
                raise SystemExit("refused: no such batch")
            await con.execute("delete from intel.c_batch where batch_id = $1", batch)
            left = await con.fetchval("select (select count(*) from intel.c_event where batch_id = $1) + (select count(*) from intel.c_edge where batch_id = $1) "
                                      "+ (select count(*) from intel.c_source where batch_id = $1)", batch)
    finally:
        await con.close()
    return {"batch": batch, "events_removed": n, "rows_left": left}


def compare_exports(old, new):
    """Source-side change between two snapshots. A delete is reported, never applied: the principal decides."""
    _m1, a = load_export(old)
    _m2, b = load_export(new)
    ea, eb = ({r["event_id"]: canonical(r, EVENT_FIELDS) for r in d["events"]} for d in (a, b))
    ka, kb = ({tuple(r[f] for f in EDGE_FIELDS) for r in d["edges"]} for d in (a, b))
    return {"inserted": sorted(eb.keys() - ea.keys()), "deleted": sorted(ea.keys() - eb.keys()),
            "changed": sorted(k for k in ea.keys() & eb.keys() if ea[k] != eb[k]), "edges_added": len(kb - ka), "edges_removed": len(ka - kb)}


def synthetic(folder, seed=7):
    """146 fictional records in five sources with the cohort's relationship shape: 48 duplicates, 3 of them with no recorded canonical."""
    rng = random.Random(seed)
    uid = lambda: str(uuid.UUID(int=rng.getrandbits(128), version=4))
    plan = (("Fictional Prudential Media Releases", 54, "APRA"), ("Fictional Prudential Publications", 56, "APRA"),
            ("Fictional Prudential Consultations", 26, "APRA"), ("Fictional Prudential Speeches", 9, "APRA"), ("Fictional Reserve Releases", 1, "RBA"))
    sources, events, edges = [], [], []
    base = dt.datetime(2026, 8, 10, tzinfo=dt.timezone.utc)
    for name, count, publisher in plan:
        sid = uid()
        sources.append({"source_id": sid, "source_name": name, "licence_url": LICENCE[publisher][0], "attribution": LICENCE[publisher][1]})
        for i in range(count):
            when = base + dt.timedelta(hours=len(events) * 5)
            events.append({"event_id": uid(), "source_id": sid, "raw_title": f"{name} item {i}", "raw_summary": f"Fictional summary {i} for {name}.",
                           "canonical_url": f"https://example.invalid/{len(events)}", "geography": "AU", "collected_at": when,
                           "published_at": when - dt.timedelta(hours=1), "published_at_basis": "backfilled" if i % 4 == 0 else "feed", "published_at_precision": "day",
                           "published_at_confidence": "verified" if i % 5 == 0 else "claimed", "signal_status": "SCORED",
                           "suppressed": rng.random() < 0.2, "suppression_reason": None, "publisher_domain": "example.invalid", "publisher_family": publisher})
    dups = rng.sample(range(1, len(events)), 48)
    originals = [i for i in range(len(events)) if i not in set(dups)]
    add = lambda a, relation, b: edges.append({"cohort_event_id": events[a]["event_id"], "relation": relation, "linked_id": b})
    for n, i in enumerate(dups):
        events[i]["signal_status"] = "DUPLICATE"
        if n < 3:
            continue                                            # flagged duplicate, canonical never recorded
        target = rng.choice(originals)
        add(i, "canonical_of_this", events[target]["event_id"])
        add(target, "has_this_as_canonical", events[i]["event_id"])
    for _ in range(4):
        add(rng.choice(originals), "has_this_as_canonical", uid())          # from outside the cohort: identifier only
    for _ in range(20):
        add(rng.choice(originals), rng.choice(("corroborates", "corroborated_by")), uid())
    for i in rng.sample(range(len(events)), 9):
        add(i, "brief_id", uid())
    for i in rng.sample(range(len(events)), 10):
        add(i, "validation", uid())
    return write_export(folder, events, edges, sources, as_of="2026-11-28T00:00:00+00:00", synthetic=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="package_c")
    ap.add_argument("cmd", choices=("synthetic", "plan", "import", "verify", "compare", "rollback"))
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--holds")
    ap.add_argument("--batch")
    ap.add_argument("--authorised")
    a = ap.parse_args(argv)
    if a.cmd == "synthetic":
        out = synthetic(a.paths[0])
    elif a.cmd == "compare":
        out = compare_exports(*a.paths)
    elif a.cmd == "rollback":
        out = asyncio.run(do_rollback(a.batch))
    elif a.cmd == "plan":
        manifest, data = load_export(a.paths[0])
        out = summary(manifest, data, load_holds(a.holds, data["events"]))
    elif a.cmd == "import":
        out = asyncio.run(do_import(a.paths[0], a.holds, a.batch, a.authorised))
    else:
        out = asyncio.run(do_verify(a.paths[0], a.holds, a.batch))
    print(json.dumps(out))
    return 2 if out.get("failed_checks") or out.get("rows_left") else 0


if __name__ == "__main__":
    sys.exit(main())
