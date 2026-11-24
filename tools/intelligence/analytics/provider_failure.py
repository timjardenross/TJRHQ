"""P1 (prototype, NON-PRODUCTION): recurring provider failure analysis.

Counts DISTINCT INCIDENTS rather than feed entries. Status-page feeds emit
several entries per incident (state updates, stspg.io short links alongside
full incident URLs, backfill re-ingests), so entries are not incidents.

Usage:
    python tools/intelligence/analytics/provider_failure.py \
        --input status_events.jsonl --as-of 2026-11-24T00:40:00Z \
        --focus "GitHub Status" --out report.md

Offline only. Reads a JSONL export; never contacts the database or network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analytics_common import (
    HYPOTHESIS,
    LABEL_LEGEND,
    OBSERVED,
    PLAUSIBLE,
    in_window,
    load_jsonl,
    median,
    parse_ts,
    windows,
)

STATE_SUFFIX = re.compile(
    r"\s*\((investigating|identified|monitoring|resolved|update|scheduled|completed|in progress)\)\s*$",
    re.IGNORECASE,
)
TITLE_PREFIX = re.compile(r"^[A-Za-z0-9 ()]+ Status:\s*")
LEADING_TAGS = re.compile(r"^(rescheduled|retrospective|incident|update|completed):\s*", re.IGNORECASE)
ID_URL = re.compile(r"/incidents?/([A-Za-z0-9]{5,})/?$")
STSPG_URL = re.compile(r"stspg\.io/([a-z0-9]+)/?$", re.IGNORECASE)

RESOLVED_MARKERS = re.compile(
    r"\(resolved\)|\(completed\)|\bresolved\s*[-:]|status:\s*resolved|has been resolved|"
    r"issue is now resolved|\bcompleted\s*[-:]|retrospective",
    re.IGNORECASE,
)
SCHEDULED_MARKERS = re.compile(
    r"this is a scheduled event|\bscheduled\s*-|planned maintenance|scheduled maintenance|"
    r"\brescheduled\b|\bmaintenance\b|\bscheduled\b",
    re.IGNORECASE,
)
EMERGENCY_MARKERS = re.compile(r"emergency maintenance|unplanned", re.IGNORECASE)
IMPACT_TAG = re.compile(r"\[Impact:\s*(critical|major|minor|none)\]", re.IGNORECASE)
AFFECTED = re.compile(r"Affected(?: components)?:?\s*(.+?)(?:\.\s|$)", re.IGNORECASE)
IMPACTED_PRODUCTS = re.compile(r"Impacted Products:\s*(.+?)(?:$|\.)", re.IGNORECASE)
SALESFORCE_SEV = re.compile(r"\b(Disruption|Degradation|Maintenance)\b")
WINDOW_HHMM = re.compile(
    r"(?:between|from)\s+(\d{1,2}):(\d{2})\s*(?:UTC)?\s*(?:and|to|-)\s*(\d{1,2}):(\d{2})\s*UTC", re.IGNORECASE
)
SCHED_WINDOW = re.compile(
    r"Start:\s*(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) UTC\s*End:\s*(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) UTC",
    re.IGNORECASE,
)

AU_STRONG = re.compile(
    r"\bsydney\b|\bmelbourne\b|\bbrisbane\b|\bperth\b|\bcanberra\b|\baustralia\b|ap-southeast-[24]|"
    r"australia[- ]?(east|southeast|central)|\bSYD\b|\bMEL\b|\bAEDT\b|\bAEST\b|\.com\.au|\bAU\b[ -]",
    re.IGNORECASE,
)
AU_WEAK = re.compile(r"\bapac\b|asia[- ]pacific|\boceania\b|\bglobal(ly)?\b|\ball regions\b|\bworldwide\b", re.IGNORECASE)
REGION_PATTERNS = [
    r"ap-southeast-\d", r"us-east-\d", r"us-west-\d", r"eu-[a-z]+-\d", r"me-central-\d",
    r"\bsydney\b", r"\bmelbourne\b", r"\bsingapore\b", r"\bhong kong\b", r"\btokyo\b",
    r"\bnew zealand\b", r"\bAPAC\b", r"\bEMEA\b", r"\bnorth america\b", r"\beurope\b",
    r"\bUS East\b", r"\bUS West\b", r"\bFrankfurt\b", r"\bLondon\b", r"\bSYD\b",
]
REGION_RE = re.compile("|".join(REGION_PATTERNS), re.IGNORECASE)

SEV_RANK = {"none": 0, "minor": 1, "major": 2, "critical": 3}
BACKFILL_MIN_ROWS = 8


def provider_of(source_name: str) -> str:
    name = re.sub(r"\s*\(.*?\)", "", source_name)
    name = re.sub(r"\s+(Trust |Service |Network )?Status$", "", name, flags=re.IGNORECASE)
    return name.strip()


def normalise_stem(title: str) -> str:
    text = title or ""
    text = TITLE_PREFIX.sub("", text)
    text = STATE_SUFFIX.sub("", text)
    text = LEADING_TAGS.sub("", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def url_incident_id(url):
    """Return ('id', value) | ('stspg', code) | None."""
    if not url:
        return None
    m = STSPG_URL.search(url)
    if m:
        return ("stspg", m.group(1))
    m = ID_URL.search(url)
    if m and m.group(1).lower() not in ("incidents", "incident"):
        return ("id", m.group(1))
    return None


def classify_schedule(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    if EMERGENCY_MARKERS.search(text):
        return "unplanned"
    if SCHEDULED_MARKERS.search(text):
        return "scheduled"
    return "unplanned"


def parse_severity(title: str, summary: str):
    m = IMPACT_TAG.search(summary or "")
    if m:
        return m.group(1).lower()
    text = f"{title} {summary}"
    if re.search(r"major outage|full outage|disruption", text, re.IGNORECASE):
        return "major"
    if re.search(r"partial outage|degrad|elevated|delay|increased error|latency|issues", text, re.IGNORECASE):
        return "minor"
    return None


def parse_services(summary: str):
    out = []
    for rx in (AFFECTED, IMPACTED_PRODUCTS):
        m = rx.search(summary or "")
        if m:
            text = re.sub(r"\((?:degraded|partial|full|major)[^)]*\)", "", m.group(1), flags=re.IGNORECASE)
            out += [s.strip() for s in re.split(r",| and ", text) if 2 < len(s.strip()) < 60]
    return out[:12]


def au_relevance(title: str, summary: str, url: str = ""):
    text = f"{title} {summary} {url}"
    if AU_STRONG.search(text):
        return "strong"
    if AU_WEAK.search(text):
        return "weak"
    return "none"


def stated_duration_minutes(summary: str):
    """Duration stated in text (UTC windows), else None. Returns (minutes, basis)."""
    m = SCHED_WINDOW.search(summary or "")
    if m:
        d1 = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:00+00:00")
        d2 = datetime.fromisoformat(f"{m.group(4)}T{m.group(5)}:{m.group(6)}:00+00:00")
        return int((d2 - d1).total_seconds() // 60), "scheduled_window"
    m = WINDOW_HHMM.search(summary or "")
    if m:
        a = int(m.group(1)) * 60 + int(m.group(2))
        b = int(m.group(3)) * 60 + int(m.group(4))
        return (b - a) % 1440, "stated_window"
    return None, None


def build_incidents(rows):
    """Group entries into distinct incidents per source.

    Order of precedence: full incident id in URL; stspg.io short link merged into an
    id-bearing incident that has the same normalised title and publish minute;
    otherwise 'stspg:<code>'; URL-less rows keyed by title stem + publish date.
    """
    incidents = {}
    by_stem_minute = {}
    pending = []

    def add(key, row):
        inc = incidents.setdefault(key, {"key": key, "source": row["source_name"], "entries": []})
        inc["entries"].append(row)

    prepared = []
    for r in rows:
        r = dict(r)
        r["_pub"] = parse_ts(r.get("published_at"))
        r["_col"] = parse_ts(r.get("collected_at"))
        r["_stem"] = normalise_stem(r.get("raw_title"))
        r["_minute"] = r["_pub"].strftime("%Y-%m-%dT%H:%M") if r["_pub"] else "nopub"
        prepared.append(r)

    for r in prepared:
        ident = url_incident_id(r.get("canonical_url"))
        if ident and ident[0] == "id":
            key = f"{r['source_name']}|id:{ident[1]}"
            by_stem_minute.setdefault((r["source_name"], r["_stem"], r["_minute"]), key)
            add(key, r)
        elif ident and ident[0] == "stspg":
            pending.append((r, ident[1]))
        else:
            day = r["_pub"].strftime("%Y-%m-%d") if r["_pub"] else "nopub"
            add(f"{r['source_name']}|t:{r['_stem']}|{day}", r)
    for r, code in pending:
        key = by_stem_minute.get((r["source_name"], r["_stem"], r["_minute"]))
        add(key or f"{r['source_name']}|stspg:{code}", r)

    out = []
    for inc in incidents.values():
        es = sorted(inc["entries"], key=lambda e: (e["_pub"] or datetime.min.replace(tzinfo=timezone.utc)))
        text_all = " ".join(f"{e.get('raw_title') or ''} {e.get('raw_summary') or ''}" for e in es)
        titles = " ".join(e.get("raw_title") or "" for e in es)
        sums = " ".join(e.get("raw_summary") or "" for e in es)
        pubs = [e["_pub"] for e in es if e["_pub"]]
        cols = [e["_col"] for e in es if e["_col"]]
        sev = [parse_severity(e.get("raw_title") or "", e.get("raw_summary") or "") for e in es]
        sev = [s for s in sev if s]
        mins, basis = stated_duration_minutes(sums)
        if mins is None and len(pubs) > 1 and pubs[-1] > pubs[0]:
            mins, basis = int((pubs[-1] - pubs[0]).total_seconds() // 60), "observed_entry_span"
        inc.update(
            provider=provider_of(inc["source"]),
            n_entries=len(es),
            first_pub=min(pubs) if pubs else None,
            last_pub=max(pubs) if pubs else None,
            first_col=min(cols) if cols else None,
            last_col=max(cols) if cols else None,
            schedule=classify_schedule(titles, sums),
            resolved=bool(RESOLVED_MARKERS.search(text_all)),
            severity=max(sev, key=lambda s: SEV_RANK[s]) if sev else None,
            services=sorted(set(parse_services(sums))),
            regions=sorted({m.group(0).lower() for m in REGION_RE.finditer(text_all)})[:8],
            au=au_relevance(titles, sums),
            duration_minutes=mins,
            duration_basis=basis,
            stem=es[0]["_stem"],
        )
        lag = None
        if inc["first_pub"] and inc["first_col"]:
            lag = (inc["first_col"] - inc["first_pub"]).total_seconds() / 3600.0
        inc["collect_lag_h"] = lag
        out.append(inc)
    return out


def detect_backfill_batches(rows, min_rows=BACKFILL_MIN_ROWS):
    """Collected-minute batches with many rows and old publish dates (bulk re-ingest)."""
    buckets = defaultdict(list)
    for r in rows:
        col, pub = parse_ts(r.get("collected_at")), parse_ts(r.get("published_at"))
        if col and pub:
            buckets[(r["source_name"], col.strftime("%Y-%m-%dT%H:%M"))].append((col - pub).total_seconds() / 3600.0)
    batches = {}
    for key, lags in buckets.items():
        if len(lags) >= min_rows and median(lags) > 24:
            batches[key] = {"rows": len(lags), "median_lag_h": round(median(lags), 1)}
    return batches


def collection_profile(rows, as_of, batches, gap_days=10):
    """Per source: gaps between non-backfill collection times, global alive check."""
    cols_all = sorted(c for c in (parse_ts(r.get("collected_at")) for r in rows) if c)
    global_days = {c.date() for c in cols_all}
    prof = {}
    start = as_of - timedelta(days=90)
    for src, items in _by_source(rows).items():
        cols = []
        for r in items:
            c = parse_ts(r.get("collected_at"))
            if c and (src, c.strftime("%Y-%m-%dT%H:%M")) not in batches:
                cols.append(c)
        cols.sort()
        gaps = []
        deltas = [(b - a).total_seconds() / 86400.0 for a, b in pairwise(cols)]
        typical = median(deltas) if len(deltas) >= 10 else None
        floor = max(gap_days, 10 * typical) if typical is not None else None
        for a, b in pairwise(cols):
            if floor is not None and (b - a).days >= floor and b > start:
                alive = sum(1 for d in global_days if a.date() < d < b.date())
                gaps.append({"from": a.date().isoformat(), "to": b.date().isoformat(),
                             "days": (b - a).days, "global_active_days_inside": alive})
        tail = (as_of - cols[-1]).days if cols else None
        prof[src] = {
            "first_collected": cols[0].date().isoformat() if cols else None,
            "last_collected": cols[-1].date().isoformat() if cols else None,
            f"silent_gaps_ge_{gap_days}d": gaps,
            "days_since_last_collect": tail,
        }
    return prof


def _by_source(rows):
    out = defaultdict(list)
    for r in rows:
        out[r["source_name"]].append(r)
    return out


def publication_gaps(incs, as_of, min_incidents=10, floor_days=7, mult=10):
    """Spans (start, end) with no incident published for >> the source's typical interval.

    A silent span is 'unevidenced': it cannot be told apart from missing coverage, so
    rates are also shown per EVIDENCED day. Needs >= min_incidents to judge 'typical'.
    """
    pubs = sorted(i["first_pub"] for i in incs if i["first_pub"])
    if len(pubs) < min_incidents:
        return []
    deltas = [(b - a).total_seconds() / 86400.0 for a, b in pairwise(pubs)]
    limit = max(floor_days, mult * median(deltas))
    spans = [(a, b) for a, b in pairwise(pubs) if (b - a).total_seconds() / 86400.0 >= limit]
    if (as_of - pubs[-1]).total_seconds() / 86400.0 >= limit:
        spans.append((pubs[-1], as_of))
    return spans


def overlap_days(span, window):
    lo, hi = max(span[0], window[0]), min(span[1], window[1])
    return max(0.0, (hi - lo).total_seconds() / 86400.0)


def compare_periods(rows, incidents, as_of, batches, recent_days=30, prior_days=60):
    recent_w, prior_w = windows(as_of, recent_days, prior_days)
    res = {}
    backfill_keys = set(batches)
    for src, items in _by_source(rows).items():
        incs = [i for i in incidents if i["source"] == src]
        gaps = publication_gaps(incs, as_of)
        row = {"unevidenced_spans": [(a.date().isoformat(), b.date().isoformat()) for a, b in gaps]}
        for name, w, days in (("recent", recent_w, recent_days), ("prior", prior_w, prior_days)):
            ent_pub = [r for r in items if in_window(parse_ts(r.get("published_at")), w)]
            ent_col = [r for r in items if in_window(parse_ts(r.get("collected_at")), w)]
            bf_rows = [
                r for r in ent_col
                if (src, parse_ts(r["collected_at"]).strftime("%Y-%m-%dT%H:%M")) in backfill_keys
            ]
            inc_pub = [i for i in incs if in_window(i["first_pub"], w)]
            contemporaneous = [i for i in inc_pub if i["collect_lag_h"] is not None and i["collect_lag_h"] <= 48]
            unplanned = [i for i in inc_pub if i["schedule"] == "unplanned"]
            unev = min(days - 1, sum(overlap_days(g, w) for g in gaps))
            evid = max(days - unev, 1)
            row[name] = {
                "days": days,
                "unevidenced_days": round(unev, 1),
                "incidents_per_30d_evidenced": round(len(inc_pub) * 30.0 / evid, 2),
                "entries_published_basis": len(ent_pub),
                "entries_collected_basis": len(ent_col),
                "entries_in_backfill_batches_collected_basis": len(bf_rows),
                "distinct_incidents": len(inc_pub),
                "distinct_unplanned_incidents": len(unplanned),
                "distinct_incidents_collected_contemporaneously": len(contemporaneous),
                "incidents_per_30d": round(len(inc_pub) * 30.0 / days, 2),
                "entries_per_incident": round(len(ent_pub) / len(inc_pub), 2) if inc_pub else None,
                "au_strong": sum(1 for i in inc_pub if i["au"] == "strong"),
                "au_weak": sum(1 for i in inc_pub if i["au"] == "weak"),
                "median_duration_min": median([i["duration_minutes"] for i in inc_pub
                                               if i["duration_minutes"] is not None and i["schedule"] == "unplanned"]),
                "resolved_share": round(sum(1 for i in inc_pub if i["resolved"]) / len(inc_pub), 2) if inc_pub else None,
            }
        res[src] = row
    return res


def flag_sources(comparison, profile, batches, ratio=2.0):
    flags = defaultdict(list)
    for (src, minute), info in batches.items():
        flags[src].append(f"backfill batch at {minute}Z: {info['rows']} rows, median publish-to-collect lag {info['median_lag_h']}h")
    for src, p in profile.items():
        for g in p.get("silent_gaps_ge_10d", []):
            flags[src].append(
                f"no non-backfill collection {g['from']} to {g['to']} ({g['days']}d; other sources collected on "
                f"{g['global_active_days_inside']} of those days)"
            )
    for src, c in comparison.items():
        if c["unevidenced_spans"]:
            flags[src].append("published-time gaps with no incidents (possible missing coverage): "
                              + ", ".join(f"{a}..{b}" for a, b in c["unevidenced_spans"][:4]))
        rec, pri = c["recent"], c["prior"]
        rate_r, rate_p = rec["entries_published_basis"] / rec["days"], pri["entries_published_basis"] / pri["days"]
        if rate_p > 0 and (rate_r / rate_p >= ratio or rate_r / rate_p <= 1 / ratio):
            flags[src].append(f"entry-rate ratio recent/prior = {rate_r / rate_p:.2f} (published basis)")
        elif rate_p == 0 and rate_r > 0 or rate_r == 0 and rate_p > 0:
            flags[src].append("entries present in only one comparison window (published basis)")
    return dict(flags)


def focus_verdict(src, comparison, flags):
    """Plain-language answer to: entry-rate change or distinct-incident change?"""
    c = comparison.get(src)
    if not c:
        return [f"[{OBSERVED}] no rows for {src}"]
    rec, pri = c["recent"], c["prior"]
    lines = []
    lines.append(
        f"[{OBSERVED}] {src}, collected_at basis: {rec['entries_collected_basis']} entries in last {rec['days']}d vs "
        f"{pri['entries_collected_basis']} in prior {pri['days']}d; of the recent ones "
        f"{rec['entries_in_backfill_batches_collected_basis']} were ingested in bulk backfill batches."
    )
    lines.append(
        f"[{OBSERVED}] {src}, published_at basis: {rec['entries_published_basis']} entries vs {pri['entries_published_basis']}; "
        f"distinct incidents {rec['distinct_incidents']} vs {pri['distinct_incidents']} "
        f"({rec['incidents_per_30d']} vs {pri['incidents_per_30d']} per 30d); entries per incident "
        f"{rec['entries_per_incident']} vs {pri['entries_per_incident']}."
    )
    lines.append(
        f"[{OBSERVED}] incidents collected within 48h of publication: {rec['distinct_incidents_collected_contemporaneously']} "
        f"recent vs {pri['distinct_incidents_collected_contemporaneously']} prior."
    )
    for f in flags.get(src, []):
        lines.append(f"[{OBSERVED}] collection flag: {f}")
    lines.append(
        f"[{OBSERVED}] unevidenced days (no incident published for far longer than the source's typical interval): "
        f"{rec['unevidenced_days']} of {rec['days']} recent, {pri['unevidenced_days']} of {pri['days']} prior; "
        f"incidents per 30 EVIDENCED days {rec['incidents_per_30d_evidenced']} vs {pri['incidents_per_30d_evidenced']}."
    )
    inc_r, inc_p = rec["incidents_per_30d_evidenced"], pri["incidents_per_30d_evidenced"]
    backfilled = rec["entries_in_backfill_batches_collected_basis"] > 0 or bool(flags.get(src))
    if backfilled:
        lines.append(
            f"[{PLAUSIBLE}] the raw entry 'increase' is at least partly a collection artefact (bulk backfill and/or a "
            f"collection gap), not evidence that incident frequency changed; per evidenced day the distinct-incident "
            f"rate is {inc_r} vs {inc_p} per 30d, and the prior window's coverage is incomplete, so a real change "
            f"cannot be established either way."
        )
    elif inc_p and inc_r / inc_p >= 1.5:
        lines.append(f"[{PLAUSIBLE}] distinct incidents per 30 evidenced days rose ({inc_r} vs {inc_p}).")
    else:
        lines.append(f"[{PLAUSIBLE}] distinct incidents per 30d are similar ({inc_r} vs {inc_p}).")
    lines.append(
        f"[{HYPOTHESIS}] any claim about why incident counts differ (provider change, load, release activity) "
        "is not testable from this data."
    )
    return lines


def is_status_source(name: str) -> bool:
    return bool(re.search(r"status|service health", name or "", re.IGNORECASE))


def analyse(rows, as_of, recent_days=30, prior_days=60):
    rows = [r for r in rows if is_status_source(r.get("source_name"))]
    incidents = build_incidents(rows)
    batches = detect_backfill_batches(rows)
    comparison = compare_periods(rows, incidents, as_of, batches, recent_days, prior_days)
    profile = collection_profile(rows, as_of, batches)
    flags = flag_sources(comparison, profile, batches)
    return {"incidents": incidents, "batches": batches, "comparison": comparison, "profile": profile, "flags": flags}


def render_markdown(result, as_of, focus=None, min_entries=15):
    comp, flags = result["comparison"], result["flags"]
    out = ["# P1 recurring provider failure analysis (prototype, non-production)", "", LABEL_LEGEND, ""]
    out.append(f"As-of: {as_of.isoformat()} | recent = 30d, prior = 60d | unit = DISTINCT INCIDENT (entries shown for contrast)")
    out += ["", "## What this adds beyond the intelligence brief", "",
            ("The brief lists entries/events. This report collapses updates into incidents, separates scheduled "
             "maintenance from unplanned incidents, and shows whether a rise is a rise in incidents or in collection volume."), ""]
    if focus:
        out += [f"## Focus: {focus}", ""]
        out += [f"- {line}" for line in focus_verdict(focus, comp, flags)]
        out.append("")
    out += ["## Per provider: distinct incidents, last 30d vs prior 60d (published_at basis)", "",
            "| Source | Entries 30d | Entries 60d | Incidents 30d | Incidents 60d | /30d recent | /30d prior (raw) | Unplanned 30d | Unplanned 60d | AU-strong 30d | AU-strong 60d | Flags |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for src, c in sorted(comp.items(), key=lambda kv: -(kv[1]["recent"]["entries_published_basis"] + kv[1]["prior"]["entries_published_basis"])):
        r, p = c["recent"], c["prior"]
        if r["entries_published_basis"] + p["entries_published_basis"] + r["entries_collected_basis"] + p["entries_collected_basis"] == 0:
            continue
        if r["entries_published_basis"] + p["entries_published_basis"] < min_entries and src not in flags and src != focus:
            continue
        out.append(
            f"| {src} | {r['entries_published_basis']} | {p['entries_published_basis']} | {r['distinct_incidents']} | "
            f"{p['distinct_incidents']} | {r['incidents_per_30d']} | {p['incidents_per_30d']} | {r['distinct_unplanned_incidents']} | "
            f"{p['distinct_unplanned_incidents']} | {r['au_strong']} | {p['au_strong']} | {len(flags.get(src, []))} |"
        )
    out += ["", "## Sources whose collection cadence or consistency changed", ""]
    shown = False
    for src, fl in sorted(flags.items()):
        c = comp.get(src)
        if not c or (c["recent"]["entries_published_basis"] + c["prior"]["entries_published_basis"]
                     + c["recent"]["entries_collected_basis"] + c["prior"]["entries_collected_basis"]) == 0:
            continue
        shown = True
        out.append(f"- **{src}**")
        out += [f"  - [{OBSERVED}] {f}" for f in fl]
    if not shown:
        out.append("- none")
    out += ["", "## Limits", "",
            ("- A status feed with no rows cannot be told apart from 'no incidents' without an independent liveness signal; "
             "gaps are only flagged when other sources were collected during the gap."),
            ("- Incident identity relies on URL ids and title+minute matching; two different incidents with identical title "
             "and minute would merge, and an update with a changed title would not."),
            "- Severity, duration and region fields are parsed from text where present; absent fields are absent, not zero.",
            "- Counts are of REPORTED incidents; provider size and reporting practice differ, so counts are not a reliability ranking.",
            f"- [{HYPOTHESIS}] causes of any change in incident frequency are not inferred.", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="JSONL export of status-feed events")
    ap.add_argument("--as-of", default=None, help="ISO timestamp; default = latest collected_at in the input")
    ap.add_argument("--focus", default=None, help="source_name to report a verdict for, e.g. 'GitHub Status'")
    ap.add_argument("--out", default=None)
    ap.add_argument("--format", choices=["md", "json"], default="md")
    args = ap.parse_args(argv)
    rows = load_jsonl(args.input)
    as_of = parse_ts(args.as_of) if args.as_of else max(parse_ts(r.get("collected_at")) for r in rows if r.get("collected_at"))
    result = analyse(rows, as_of)
    if args.format == "json":
        payload = {k: v for k, v in result.items() if k != "incidents"}
        payload["batches"] = {f"{k[0]}|{k[1]}": v for k, v in result["batches"].items()}
        text = json.dumps(payload, indent=2, default=str)
    else:
        text = render_markdown(result, as_of, args.focus)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
