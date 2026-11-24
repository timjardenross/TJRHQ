#!/usr/bin/env python3
"""Render a REPLAY sample of the tiered/clustered brief and the alert payloads for named past incidents (offline, nothing sent).

Events come from a SELECT-only export (TSV as ``alert_replay.load_events`` reads it). For each family the events are replayed in
collection order: after every collection batch the dispatcher runs in DRY-RUN with an in-memory store (alert once, restoration once),
and the tiered brief is rendered at the first brief time (07:00 AEST = 20:00Z, a fixed UTC+11 approximation) after the alert and at the
end of the family's window. Output is markdown, labelled REPLAY. No network, no database, no send.

Usage: python3 tools/intelligence/replay_sample.py --events tests/fixtures/incident_clustering/events_30d_sample.tsv --out docs/x.md
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence import alert_dispatcher as ad
from intelligence import incident_clustering as ic
from intelligence import tiered_brief as tb
from tools.intelligence.alert_replay import _ts, load_events

FAMILIES = {
    "Microsoft 365 / Outlook global outage": {"rx": r"microsoft|m365|outlook", "note": "Global outage, 12-13 Nov 2026."},
    "Coles cyber incident": {"rx": r"coles", "note": "Retailer cyber attack, 16 Nov 2026."},
    "Telstra outage (aftermath family)": {"rx": r"telstra", "note": "The original July national outage is OUTSIDE the 30-day sample; this family holds the local Stockton/Kingswood/AWS items and the aftermath reports, so it shows how an outage-and-aftermath cluster is handled, not the July alert."},
}
BRIEF_HOUR_UTC = 20


def _next_brief(t: datetime) -> datetime:
    b = t.replace(hour=BRIEF_HOUR_UTC, minute=0, second=0, microsecond=0)
    return b if b > t else b + timedelta(days=1)


def replay_family(events: list[dict]) -> dict:
    evs = sorted(events, key=lambda e: (_ts(e["collected_at"]), str(e["id"])))
    batches = sorted({_ts(e["collected_at"]) for e in evs})
    store = ad.InMemoryAlertStore()
    payloads: list[dict] = []
    for now in batches:
        seen = [e for e in evs if _ts(e["collected_at"]) <= now]
        incs = ic.cluster_incidents(seen, now=now, force=True)
        payloads += ad.process(incs, now=now, store=store, force=True)       # force: replay only; never a real send (no sender)
    return {"payloads": payloads, "batches": batches, "events": evs}


def render_markdown(events: list[dict]) -> str:
    out = ["# REPLAY: tiered and clustered brief and alert payloads for three past incidents", "",
           ("> **REPLAY, not a record of what was sent.** Offline reconstruction from SELECT-only data (`intelligence_events`, 30 days to 2026-11-24). "
            "Nothing was sent, published or written. The production system produced none of the alert payloads below; the dispatcher ran in dry-run "
            "with an in-memory store. Alert times are COLLECTION times (feed lag excluded). Brief times assume 07:00 AEDT = 20:00Z."), ""]
    for name, fam in FAMILIES.items():
        pat = re.compile(fam["rx"], re.IGNORECASE)
        sub = [e for e in events if pat.search(e["title"])]
        out += [f"## {name}", "", fam["note"], ""]
        if not sub:
            out += ["No events in the export.", ""]
            continue
        res = replay_family(sub)
        first = res["batches"][0]
        out += [f"Events: {len(sub)}, first collected {first.strftime('%d %b %H:%MZ')}, last {res['batches'][-1].strftime('%d %b %H:%MZ')}.", "",
                "### Alert payloads (dry-run, in collection order)", ""]
        if not res["payloads"]:
            out += ["No alert-level payload at any collection batch. Reason, from the final tiering below.", ""]
        for p in res["payloads"]:
            lat = (_ts(p["generated_at"]) - first).total_seconds() / 3600
            out += [f"**{p['kind'].upper()}** at {_ts(p['generated_at']).strftime('%d %b %H:%MZ')} ({lat:.1f} h after first collection; dry_run={p['dry_run']}, sent={p['sent']})", "", "```", p["text"], "```", ""]
        alert_times = [_ts(p["generated_at"]) for p in res["payloads"]]
        times = ([_next_brief(alert_times[0])] if alert_times else []) + [res["batches"][-1] + timedelta(hours=1)]
        for t in times:
            seen = [e for e in res["events"] if _ts(e["collected_at"]) <= t]
            lines, shown = tb.render(seen, now=t, window_hours=72)
            out += [f"### Tiered brief as rendered at {t.strftime('%d %b %H:%MZ')} ({len(shown)} report ids shown)", "", "```", *lines, "```", ""]
        final = ic.cluster_incidents(res["events"], now=res["batches"][-1] + timedelta(hours=1), force=True)
        from intelligence import delivery_tiers as dt
        out += ["### Incident tiers at the end of the window", "", "| Incident | Reports | Tier | Reason |", "|---|---|---|---|"]
        for inc in final:
            td = dt.tier_for_incident(inc, now=res["batches"][-1] + timedelta(hours=1))
            out.append(f"| {tb.incident_key(inc)}: {inc.decision.headline.title[:70].replace('|', '/')} | {inc.n_reports} | {td.tier} | {td.reasons[0][:110].replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--events", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    text = render_markdown(load_events(Path(a.events)))
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
