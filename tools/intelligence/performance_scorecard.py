#!/usr/bin/env python3
"""Weekly intelligence PERFORMANCE scorecard (read-only, offline).

Scores the intelligence pipeline against the curated reference incident set in
``knowledge/intelligence-reference-set/``. It reads only local JSON/CSV files, never
touches the network or the database, and writes nothing unless ``--out`` is given.

Inputs
  --reference  reference_set.json (or baseline-YYYY-MM-DD.json)       required
  --events     exported intelligence_events rows (JSON list)           optional
  --briefs     exported captains_daily_briefs rows (JSON list)         optional
  --ratings    Captain's CSV (see below)                               optional
  --week-start/--week-end  ISO dates; incidents whose first public report falls in the window
               are scored (default: all incidents in the reference set)

Without --events the scorecard falls back to each incident's embedded ``tjr_detection``
block (the frozen baseline). With --events it re-derives detection from the snapshot.

Events JSON row:  event_id, source_name, raw_title, [raw_summary], published_at, collected_at,
                  [brief_id], [suppressed], [risk_rating], [source_tier]
Briefs JSON row:  brief_date (YYYY-MM-DD), brief_type, brief_text
Captain CSV:      date,brief_usefulness_1to5,noise_count,manual_verification_minutes[,notes]

Metric semantics
  * material incident = reference record, not a negative example, Australian materiality high|med,
    and not verification_status 'unverified' (unverified records are counted separately).
  * time to first detection = first matching event collected_at minus the reference
    first_public_report_time (hours). It bundles feed and collection lag; it is NOT a score by itself.
  * false escalation = a negative example that reached a brief (brief_id set, or a brief's text matches).
  * false recovery = a matching event claiming restoration (restored/resolved/back online...) published
    more than 1h BEFORE the reference end time. Only incidents with a reference end time are checked.
  * independent corroboration share = detected incidents with >= 2 independent publisher families
    among NON-aggregator events (aggregators excluded, one organisation under several names counted once,
    as in intelligence.weekly_evidence / PR #693 semantics).
  * unique analytical contribution per source = first report, confirmation, restoration evidence and
    chronology roles per source across matched events, plus roles only that source supplied. First
    detection is one role of four and is deliberately not the headline.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intelligence import weekly_evidence as we

MATERIAL_LEVELS = {"high", "med"}
RESTORE_RE = re.compile(r"(restor|resolved|back online|back up|recovered|services? (return|resum)|fixed)", re.IGNORECASE)
CHRONO_RE = re.compile(r"(what we know|what happened|explained|root cause|timeline|post-incident|findings|review|why )", re.IGNORECASE)
FALSE_RECOVERY_TOLERANCE = timedelta(hours=1)
CONFIRMING_KINDS = {we.PRIMARY, we.MAINSTREAM, we.SPECIALIST}


# ── data source abstraction (tests inject a fake) ───────────────────────────────

class DataSource(Protocol):
    def events(self) -> list[dict] | None: ...
    def briefs(self) -> list[dict] | None: ...
    def ratings(self) -> list[dict] | None: ...


class FileSource:
    """Exported JSON / CSV files. Any path may be None."""

    def __init__(self, events=None, briefs=None, ratings=None):
        self._p = {"events": events, "briefs": briefs, "ratings": ratings}

    def events(self):
        return _load_json(self._p["events"])

    def briefs(self):
        return _load_json(self._p["briefs"])

    def ratings(self):
        p = self._p["ratings"]
        if not p:
            return None
        with open(p, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))


def _load_json(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["events"] if isinstance(data, dict) and "events" in data else data


# ── helpers ─────────────────────────────────────────────────────────────────────

def parse_ts(v):
    if not v:
        return None
    s = str(v).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if re.search(r"[+-]\d\d$", s):
        s += ":00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _day(v):
    return parse_ts(v if "T" in str(v) else f"{v}T00:00:00Z")


def to_python_regex(pg: str) -> re.Pattern:
    """Reference regexes were run in Postgres (~*): \\m \\M are word boundaries."""
    return re.compile(pg.replace(r"\m", r"\b").replace(r"\M", r"\b"), re.IGNORECASE | re.DOTALL)


def hours(a, b):
    return None if a is None or b is None else round((a - b).total_seconds() / 3600, 2)


def _median(xs):
    return round(statistics.median(xs), 2) if xs else None


def _p90(xs):
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, round(0.9 * (len(s) - 1)))], 2)


def is_material(inc):
    return (not inc.get("is_negative_example")
            and inc["australian_materiality"]["level"] in MATERIAL_LEVELS
            and inc.get("verification_status") != "unverified")


def in_window(inc, w0, w1):
    if w0 is None and w1 is None:
        return True
    t = parse_ts(inc["first_public_report_time"]["value"]) or parse_ts(inc["start_time_utc"]["value"])
    if t is None:
        return True  # undated records are never silently dropped
    return (w0 is None or t >= w0) and (w1 is None or t < w1)


def match_events(inc, events):
    det = inc.get("tjr_detection") or {}
    m = det.get("match") or {}
    if not m.get("title_regex"):
        return []
    rx = to_python_regex(m["title_regex"])
    w0 = _day(m["published_from"]) - timedelta(days=1) if m.get("published_from") else None
    w1 = _day(m["published_to"]) + timedelta(days=2) if m.get("published_to") else None
    out = []
    for e in events:
        if not rx.search(e.get("raw_title") or ""):
            continue
        p = parse_ts(e.get("published_at"))
        if p and ((w0 and p < w0) or (w1 and p >= w1)):
            continue
        out.append(e)
    out.sort(key=lambda e: (parse_ts(e.get("collected_at")) or datetime.max.replace(tzinfo=timezone.utc)))
    return out


def family_of(e):
    return we.publisher_family(e.get("source_name") or "", e.get("raw_title") or "")


def independent_families(evs):
    return {family_of(e) for e in evs if we.source_kind(e.get("source_name") or "") != we.AGGREGATOR}


# ── per-incident evaluation ─────────────────────────────────────────────────────

def evaluate_incident(inc, events, briefs):
    """Return a detection dict for one incident from a live events snapshot."""
    evs = match_events(inc, events)
    first_pub = parse_ts(inc["first_public_report_time"]["value"])
    d = {"appeared": bool(evs), "n_events": len(evs), "from": "events_snapshot"}
    if not evs:
        d.update(first_collected_at=None, first_source=None, brief_surfaced=False, independent_publishers=0,
                 escalated=False, restoration_claims_before_end=0)
        return d, []
    first = evs[0]
    fc = parse_ts(first.get("collected_at"))
    d.update(first_collected_at=first.get("collected_at"), first_source=first.get("source_name"),
             first_source_kind=we.source_kind(first.get("source_name") or ""),
             hours_after_first_public=hours(fc, first_pub),
             events_with_brief_id=sum(1 for e in evs if e.get("brief_id")),
             independent_publishers=len(independent_families(evs)))
    d["brief_surfaced"] = d["events_with_brief_id"] > 0 or _brief_text_hit(inc, briefs, first_pub)
    d["escalated"] = d["brief_surfaced"]
    end = parse_ts(inc["end_time_utc"]["value"])
    fr = 0
    if end:
        for e in evs:
            p = parse_ts(e.get("published_at"))
            text = f"{e.get('raw_title') or ''} {e.get('raw_summary') or ''}"
            if p and RESTORE_RE.search(e.get("raw_title") or "") and p < end - FALSE_RECOVERY_TOLERANCE and text:
                fr += 1
    d["restoration_claims_before_end"] = fr
    return d, evs


def _brief_text_hit(inc, briefs, first_pub):
    if not briefs:
        return False
    rx_s = (inc.get("tjr_detection") or {}).get("match", {}).get("title_regex")
    if not rx_s:
        return False
    rx = to_python_regex(rx_s)
    lo = (first_pub or datetime.min.replace(tzinfo=timezone.utc))
    hi = lo + timedelta(days=7)
    for b in briefs:
        bd = _day(b.get("brief_date") or "")
        if bd and lo - timedelta(days=1) <= bd <= hi and rx.search(b.get("brief_text") or ""):
            return True
    return False


def detection_from_embedded(inc):
    t = inc.get("tjr_detection") or {}
    first_pub = parse_ts(inc["first_public_report_time"]["value"])
    fc = parse_ts(t.get("first_collected_at"))
    return {"appeared": bool(t.get("appeared")), "n_events": t.get("n_events", 0), "from": "embedded_baseline",
            "first_collected_at": t.get("first_collected_at"), "first_source": t.get("first_source"),
            "first_source_kind": t.get("first_source_kind"),
            "hours_after_first_public": hours(fc, first_pub),
            "events_with_brief_id": t.get("events_with_brief_id", 0),
            "brief_surfaced": bool(t.get("events_with_brief_id") or t.get("daily_briefs_mentioning")),
            "escalated": bool(t.get("events_with_brief_id") or t.get("daily_briefs_mentioning")),
            "independent_publishers": t.get("n_non_aggregator_sources") or 0,
            "restoration_claims_before_end": None}


# ── contribution analysis ───────────────────────────────────────────────────────

def contributions(per_incident_events):
    """Roles per source. per_incident_events: {incident_id: [events sorted by collected]}."""
    roles = defaultdict(lambda: {"first_report": 0, "confirmation": 0, "restoration_evidence": 0, "chronology": 0,
                                 "events": 0, "sole_role_incidents": 0})
    for evs in per_incident_events.values():
        if not evs:
            continue
        first_family = family_of(evs[0])
        seen_role_sources = defaultdict(set)
        confirmed_families = set()
        for i, e in enumerate(evs):
            src = e.get("source_name") or "unknown"
            r = roles[src]
            r["events"] += 1
            kind = we.source_kind(src)
            if i == 0:
                r["first_report"] += 1
                seen_role_sources["first_report"].add(src)
            fam = family_of(e)
            if i > 0 and kind in CONFIRMING_KINDS and fam != first_family and fam not in confirmed_families:
                confirmed_families.add(fam)
                r["confirmation"] += 1
                seen_role_sources["confirmation"].add(src)
            if RESTORE_RE.search(e.get("raw_title") or ""):
                r["restoration_evidence"] += 1
                seen_role_sources["restoration_evidence"].add(src)
            if CHRONO_RE.search(e.get("raw_title") or ""):
                r["chronology"] += 1
                seen_role_sources["chronology"].add(src)
        for srcs in seen_role_sources.values():
            if len(srcs) == 1:
                roles[next(iter(srcs))]["sole_role_incidents"] += 1
    out = []
    for src, r in roles.items():
        total_roles = r["first_report"] + r["confirmation"] + r["restoration_evidence"] + r["chronology"]
        r = dict(r, source=src, source_kind=we.source_kind(src), roles_total=total_roles,
                 first_report_share_of_roles=round(r["first_report"] / total_roles, 2) if total_roles else None)
        out.append(r)
    out.sort(key=lambda r: (-r["roles_total"], r["source"]))
    return out


# ── Captain's ratings ───────────────────────────────────────────────────────────

def summarise_ratings(rows, w0, w1):
    if rows is None:
        return {"provided": False, "brief_usefulness_mean_1to5": None, "noise_count": None,
                "manual_verification_minutes": None, "rows": 0, "warnings": []}
    warnings, use, noise, mins, n = [], [], 0, 0.0, 0
    for i, r in enumerate(rows, start=2):
        d = _day(r.get("date") or "")
        if d is None:
            warnings.append(f"row {i}: unparseable date {r.get('date')!r}")
            continue
        if (w0 and d < w0) or (w1 and d >= w1):
            continue
        n += 1
        u = (r.get("brief_usefulness_1to5") or "").strip()
        if u:
            try:
                uf = float(u)
                if 1 <= uf <= 5:
                    use.append(uf)
                else:
                    warnings.append(f"row {i}: usefulness {u} outside 1-5 (ignored)")
            except ValueError:
                warnings.append(f"row {i}: usefulness {u!r} not a number (ignored)")
        for key, acc in (("noise_count", "n"), ("manual_verification_minutes", "m")):
            v = (r.get(key) or "").strip()
            if not v:
                continue
            try:
                x = float(v)
                if x < 0:
                    raise ValueError
                if acc == "n":
                    noise += int(x)
                else:
                    mins += x
            except ValueError:
                warnings.append(f"row {i}: {key} {v!r} invalid (ignored)")
    return {"provided": True, "rows": n, "brief_usefulness_mean_1to5": round(statistics.mean(use), 2) if use else None,
            "noise_count": noise, "manual_verification_minutes": mins, "warnings": warnings}


# ── scorecard ───────────────────────────────────────────────────────────────────

def compute_scorecard(reference, source: DataSource, week_start=None, week_end=None):
    w0, w1 = (_day(week_start) if week_start else None), (_day(week_end) if week_end else None)
    events, briefs = source.events(), source.briefs()
    incidents = [i for i in reference["incidents"] if in_window(i, w0, w1)]
    per_inc, per_inc_events, rows = {}, {}, []
    for inc in incidents:
        if events is not None:
            det, evs = evaluate_incident(inc, events, briefs)
        else:
            det, evs = detection_from_embedded(inc), []
        per_inc[inc["id"]] = det
        per_inc_events[inc["id"]] = evs
        rows.append((inc, det))

    material = [(i, d) for i, d in rows if is_material(i)]
    unverified_material = [i["id"] for i, _ in rows if not i.get("is_negative_example")
                           and i["australian_materiality"]["level"] in MATERIAL_LEVELS
                           and i.get("verification_status") == "unverified"]
    detected = [(i, d) for i, d in material if d["appeared"]]
    missed = [i["id"] for i, d in material if not d["appeared"]]
    ttd = [d["hours_after_first_public"] for _, d in detected if d.get("hours_after_first_public") is not None]
    negatives = [(i, d) for i, d in rows if i.get("is_negative_example")]
    false_esc = [i["id"] for i, d in negatives if d["escalated"]]
    fr_claims = {i["id"]: d["restoration_claims_before_end"] for i, d in rows
                 if d.get("restoration_claims_before_end")}
    corroborated = [i["id"] for i, d in detected if d["independent_publishers"] >= 2]
    escalated_pos = [(i, d) for i, d in rows if d["escalated"]]
    au_rel = [i for i, _ in escalated_pos if i["australian_materiality"]["level"] in MATERIAL_LEVELS
              and not i.get("is_negative_example")]
    pairs = defaultdict(list)
    for i, d in rows:
        if i.get("correlation_trap"):
            pairs[i["correlation_trap"]["pair_id"]].append((i, d))
    # incorrect correlation: an unrelated pair where one canonical signal/regex-group contains both incidents' events
    wrong_corr = []
    for pid, members in pairs.items():
        if len(members) == 2 and events is not None:
            a, b = (per_inc_events[members[0][0]["id"]], per_inc_events[members[1][0]["id"]])
            shared = {e.get("canonical_signal_id") for e in a if e.get("canonical_signal_id")} & \
                     {e.get("canonical_signal_id") for e in b if e.get("canonical_signal_id")}
            shared_ids = {e.get("event_id") for e in a} & {e.get("event_id") for e in b}
            if shared or shared_ids:
                wrong_corr.append(pid)

    card = {
        "scorecard_version": "1.0",
        "mode": "events_snapshot" if events is not None else "embedded_baseline",
        "window": {"start": week_start, "end": week_end},
        "reference_set": {"name": reference.get("name"), "created_utc": reference.get("created_utc"),
                          "reviewed_by_human": all(i.get("reviewed_by_human") for i in reference["incidents"]),
                          "incidents_scored": len(incidents)},
        "material_incidents": {
            "total": len(material), "detected": len(detected), "missed": len(missed),
            "detection_rate": round(len(detected) / len(material), 3) if material else None,
            "missed_ids": missed, "unverified_material_not_scored": unverified_material},
        "time_to_first_detection_hours": {
            "n": len(ttd), "median": _median(ttd), "p90": _p90(ttd), "max": max(ttd) if ttd else None,
            "by_incident": {i["id"]: d.get("hours_after_first_public") for i, d in detected},
            "note": "includes feed polling and collection lag; interpret with contribution roles, not alone"},
        "brief_surfacing": {
            "material_detected_in_brief": sum(1 for _, d in detected if d["brief_surfaced"]),
            "material_detected_not_in_brief": [i["id"] for i, d in detected if not d["brief_surfaced"]]},
        "false_escalation": {"negatives_total": len(negatives), "escalated": len(false_esc), "ids": false_esc,
                             "rate": round(len(false_esc) / len(negatives), 3) if negatives else None},
        "false_recovery": {"incidents_with_early_recovery_claims": len(fr_claims), "claims_by_incident": fr_claims,
                           "checkable": events is not None},
        "incorrect_correlation": {"unrelated_pairs": len(pairs), "wrongly_correlated": wrong_corr,
                                  "checkable": events is not None},
        "independent_corroboration": {
            "detected_incidents": len(detected), "corroborated": len(corroborated),
            "share": round(len(corroborated) / len(detected), 3) if detected else None,
            "uncorroborated_ids": [i["id"] for i, d in detected if d["independent_publishers"] < 2],
            "rule": ">=2 independent non-aggregator publisher families; aggregators excluded"},
        "australian_relevance": {
            "escalated_incidents": len(escalated_pos), "escalated_with_au_materiality": len(au_rel),
            "precision": round(len(au_rel) / len(escalated_pos), 3) if escalated_pos else None},
        "source_contribution": contributions(per_inc_events) if events is not None else None,
        "captain_ratings": summarise_ratings(source.ratings(), w0, w1),
        "per_incident": per_inc,
    }
    return card


# ── output ──────────────────────────────────────────────────────────────────────

def render_text(c):
    m, t = c["material_incidents"], c["time_to_first_detection_hours"]
    fe, ic, au = c["false_escalation"], c["independent_corroboration"], c["australian_relevance"]
    r = c["captain_ratings"]
    lines = [f"Intelligence performance scorecard ({c['mode']}; window {c['window']['start'] or '-'}..{c['window']['end'] or '-'})",
             f"  reference set reviewed by human: {c['reference_set']['reviewed_by_human']}  incidents scored: {c['reference_set']['incidents_scored']}",
             f"  material detected {m['detected']}/{m['total']} (rate {m['detection_rate']}); missed: {', '.join(m['missed_ids']) or 'none'}",
             f"  unverified material records not scored: {', '.join(m['unverified_material_not_scored']) or 'none'}",
             f"  time to first detection h: median {t['median']} p90 {t['p90']} max {t['max']} (n={t['n']})",
             f"  detected but never in a brief: {', '.join(c['brief_surfacing']['material_detected_not_in_brief']) or 'none'}",
             f"  false escalation {fe['escalated']}/{fe['negatives_total']} {fe['ids']}",
             f"  false recovery incidents: {c['false_recovery']['incidents_with_early_recovery_claims']} (checkable={c['false_recovery']['checkable']})",
             f"  incorrect correlation: {c['incorrect_correlation']['wrongly_correlated']} of {c['incorrect_correlation']['unrelated_pairs']} unrelated pairs (checkable={c['incorrect_correlation']['checkable']})",
             f"  independent corroboration share {ic['share']} ({ic['corroborated']}/{ic['detected_incidents']}); uncorroborated: {', '.join(ic['uncorroborated_ids']) or 'none'}",
             f"  Australian relevance precision of escalated items: {au['precision']}",
             f"  Captain ratings: provided={r['provided']} usefulness={r['brief_usefulness_mean_1to5']} noise={r['noise_count']} verify_min={r['manual_verification_minutes']}"]
    for w in r["warnings"]:
        lines.append(f"    ratings warning: {w}")
    if c["source_contribution"]:
        lines.append("  source contribution (first/confirm/restore/chrono; events):")
        for s in c["source_contribution"][:12]:
            lines.append(f"    {s['source'][:38]:38s} {s['first_report']}/{s['confirmation']}/{s['restoration_evidence']}/{s['chronology']}; {s['events']} ev [{s['source_kind']}]")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--reference", required=True)
    ap.add_argument("--events")
    ap.add_argument("--briefs")
    ap.add_argument("--ratings")
    ap.add_argument("--week-start")
    ap.add_argument("--week-end")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--out", help="optional path to write the JSON scorecard")
    a = ap.parse_args(argv)
    with open(a.reference, encoding="utf-8") as fh:
        ref = json.load(fh)
    card = compute_scorecard(ref, FileSource(a.events, a.briefs, a.ratings), a.week_start, a.week_end)
    if a.out:
        Path(a.out).write_text(json.dumps(card, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(card, indent=1, ensure_ascii=False) if a.format == "json" else render_text(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
