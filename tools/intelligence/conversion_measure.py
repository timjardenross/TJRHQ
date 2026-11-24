#!/usr/bin/env python3
"""Compare three systems on the frozen reference set with ONE set of definitions (offline, read-only, writes only with --out).

Systems
  legacy     the dispositions production assigned (the export's ``disposition`` / ``brief_id``). Immediate = ESCALATE; briefed = ESCALATE or
             BRIEF. Legacy has no incident object and no restoration claim, so duplicate representation and false restoration are n/a.
  morning_v1 ``event_detection.run`` (the staged detector behind ``brief_evidence.morning_view``), baseline grouping, replayed in
             collection order. Immediate = priority ESCALATE; briefed = priority ESCALATE/VERIFY/WATCH.
  tiered_additive  the tiered brief as rendered: ``tiered`` plus the Morning V1 sections it is additive over (minus V1 incidents made only of
             HISTORICAL_REFERENCE reports). Immediate = IMMEDIATE_ALERT; briefed = any of the above.
  tiered     clustered incidents (``incident_clustering``) with ``delivery_tiers``. Immediate = IMMEDIATE_ALERT; briefed = IMMEDIATE_ALERT or
             SCHEDULED_BRIEF.

Definitions (identical for all three)
  material set           reference records with status confirmed_material that the export covers
  negative set           confirmed_non_material, stale_or_resurfaced, unrelated_incident, duplicate_report (the set ``alert_replay`` uses)
  material detection     share of the material set that reaches the briefed level at any collection batch
  alert latency          hours from the record's reference first_public_report_time to the first collection batch at which an event of the
                         record is at the immediate level (median over alerted material records), plus hours from first collection
  false urgency          negative-set records with an event at the immediate level
  false restoration      records where the system states "restored" from a report published more than 1 h before the reference end time
  duplicate representation  records whose events end up in more than one incident at the final state (V1 vs tiered only)
Limits are in docs/incident-clustering-delivery-tiers-findings.md (section "Conversion measurement").
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence import delivery_tiers as dt
from intelligence import event_detection as ed
from intelligence import incident_clustering as ic
from tools.intelligence.alert_replay import NEGATIVE_STATUSES, _ts, load_events

REF = ROOT / "knowledge/intelligence-reference-set/reference_set_v1.json"
EXPORT = ROOT / "knowledge/intelligence-reference-set/events_export_2026-11-24.json"


def _records(events, reference):
    st = {r["id"]: r for r in reference["incidents"]}
    ev_rec = {str(e["id"]): e.get("incident_id") for e in events if e.get("incident_id")}
    cov = sorted(set(ev_rec.values()))
    return st, ev_rec, [r for r in cov if st[r]["status"] == "confirmed_material"], [r for r in cov if st[r]["status"] in NEGATIVE_STATUSES]


def _first_levels(events, ev_rec, level_fn):
    """Replay in collection order. ``level_fn(seen, now)`` yields (event_ids, level) with level in {"immediate","briefed"}.
    Returns record -> {"immediate": first batch time, "briefed": first batch time}."""
    evs = sorted(events, key=lambda e: (_ts(e["collected_at"]), str(e["id"])))
    first: dict[str, dict] = {}
    for now in sorted({_ts(e["collected_at"]) for e in evs}):
        seen = [e for e in evs if _ts(e["collected_at"]) <= now]
        for ids, level in level_fn(seen, now):
            for rec in {ev_rec[i] for i in ids if i in ev_rec}:
                f = first.setdefault(rec, {})
                if level == "immediate":
                    f.setdefault("immediate", now)
                f.setdefault("briefed", now)
    return first


def _v1_levels(seen, now):
    for d in ed.run(seen, now=now):
        ids = [m.event_id for m in d.group.members]
        if d.priority == "ESCALATE":
            yield ids, "immediate"
        elif d.priority in ("VERIFY", "WATCH"):
            yield ids, "briefed"


def _tier_levels(seen, now):
    for inc in ic.cluster_incidents(seen, now=now, force=True):
        td = dt.tier_for_incident(inc, now=now)
        ids = [r.event_id for r in inc.reports]
        if td.tier == dt.IMMEDIATE_ALERT:
            yield ids, "immediate"
        elif td.tier == dt.SCHEDULED_BRIEF:
            yield ids, "briefed"


def _additive_levels(seen, now):
    """The tiered brief as rendered with DELIVERY_TIERS_V1: the tier sections PLUS the Morning V1 sections it is additive over
    (``tiered_brief.v1_additive_view``: every V1 incident except those made only of HISTORICAL_REFERENCE reports)."""
    yield from _tier_levels(seen, now)
    rel = {r.event_id: r.relation for inc in ic.cluster_incidents(seen, now=now, force=True) for r in inc.reports}
    for d in ed.run(seen, now=now):
        ids = [m.event_id for m in d.group.members]
        if d.priority in ("ESCALATE", "VERIFY", "WATCH") and not all(rel.get(i) == ic.HISTORICAL_REFERENCE for i in ids):
            yield ids, "briefed"


def _legacy_first(events, ev_rec):
    first: dict[str, dict] = {}
    for e in sorted(events, key=lambda e: _ts(e["collected_at"])):
        rec = ev_rec.get(str(e["id"]))
        disp = (e.get("disposition") or "")
        if rec and disp in ("ESCALATE", "BRIEF"):
            f = first.setdefault(rec, {})
            f.setdefault("briefed", _ts(e["collected_at"]))
            if disp == "ESCALATE":
                f.setdefault("immediate", _ts(e["collected_at"]))
    return first


def _false_restoration(events, ev_rec, st, final_incidents=None):
    out = set()
    now_end = max(_ts(e["collected_at"]) for e in events)
    if final_incidents is None:                                    # morning_v1: member-level 'restored' state from the baseline detector
        for d in ed.run(events, now=now_end):
            for m in d.group.members:
                rec = ev_rec.get(m.event_id)
                end = _ts(((st.get(rec) or {}).get("end_time_utc") or {}).get("value")) if rec else None
                if end and m.published and ed._report_state(m, now_end) == "restored" and (end - m.published) > timedelta(hours=1):
                    out.add(rec)
    else:
        for inc in final_incidents:
            for r in inc.reports:
                rec = ev_rec.get(r.event_id)
                end = _ts(((st.get(rec) or {}).get("end_time_utc") or {}).get("value")) if rec else None
                if r.relation == ic.RESTORATION_UPDATE and r.restoration == "full" and end and r.candidate.published and (end - r.candidate.published) > timedelta(hours=1):
                    out.add(rec)
    return sorted(out)


def _split(incidents, ev_rec):
    by: dict[str, set] = {}
    for n, inc in enumerate(incidents):
        ids = [r.event_id for r in inc.reports] if hasattr(inc, "reports") else [m.event_id for m in inc.group.members]
        for rec in {ev_rec[i] for i in ids if i in ev_rec}:
            by.setdefault(rec, set()).add(n)
    return sorted(r for r, s in by.items() if len(s) > 1)


def measure(events: list[dict], reference: dict) -> dict:
    st, ev_rec, material, negative = _records(events, reference)
    end = max(_ts(e["collected_at"]) for e in events)
    first_collect: dict[str, object] = {}
    for e in events:
        r = ev_rec.get(str(e["id"]))
        if r:
            first_collect[r] = min(first_collect.get(r, _ts(e["collected_at"])), _ts(e["collected_at"]))
    systems = {"legacy": _legacy_first(events, ev_rec), "morning_v1": _first_levels(events, ev_rec, _v1_levels),
               "tiered": _first_levels(events, ev_rec, _tier_levels),
               "tiered_additive": _first_levels(events, ev_rec, _additive_levels)}
    base = ic.cluster_incidents(events, now=end, force=False)
    cons = ic.cluster_incidents(events, now=end, force=True)
    extra = {"legacy": {"false_restoration": None, "split_records": None},
             "morning_v1": {"false_restoration": _false_restoration(events, ev_rec, st), "split_records": _split(base, ev_rec)},
             "tiered": {"false_restoration": _false_restoration(events, ev_rec, st, cons), "split_records": _split(cons, ev_rec)}}
    extra["tiered_additive"] = extra["tiered"]
    out = {"n_events": len(events), "material_records": len(material), "negative_records": len(negative), "systems": {}}
    for name, first in systems.items():
        det = sorted(r for r in material if "briefed" in first.get(r, {}))
        alerted = sorted(r for r in material if "immediate" in first.get(r, {}))
        lat_ref, lat_col = [], []
        for r in alerted:
            ref_t = _ts((st[r].get("first_public_report_time") or {}).get("value"))
            if ref_t:
                lat_ref.append((first[r]["immediate"] - ref_t).total_seconds() / 3600)
            lat_col.append((first[r]["immediate"] - first_collect[r]).total_seconds() / 3600)
        med = lambda xs: round(statistics.median(xs), 1) if xs else None
        out["systems"][name] = {
            "material_detected": f"{len(det)}/{len(material)}", "material_detected_ids": det,
            "material_alerted": f"{len(alerted)}/{len(material)}", "material_alerted_ids": alerted,
            "median_alert_latency_h_from_reference_first_report": med(lat_ref), "median_alert_latency_h_from_first_collection": med(lat_col),
            "false_urgency_records": sorted(r for r in negative if "immediate" in first.get(r, {})),
            "negatives_reaching_brief_level": sorted(r for r in negative if "briefed" in first.get(r, {})),
            "false_restoration_records": extra[name]["false_restoration"], "records_split_across_incidents": extra[name]["split_records"]}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--events", default=str(EXPORT))
    ap.add_argument("--reference", default=str(REF))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    res = measure(load_events(Path(a.events)), json.loads(Path(a.reference).read_text(encoding="utf-8")))
    text = json.dumps(res, indent=2, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
