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

CATEGORY MODE (reference set v3 and later; selected automatically when the reference records carry ``intelligence_category``):

    python tools/intelligence/weekly_baseline.py --reference knowledge/intelligence-reference-set/reference_set_v3.json \\
        --coverage knowledge/intelligence-reference-set/coverage_v3-2026-11-24.json --window-start 2026-07-28 --window-end 2026-11-24 \\
        --as-of 2026-11-24T10:00:00Z --out-md docs/intelligence-baseline-v3-2026-11-24.md --out-json knowledge/intelligence-reference-set/baseline_v3-2026-11-24.json

  * Observation periods are fixed 7-day UTC blocks from the window start (P01..); an incident belongs to the period of its first public report.
  * A period is COVERAGE-COMPLETE only if no dated collection confounder touches it (intelligence.longitudinal_trends.COVERAGE_CHANGES: an
    outage/collection gap, or the feed-ceiling/source-set step, or a period before the last such step) and its collected volume is not an outlier
    (coverage file, SELECT-derived). Incomplete periods are reported separately and are excluded from the rate comparisons.
  * Assessment is by CATEGORY: detection is scored against material_operational_disruption only; material_emerging_risk_or_warning is assessed on
    detection AND conversion (surfaced in an event brief_id, daily brief text, intelligence_briefs forward watch/other sections or an
    intelligence_products body; 'NOT PROVIDED' where conversion was not measured, never estimated); material_retrospective_finding on collected and
    surfaced; non_material and unresolved are excluded from scores and only listed.
  * The manual verification burden is never estimated (owner supplies ratings.csv).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
for _p in (str(_REPO), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import performance_scorecard as ps

from intelligence import longitudinal_trends as lt
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


# ── category mode: observation periods, coverage state, assessment by intelligence_category ─────────────────────────────────

MOD, MEW, MRF = "material_operational_disruption", "material_emerging_risk_or_warning", "material_retrospective_finding"
NONMAT, UNRES = "non_material", "unresolved"
MATERIAL_CATS = (MOD, MEW, MRF)
NOT_PROVIDED = "NOT PROVIDED"
PERIOD_DAYS = 7
LIMIT_PRIORITY = ("outage_or_gap", "transition_feed_ceiling", "pre_feed_ceiling", "volume_outlier")
LIMIT_LABEL = {"outage_or_gap": "collection outage / no-collection days", "transition_feed_ceiling": "feed-ceiling step inside the period",
               "pre_feed_ceiling": "before the last feed-ceiling/source-set step (reduced mainstream volume)", "volume_outlier": "collected volume outlier"}


def is_category_reference(ref: dict) -> bool:
    incs = ref.get("incidents") or []
    return bool(incs) and all("intelligence_category" in i for i in incs)


def make_periods(window_start: str, window_end: str, days: int = PERIOD_DAYS) -> list[dict]:
    """Fixed-length, back-to-back UTC periods from the window start; the window must be a whole number of periods (no short final period)."""
    w0, w1 = ps._day(window_start), ps._day(window_end)
    n_days = (w1 - w0).days
    if n_days <= 0 or n_days % days:
        raise SystemExit(f"window {window_start}..{window_end} is {n_days} days: not a whole number of {days}-day periods")
    out = []
    for k in range(n_days // days):
        a = w0 + timedelta(days=k * days)
        out.append({"id": f"P{k + 1:02d}", "start": a, "end": a + timedelta(days=days)})
    return out


def period_states(periods, coverage: dict | None, changes=None) -> list[dict]:
    """Coverage state of each period. `coverage` is the SELECT-derived coverage file (weekly collected volumes, zero-collection days); the dated
    confounders come from intelligence.longitudinal_trends.COVERAGE_CHANGES so there is a single list of them."""
    changes = lt.COVERAGE_CHANGES if changes is None else changes
    weekly = {w["period"]: w for w in (coverage or {}).get("weekly_collection", [])}
    zero_days = [z["date"] for z in (coverage or {}).get("zero_collection_days", [])]
    persistent = sorted(date.fromisoformat(c["date"]) for c in changes if c["kind"] == "rate" and c.get("confounds", True))
    last_step = persistent[-1] if persistent else None
    rows = []
    for p in periods:
        a, b = p["start"].date(), (p["end"] - timedelta(days=1)).date()
        reasons, kinds = [], []
        for c in changes:
            if not c.get("confounds", True) or c["kind"] not in lt.RELIABILITY_KINDS or c["kind"] == "start":
                continue
            if lt.change_overlaps(c, a, b):
                kinds.append("outage_or_gap" if c["kind"] == "outage" else "transition_feed_ceiling")
                reasons.append(f"{c['date']}{('..' + c['end']) if c.get('end') else ''} {c['kind']}: {c['note']}")
        zd = [z for z in zero_days if a <= date.fromisoformat(z) <= b]
        if zd:
            kinds.append("outage_or_gap")
            reasons.append("no reports collected on " + ", ".join(zd))
        if last_step and b < last_step:
            kinds.append("pre_feed_ceiling")
            reasons.append(f"ends before the {last_step.isoformat()} feed-ceiling step (mainstream volume about 4x lower, six sources not yet added)")
        w = weekly.get(p["id"], {})
        rows.append({**p, "collected": w.get("reports_collected"), "active_sources": w.get("active_sources"), "reasons": reasons, "kinds": kinds})
    clean = [r["collected"] for r in rows if not r["kinds"] and r["collected"]]
    med = statistics.median(clean) if clean else None
    for r in rows:
        if med and r["collected"] and not r["kinds"]:
            ratio = r["collected"] / med
            if ratio < lt.PARAMS["volume_anomaly_low"] or ratio > lt.PARAMS["volume_anomaly_high"]:
                r["kinds"].append("volume_outlier")
                r["reasons"].append(f"collected volume {ratio:.2f}x the median of coverage-clean periods")
        r["collected_vs_clean_median"] = round(r["collected"] / med, 2) if med and r["collected"] else None
        r["limit_kind"] = next((k for k in LIMIT_PRIORITY if k in r["kinds"]), None)
        r["state"] = "limited" if r["kinds"] else "complete"
    return rows


def assign_period(inc, periods, w0, w1):
    t = ps.parse_ts(inc["first_public_report_time"].get("value")) or ps.parse_ts(inc["start_time_utc"].get("value"))
    if t is None:
        return "undated"
    if t < w0:
        return "pre_window"
    if t >= w1:
        return "after_window"
    for p in periods:
        if p["start"] <= t < p["end"]:
            return p["id"]
    return "undated"


def _detect(inc, events, briefs):
    if events is not None:
        d, _ = ps.evaluate_incident(inc, events, briefs)
        d["conversion_known"] = False  # the events file carries brief_id and (optionally) brief text only
        d["converted"] = d.get("brief_surfaced") if d.get("brief_surfaced") else None
        return d
    d = ps.detection_from_embedded(inc)
    conv = (inc.get("tjr_detection") or {}).get("conversion") or {}
    d["conversion_known"] = bool(conv.get("measured"))
    d["converted"] = conv.get("converted") if conv.get("measured") else None
    d["triaged_brief_or_escalate"] = ((inc.get("tjr_detection") or {}).get("events_brief_or_escalate") or 0) > 0
    return d


def _stat_ttd(xs):
    return {"n": len(xs), "median": ps._median(xs), "p90": ps._p90(xs), "max": max(xs) if xs else None}


def category_metrics(rows):
    """rows: dicts with id, category, det. Metrics per category; unmeasured conversion is reported as NOT PROVIDED, never filled in."""
    mod = [r for r in rows if r["category"] == MOD]
    mew = [r for r in rows if r["category"] == MEW]
    mrf = [r for r in rows if r["category"] == MRF]
    det_mod = [r for r in mod if r["det"]["appeared"]]
    ttd = [r["det"]["hours_after_first_public"] for r in det_mod if r["det"].get("hours_after_first_public") is not None]

    def conv_block(group):
        det = [r for r in group if r["det"]["appeared"]]
        known = [r for r in det if r["det"]["converted"] is not None]
        conv = [r for r in known if r["det"]["converted"]]
        return {"total": len(group), "detected": len(det), "missed_ids": [r["id"] for r in group if not r["det"]["appeared"]],
                "detection_rate": round(len(det) / len(group), 3) if group else None,
                "converted": len(conv), "converted_ids": [r["id"] for r in conv],
                "not_converted_ids": [r["id"] for r in known if not r["det"]["converted"]],
                "conversion_not_provided_ids": [r["id"] for r in det if r["det"]["converted"] is None],
                "conversion_rate_of_measured": round(len(conv) / len(known), 3) if known else NOT_PROVIDED}
    ev_mrf = conv_block(mrf)
    ev_mrf["collected"] = ev_mrf.pop("detected")
    ev_mrf["surfaced"] = ev_mrf.pop("converted")
    return {
        MOD: {"total": len(mod), "detected": len(det_mod), "missed": len(mod) - len(det_mod), "detection_rate": round(len(det_mod) / len(mod), 3) if mod else None,
              "missed_ids": [r["id"] for r in mod if not r["det"]["appeared"]], "time_to_first_detection_hours": _stat_ttd(ttd),
              "detected_within_24h": sum(1 for h in ttd if h <= 24), "detected_after_24h_ids": [r["id"] for r in det_mod if (r["det"].get("hours_after_first_public") or 0) > 24],
              "reached_a_brief_ids": [r["id"] for r in det_mod if r["det"].get("escalated")],
              "dispositioned_brief_or_escalate_ids": [r["id"] for r in det_mod if r["det"].get("triaged_brief_or_escalate")]},
        MEW: conv_block(mew), MRF: ev_mrf}


def build_category_report(reference, coverage, window_start, window_end, as_of, events=None, briefs=None, ratings_path=None, previous=None, changes=None):
    assert_scoreable_reference(reference)
    w0, w1 = ps._day(window_start), ps._day(window_end)
    periods = period_states(make_periods(window_start, window_end), coverage, changes)
    pstate = {p["id"]: p for p in periods}
    rows, listed = [], {NONMAT: [], UNRES: []}
    for inc in reference["incidents"]:
        cat = inc["intelligence_category"]
        pid = assign_period(inc, periods, w0, w1)
        pool = pid if pid in ("pre_window", "undated", "after_window") else pstate[pid]["state"]
        base = {"id": inc["id"], "title": inc["title"], "status": inc["status"], "category": cat, "period": pid, "pool": pool,
                "limit_kind": pstate[pid]["limit_kind"] if pid in pstate else None, "coverage_limits": inc.get("coverage_limits") or []}
        if cat in MATERIAL_CATS:
            rows.append({**base, "det": _detect(inc, events, briefs), "first_report": inc["first_public_report_time"].get("value")})
        else:
            det = _detect(inc, events, briefs) if inc.get("tjr_detection") else {}
            listed[cat].append({**base, "appeared": det.get("appeared"), "reached_a_brief": det.get("escalated"), "duplicate_of": inc.get("duplicate_of"),
                                "non_material_type": inc.get("non_material_type")})
    complete = [r for r in rows if r["pool"] == "complete"]
    limited = [r for r in rows if r["pool"] == "limited"]
    by_kind = {k: category_metrics([r for r in limited if r["limit_kind"] == k]) for k in LIMIT_PRIORITY if any(r["limit_kind"] == k for r in limited)}
    per_period = []
    for p in periods:
        pr = [r for r in rows if r["period"] == p["id"]]
        m = category_metrics(pr)
        per_period.append({"period": p["id"], "start": p["start"].date().isoformat(), "end_inclusive": (p["end"] - timedelta(days=1)).date().isoformat(), "state": p["state"],
                           "limit_kind": p["limit_kind"], "reasons": p["reasons"], "reports_collected": p["collected"], "active_sources": p["active_sources"],
                           "collected_vs_clean_median": p["collected_vs_clean_median"], "records": {c: m[c]["total"] for c in MATERIAL_CATS},
                           MOD: {k: m[MOD][k] for k in ("total", "detected", "detection_rate", "missed_ids")}, "material_ids": [r["id"] for r in pr]})
    full = category_metrics(rows)
    n_complete = sum(1 for p in periods if p["state"] == "complete")
    # incidents whose natural primary source was not collected in any period (persistent source gap, independent of the period state)
    gap_rows = [{"id": r["id"], "period": r["period"], "coverage_limits": r["coverage_limits"], "detected": r["det"]["appeared"]} for r in rows if r["coverage_limits"]]
    rat = ps.summarise_ratings(ps.FileSource(None, None, ratings_path).ratings(), w0, w1)
    burden = {"status": "provided" if rat["provided"] and rat["manual_verification_minutes"] else NOT_PROVIDED,
              "minutes": rat["manual_verification_minutes"] if rat["provided"] and rat["manual_verification_minutes"] else None, "owner_prompt": OWNER_PROMPT}
    return {
        "report": "category_baseline", "generated_for": {"window_start": window_start, "window_end_exclusive": window_end, "period_days": PERIOD_DAYS, "as_of": as_of.isoformat()},
        "reference_set": {"name": reference.get("name"), "set_version": reference.get("set_version"), "records": len(reference["incidents"]),
                          "reviewed_by_human": (reference.get("review") or {}).get("reviewed_by_human"), "reviewer": (reference.get("review") or {}).get("reviewer"),
                          "review_date": (reference.get("review") or {}).get("date"),
                          "material_records_all_reviewed": all(i.get("reviewed_by_human") for i in reference["incidents"] if i["intelligence_category"] in MATERIAL_CATS),
                          "records_not_reviewed": len((reference.get("review") or {}).get("not_reviewed_record_ids", [])),
                          "detection_basis": "events snapshot" if events is not None else "embedded tjr_detection measured by read-only SELECT (measurements_v3-2026-11-24.json)"},
        "period_definition": ("Fixed 7-day UTC observation periods from the window start; an incident belongs to the period of its first public report; "
                              "pre_window = first report before the window start. COMPLETE = no dated collection confounder in or after the period (all periods from the last feed-ceiling step "
                              "that are free of outage/transition) and no volume outlier; otherwise LIMITED (reported separately, excluded from rate comparisons)."),
        "periods": per_period,
        "period_counts": {"total": len(periods), "complete": n_complete, "limited": len(periods) - n_complete,
                          "limited_by_kind": dict(Counter(p["limit_kind"] for p in periods if p["state"] == "limited"))},
        "results": {
            "comparable_complete_coverage_periods": {"periods": [p["id"] for p in periods if p["state"] == "complete"], "metrics": category_metrics(complete)},
            "limited_coverage_periods_reported_separately": {"periods": [p["id"] for p in periods if p["state"] == "limited"], "NOT_FOR_RATE_COMPARISON": True,
                                                             "metrics": category_metrics(limited), "by_limit_kind": by_kind},
            "pre_window_onset_not_in_rates": [{"id": r["id"], "title": r["title"], "category": r["category"], "detected": r["det"]["appeared"]} for r in rows if r["pool"] == "pre_window"],
            "undated_not_scored": [r["id"] for r in rows if r["pool"] == "undated"],
            "full_window_total_not_a_rate_for_comparison": {"metrics": full, "composition": f"{len(complete)} records in {n_complete} complete periods + {len(limited)} records in {len(periods) - n_complete} limited periods + {sum(1 for r in rows if r['pool'] == 'pre_window')} pre-window; shown as a total only"}},
        "persistent_source_gaps": {"note": "Sources collecting only from 2026-11-24 (ASIC, OAIC, ATO, Optus outage register, RBA) mean incident types first reported there were not observable in ANY period; excluding weeks cannot remove this.",
                                   "records_with_declared_limits": gap_rows,
                                   "coverage_file": "coverage_v3-2026-11-24.json"},
        "excluded_from_scores_but_listed": {"non_material": listed[NONMAT], "unresolved": listed[UNRES],
                                            "false_escalation_info_only": {"non_material_reached_a_brief_ids": [x["id"] for x in listed[NONMAT] if x["reached_a_brief"] and not x["duplicate_of"]],
                                                                          "note": "information only, not a score (owner: non-material and unresolved are excluded from scores)"}},
        "manual_verification_burden": burden,
        "per_incident": [{k: v for k, v in r.items() if k != "det"} | {"appeared": r["det"]["appeared"], "first_source": r["det"].get("first_source"),
                                                                       "hours_after_first_public": r["det"].get("hours_after_first_public"), "reached_a_brief": r["det"].get("escalated"),
                                                                       "conversion": (NOT_PROVIDED if r["det"].get("converted") is None else r["det"]["converted"]) if r["category"] in (MEW, MRF) else None}
                         for r in rows],
        "comparison_with_previous_baseline": compare_with_previous(rows, previous),
    }


def compare_with_previous(rows, previous):
    """Like-for-like against the v1 first baseline (baseline_v1-2026-11-24.json 'all' view): the records that were material in v1 AND are
    material operational disruptions in v3 are re-scored here with v3 measurements, next to the v1 numbers. Nothing in the v1 file is changed."""
    if not previous:
        return {"provided": False}
    v1 = previous["baseline_scorecards"]["all"]
    v1_ids = set(v1["time_to_first_detection_hours"]["by_incident"]) | set(v1["material_incidents"]["missed_ids"])
    shared = [r for r in rows if r["category"] == MOD and r["id"] in v1_ids]
    sh = category_metrics(shared)[MOD]
    ids = {r["id"] for r in shared}
    v1_ttd = [h for i, h in v1["time_to_first_detection_hours"]["by_incident"].items() if i in ids and h is not None]
    return {"provided": True,
            "v1_first_baseline": {"material": v1["material_incidents"]["total"], "detected": v1["material_incidents"]["detected"], "detection_rate": v1["material_incidents"]["detection_rate"],
                                  "missed_ids": v1["material_incidents"]["missed_ids"], "ttd_median_h": v1["time_to_first_detection_hours"]["median"], "ttd_p90_h": v1["time_to_first_detection_hours"]["p90"],
                                  "false_escalation": f"{v1['false_escalation']['escalated']}/{v1['false_escalation']['negatives_scored']}"},
            "like_for_like_shared_operational_disruptions": {"ids": [r["id"] for r in shared], "v1_detected": sum(1 for r in shared if r["id"] not in v1["material_incidents"]["missed_ids"]),
                                                             "v3_detected": sh["detected"], "total": sh["total"], "v1_missed": [r["id"] for r in shared if r["id"] in v1["material_incidents"]["missed_ids"]],
                                                             "v3_missed": sh["missed_ids"], "v1_ttd_median_h": ps._median(v1_ttd), "v3_ttd_median_h": sh["time_to_first_detection_hours"]["median"]},
            "what_changed": ["scoring population: v1 scored 15 material records of any kind; v3 scores detection on operational disruptions only and moves alerts/advisories (RS-031) to the warning category, RS-005 to retrospective and RS-004 to non-material",
                             "window start moved from 2026-09-01 to 2026-07-28 and periods with incomplete coverage are separated",
                             "measurement corrections: RS-030 first detection (v1 recorded 2 days late; actually minutes), first-report placeholders for RS-002/RS-003, RS-029 first report added",
                             "new records from the owner's review (RS-054..RS-084)"]}


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _metrics_lines(m, indent="- "):
    d, w, r = m[MOD], m[MEW], m[MRF]
    t = d["time_to_first_detection_hours"]
    conv = w["conversion_rate_of_measured"]
    L = [(f"{indent}Operational disruptions: {d['total']} records, detected {d['detected']} (rate {_pct(d['detection_rate'])}); missed: {', '.join(d['missed_ids']) or 'none'}; "
          f"hours to first collection median {t['median']}, p90 {t['p90']}, max {t['max']} (n={t['n']}); detected within 24 h: {d['detected_within_24h']}; detected after 24 h: {', '.join(d['detected_after_24h_ids']) or 'none'}."),
         (f"{indent}Emerging risks/warnings: {w['total']} records, detected {w['detected']}; converted {w['converted']} ({', '.join(w['converted_ids']) or 'none'}); "
          f"not converted: {', '.join(w['not_converted_ids']) or 'none'}; conversion {NOT_PROVIDED}: {', '.join(w['conversion_not_provided_ids']) or 'none'}; conversion rate of measured: {conv if isinstance(conv, str) else _pct(conv)}."),
         f"{indent}Retrospective findings: {r['total']} records, collected {r['collected']}; surfaced {r['surfaced']} ({', '.join(r['converted_ids']) or 'none'}); not surfaced: {', '.join(r['not_converted_ids']) or 'none'}."]
    return L


def render_category_markdown(r, label=""):
    g, rs, res = r["generated_for"], r["reference_set"], r["results"]
    L = []
    if label:
        L += [f"> **{label}**", ""]
    L += [f"# Intelligence baseline (category mode): {g['window_start']} to {g['window_end_exclusive']} (end exclusive)", "",
          (f"Generated by `tools/intelligence/weekly_baseline.py` as of {g['as_of']}. Reference set: {rs['name']} {rs['set_version']} ({rs['records']} records; reviewed by human: {rs['reviewed_by_human']}, "
           f"reviewer {rs['reviewer']}, {rs['review_date']}; all material records reviewed: {rs['material_records_all_reviewed']}; {rs['records_not_reviewed']} carried v1 records not reviewed). Detection basis: {rs['detection_basis']}."), "",
          "## Observation periods and coverage", "", r["period_definition"], "",
          f"Periods: {r['period_counts']['total']}; coverage-complete {r['period_counts']['complete']}; limited {r['period_counts']['limited']} ({r['period_counts']['limited_by_kind']}).", "",
          "| Period | Dates (UTC) | State | Reason | Reports collected | Active sources | Material records | Operational disruptions detected |", "|---|---|---|---|---|---|---|---|"]
    for p in r["periods"]:
        md = p[MOD]
        L.append(f"| {p['period']} | {p['start']}..{p['end_inclusive']} | {p['state'].upper()} | {LIMIT_LABEL.get(p['limit_kind'], '-')} | {p['reports_collected']} | {p['active_sources']} | "
                 f"{sum(p['records'].values())} ({', '.join(p['material_ids']) or '-'}) | {md['detected']}/{md['total']} |")
    cc = res["comparable_complete_coverage_periods"]
    lc = res["limited_coverage_periods_reported_separately"]
    L += ["", "## Results: coverage-complete periods (the only basis for rate comparison)", "", f"Periods: {', '.join(cc['periods'])}.", ""] + _metrics_lines(cc["metrics"])
    L += ["", "## Results: coverage-limited periods (reported separately; NOT for rate comparison)", "", f"Periods: {', '.join(lc['periods'])}.", ""] + _metrics_lines(lc["metrics"])
    for k, m in lc["by_limit_kind"].items():
        L += ["", f"### Limited by: {LIMIT_LABEL[k]}", ""] + _metrics_lines(m)
    pw = res["pre_window_onset_not_in_rates"]
    L += ["", "## Pre-window onset and undated (not in any rate)", "",
          "- Pre-window: " + ("; ".join(f"{x['id']} ({x['category']}; detected at onset: {x['detected']})" for x in pw) or "none") + ".",
          f"- Undated: {', '.join(res['undated_not_scored']) or 'none'}.", "",
          "## Full-window total (labelled total, not a rate for comparison)", "", res["full_window_total_not_a_rate_for_comparison"]["composition"] + ".", ""]
    L += _metrics_lines(res["full_window_total_not_a_rate_for_comparison"]["metrics"])
    gp = r["persistent_source_gaps"]
    L += ["", "## Persistent source gaps (not removable by excluding periods)", "", gp["note"], ""]
    for x in gp["records_with_declared_limits"]:
        L.append(f"- {x['id']} ({x['period']}; detected: {x['detected']}): " + "; ".join(x["coverage_limits"]))
    ex = r["excluded_from_scores_but_listed"]
    L += ["", "## Excluded from scores (listed)", "",
          f"- Non-material ({len(ex['non_material'])}): " + ", ".join(f"{x['id']}" for x in ex["non_material"]) + ".",
          f"- Unresolved ({len(ex['unresolved'])}): " + ", ".join(x["id"] for x in ex["unresolved"]) + ".",
          f"- Information only, not a score: non-material records that reached a brief: {', '.join(ex['false_escalation_info_only']['non_material_reached_a_brief_ids']) or 'none'}.", ""]
    mb = r["manual_verification_burden"]
    L += ["## Manual verification burden (owner fills in)", "", f"- Status: **{mb['status']}**; minutes: {mb['minutes'] if mb['minutes'] is not None else '__________'}", f"- {mb['owner_prompt']}", ""]
    cmp_ = r["comparison_with_previous_baseline"]
    if cmp_.get("provided"):
        v, lf = cmp_["v1_first_baseline"], cmp_["like_for_like_shared_operational_disruptions"]
        L += ["## Against the previous baseline (v1 first baseline, 2026-11-24)", "",
              f"- Previous: {v['detected']}/{v['material']} material detected (rate {_pct(v['detection_rate'])}), missed {', '.join(v['missed_ids'])}; hours to first collection median {v['ttd_median_h']}, p90 {v['ttd_p90_h']}; false escalation {v['false_escalation']}.",
              f"- Like-for-like (records material in v1 and operational disruptions in v3: {', '.join(lf['ids'])}): v1 detected {lf['v1_detected']}/{lf['total']}, v3 detected {lf['v3_detected']}/{lf['total']}; missed v1 {', '.join(lf['v1_missed']) or 'none'}, v3 {', '.join(lf['v3_missed']) or 'none'}; median hours v1 {lf['v1_ttd_median_h']} vs v3 {lf['v3_ttd_median_h']}.",
              "- What changed: " + "; ".join(cmp_["what_changed"]) + ".", ""]
    L += ["## Per material record", "", "| Id | Category | Period | State | Detected | First source | Hours | Reached a brief | Conversion |", "|---|---|---|---|---|---|---|---|---|"]
    for x in r["per_incident"]:
        L.append(f"| {x['id']} | {x['category'].replace('material_', '')} | {x['period']} | {x['pool']} | {x['appeared']} | {x['first_source']} | {x['hours_after_first_public']} | {x['reached_a_brief']} | {x['conversion'] if x['conversion'] is not None else '-'} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--reference", default=str(DEFAULT_REFERENCE), help="frozen reference set (default: reference_set_v1.json); a v3 file switches to category mode")
    ap.add_argument("--export-dir", help="directory with events.json, briefs.json, sources.json[, ratings.csv]")
    ap.add_argument("--events"), ap.add_argument("--briefs"), ap.add_argument("--sources"), ap.add_argument("--ratings")
    ap.add_argument("--week-start"), ap.add_argument("--week-end", help="exclusive")
    ap.add_argument("--window-start", help="category mode: window start (default: from the reference header)")
    ap.add_argument("--window-end", help="category mode: exclusive window end")
    ap.add_argument("--coverage", help="category mode: coverage JSON (weekly collected volumes and zero-collection days from SELECTs)")
    ap.add_argument("--previous-baseline", help="category mode: previous baseline JSON for the like-for-like comparison")
    ap.add_argument("--as-of", help="ISO timestamp for source classification (default: now UTC)")
    ap.add_argument("--print-export-sql", action="store_true")
    ap.add_argument("--out-md"), ap.add_argument("--out-json")
    ap.add_argument("--label", default="", help="banner line placed at the top of the Markdown")
    a = ap.parse_args(argv)
    ref = json.loads(Path(a.reference).read_text(encoding="utf-8"))
    category_mode = is_category_reference(ref)
    if a.print_export_sql:
        if not (a.week_start and a.week_end):
            raise SystemExit("--print-export-sql needs --week-start and --week-end")
        print(print_export_sql(a.week_start, a.week_end))
        return 0
    d = Path(a.export_dir) if a.export_dir else None
    pick = lambda explicit, name: explicit or (str(d / name) if d and (d / name).exists() else None)
    ev_p, br_p, so_p, ra_p = pick(a.events, "events.json"), pick(a.briefs, "briefs.json"), pick(a.sources, "sources.json"), pick(a.ratings, "ratings.csv")
    as_of = ps.parse_ts(a.as_of) if a.as_of else datetime.now(timezone.utc)
    if category_mode:
        w_start, w_end = a.window_start, a.window_end
        if not (w_start and w_end):
            hdr = (ref.get("window") or "").split(" ")[0]
            if ".." not in hdr:
                raise SystemExit("category mode needs --window-start/--window-end (or a reference header window)")
            w_start, w_end = hdr.split("..")
        cov = json.loads(Path(a.coverage).read_text(encoding="utf-8")) if a.coverage else None
        prev = json.loads(Path(a.previous_baseline).read_text(encoding="utf-8")) if a.previous_baseline else None
        rep = build_category_report(ref, cov, w_start, w_end, as_of, _load_rows(ev_p) if ev_p else None, _load_rows(br_p) if br_p else None, ra_p, prev)
        md = render_category_markdown(rep, a.label)
    else:
        if not (a.week_start and a.week_end):
            raise SystemExit("--week-start and --week-end are required")
        if not ev_p:
            raise SystemExit("events.json is required (use --print-export-sql for the SELECT)")
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
