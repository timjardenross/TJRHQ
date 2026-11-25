"""PostgREST (GET only) equivalent of tools/intelligence/verify_operational.py's SELECT statements.

The VM has the Supabase REST API (service key from the Infisical wrapper) but no psql, so the verification stage cannot run the raw
SQL that ``verify_operational --print-sql`` prints. ``collect_results`` produces the same ``{query name: [row, ...]}`` shape from
bounded, paged GETs and aggregates client side. Every fetch is capped; a capped fetch is flagged in ``_meta`` so the checks report
NOT_YET_OBSERVABLE instead of judging absence on a partial export. Nothing here writes.
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

Getter = Callable[[str, str], list]
PAGE = 1000
HEALTH_CAP, EVENT_CAP, WINDOW_LIMIT = 40000, 40000, 3000
LABEL_COLS = ("published_at_basis", "published_at_precision", "published_at_confidence", "published_at_label")
PROV_COLS = "publisher_domain,publisher_family,published_at_basis,published_at_precision,published_at_confidence,published_at_label"


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def fetch(get: Getter, table: str, query: str, cap: int) -> tuple[list[dict], bool]:
    """Paged GET. Returns (rows, complete). ``query`` must carry a stable order."""
    out: list[dict] = []
    while len(out) < cap:
        want = min(PAGE, cap - len(out))
        chunk = get(table, f"{query}&limit={want}&offset={len(out)}")
        out += chunk
        if len(chunk) < want:
            return out, True
    return out, False


def sweep_starts(now: datetime, sweep_hour: int, n: int = 5) -> list[datetime]:
    s = now.replace(hour=sweep_hour, minute=0, second=0, microsecond=0)
    s = s if s <= now else s - timedelta(days=1)
    return [s - timedelta(days=i) for i in range(n)]


def read_deadman_journal(runner=subprocess.run) -> list[dict] | None:
    """Best effort: the deadman result only exists in the journal. None when journalctl is unavailable or not permitted."""
    try:
        p = runner(["journalctl", "-u", "intelligence-scheduler", "--since", "2 days ago", "--no-pager", "-q"], capture_output=True, text=True, timeout=20)
    except Exception:  # noqa: BLE001 - optional evidence
        return None
    if p.returncode != 0:
        return None
    return [{"line": ln} for ln in p.stdout.splitlines() if re.search(r"deadman|MISSED BRIEF", ln, re.IGNORECASE)]


def collect_results(get: Getter, now: datetime, *, sweep_hour: int, deployed_at: datetime, journal: Callable[[], list | None] | None = None) -> dict:
    meta: dict = {}
    res: dict = {"as_of": [{"as_of": now.isoformat()}]}

    reg, ok = fetch(get, "intelligence_source_registry", "select=source_id,source_name,source_type,category,active,updated_at&order=source_id.asc", 2000)
    meta["sources_complete"] = ok
    by_id = {r["source_id"]: r for r in reg}

    def name(sid):
        return (by_id.get(sid) or {}).get("source_name")

    starts = sweep_starts(now, sweep_hour)
    h7, ok = fetch(get, "intelligence_source_health",
                   f"select=source_id,status,checked_at,items_retrieved,content_valid,error_message&checked_at=gte.{iso(now - timedelta(days=7))}&order=checked_at.desc,health_id.desc",
                   HEALTH_CAP)
    meta["health_complete"] = ok
    for r in h7:
        r["_t"] = _ts(r["checked_at"])

    days = []
    for s in starts:
        win = [r for r in h7 if s <= r["_t"] < s + timedelta(hours=3)]
        days.append({"sweep_start": iso(s), "checks": len(win), "sources": len({r["source_id"] for r in win}),
                     "ok": sum(r["status"] == "ok" for r in win), "not_ok": sum(r["status"] != "ok" for r in win)})
    res["sweep_days"] = days
    cur = starts[0]
    res["sweep_failures"] = sorted(
        ({"source_name": name(r["source_id"]), "status": r["status"], "items_retrieved": r.get("items_retrieved"), "content_valid": r.get("content_valid"),
          "error": (r.get("error_message") or "")[:120]} for r in h7 if cur <= r["_t"] < cur + timedelta(hours=3) and r["status"] != "ok"),
        key=lambda x: x["source_name"] or "")[:60]

    hb, _ = fetch(get, "domain_heartbeats", f"select=checked_at,status,detail,error_message&domain_key=eq.intelligence_collection&checked_at=gte.{iso(now - timedelta(days=5))}&order=checked_at.desc", 40)
    res["heartbeats"] = [{**r, "error_message": (r.get("error_message") or "")[:160]} for r in hb]

    ev_cols = "event_id,source_id,collected_at,published_at,dedup_hash,canonical_url"
    ev7, ok = fetch(get, "intelligence_events", f"select={ev_cols}&collected_at=gte.{iso(now - timedelta(days=7))}&order=collected_at.desc,event_id.desc", EVENT_CAP)
    meta["events_complete"] = ok
    for r in ev7:
        r["_t"] = _ts(r["collected_at"])
    res["sweep_items"] = []
    for s in starts:
        win = [r for r in ev7 if s <= r["_t"] < s + timedelta(hours=3)]
        res["sweep_items"].append({"sweep_start": iso(s), "items": len(win), "sources": len({r["source_id"] for r in win})})

    # per-source rollup (the 'sources' query)
    hs, es = defaultdict(list), defaultdict(list)
    for r in h7:
        hs[r["source_id"]].append(r)
    for r in ev7:
        es[r["source_id"]].append(r)
    srcs = []
    for sid, s in sorted(by_id.items(), key=lambda kv: (not kv[1].get("active"), kv[1]["source_name"])):
        h, e = hs.get(sid, []), es.get(sid, [])           # h is newest first
        h72 = [x for x in h if x["_t"] > now - timedelta(hours=72)]
        oks = [x for x in h if x["status"] == "ok"]
        pubs = [x["published_at"] for x in e if x.get("published_at")]
        srcs.append({"source_name": s["source_name"], "source_type": s.get("source_type"), "category": s.get("category"), "active": s.get("active"),
                     "updated_at": s.get("updated_at"), "checks7": len(h), "bad7": sum(x["status"] != "ok" for x in h), "checks72": len(h72),
                     "ok72": sum(x["status"] == "ok" for x in h72), "last_check": h[0]["checked_at"] if h else None, "last_ok": oks[0]["checked_at"] if oks else None,
                     "last_status": h[0]["status"] if h else None, "last_items": h[0].get("items_retrieved") if h else None,
                     "last_valid": h[0].get("content_valid") if h else None, "last_error": (h[0].get("error_message") or "")[:100] if h else None,
                     "n24": sum(x["_t"] > now - timedelta(hours=24) for x in e), "n7": len(e), "n30": len(e),
                     "last_event": e[0]["collected_at"] if e else None, "newest_pub": max(pubs) if pubs else None})
    res["sources"] = srcs

    post = defaultdict(list)
    for r in h7:
        if r["_t"] >= deployed_at and (by_id.get(r["source_id"]) or {}).get("source_type") in ("rss", "atom", "json_feed", "feed"):
            post[r["source_id"]].append(r)
    res["feed_health_post_deploy"] = sorted(
        ({"source_name": name(k), "source_type": by_id[k]["source_type"], "checks": len(v), "max_items": max((x.get("items_retrieved") or 0) for x in v),
          "last_check": v[0]["checked_at"]} for k, v in post.items()), key=lambda x: -x["max_items"])[:20]
    itn = [r["source_id"] for r in reg if r["source_name"] == "iTnews"]
    res["itnews_checks"] = [{"checked_at": r["checked_at"], "status": r["status"], "items_retrieved": r.get("items_retrieved")}
                            for r in sorted(h7, key=lambda x: x["_t"]) if r["source_id"] in itn and r["_t"] >= min(deployed_at, now - timedelta(hours=24))][:100]

    def _recent(r):
        return r["_t"] > now - timedelta(hours=3)
    rec = [r for r in h7 if _recent(r)]
    base = [r for r in h7 if not _recent(r)]
    res["health_split"] = [{"w": "recent", "checks": len(rec), "not_ok": sum(r["status"] != "ok" for r in rec)},
                           {"w": "baseline", "checks": len(base), "not_ok": sum(r["status"] != "ok" for r in base)}]

    # NVD (10 days, its own pull so the 7-day cache does not truncate it)
    nvd_ids = [r["source_id"] for r in reg if re.search("nvd|nist cve", r["source_name"], re.IGNORECASE)]
    nvd: list[dict] = []
    if nvd_ids:
        nvd, ok = fetch(get, "intelligence_events", f"select=source_id,collected_at,published_at,dedup_hash,canonical_url&source_id=in.({','.join(nvd_ids)})&collected_at=gte.{iso(now - timedelta(days=10))}&order=collected_at.desc,event_id.desc", 5000)
        meta["nvd_complete"] = ok
    runs = defaultdict(list)
    for r in nvd:
        runs[r["collected_at"][:16]].append(r)
    res["nvd_runs"] = [{"run_minute": k + ":00Z", "items": len(v), "distinct_hash": len({x["dedup_hash"] for x in v}), "distinct_url": len({x["canonical_url"] for x in v}),
                        "oldest_published": min((x["published_at"] for x in v if x.get("published_at")), default=None),
                        "newest_published": max((x["published_at"] for x in v if x.get("published_at")), default=None)} for k, v in sorted(runs.items(), reverse=True)[:30]]
    res["nvd_totals"] = [{"total": len(nvd), "distinct_hash": len({x["dedup_hash"] for x in nvd}), "distinct_url": len({x["canonical_url"] for x in nvd}),
                          "post_deploy_items": sum(_ts(x["collected_at"]) >= deployed_at for x in nvd)}]

    # provenance (columns may not exist: then the rows simply carry none)
    prov: list[dict] = []
    try:
        prov, ok = fetch(get, "intelligence_events", f"select=event_id,source_id,collected_at,published_at,{PROV_COLS}&collected_at=gte.{iso(now - timedelta(days=7))}&order=collected_at.desc,event_id.desc", EVENT_CAP)
        meta["provenance_complete"] = ok
    except Exception as exc:  # noqa: BLE001 - columns absent / flag-off schema
        meta["provenance_error"] = str(exc)[:200]
    pd = defaultdict(lambda: defaultdict(int))
    for r in prov:
        d = pd[r["collected_at"][:10]]
        d["total"] += 1
        for c in ("publisher_domain", "publisher_family", "published_at_basis", "published_at_precision", "published_at_confidence"):
            d[c] += r.get(c) is not None
    res["provenance_days"] = [{"collected_day": k + "T00:00:00Z", **dict(v)} for k, v in sorted(pd.items(), reverse=True)]
    res["provenance_labels"] = [{**{k: r.get(k) for k in ("event_id", "collected_at", "published_at", "published_at_label", "published_at_basis", "published_at_precision", "published_at_confidence")},
                                 "source_name": name(r["source_id"])} for r in prov
                                if _ts(r["collected_at"]) > now - timedelta(days=3) and any(r.get(c) is not None for c in LABEL_COLS)][:2000]

    brs, _ = fetch(get, "captains_daily_briefs", f"select=brief_type,brief_date,generated_at,signals_count,evidence_window_hours,collection_caveat,brief_text&generated_at=gte.{iso(now - timedelta(days=12))}&order=generated_at.desc", 60)
    res["briefs"] = [{**{k: v for k, v in r.items() if k != "brief_text"}, "text_len": len(r.get("brief_text") or "")} for r in brs]
    morning = next((r for r in brs if r["brief_type"] == "morning"), None)
    res["latest_morning_brief"] = [morning] if morning else []

    def window(since: datetime, until: datetime | None):
        q = (f"select=event_id,raw_title,raw_summary,geography,collected_at,published_at,suppressed,signal_status,source_id&collected_at=gte.{iso(since)}"
             + (f"&collected_at=lte.{iso(until)}" if until else "") + "&order=collected_at.desc,event_id.desc")
        got, complete = fetch(get, "intelligence_events", q, WINDOW_LIMIT)
        return [{**{k: v for k, v in r.items() if k != "source_id"}, "raw_title": (r.get("raw_title") or "")[:200],
                 "raw_summary": (r.get("raw_summary") or "")[:300], "source_name": name(r["source_id"])} for r in got], complete
    if morning:
        gen, hours = _ts(morning["generated_at"]), int(morning.get("evidence_window_hours") or 24)
        res["window_events"], c = window(gen - timedelta(hours=hours), gen)
        meta["window_events_complete"] = c
    else:
        res["window_events"] = []
    res["live_window_events"], meta["live_window_events_complete"] = window(now - timedelta(hours=24), None)

    ext, _ = fetch(get, "external_fetch_usage", f"select=provider,billing_cycle_start,billing_cycle_end,call_count,updated_at&billing_cycle_end=gte.{(now - timedelta(days=1)).date()}&order=provider.asc,billing_cycle_start.desc", 12)
    res["external_fetch_usage"] = ext

    prods, _ = fetch(get, "intelligence_products",
                     f"select=product_key,generated_for,as_of,title,summary,sections,exceptions,body_md&generated_for=gte.{(now - timedelta(days=1)).date()}&order=generated_for.desc,as_of.desc,product_key.asc", 60)
    res["products_today"] = [{"product_key": p["product_key"], "generated_for": p["generated_for"], "as_of": p.get("as_of"), "title": (p.get("title") or "")[:80],
                              "summary": (p.get("summary") or "")[:120],
                              "sections_type": "array" if isinstance(p.get("sections"), list) else "object" if isinstance(p.get("sections"), dict) else None,
                              "exceptions_type": "array" if isinstance(p.get("exceptions"), list) else "object" if isinstance(p.get("exceptions"), dict) else None,
                              "body_len": len(p.get("body_md") or "")} for p in prods]

    if journal is not None and (j := journal()) is not None:
        res["deadman_journal"] = j
    # a capped pull must not let absence be judged on a partial export
    if not meta.get("events_complete", True) or not meta.get("health_complete", True):
        meta["window_events_complete"] = False
    res["_meta"] = meta
    return res
