#!/usr/bin/env python3
"""Offline material-incident alert replay (read-only, no network, no database, never sends anything).

Replays a historical event export in COLLECTION order, as the pipeline would have seen it: after every collection batch the
events collected so far are clustered (``intelligence.incident_clustering``) and tiered (``intelligence.delivery_tiers``) with
``now`` set to that batch time. The first batch at which an incident reaches IMMEDIATE_ALERT is the alert; its latency is measured
from the incident's first report COLLECTION time. Nothing is sent: this is a measurement harness, not a notifier.

Against the frozen reference set (v1, never modified) it reports:
  * false urgency      an alert whose incident contains a report of a reference record that is NOT a confirmed material incident
                       (confirmed_non_material / stale_or_resurfaced / unrelated_incident / duplicate_report)
  * missed material    a confirmed_material reference record covered by the export that never reached IMMEDIATE_ALERT
  * false restoration  a RESTORATION_UPDATE report (or restored status) published more than 1 h BEFORE the reference end time,
                       the same rule as tools/intelligence/performance_scorecard.py
  * duplicate alerts   more than one distinct incident alerting for the same reference record

Usage
  python3 tools/intelligence/alert_replay.py --events tests/fixtures/incident_clustering/events_30d_sample.tsv
  python3 tools/intelligence/alert_replay.py --reference knowledge/intelligence-reference-set/reference_set_v1.json \\
      --events knowledge/intelligence-reference-set/events_export_2026-11-24.json [--baseline] [--out replay.json]

``--baseline`` replays with the current (v1) grouping instead of the consolidated one, for before/after comparison.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence import delivery_tiers as dt
from intelligence import incident_clustering as ic

NEGATIVE_STATUSES = ("confirmed_non_material", "stale_or_resurfaced", "unrelated_incident", "duplicate_report")


def _ts(s):
    if not s:
        return None
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def load_events(path: Path) -> list[dict]:
    """Events as event_detection reads them: id, title, source, published_at, collected_at (+ optional incident_id, brief_id)."""
    if path.suffix == ".tsv":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            eid, pub, col, flags, disp, src, title = line.split("|", 6)
            rows.append({"id": eid, "source": src, "title": title, "published_at": f"2026-{pub}:00+00:00", "collected_at": f"2026-{col}:00+00:00",
                         "brief_id": "brief" if flags[0] == "1" else None, "suppressed": flags[1] == "1", "disposition": disp})
        return rows
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["events"] if isinstance(data, dict) else data
    return [{"id": r.get("event_id") or r.get("id"), "source": r.get("source_name") or r.get("source") or "", "title": r.get("raw_title") or r.get("title") or "",
             "published_at": r.get("published_at"), "collected_at": r.get("collected_at"), "incident_id": r.get("incident_id"),
             "brief_id": r.get("brief_id"), "suppressed": bool(r.get("suppressed")), "disposition": r.get("disposition")} for r in rows]


def replay(events: list[dict], *, consolidated: bool = True) -> dict:
    """Replay in collection order. Returns alerts (first IMMEDIATE_ALERT per incident) and the final incident state."""
    evs = sorted(events, key=lambda e: (_ts(e["collected_at"]), str(e["id"])))
    batches = sorted({_ts(e["collected_at"]) for e in evs})
    first_collect: dict[str, datetime] = {}
    alerts: dict[str, dict] = {}                    # keyed by the sorted-member signature of the FIRST alerting state
    alerted_members: dict[str, str] = {}            # event id -> alert key (so a growing incident is one alert, not many)
    for now in batches:
        seen = [e for e in evs if _ts(e["collected_at"]) <= now]
        for e in seen:
            first_collect.setdefault(str(e["id"]), _ts(e["collected_at"]))
        for inc in ic.cluster_incidents(seen, now=now, force=consolidated):
            td = dt.tier_for_incident(inc, now=now)
            ids = [r.event_id for r in inc.reports]
            known = {alerted_members[i] for i in ids if i in alerted_members}
            if td.tier == dt.IMMEDIATE_ALERT and not known:
                key = f"alert-{len(alerts) + 1}"
                alerts[key] = {"alert_key": key, "alerted_at": now.isoformat(), "headline": inc.decision.headline.title, "subject": inc.subject,
                               "first_report_collected_at": min(first_collect[i] for i in ids).isoformat(),
                               "latency_hours_from_first_collection": round((now - min(first_collect[i] for i in ids)).total_seconds() / 3600, 2),
                               "event_ids_at_alert": ids, "reasons": td.reasons}
                for i in ids:
                    alerted_members[i] = key
            elif td.tier == dt.IMMEDIATE_ALERT and known:
                for i in ids:
                    alerted_members.setdefault(i, min(known))
    final = ic.cluster_incidents(evs, now=batches[-1], force=consolidated) if batches else []
    return {"alerts": list(alerts.values()), "final_incidents": final, "alerted_members": alerted_members, "first_collect": first_collect,
            "tiers": {inc.incident_id: dt.tier_for_incident(inc, now=batches[-1]) for inc in final} if batches else {}}


def score_against_reference(result: dict, events: list[dict], reference: dict) -> dict:
    """False urgency / missed material / false restoration / duplicate alerts versus the frozen reference set."""
    rec_by_id = {r["id"]: r for r in reference["incidents"]}
    ev_rec = {str(e["id"]): e.get("incident_id") for e in events if e.get("incident_id")}
    covered = sorted(set(ev_rec.values()))
    alert_of = result["alerted_members"]
    alerts_per_rec: dict[str, set] = {}
    for eid, key in alert_of.items():
        if eid in ev_rec:
            alerts_per_rec.setdefault(ev_rec[eid], set()).add(key)
    false_urgency = sorted(r for r in alerts_per_rec if rec_by_id[r].get("status") in NEGATIVE_STATUSES)
    material = [r for r in covered if rec_by_id[r].get("status") == "confirmed_material"]
    missed = sorted(r for r in material if r not in alerts_per_rec)
    detected = sorted(r for r in material if r in alerts_per_rec)
    dup = sorted(r for r, keys in alerts_per_rec.items() if len(keys) > 1)
    false_restore = []
    for inc in result["final_incidents"]:
        for rep in inc.reports:
            r = ev_rec.get(rep.event_id)
            end = _ts(((rec_by_id.get(r) or {}).get("end_time_utc") or {}).get("value")) if r else None
            if rep.relation == ic.RESTORATION_UPDATE and rep.restoration == "full" and end and rep.candidate.published and (end - rep.candidate.published) > timedelta(hours=1):
                false_restore.append({"record": r, "event_id": rep.event_id, "published": rep.candidate.published.isoformat(), "reference_end": end.isoformat()})
    false_surfacing = sorted({ev_rec[r.event_id] for inc in result["final_incidents"]
                              if result["tiers"][inc.incident_id].tier in (dt.IMMEDIATE_ALERT, dt.SCHEDULED_BRIEF)
                              for r in inc.reports if r.event_id in ev_rec and rec_by_id[ev_rec[r.event_id]].get("status") in NEGATIVE_STATUSES})
    lat = []
    for a in result["alerts"]:
        recs = {ev_rec[i] for i in a["event_ids_at_alert"] if i in ev_rec}
        for r in recs & set(material):
            first = _ts((rec_by_id[r].get("first_public_report_time") or {}).get("value"))
            if first:
                lat.append({"record": r, "alert_vs_reference_first_report_hours": round((_ts(a["alerted_at"]) - first).total_seconds() / 3600, 2),
                            "alert_vs_first_collection_hours": a["latency_hours_from_first_collection"]})
    return {"covered_records": len(covered), "covered_material": len(material), "material_alerted": detected, "material_missed": missed,
            "false_urgency_records": false_urgency, "negatives_reaching_scheduled_brief_or_alert": false_surfacing, "duplicate_alert_records": dup, "false_restoration": false_restore, "latency": lat,
            "n_alerts": len(result["alerts"]), "n_alerts_on_reference_events": len({k for r in alerts_per_rec.values() for k in r}),
            "note": "reference coverage is only the sampled export; records with no events in the export are not scored"}


FAMILIES = {"microsoft_365_outage": r"microsoft|m365|outlook", "telstra": r"telstra", "coles_cyber": r"coles"}


def duplicate_representation(events: list[dict], now: datetime) -> dict:
    """Separate incidents carrying reports of a named disruption family, baseline grouping vs consolidated grouping.
    ``total`` counts every incident holding a matching report; ``actionable`` only those rated ESCALATE/VERIFY/WATCH."""
    import re
    out = {}
    base = ic.cluster_incidents(events, now=now, force=False)
    new = ic.cluster_incidents(events, now=now, force=True)
    for name, rx in FAMILIES.items():
        pat = re.compile(rx, re.IGNORECASE)
        out[name] = {mode: {"total": ic.representation(inc, pat), "actionable": ic.representation(inc, pat, actionable_only=True)}
                     for mode, inc in (("baseline", base), ("consolidated", new))}
        for mode in out[name]:
            for k in ("total", "actionable"):
                out[name][mode][k] = {x: out[name][mode][k][x] for x in ("incidents", "reports")}
    return out


def surfacing_audit(result: dict, events: list[dict]) -> dict:
    """Material incidents (tier IMMEDIATE_ALERT or SCHEDULED_BRIEF by evidence) that no member report ever reached a brief for
    (``brief_id`` on any member event), and why. ``brief_id`` is the only surfacing evidence in the export, so this under-counts
    briefs that name an incident without linking its events (brief text is not exported)."""
    by_id = {str(e["id"]): e for e in events}
    material, surfaced, never, why = [], [], [], {}
    for inc in result["final_incidents"]:
        tier = result["tiers"][inc.incident_id].tier
        if tier not in (dt.IMMEDIATE_ALERT, dt.SCHEDULED_BRIEF):
            continue
        material.append(inc)
        rows = [by_id[r.event_id] for r in inc.reports]
        linked = [e for e in rows if e.get("brief_id")]
        if linked:
            factual_ids = {r.event_id for r in inc.reports if r.relation in (ic.NEW, ic.SUBSEQUENT, ic.RESTORATION_UPDATE)}
            surfaced.append(inc)
            if not any(str(e["id"]) in factual_ids for e in linked):
                why.setdefault("surfaced_only_via_a_commentary_or_aftermath_report", []).append(inc.incident_id)
            continue
        never.append(inc)
        disp = {str(e.get("disposition") or "-")[:3] for e in rows}
        if any(e.get("suppressed") for e in rows):
            reason = "member reports suppressed"
        elif disp & {"ESC", "BRI"}:
            reason = "dispositioned ESCALATE/BRIEF but never attached to a brief"
        elif disp & {"WAT"}:
            reason = "dispositioned WATCH only (no promotion path to a brief)"
        else:
            reason = "dispositioned REFERENCE or unset"
        why.setdefault(reason, []).append(inc.incident_id)
    return {"material_incidents": len(material), "surfaced_in_a_brief": len(surfaced), "never_surfaced": len(never),
            "never_surfaced_headlines": [i.decision.headline.title[:90] for i in never], "why": {k: len(v) for k, v in why.items()},
            "caveat": "material = tier IMMEDIATE_ALERT/SCHEDULED_BRIEF from the offline rules; surfacing = brief_id on any member event"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--events", required=True)
    ap.add_argument("--reference", help="reference_set_v1.json (read-only)")
    ap.add_argument("--baseline", action="store_true", help="replay with the v1 grouping (no consolidation)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    events = load_events(Path(a.events))
    res = replay(events, consolidated=not a.baseline)
    out = {"mode": "baseline" if a.baseline else "consolidated", "n_events": len(events), "n_alerts": len(res["alerts"]), "alerts": res["alerts"],
           "tiers": {t: sum(1 for x in res["tiers"].values() if x.tier == t) for t in dt.TIERS}}
    out["surfacing_audit"] = surfacing_audit(res, events)
    if events:
        out["duplicate_representation"] = duplicate_representation(events, max(_ts(e["collected_at"]) for e in events))
    if a.reference:
        out["vs_reference"] = score_against_reference(res, events, json.loads(Path(a.reference).read_text(encoding="utf-8")))
    text = json.dumps(out, indent=2, default=str)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
