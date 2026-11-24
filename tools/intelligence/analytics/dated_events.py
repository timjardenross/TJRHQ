"""Deterministic extractor of dated FUTURE events from items we already collect (OFFLINE, default OFF, not wired).

Only dates the source text states count. Output record (one per event):

    event            short title of the source item
    date             ISO date of the event (start date for a window)
    date_basis       'stated explicit year' | 'inferred from publication context'
    source           source_name of the row
    evidence_span    the source text around the date (quoted, never paraphrased)
    kind             regulatory | vendor_lifecycle | planned_maintenance | advisory_deadline
    uncertainty_label  fixed vocabulary, see LABELS
    (also: event_id, published_at, time, end_date, precision, tier)

Rules (no model, no network, no inference beyond these):
  - 'Future' means strictly after the item's own publication date. Dates inside "Revised on", "Published:", "Updated:" and
    similar are never events. Past-tense phrasing ("started operating from") is not an event.
  - A date needs a kind cue (maintenance, end of life, closes, comes into effect, will publish ...) in the same clause. No cue, no event.
  - Year-less dates ("on 20 November") take the first such date on or after the publication date and are labelled INFERRED_YEAR.
  - Relative dates ('tomorrow', 'next Tuesday', 'next week') resolve only against the row's own publication date, only when that date is
    verified (not an aggregator, not later than collection), and are labelled RELATIVE_DATE_LOWER_CONFIDENCE.
  - Numeric dates: D/M/YYYY for Australian official sources; M/D/YYYY only when the day is above 12; an ambiguous numeric date from
    any other source is skipped.
  - News and other relays are not authoritative and are skipped unless include_news=True (then labelled RELAYED_BY_NEWS).
  - A later cancellation notice from the same source that matches an earlier forecast (same date, same salient tokens) removes it.
  - Dates are compared with the UTC publication date; a same-local-day item can be classed future when UTC and local days differ.

Usage:
    python dated_events.py --enable --input export.jsonl --as-of 2026-11-24 --horizon-days 30 --out events.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analytics_common import parse_ts
from product_common import clean_text, load_rows

ENABLE_ENV = "INTEL_DATED_EVENTS_ENABLED"

KINDS = ("regulatory", "vendor_lifecycle", "planned_maintenance", "advisory_deadline")
LABELS = {
    "SCHEDULED_BY_OWNER": "provider published its own window; can be moved or cancelled",
    "OFFICIAL_DATE_STATED": "regulator, operator or vendor states the date; subject to amendment",
    "OPERATOR_FORECAST": "market operator forecast for a date; it is a forecast, not a commitment",
    "INFERRED_YEAR": "year not stated; taken from the publication date (lower confidence)",
    "RELATIVE_DATE_LOWER_CONFIDENCE": "relative wording resolved against the publication date (lower confidence)",
    "DATE_PRECISION_MONTH": "only the month is stated",
    "RELAYED_BY_NEWS": "secondary report; not checked against the primary source",
}

BASIS_EXPLICIT = "stated explicit year"
BASIS_INFERRED = "inferred from publication context"

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
# Year-less forms need a capitalised month (no re.I) so that "may 5" or "march 2" in prose is not read as a date.
DMY = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON}\.?,?\s+(\d{{4}})\b", re.IGNORECASE
)
MDY = re.compile(
    rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE
)
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUM = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])")
MONTH_YEAR = re.compile(rf"\b{_MON}\s+(\d{{4}})\b", re.IGNORECASE)
_CAP_MONTH = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"
DM_NOYEAR = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_CAP_MONTH}\b(?!\.?,?\s*\d{{4}})"
)
MD_NOYEAR = re.compile(
    rf"\b{_CAP_MONTH}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!\s*,?\s*\d{{4}})(?!\d)"
)
WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
REL = re.compile(
    r"\b(tomorrow|tonight|this weekend|next week|next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
    re.IGNORECASE,
)
TIME_AFTER = re.compile(
    r"^[,\s]*(?:at\s+|from\s+)?(\d{1,2}:\d{2})(?::\d{2})?\s*([A-Z]{3,4})?"
)
RANGE_WORDS = {
    "at", "from", "until", "till", "through", "to", "am", "pm", "and", "between",
    *WEEKDAYS, *(w[:3] for w in WEEKDAYS),
}  # fmt: skip


def is_range_gap(gap):
    """True when the text between two dates only links them as a window ('until', '-', a time, a time zone, a weekday)."""
    if (
        len(gap) > 45
        or ". " in gap
        or not re.search(r"\b(?:until|till|through|to)\b|[-–—]", gap)
    ):
        return False
    return all(
        w.lower() in RANGE_WORDS or (w.isupper() and 2 <= len(w) <= 5)
        for w in re.findall(r"[A-Za-z]+", gap)
    )


# Dates that label the item itself, not an upcoming event.
LABEL_BEFORE = re.compile(
    r"(?:revised|updated|published|released|created|modified|last updated|posted|added|issued|as of|first published)\b[^.]{0,12}$",
    re.IGNORECASE,
)
PAST_BEFORE = re.compile(
    r"(?:started|ceased|stopped|began|was|were|has been|have been|had been|became|completed|resolved)\s+(?:operating\s+)?(?:from|on|at|since)?\s*$",
    re.IGNORECASE,
)

CUES = [
    (
        "planned_maintenance",
        re.compile(
            r"scheduled (?:event|maintenance|downtime)|planned (?:maintenance|outage|downtime)|(?:emergency|upstream provider) maintenance|"
            r"maintenance window|performing maintenance|conducting a (?:planned|emergency) maintenance|will be (?:unavailable|offline|disrupted)|"
            r"\bmaintenance\b",
            re.IGNORECASE,
        ),
    ),
    (
        "vendor_lifecycle",
        re.compile(
            r"end[- ]of[- ](?:life|support|service|sale|maintenance)|\bEOL\b|\bEOS\b|reaches end of|deprecat|retire|sunset|discontinu|"
            r"no longer (?:be )?(?:supported|available)|decommission|requirement also applies|will be required|enforcement|"
            r"minimum (?:version|tls)|must (?:be )?(?:migrat|upgrad)",
            re.IGNORECASE,
        ),
    ),
    (
        "advisory_deadline",
        re.compile(
            r"due (?:by|on|date)|deadline|remediat\w* (?:by|before)|patch (?:by|before)|apply (?:the )?(?:update|patch|mitigation)s? by|"
            r"will (?:publish|disclose|release)|next planned publication|(?:set|scheduled|planned) for (?:public )?(?:disclosure|release)|"
            r"advance notification|public disclosure",
            re.IGNORECASE,
        ),
    ),
    (
        "regulatory",
        re.compile(
            r"consultation (?:closes?|closing|period|ends?)|consultation is (?:now )?open,? until|open,? until|no later than|"
            r"requested to be provided|submissions? (?:close|closes|due|must|by)|closes?\b|closing date|"
            r"comes? into (?:force|effect)|come into (?:force|effect)|take[s]? effect|commenc\w+|effective (?:from|on|date)|"
            r"mandatory from|apply(?:ing)? from|transition(?:al)? (?:period )?(?:ends?|until)|compliance date|"
            r"final (?:rules?|standards?) (?:will|to) ",
            re.IGNORECASE,
        ),
    ),
]

# AEMO notices that name a future date for a forecast condition or a planned network change.
AEMO_FORECAST = re.compile(
    r"\bForecast\b|\bSTPASA\b|\bPDPASA\b|Inter-regional transfer limit variation|Possible intervention|Foreseeable|"
    r"Network Augmentation|Interconnector Registered|\bLack Of Reserve\b",
    re.IGNORECASE,
)
CANCEL = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)?(?:STPASA\s*-\s*|PDPASA\s*-?\s*)?Cancellation\b",
    re.IGNORECASE,
)

AU_OFFICIAL = re.compile(
    r"\bAEMO\b|\bAEMC\b|\bAER\b|APRA|\bASIC\b|AUSTRAC|\bRBA\b|Reserve Bank|OAIC|Treasury|Home Affairs|\bACSC\b|Council of Financial|"
    r"\bATO\b|Australian Taxation",
    re.IGNORECASE,
)
OFFICIAL = re.compile(
    AU_OFFICIAL.pattern
    + r"|\bCISA\b|\bNCSC\b|ENISA|\bFSB\b|\bBIS\b|\bNIST\b|Federal Register|Gazette",
    re.IGNORECASE,
)
VENDOR = re.compile(
    r"Cisco|MSRC|Microsoft Security|Google Cloud|Fortinet|Palo Alto|Security Bulletins?|Security Advisor|PSIRT|Security Response",
    re.IGNORECASE,
)
PROVIDER = re.compile(r"status|service health", re.IGNORECASE)
EXCLUDED = re.compile(
    r"NVD|Known Exploited", re.IGNORECASE
)  # KEV rows carry no due date in our export
AGGREGATOR = re.compile(r"google news", re.IGNORECASE)


def enabled(flag=False):
    return bool(flag) or os.environ.get(ENABLE_ENV, "0") == "1"


def tier(source_name):
    s = source_name or ""
    if EXCLUDED.search(s):
        return None
    if PROVIDER.search(s):
        return "PROVIDER"
    if OFFICIAL.search(s):
        return "OFFICIAL"
    if VENDOR.search(s):
        return "VENDOR"
    return "NEWS"


def _mk(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text, pub, au_numeric, infer_year=True):
    """[(date, start, end, precision, basis)] for stated dates, in text order. Overlapping matches keep the most explicit."""
    out = []

    def add(dt, m, prec="day", basis=BASIS_EXPLICIT):
        if dt is not None:
            out.append((dt, m.start(), m.end(), prec, basis))

    for m in DMY.finditer(text):
        add(_mk(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1))), m)
    for m in MDY.finditer(text):
        add(_mk(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2))), m)
    for m in ISO.finditer(text):
        add(_mk(int(m.group(1)), int(m.group(2)), int(m.group(3))), m)
    for m in NUM.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:
            add(_mk(y, b, a), m)
        elif b > 12 and a <= 12:
            add(_mk(y, a, b), m)
        elif a <= 12 and b <= 12 and au_numeric:
            add(_mk(y, b, a), m)
    covered = [(s, e) for _, s, e, _, _ in out]

    def free(m):
        return not any(s <= m.start() < e or s < m.end() <= e for s, e in covered)

    for m in MONTH_YEAR.finditer(text):
        if free(m):
            add(_mk(int(m.group(2)), MONTHS[m.group(1)[:3].lower()], 1), m, "month")
    covered = [(s, e) for _, s, e, _, _ in out]

    def infer(month, day, m):
        # Year-less: this year if the date has not passed; next year only when that is within 120 days (e.g. a December item
        # naming 10 January). A date that already passed this year is skipped, never rolled forward a year.
        for y in (pub.year, pub.year + 1):
            dt = _mk(y, month, day)
            if dt is not None and dt >= pub:
                if (dt - pub).days <= 120:
                    add(dt, m, "day", BASIS_INFERRED)
                return

    for m in DM_NOYEAR.finditer(text) if infer_year else ():
        if free(m):
            infer(MONTHS[m.group(2)[:3].lower()], int(m.group(1)), m)
    for m in MD_NOYEAR.finditer(text) if infer_year else ():
        if free(m):
            infer(MONTHS[m.group(1)[:3].lower()], int(m.group(2)), m)
    return sorted(out, key=lambda d: d[1])


def kind_of(window):
    for name, rx in CUES:
        if rx.search(window):
            return name
    return None


def _clause(text, s, e):
    """The clause around [s, e): bounded by sentence ends, capped at 220 chars each side."""
    lo = max(0, s - 220)
    for sep in (". ", "! ", "? "):
        i = text.rfind(sep, lo, s)
        if i != -1:
            lo = max(lo, i + 2)
    hi = min(len(text), e + 220)
    for sep in (". ", "! ", "? "):
        i = text.find(sep, e, hi)
        if i != -1:
            hi = min(hi, i + 1)
    return text[lo:hi]


def _span(text, s, e):
    a, b = max(0, s - 90), min(len(text), e + 90)
    out = text[a:b]
    if a > 0:
        out = out.split(" ", 1)[-1]
    if b < len(text):
        out = out.rsplit(" ", 1)[0]
    return out.strip()


def pub_verified(row):
    """Publication date counts as verified for relative-date resolution: present, not an aggregator, not after collection."""
    p = parse_ts(row.get("published_at"))
    if p is None or AGGREGATOR.search(row.get("source_name") or ""):
        return None
    c = parse_ts(row.get("collected_at")) if row.get("collected_at") else None
    if c is not None and p > c + timedelta(hours=1):
        return None
    return p


_STOP = {
    "cancellation",
    "of",
    "the",
    "a",
    "an",
    "in",
    "on",
    "event",
    "condition",
    "forecast",
    "region",
    "level",
    "update",
    "stpasa",
    "pdpasa",
    "notice",
}


def _tokens(title):
    toks = re.findall(r"[A-Za-z0-9]+", re.sub(r"\d{1,2}/\d{1,2}/\d{4}", " ", title))
    return {t.lower() for t in toks} - _STOP


def _title_date(title, au):
    for dt, _, _, prec, _ in find_dates(title, date(2000, 1, 1), au):
        if prec == "day":
            return dt
    return None


def extract_events(rows, include_news=False):
    """Every dated future event stated by the rows (future relative to each row's own publication date)."""
    events, cancels = [], []
    for r in rows:
        src = r.get("source_name") or ""
        t = tier(src)
        if t is None or (t == "NEWS" and not include_news):
            continue
        # Reference date: the row's publication date; when it is missing (several regulator feeds carry none) the collection
        # date, which is safe only for explicit-year dates, so year inference and relative dates are switched off.
        p = parse_ts(r.get("published_at"))
        ref = "published_at"
        if p is None:
            p, ref = (
                parse_ts(r.get("collected_at")),
                "collected_at (published_at missing)",
            )
        if p is None:
            continue
        pub = p.date()
        au = bool(AU_OFFICIAL.search(src))
        title = clean_text(r.get("raw_title"))
        summary = clean_text(r.get("raw_summary"))
        text = f"{title}. {summary}" if summary else title
        if re.search(
            r"\(completed\)|\(resolved\)|\bhas been completed\b|Status:\s*Complete\b",
            text,
            re.IGNORECASE,
        ):
            continue
        if au and CANCEL.search(title):
            d = _title_date(title, au)
            if d:
                cancels.append((src, d, _tokens(title), p))
            continue
        found = []
        ds = find_dates(text, pub, au, infer_year=ref == "published_at")
        i = 0
        while i < len(ds):
            dt, s, e, prec, basis = ds[i]
            end_date, hi = None, e
            if i + 1 < len(ds) and ds[i + 1][3] == "day" and prec == "day":
                nxt = ds[i + 1]
                if is_range_gap(text[e : nxt[1]]):
                    end_date, hi = nxt[0], nxt[2]
                    i += 1
            i += 1
            if end_date == dt:
                end_date = None
            before = text[max(0, s - 40) : s]
            if LABEL_BEFORE.search(before) or PAST_BEFORE.search(before):
                continue
            future = (
                dt > pub
                if prec == "day"
                else (dt.year, dt.month) > (pub.year, pub.month)
            )
            if not future:
                continue
            clause = _clause(text, s, hi)
            kind = kind_of(clause) or (kind_of(title) if len(title) < 200 else None)
            if au and t == "OFFICIAL" and AEMO_FORECAST.search(title):
                kind = "advisory_deadline"
            if kind is None:
                continue
            if kind == "regulatory" and t not in ("OFFICIAL", "NEWS"):
                kind = "vendor_lifecycle" if t == "VENDOR" else None
                if kind is None:
                    continue
            if t == "NEWS":
                label = "RELAYED_BY_NEWS"
            elif prec == "month":
                label = "DATE_PRECISION_MONTH"
            elif basis == BASIS_INFERRED:
                label = "INFERRED_YEAR"
            elif au and t == "OFFICIAL" and AEMO_FORECAST.search(title):
                label = "OPERATOR_FORECAST"
            elif t == "PROVIDER" and kind == "planned_maintenance":
                label = "SCHEDULED_BY_OWNER"
            else:
                label = "OFFICIAL_DATE_STATED"
            tm = TIME_AFTER.match(text[hi : hi + 30]) if prec == "day" else None
            found.append(
                {
                    "event": title[:140],
                    "date": dt.isoformat(),
                    "end_date": end_date.isoformat() if end_date else None,
                    "time": (f"{tm.group(1)} {tm.group(2) or ''}".strip())
                    if tm
                    else None,
                    "precision": prec,
                    "date_basis": basis,
                    "source": src,
                    "evidence_span": _span(text, s, hi),
                    "kind": kind,
                    "uncertainty_label": label,
                    "event_id": r.get("event_id"),
                    "published_at": p.isoformat(),
                    "reference_date": ref,
                    "tier": t,
                }
            )
        # Relative dates: only against a verified publication date, only for authoritative tiers, only with a kind cue.
        pv = pub_verified(r) if t != "NEWS" or include_news else None
        if pv is not None:
            for m in REL.finditer(text):
                if LABEL_BEFORE.search(text[max(0, m.start() - 40) : m.start()]):
                    continue
                kind = kind_of(_clause(text, m.start(), m.end()))
                if kind is None:
                    continue
                w = m.group(1).lower()
                d0 = pv.date()
                prec = "day"
                if w in ("tomorrow", "tonight"):
                    dt = d0 + (
                        timedelta(days=1) if w == "tomorrow" else timedelta(days=0)
                    )
                elif w == "this weekend":
                    dt = d0 + timedelta(days=(5 - d0.weekday()) % 7)
                elif w == "next week":
                    dt, prec = d0 + timedelta(days=7 - d0.weekday()), "week"
                else:
                    wd = WEEKDAYS.index(w.split()[1])
                    dt = d0 + timedelta(days=(wd - d0.weekday()) % 7 or 7)
                if dt <= d0 and w != "tonight":
                    continue
                found.append(
                    {
                        "event": title[:140],
                        "date": dt.isoformat(),
                        "end_date": None,
                        "time": None,
                        "precision": prec,
                        "date_basis": BASIS_INFERRED,
                        "source": src,
                        "evidence_span": _span(text, m.start(), m.end()),
                        "kind": kind,
                        "uncertainty_label": "RELATIVE_DATE_LOWER_CONFIDENCE",
                        "event_id": r.get("event_id"),
                        "published_at": p.isoformat(),
                        "reference_date": ref,
                        "tier": t,
                    }
                )
        # One event per (date, kind) per row; an explicit year beats an inferred one.
        pick = {}
        for f in found:
            k = (f["date"], f["kind"])
            if k not in pick or (
                pick[k]["date_basis"] != BASIS_EXPLICIT
                and f["date_basis"] == BASIS_EXPLICIT
            ):
                pick[k] = f
        for f in pick.values():
            f["_toks"] = _tokens(title)
        events.extend(pick.values())
    # A later cancellation of the same forecast (same source, same date, shared salient tokens) removes it.
    kept = []
    for ev in events:
        ed = date.fromisoformat(ev["date"])
        gone = False
        for src, cd, ctoks, cp in cancels:
            if src == ev["source"] and cd == ed and cp >= parse_ts(ev["published_at"]):
                inter = len(ctoks & ev["_toks"])
                union = len(ctoks | ev["_toks"]) or 1
                if inter / union >= 0.5:
                    gone = True
                    break
        if not gone:
            kept.append(ev)
    for ev in kept:
        ev.pop("_toks", None)
    kept.sort(key=lambda e: (e["date"], e["source"], e["event_id"] or "", e["kind"]))
    return kept


def latest_per_notice(events):
    """When the same notice is re-published, keep the event from its latest row (same source, event text and date)."""
    best = {}
    for e in events:
        k = (
            e["source"],
            re.sub(r"[^a-z0-9]+", " ", e["event"].lower()).strip(),
            e["date"],
            e["kind"],
        )
        if k not in best or e["published_at"] >= best[k]["published_at"]:
            best[k] = e
    return sorted(
        best.values(), key=lambda e: (e["date"], e["source"], e["event_id"] or "")
    )


def upcoming(events, as_of, horizon_days=30):
    today, last = as_of.date(), as_of.date() + timedelta(days=horizon_days)
    return [e for e in events if today <= date.fromisoformat(e["date"]) <= last]


def rows_from_statuspage_maintenances(
    payload, source_name="ATO Online services for agents Status"
):
    """Rows (export shape) from a Statuspage scheduled-maintenances JSON payload.

    The structured scheduled_for/scheduled_until fields are explicit dates; the human text in the last update is kept as the summary.
    """
    rows = []
    for m in payload.get("scheduled_maintenances", []):
        if (m.get("status") or "").lower() not in (
            "scheduled",
            "in_progress",
            "verifying",
        ):
            continue
        ups = m.get("incident_updates") or []
        body = clean_text((ups[-1].get("body") if ups else "") or "")
        rows.append(
            {
                "event_id": m.get("id"),
                "source_name": source_name,
                "published_at": m.get("created_at"),
                "collected_at": m.get("updated_at"),
                "canonical_url": m.get("shortlink"),
                "raw_title": f"{m.get('name')}: scheduled maintenance",
                "raw_summary": f"Scheduled maintenance {body}",
            }
        )
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--horizon-days", type=int, default=30)
    ap.add_argument("--include-news", action="store_true")
    ap.add_argument(
        "--all", action="store_true", help="emit every event, not only upcoming ones"
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--enable", action="store_true")
    args = ap.parse_args(argv)
    if not enabled(args.enable):
        print(
            f"Disabled by default. Re-run with --enable (or {ENABLE_ENV}=1). Offline, read-only; reads only the files given with --input.",
            file=sys.stderr,
        )
        return 2
    rows = load_rows(args.input)
    as_of = (
        parse_ts(args.as_of if "T" in args.as_of else args.as_of + "T00:00:00Z")
        if args.as_of
        else datetime.now(timezone.utc)
    )
    ev = latest_per_notice(extract_events(rows, include_news=args.include_news))
    if not args.all:
        ev = upcoming(ev, as_of, args.horizon_days)
    text = json.dumps(ev, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
