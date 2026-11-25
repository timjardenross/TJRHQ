"""Weekly 'forward watch' generator (OFFLINE, default OFF, not wired).

Lists KNOWN, dated, future events that sources in the export state explicitly: provider planned maintenance,
regulator or operator dates, vendor end-of-life or enforcement dates. It never predicts. Every item carries:

  - a stated basis (the source's own words, quoted, plus where the date came from),
  - a date (only explicit dates with a year; nothing is inferred from 'next week' or a bare weekday),
  - an uncertainty label from a fixed vocabulary,
  - event id and source for audit.

Source authority tiers decide what is listed as an item:
  PRIMARY_PROVIDER   provider's own status feed (planned maintenance, enforcement dates in lifecycle notices)
  PRIMARY_OFFICIAL   regulator, market operator, standards or government security body
  SECONDARY          news and other relays: listed separately, labelled RELAYED_BY_NEWS, never as confirmed

Uncertainty labels:
  SCHEDULED_BY_OWNER   owner published its own window; can be moved or cancelled
  OFFICIAL_DATE_STATED regulator/operator states the date; subject to amendment
  RELAYED_BY_NEWS      secondary report of a date; not checked against the primary source
  DATE_PRECISION_MONTH only a month is stated
  DATE_NOT_STATED      a planned event is announced but the export gives no date

A later row for the same notice that says completed/cancelled removes the item; only the latest row per notice counts.

Fifth input, 'Dated events' (flag-gated, default OFF): with --dated-events (or INTEL_DATED_EVENTS_ENABLED=1) the deterministic
extractor in dated_events.py also reads the same rows and its upcoming events (regulatory dates, vendor lifecycle dates,
planned maintenance, advisory deadlines; stated year or labelled inferred) are listed in a 'Dated events' section. Without the
flag the output is byte-for-byte the original.

Usage:
    python forward_watch.py --enable --input a.jsonl --input b.jsonl --as-of 2026-11-24 --horizon-days 42 --out watch.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analytics_common import HYPOTHESIS, OBSERVED, parse_ts
from product_common import clean_text, load_rows, md_cell, require_enabled, short
from provider_failure import url_incident_id

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ],
        1,
    )
}
_MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DMY = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON}\.?,?\s+(\d{{4}})\b", re.IGNORECASE
)
MDY = re.compile(
    rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE
)
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MY = re.compile(rf"\b{_MON}\s+(\d{{4}})\b", re.IGNORECASE)
TIME_AFTER = re.compile(
    r"^[,\s]*(?:at\s+|from\s+)?(\d{1,2}:\d{2})(?::\d{2})?\s*([A-Z]{3,4})?"
)

CUES = [
    (
        "maintenance",
        re.compile(
            r"scheduled (?:event|maintenance)|planned (?:maintenance|outage)|maintenance window|status:\s*scheduled|\bmaintenance\b",
            re.IGNORECASE,
        ),
    ),
    (
        "deadline",
        re.compile(
            r"deadline|due (?:by|on|date)|closes?\b|closing|submissions?\b|consultation",
            re.IGNORECASE,
        ),
    ),
    (
        "lifecycle",
        re.compile(
            r"end[- ]of[- ](?:life|support|service|sale)|\bEOL\b|deprecat|retire|sunset|discontinu|minimum version|enforc",
            re.IGNORECASE,
        ),
    ),
    (
        "regulatory_effective",
        re.compile(
            r"come[s]? into (?:force|effect)|effective (?:from|on|date)|commenc|mandatory from|apply(?:ing)? from",
            re.IGNORECASE,
        ),
    ),
]
DROP = re.compile(
    r"\(completed\)|\(resolved\)|\bcompleted\b|\bcancel+ed\b|\bresolved\b",
    re.IGNORECASE,
)
STEM_STRIP = re.compile(
    r"^(?:rescheduled|update|reminder|maintenance|completed|cancel+ed|initial)\s*(?::|-|\u2013)\s*|\s*\([a-z ]+\)\s*$",
    re.IGNORECASE,
)

PRIMARY_PROVIDER = re.compile(r"status|service health", re.IGNORECASE)
PRIMARY_OFFICIAL = re.compile(
    r"\bAEMO\b|\bAEMC\b|\bAER\b|APRA|\bASIC\b|AUSTRAC|\bRBA\b|Reserve Bank|OAIC|Treasury|Home Affairs|\bACSC\b|"
    r"\bCISA\b|\bNCSC\b|ENISA|\bFSB\b|\bBIS\b|\bNIST\b|\bMSRC\b|Security Bulletins?|Security Response|Federal Register|Gazette",
    re.IGNORECASE,
)
EXCLUDED_SOURCES = re.compile(
    r"NVD|Known Exploited", re.IGNORECASE
)  # CVE feeds: no scheduled-event semantics in these rows

LABEL_NOTES = {
    "SCHEDULED_BY_OWNER": "owner-published window; can be moved or cancelled",
    "OFFICIAL_DATE_STATED": "official source states the date; subject to amendment",
    "RELAYED_BY_NEWS": "secondary report; not checked against the primary source",
    "DATE_PRECISION_MONTH": "only the month is stated",
    "DATE_NOT_STATED": "planned event announced, no date in the export",
}


def tier(source_name):
    s = source_name or ""
    if EXCLUDED_SOURCES.search(s):
        return None
    if PRIMARY_PROVIDER.search(s):
        return "PRIMARY_PROVIDER"
    if PRIMARY_OFFICIAL.search(s):
        return "PRIMARY_OFFICIAL"
    return "SECONDARY"


def find_dates(text):
    """[(date, start, end, precision)] for explicit dates with a year, in text order."""
    out = []
    for m in DMY.finditer(text):
        out.append(
            (
                date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1))),
                m.start(),
                m.end(),
                "day",
            )
        )
    for m in MDY.finditer(text):
        out.append(
            (
                date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2))),
                m.start(),
                m.end(),
                "day",
            )
        )
    for m in ISO.finditer(text):
        try:
            out.append(
                (
                    date(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                    m.start(),
                    m.end(),
                    "day",
                )
            )
        except ValueError:
            pass
    covered = [(s, e) for _, s, e, _ in out]
    for m in MY.finditer(text):
        if any(s <= m.start() < e for s, e in covered):
            continue
        out.append(
            (
                date(int(m.group(2)), MONTHS[m.group(1)[:3].lower()], 1),
                m.start(),
                m.end(),
                "month",
            )
        )
    return sorted(out, key=lambda d: d[1])


def cue_type(window):
    for name, rx in CUES:
        if rx.search(window):
            return name
    return None


def _stem(row):
    """Notice identity: the source's incident id (from the notice URL) when it has one, else the title stem.

    Titles are reused across distinct notices (e.g. one 'SMS and MMS Maintenance' headline for several dates),
    so the title is only a fallback; an update then replaces its own notice, not a sibling's.
    """
    ident = url_incident_id(row.get("canonical_url"))
    if ident:
        return (row.get("source_name"), "id:" + ident[0] + ":" + ident[1])
    t = clean_text(row.get("raw_title"))
    prev = None
    while prev != t:
        prev, t = t, STEM_STRIP.sub("", t).strip()
    return (row.get("source_name"), re.sub(r"[^a-z0-9]+", " ", t.lower()).strip())


def latest_per_notice(rows):
    """Latest row per (source, incident id from URL, else normalised title stem).

    A row with no published_at (several regulator and scrape feeds) is ordered by its collected_at, so a later 'Completed' or
    'Cancelled' notice with no publication date still retires the earlier notice instead of being invisible.
    """
    best = {}
    for r in rows:
        p = parse_ts(r.get("published_at")) or parse_ts(r.get("collected_at"))
        if p is None:
            continue
        k = _stem(r)
        if k not in best or p >= best[k][0]:
            best[k] = (p, r)
    return [v[1] for v in best.values()]


def extract_items(rows, as_of, horizon_days=42):
    today = as_of.date()
    last = today + timedelta(days=horizon_days)
    items, undated, later = [], [], 0
    for r in latest_per_notice(rows):
        t = tier(r.get("source_name"))
        if t is None:
            continue
        title, summary = (
            clean_text(r.get("raw_title")),
            clean_text(r.get("raw_summary")),
        )
        text = f"{title}. {summary}" if summary else title
        if DROP.search(title) or re.search(
            r"\bhas been completed\b|\bwork is complete", summary, re.IGNORECASE
        ):
            continue
        title_cue = cue_type(title)
        picked = None
        for d, s, e, prec in find_dates(text):
            kind = cue_type(text[max(0, s - 160) : e + 160]) or title_cue
            if kind is None or d <= today:
                continue
            if d > last:
                later += 1
                break
            picked = (d, s, e, prec, kind)
            break
        if picked is None:
            if (
                t == "PRIMARY_OFFICIAL"
                and re.search(
                    r"planned maintenance|scheduled maintenance", text, re.IGNORECASE
                )
                and not find_dates(text)
            ):
                undated.append({"row": r, "tier": t, "text": text})
            continue
        d, s, e, prec, kind = picked
        tm = TIME_AFTER.match(text[e : e + 30])
        when = d.isoformat() + (
            f" {tm.group(1)} {tm.group(2) or 'time zone as stated'}"
            if tm and prec == "day"
            else ""
        )
        if prec == "month":
            label = "DATE_PRECISION_MONTH"
        elif t == "PRIMARY_PROVIDER" and kind == "maintenance":
            label = "SCHEDULED_BY_OWNER"
        elif t == "SECONDARY":
            label = "RELAYED_BY_NEWS"
        else:
            label = "OFFICIAL_DATE_STATED"
        quote = text[max(0, s - 70) : e + 70]
        if s > 70:
            quote = quote.split(" ", 1)[-1]  # start on a word boundary
        quote = quote.strip()
        basis = {
            "PRIMARY_PROVIDER": "provider's own status feed",
            "PRIMARY_OFFICIAL": "official source feed",
            "SECONDARY": "news or other relay (not authoritative)",
        }[t]
        items.append(
            {
                "row": r,
                "tier": t,
                "date": d,
                "when": when,
                "precision": prec,
                "kind": kind,
                "label": label,
                "basis": f"{basis}; date read from text; cue type '{kind}'",
                "quote": quote,
            }
        )
    items.sort(
        key=lambda i: (
            i["date"],
            i["row"].get("source_name") or "",
            i["row"].get("event_id") or "",
        )
    )
    return items, undated, later


def _monday(d):
    return d - timedelta(days=d.weekday())


def dated_events_input(rows, as_of, horizon_days, items):
    """Fifth input: upcoming events from the dated-events extractor, minus any already listed as an item above."""
    import dated_events as de

    listed = {(i["row"].get("event_id"), i["date"].isoformat()) for i in items}

    def already_listed(e):
        # A multi-day window the item list already carries (for example item date 25 Nov, window 24 to 25 Nov) is one event.
        lo, hi = e["date"], e.get("end_date") or e["date"]
        return any(eid == e["event_id"] and lo <= d <= hi for eid, d in listed)

    evs = de.upcoming(
        de.latest_per_notice(de.extract_events(rows)), as_of, horizon_days
    )
    return [e for e in evs if not already_listed(e)]


def render(items, undated, later, as_of, horizon_days, n_rows, source_note, dated=None):
    today = as_of.date()
    primary = [i for i in items if i["tier"] != "SECONDARY"]
    secondary = [i for i in items if i["tier"] == "SECONDARY"]
    kinds = {k: sum(1 for i in primary if i["kind"] == k) for k, _ in CUES}
    off = [i for i in primary if i["tier"] == "PRIMARY_OFFICIAL"]
    out = [
        f"# Forward watch, generated {today.isoformat()} (horizon {horizon_days} days to {today + timedelta(days=horizon_days)})",
        "",
        f"Source: {source_note}. {n_rows} rows read. Generated by the scheduled read-only refresh; nothing is sent.",
        "",
        (
            "This lists dated events that sources state explicitly. It is not a forecast: nothing here predicts an outage, "
            "a regulatory decision or a vendor action. Dates come from the source text; no date is inferred. A scheduled "
            "item can still be moved or cancelled, and each carries an uncertainty label."
        ),
        "",
        "Uncertainty labels: "
        + "; ".join(f"**{k}** = {v}" for k, v in LABEL_NOTES.items())
        + ".",
        "",
        "## Coverage",
        "",
        f"- [{OBSERVED}] Authoritative items in horizon: {len(primary)} "
        + "("
        + ", ".join(f"{k} {v}" for k, v in kinds.items())
        + f"); from official/regulator sources: {len(off)}.",
        f"- [{OBSERVED}] Secondary (news) items with an explicit future date: {len(secondary)}. Dated items beyond the horizon: {later}.",
        f"- [{OBSERVED}] Planned events with no stated date (official sources): {len(undated)}.",
    ]
    if not off:
        out.append(
            "- No regulator consultation deadline, regulator effective date, vendor end-of-life notice or AEMO forward "
            "notice with an explicit future date was found in this export. That is a statement about the export, not "
            "about the world: the feeds may not carry such items, or may state them without a year."
        )
    out += ["", "## Authoritative items by week", ""]
    if not primary:
        out += ["None found.", ""]
    by_week = {}
    for i in primary:
        by_week.setdefault(_monday(i["date"]), []).append(i)
    for wk in sorted(by_week):
        out += [
            f"### Week commencing {wk.isoformat()}",
            "",
            "| Date | Source | Item | Basis and quote | Uncertainty | Event id |",
            "|---|---|---|---|---|---|",
        ]
        for i in by_week[wk]:
            r = i["row"]
            out.append(
                f"| {i['when']} | {md_cell(r.get('source_name'))} | {md_cell(short(r.get('raw_title'), 80))} | "
                f'{md_cell(i["basis"])}: "{md_cell(short(i["quote"], 150))}" | {i["label"]} | `{r.get("event_id")}` |'
            )
        out.append("")
    if dated is not None:
        out += _render_dated(dated)
    out += ["## Announced but undated (official sources)", ""]
    if undated:
        out += ["| Source | Item | Uncertainty | Event id |", "|---|---|---|---|"]
        for u in undated:
            r = u["row"]
            out.append(
                f"| {md_cell(r.get('source_name'))} | {md_cell(short(r.get('raw_title'), 100))} | DATE_NOT_STATED | `{r.get('event_id')}` |"
            )
    else:
        out.append("None.")
    out += ["", "## Relayed by news (not authoritative, not confirmed)", ""]
    if secondary:
        out += [
            "| Date | Source | Item | Quote | Uncertainty | Event id |",
            "|---|---|---|---|---|---|",
        ]
        for i in secondary:
            r = i["row"]
            out.append(
                f"| {i['when']} | {md_cell(r.get('source_name'))} | {md_cell(short(r.get('raw_title'), 80))} | "
                f'"{md_cell(short(i["quote"], 150))}" | {i["label"]} | `{r.get("event_id")}` |'
            )
    else:
        out.append("None.")
    out += [
        "",
        "## Limits",
        "",
        "- Only explicit dates with a year are read. 'Next Tuesday', 'Q1' and bare 'Dec 8' are ignored, so real events can be missed.",
        "- Times are copied as the source states them (zone as written); this tool does not convert zones.",
        (
            "- Cue words decide whether a date is a planned event. A date inside an unrelated sentence near a cue can be picked up; "
            "read the quote."
        ),
        "- CVE/KEV feeds are excluded: their rows carry no scheduled-event dates (KEV due dates are not in the export).",
        f"- [{HYPOTHESIS}] Whether a listed window will cause customer impact is not assessed.",
        "",
    ]
    return "\n".join(out)


def _render_dated(dated):
    out = [
        "## Dated events (extractor, flag-gated)",
        "",
        (
            "Events read by the deterministic dated-events extractor from the same rows, not already listed above. "
            "Only dates the text states count; a year taken from the publication date is labelled INFERRED_YEAR and a "
            "relative date RELATIVE_DATE_LOWER_CONFIDENCE. Kinds: regulatory, vendor_lifecycle, planned_maintenance, "
            "advisory_deadline."
        ),
        "",
    ]
    if not dated:
        return out + ["None in the horizon.", ""]
    out += [
        "| Date | Kind | Source | Item | Basis and evidence | Uncertainty | Event id |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in dated:
        when = e["date"] + (f" to {e['end_date']}" if e.get("end_date") else "")
        out.append(
            f"| {when} | {e['kind']} | {md_cell(e['source'])} | {md_cell(short(e['event'], 80))} | "
            f'{md_cell(e["date_basis"])}: "{md_cell(short(e["evidence_span"], 150))}" | {e["uncertainty_label"]} | `{e["event_id"]}` |'
        )
    return out + [""]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--horizon-days", type=int, default=42)
    ap.add_argument("--out", default=None)
    ap.add_argument("--source-note", default="events export (read-only SELECT)")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument(
        "--dated-events",
        action="store_true",
        help="add the fifth input: upcoming events from dated_events.py (or INTEL_DATED_EVENTS_ENABLED=1)",
    )
    args = ap.parse_args(argv)
    if not require_enabled(args.enable):
        return 2
    rows = load_rows(args.input)
    as_of = (
        parse_ts(args.as_of if "T" in args.as_of else args.as_of + "T00:00:00Z")
        if args.as_of
        else datetime.now(timezone.utc)
    )
    items, undated, later = extract_items(rows, as_of, args.horizon_days)
    dated = None
    if args.dated_events or os.environ.get("INTEL_DATED_EVENTS_ENABLED", "0") == "1":
        dated = dated_events_input(rows, as_of, args.horizon_days, items)
    text = render(
        items,
        undated,
        later,
        as_of,
        args.horizon_days,
        len(rows),
        args.source_note,
        dated,
    )
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
