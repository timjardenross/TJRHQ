#!/usr/bin/env python3
"""Weekly intelligence BASELINE report (offline, read-only).

One repeatable command that scores the current week's production export against the FROZEN reference set and
writes a Markdown + JSON report. It never connects to anything: the owner (or an agent) exports three read-only
SELECTs (``--print-export-sql`` prints them) into a directory and points the command at it.

    python tools/intelligence/weekly_baseline.py --print-export-sql --week-start 2026-11-18 --week-end 2026-11-25
    python tools/intelligence/weekly_baseline.py --export-dir <dir> --week-start 2026-11-18 --week-end 2026-11-25 \\
        --out-md docs/intelligence-weekly-baseline-<date>.md --out-json <path>.json

Export directory: events.json (required), briefs.json, sources.json, optional ratings.csv (the Captain CSV the
scorecard already reads; its manual_verification_minutes column is the ONLY source of the manual verification burden).

Definitions are the existing scorecard's (tools/intelligence/performance_scorecard.py); this file adds no new metric
semantics. It adds: (a) Morning V1 vs legacy brief surfacing, (b) brief noise counts, (c) source-coverage state counts
via intelligence.source_effectiveness, (d) an owner-filled manual verification burden field that is never estimated.

Morning variants (decided from the stored brief text):
    morning_v1      contains the evidence-based picture heading, no legacy posture heading
    morning_legacy  contains the legacy "INTELLIGENCE POSTURE" heading, no evidence-based picture heading
    morning_v1_fallback  contains both (evidence block present but coverage insufficient, legacy posture shown)
Surfacing is a title-regex match of the incident in brief text (weaker evidence than brief_id; the scorecard says the same).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
for _p in (str(_REPO), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import performance_scorecard as ps

from intelligence import source_effectiveness as se

DEFAULT_REFERENCE = _REPO / "knowledge" / "intelligence-reference-set" / "reference_set_v1.json"
V1_HEADING = "EVIDENCE-BASED PICTURE"
LEGACY_HEADINGS = ("INTELLIGENCE POSTURE", "LEGACY POSTURE")
BOLD_RE = re.compile(r"<b>([^<]{1,120})</b>")
POSTURE_BADGE_RE = re.compile(r"^\W*(RED|AMBER|GREEN|YELLOW)\W*$", re.IGNORECASE)
ITEM_RE = re.compile(r"^\s*(\d+[.)]|[•▪▸►*-]|[\U0001F534\U0001F7E0\U0001F7E1\U0001F7E2⚠✅❌])\s", re.MULTILINE)
PLACEHOLDER_RE = re.compile(r"\s*(None\b|No )")  # "- None." / "- No active warning" lines are empty-section placeholders, not items
OWNER_PROMPT = ("OWNER TO FILL, never estimated by this tool: total minutes you spent manually verifying the week's briefs and alerts "
                "(opening sources, cross-checking claims). Record it in ratings.csv (column manual_verification_minutes) and re-run.")

EXPORT_SQL = {
    "events.json": """-- run read-only; save the rows as a JSON list
select e.event_id::text as event_id, s.source_name, e.raw_title, e.published_at, e.collected_at, e.brief_id::text as brief_id,
       e.suppressed, e.risk_rating, e.disposition, e.canonical_signal_id::text as canonical_signal_id
from intelligence_events e join intelligence_source_registry s using (source_id)
where e.published_at >= '{ev_from}' and e.published_at < '{ev_to}'
order by e.published_at""",
    "briefs.json": """-- run read-only; save the rows as a JSON list (brief_text stays local, do not commit it)
select id::text as id, brief_date, brief_type, brief_text
from captains_daily_briefs
where brief_date >= '{br_from}' and brief_date < '{br_to}'
order by brief_date, generated_at""",
    "sources.json": se.SOURCE_ROWS_SQL.strip(),
}


# ── input handling ──────────────────────────────────────────────────────────────

def _load_rows(path):
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["events"] if isinstance(data, dict) and "events" in data else data


def print_export_sql(week_start: str, week_end: str) -> str:
    w0, w1 = ps._day(week_start), ps._day(week_end)
    fmt = {"ev_from": (w0 - timedelta(days=3)).date().isoformat(), "ev_to": (w1 + timedelta(days=3)).date().isoformat(),
           "br_from": (w0 - timedelta(days=1)).date().isoformat(), "br_to": (w1 + timedelta(days=8)).date().isoformat()}
    return "\n\n".join(f"-- {name}\n{sql.format(**fmt)};" for name, sql in EXPORT_SQL.items())


def assert_scoreable_reference(ref: dict) -> None:
    """Candidates (v2 candidate file) must never enter scoring: only a human-promoted set may."""
    bad = [i.get("id") for i in ref.get("incidents", [])
           if i.get("status") in ("candidate", "unresolved") or i.get("set_membership") == "v2_candidate"]
    if bad:
        raise SystemExit(f"refusing to score a reference file containing candidate/unpromoted records: {bad[:5]}")


def weekly_reference(ref: dict, w0, w1):
    """Frozen reference restricted to records whose first public report is in the window. Undated records are NOT
    carried into a weekly window (the scorecard would otherwise count them as missed every week)."""
    keep, undated = [], []
    for inc in ref["incidents"]:
        t = ps.parse_ts(inc["first_public_report_time"].get("value")) or ps.parse_ts(inc["start_time_utc"].get("value"))
        if t is None:
            undated.append(inc["id"])
        elif w0 <= t < w1:
            keep.append(inc)
    sub = copy.deepcopy({k: v for k, v in ref.items() if k != "incidents"})
    sub["incidents"] = keep
    return sub, undated


# ── briefs: variants, noise, surfacing ──────────────────────────────────────────

def morning_variant(text: str) -> str:
    v1 = V1_HEADING in text
    legacy = any(h in text for h in LEGACY_HEADINGS)
    if v1 and legacy:
        return "morning_v1_fallback"
    if v1:
        return "morning_v1"
    if legacy:
        return "morning_legacy"
    return "morning_unclassified"


def brief_shape(text: str) -> dict:
    """Noise counts. sections = bold headings minus the title line and bare posture badges; items = bullet/numbered lines."""
    heads = [h.strip() for h in BOLD_RE.findall(text or "")]
    sections = [h for h in heads[1:] if not POSTURE_BADGE_RE.match(h)]
    n_sections = len(sections) + (1 if V1_HEADING in (text or "") and not any(V1_HEADING in h for h in heads) else 0)
    items = [m for m in ITEM_RE.finditer(text or "") if not PLACEHOLDER_RE.match((text or "")[m.end():m.end() + 12])]
    return {"sections": n_sections, "items": len(items), "chars": len(text or "")}


def summarise_briefs(briefs, w0, w1):
    rows, groups = [], defaultdict(list)
    for b in briefs or []:
        d = ps._day(b.get("brief_date") or "")
        if d is None or not (w0 <= d < w1):
            continue
        t = b.get("brief_type") or "unknown"
        kind = morning_variant(b.get("brief_text") or "") if t == "morning" else t
        shp = brief_shape(b.get("brief_text") or "")
        rows.append({"brief_date": str(b.get("brief_date"))[:10], "brief_type": t, "variant": kind, **shp})
        groups[kind].append(shp)
    by_kind = {}
    for kind, xs in sorted(groups.items()):
        n = len(xs)
        by_kind[kind] = {"briefs": n, "sections_total": sum(x["sections"] for x in xs), "items_total": sum(x["items"] for x in xs),
                         "sections_mean": round(sum(x["sections"] for x in xs) / n, 1), "items_mean": round(sum(x["items"] for x in xs) / n, 1)}
    return {"by_kind": by_kind, "rows": rows,
            "note": "counts of bold headings (excluding title and posture badge) and bullet/numbered lines; indicative, not a usefulness measure"}


def variant_surfacing(material_incs, briefs, w0, w1):
    """For each Morning variant: which in-window material incidents appear (regex) in a brief of that variant dated within
    [first report - 1 day, +7 days]. An incident is only eligible for a variant if such a brief exists after its first report."""
    morning = []
    for b in briefs or []:
        if b.get("brief_type") != "morning":
            continue
        d = ps._day(b.get("brief_date") or "")
        if d is not None:
            morning.append((d, morning_variant(b.get("brief_text") or ""), b.get("brief_text") or ""))
    variants = sorted({v for _, v, _ in morning})
    out = {v: {"briefs_in_scope": sum(1 for d, vv, _ in morning if vv == v and w0 <= d < w1), "eligible": [], "surfaced": [], "not_surfaced": []}
           for v in variants}
    for inc in material_incs:
        first = ps.parse_ts(inc["first_public_report_time"]["value"]) or ps.parse_ts(inc["start_time_utc"]["value"])
        rx_s = (inc.get("tjr_detection") or {}).get("match", {}).get("title_regex")
        rx = ps.to_python_regex(rx_s) if rx_s else None
        for v in variants:
            cands = [(d, t) for d, vv, t in morning if vv == v and first - timedelta(days=1) <= d <= first + timedelta(days=7)]
            if not cands:
                continue
            out[v]["eligible"].append(inc["id"])
            (out[v]["surfaced"] if rx and any(rx.search(t) for _, t in cands) else out[v]["not_surfaced"]).append(inc["id"])
    for v, o in out.items():
        o["note"] = ("fewer than 5 briefs of this variant in scope: not enough to compare" if o["briefs_in_scope"] < 5 else "")
    return out


# ── sources ─────────────────────────────────────────────────────────────────────

def source_coverage(rows, now):
    if rows is None:
        return {"provided": False, "counts": None, "not_healthy": [], "note": "sources.json not provided"}
    res = se.classify_all(rows, now=now)
    return {"provided": True, "counts": se.summarise(res), "registry_rows": len(rows),
            "not_healthy": [{"source": c["source_name"], "state": c["state"], "reason": c["reason"]} for c in res if c["state"] != se.HEALTHY],
            "definitions": "intelligence/source_effectiveness.py (HEALTHY QUIET UNVERIFIED DEGRADED BROKEN UNCOVERED)"}


# ── report ──────────────────────────────────────────────────────────────────────

def build_report(reference, events, briefs, source_rows, ratings_path, week_start, week_end, as_of):
    assert_scoreable_reference(reference)
    w0, w1 = ps._day(week_start), ps._day(week_end)
    ref_w, undated = weekly_reference(reference, w0, w1)
    src = ps.FileSource(None, None, ratings_path)
    src._events = events
    src.briefs = lambda: briefs  # the scorecard reads briefs through this accessor
    card = ps.compute_scorecard(ref_w, src, week_start, week_end)
    material_incs = [i for i in ref_w["incidents"] if ps.is_material(i) and not ps.is_excluded(i)]
    surf = variant_surfacing(material_incs, briefs, w0, w1)
    det = card["per_incident"]
    detail = []
    for inc in ref_w["incidents"]:
        d = det.get(inc["id"], {})
        detail.append({"id": inc["id"], "title": inc["title"], "status": inc.get("status"), "scored": not ps.is_excluded(inc),
                       "appeared": d.get("appeared"), "first_source": d.get("first_source"),
                       "hours_after_first_public": d.get("hours_after_first_public"), "events_with_brief_id": d.get("events_with_brief_id"),
                       "escalated": d.get("escalated"),
                       "surfaced_in": {v: (inc["id"] in o["surfaced"]) for v, o in surf.items() if inc["id"] in o["eligible"]}})
    rat = card["captain_ratings"]
    burden = {"status": "provided" if rat["provided"] and rat["manual_verification_minutes"] else "NOT PROVIDED",
              "minutes": rat["manual_verification_minutes"] if rat["provided"] and rat["manual_verification_minutes"] else None,
              "owner_prompt": OWNER_PROMPT,
              "csv_columns": "date,brief_usefulness_1to5,noise_count,manual_verification_minutes,notes"}
    contribution = (card.get("source_contribution") or [])[:10]
    return {
        "report": "weekly_baseline", "generated_for": {"week_start": week_start, "week_end_exclusive": week_end, "as_of": as_of.isoformat()},
        "reference_set": {"name": reference.get("name"), "set_version": reference.get("set_version"),
                          "reviewed_by_human": card["reference_set"]["reviewed_by_human"],
                          "records_in_window": len(ref_w["incidents"]), "records_scored": card["reference_set"]["records_scored"],
                          "undated_records_not_scored_weekly": undated,
                          "caveat": "frozen draft set, every record reviewed_by_human=false; treat results as indicative"},
        "inputs": {"events_rows": len(events or []), "briefs_rows": len(briefs or []), "source_rows": None if source_rows is None else len(source_rows)},
        "material_incidents": card["material_incidents"],
        "morning_v1_vs_legacy": {"by_variant": surf,
                                 "detected_by_pipeline": [i["id"] for i in material_incs if det[i["id"]]["appeared"]],
                                 "missed_by_pipeline": card["material_incidents"]["missed_ids"],
                                 "basis": "regex match of the incident title pattern in Morning brief text; pipeline detection is the scorecard's events match"},
        "time_to_first_detection_hours": card["time_to_first_detection_hours"],
        "false_escalation": card["false_escalation"],
        "false_recovery": card["false_recovery"],
        "independent_corroboration": card["independent_corroboration"],
        "australian_relevance": card["australian_relevance"],
        "unique_contribution_top_sources": contribution,
        "brief_noise": summarise_briefs(briefs, w0, w1),
        "source_coverage": source_coverage(source_rows, as_of),
        "manual_verification_burden": burden,
        "per_incident": detail,
    }


def _ids(xs):
    return ", ".join(xs) if xs else "none"


def render_markdown(r, label=""):
    g, rs, m = r["generated_for"], r["reference_set"], r["material_incidents"]
    t, fe, ic, au = r["time_to_first_detection_hours"], r["false_escalation"], r["independent_corroboration"], r["australian_relevance"]
    fr, bn, sc, mb = r["false_recovery"], r["brief_noise"], r["source_coverage"], r["manual_verification_burden"]
    L = []
    if label:
        L += [f"> **{label}**", ""]
    L += [f"# Intelligence weekly baseline: {g['week_start']} to {g['week_end_exclusive']} (end exclusive)", "",
          (f"Generated by `tools/intelligence/weekly_baseline.py` as of {g['as_of']}. Reference set: {rs['name']} {rs['set_version']} (frozen; "
           f"reviewed by human: {rs['reviewed_by_human']}). {rs['caveat']}."), "",
          (f"Inputs: {r['inputs']['events_rows']} event rows, {r['inputs']['briefs_rows']} brief rows, {r['inputs']['source_rows']} source rows. "
           f"Reference records with a first report in the window: {rs['records_in_window']} ({rs['records_scored']} scored). "
           f"Undated records are not scored weekly: {_ids(rs['undated_records_not_scored_weekly'])}."), "",
          "## Material incidents", "",
          f"- Total in window: {m['total']}; detected {m['detected']}; missed {m['missed']} (rate {m['detection_rate']}).",
          f"- Missed: {_ids(m['missed_ids'])}.",
          f"- Unresolved material-looking records, not scored: {_ids(m['unresolved_material_not_scored'])}.", "",
          "### Morning V1 vs legacy (surfaced in a Morning brief of that variant)", "",
          "| Variant | Briefs in window | Eligible incidents | Surfaced | Not surfaced | Note |", "|---|---|---|---|---|---|"]
    for v, o in r["morning_v1_vs_legacy"]["by_variant"].items():
        L.append(f"| {v} | {o['briefs_in_scope']} | {len(o['eligible'])} | {_ids(o['surfaced'])} | {_ids(o['not_surfaced'])} | {o['note']} |")
    L += ["", f"Detected by the pipeline: {_ids(r['morning_v1_vs_legacy']['detected_by_pipeline'])}. {r['morning_v1_vs_legacy']['basis']}.", "",
          "## Time to first detection", "",
          f"Hours from first public report to first collection: n={t['n']}, median {t['median']}, p90 {t['p90']}, max {t['max']}. {t['note']}.", "",
          "## False escalation and false recovery", "",
          f"- False escalation: {fe['escalated']} of {fe['negatives_scored']} scored negatives ({fe['negatives_observed_in_tjr']} observed in TJR); ids {_ids(fe['ids'])}.",
          f"- False recovery candidates: {fr['incidents_with_early_recovery_claims']} ({_ids(list(fr['claims_by_incident']))}); checkable {fr['checkable']}.", "",
          "## Corroboration, Australian relevance, unique contribution", "",
          f"- Independent corroboration: {ic['corroborated']} of {ic['detected_incidents']} detected incidents (share {ic['share']}); {ic['rule']}.",
          f"- Australian relevance precision of escalated items: {au['precision']} ({au['escalated_confirmed_material']} of {au['escalated_incidents']}).", "",
          "| Source | First report | Confirmation | Restoration | Chronology | Events | Kind |", "|---|---|---|---|---|---|---|"]
    for s in r["unique_contribution_top_sources"]:
        L.append(f"| {s['source']} | {s['first_report']} | {s['confirmation']} | {s['restoration_evidence']} | {s['chronology']} | {s['events']} | {s['source_kind']} |")
    if not r["unique_contribution_top_sources"]:
        L.append("| none | | | | | | |")
    L += ["", "## Brief noise (counts)", "", "| Brief kind | Briefs | Sections (mean) | Items (mean) |", "|---|---|---|---|"]
    for k, o in bn["by_kind"].items():
        L.append(f"| {k} | {o['briefs']} | {o['sections_total']} ({o['sections_mean']}) | {o['items_total']} ({o['items_mean']}) |")
    L += ["", bn["note"] + ".", "", "## Source-coverage state counts", ""]
    if sc["provided"]:
        L.append(", ".join(f"{k} {v}" for k, v in sc["counts"].items()) + f" (registry rows {sc['registry_rows']}; {sc['definitions']}).")
        L += ["", "Not healthy:"] + [f"- {x['state']} {x['source']}: {x['reason']}" for x in sc["not_healthy"]]
    else:
        L.append(sc["note"])
    L += ["", "## Manual verification burden (owner fills in)", "",
          f"- Status: **{mb['status']}**; minutes: {mb['minutes'] if mb['minutes'] is not None else '__________'}",
          f"- {mb['owner_prompt']}", f"- CSV columns: `{mb['csv_columns']}`", "",
          "## Per incident", "", "| Id | Status | Appeared | First source | Hours | In brief (event) | Morning surfacing |", "|---|---|---|---|---|---|---|"]
    for d in r["per_incident"]:
        L.append(f"| {d['id']} | {d['status']}{'' if d['scored'] else ' (not scored)'} | {d['appeared']} | {d['first_source']} | "
                 f"{d['hours_after_first_public']} | {d['escalated']} | {d['surfaced_in'] or '-'} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--reference", default=str(DEFAULT_REFERENCE), help="frozen reference set (default: reference_set_v1.json)")
    ap.add_argument("--export-dir", help="directory with events.json, briefs.json, sources.json[, ratings.csv]")
    ap.add_argument("--events"), ap.add_argument("--briefs"), ap.add_argument("--sources"), ap.add_argument("--ratings")
    ap.add_argument("--week-start", required=True)
    ap.add_argument("--week-end", required=True, help="exclusive")
    ap.add_argument("--as-of", help="ISO timestamp for source classification (default: now UTC)")
    ap.add_argument("--print-export-sql", action="store_true")
    ap.add_argument("--out-md"), ap.add_argument("--out-json")
    ap.add_argument("--label", default="", help="banner line placed at the top of the Markdown")
    a = ap.parse_args(argv)
    if a.print_export_sql:
        print(print_export_sql(a.week_start, a.week_end))
        return 0
    d = Path(a.export_dir) if a.export_dir else None
    pick = lambda explicit, name: explicit or (str(d / name) if d and (d / name).exists() else None)
    ev_p, br_p, so_p, ra_p = pick(a.events, "events.json"), pick(a.briefs, "briefs.json"), pick(a.sources, "sources.json"), pick(a.ratings, "ratings.csv")
    if not ev_p:
        raise SystemExit("events.json is required (use --print-export-sql for the SELECT)")
    as_of = ps.parse_ts(a.as_of) if a.as_of else datetime.now(timezone.utc)
    ref = json.loads(Path(a.reference).read_text(encoding="utf-8"))
    rep = build_report(ref, _load_rows(ev_p), _load_rows(br_p), _load_rows(so_p), ra_p, a.week_start, a.week_end, as_of)
    md = render_markdown(rep, a.label)
    if a.out_md:
        Path(a.out_md).write_text(md, encoding="utf-8")
    if a.out_json:
        Path(a.out_json).write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
