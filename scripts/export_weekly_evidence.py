"""Read-only exporter for the shadow comparison: pulls a week of evidence into a LOCAL JSON file.

Guarantees (each is asserted by tests):
* HTTP GET only (PostgREST reads). No POST/PUT/PATCH/DELETE, no RPC, no writes of any kind.
* No messaging, email, chat, scheduler or report-delivery code path.
* Exports the FULL week of events (paged), not a pool chosen with legacy fields.
* Personal data minimised: capacity rows are exported as dates only, never values.
* Output is a file on this machine, consumed by scripts/render_shadow_report.py.

    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \\
    python3 scripts/export_weekly_evidence.py --start 2026-11-16T13:00:00Z --end 2026-11-23T13:00:00Z --out week.json
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

PAGE = 1000
EVENT_SELECT = ("event_id,raw_title,raw_summary,canonical_url,collected_at,geography,source_tier,"
                "rank_score,operational_relevance,osint_confidence_level,disposition,risk_rating,signal_status,"
                "intelligence_source_registry(source_name)")


def _urllib_get(url: str, headers: dict) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310 - SUPABASE_URL from env, https
        return resp.status, dict(resp.headers), resp.read()


class Reader:
    def __init__(self, base: str, key: str, http=_urllib_get):
        self.base, self.http = base.rstrip("/") + "/rest/v1/", http
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}

    def count(self, table: str, query: str) -> int:
        hdr = {**self.headers, "Prefer": "count=exact", "Range": "0-0"}
        _s, h, _b = self.http(f"{self.base}{table}?{query}&select=count", hdr)
        total = {k.lower(): v for k, v in h.items()}.get("content-range", "*/0").split("/")[-1]
        return int(total) if total.isdigit() else 0

    def pages(self, table: str, query: str, select: str):
        start = 0
        while True:
            hdr = {**self.headers, "Range": f"{start}-{start + PAGE - 1}", "Range-Unit": "items"}
            _s, _h, body = self.http(f"{self.base}{table}?{query}&select={urllib.parse.quote(select, safe='(),')}", hdr)
            rows = json.loads(body or b"[]")
            yield from rows
            if len(rows) < PAGE:
                return
            start += PAGE


def export(reader: Reader, start: str, end: str) -> dict:
    win = f"collected_at=gte.{start}&collected_at=lt.{end}"
    base_q = f"{win}&suppressed=eq.false&raw_title=not.ilike.GitHub%20Status:*"
    usable = reader.count("intelligence_events", base_q)
    dupes = reader.count("intelligence_events", base_q + "&signal_status=eq.DUPLICATE")
    au = reader.count("intelligence_events", base_q + "&geography=eq.AU")
    events = []
    for r in reader.pages("intelligence_events", base_q + "&signal_status=neq.DUPLICATE&order=collected_at.asc", EVENT_SELECT):
        events.append({
            "id": str(r["event_id"])[:8], "title": r.get("raw_title") or "", "summary": (r.get("raw_summary") or "")[:300],
            "url": r.get("canonical_url"), "collected_at": r.get("collected_at"), "geography": r.get("geography"),
            "source": (r.get("intelligence_source_registry") or {}).get("source_name") or "",
            "legacy": {"rank": r.get("rank_score"), "relevance": r.get("operational_relevance"),
                       "conf": r.get("osint_confidence_level"), "disp": r.get("disposition"), "risk": r.get("risk_rating")}})
    hwin = f"collected_at=gte.{start}&collected_at=lt.{end}&suppressed=eq.false"
    health = {"total": 0, "registrations": 0, "other": 0, "leads": []}
    others = []
    for r in reader.pages("health_signals", hwin + "&order=rank_score.desc", "title,rank_score,signal_type,health_source_registry(source_name)"):
        health["total"] += 1
        src = (r.get("health_source_registry") or {}).get("source_name") or ""
        if "clinicaltrials" in src.lower():
            health["registrations"] += 1
        else:
            health["other"] += 1
            others.append(r.get("title") or "")
    health["leads"] = others[:5]
    today = end[:10]
    capacity = {"source": "none", "entries": []}
    for table, src, dcol in (("captains_log_entries", "log", "log_date"), ("recovery_pulses", "pulse", "log_date"),
                             ("capacity_checkins", "checkin", "log_date")):
        extra = "&checkin_type=eq.capacity" if table == "capacity_checkins" else ""
        rows = list(reader.pages(table, f"{dcol}=gte.{start[:10]}{extra}", dcol))   # dates only, never values
        if rows:
            capacity = {"source": src, "entries": [{"log_date": r[dcol]} for r in rows]}
            break
    return {"now": end, "window": {"start": start, "end": end}, "events": events,
            "universe": {"usable": usable, "duplicates": dupes, "au_events": au, "exported_events": len(events)},
            "health": health, "capacity": capacity, "db_snapshots": [], "_exported_through": today}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set; nothing exported.")
        return 2
    data = export(Reader(url, key), a.start, a.end)
    Path(a.out).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"exported {data['universe']['exported_events']} events, {data['health']['total']} health records -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
