"""Retrospective outage-register records (Optus National Outage Register, PR #709) for the recurring-provider product.

The register is a RETROSPECTIVE RECORD: carriers publish each Major / Significant Local Outage after it is rectified.
It is used here only as authoritative confirmation of an outage that already happened (start/end, duration, services
affected, stated cause) and as history. It is never a new outage, never an alert candidate, and never produces an
exception. Entries are bucketed by the outage's OWN start date, never by collection or first-published date, so a
historical import cannot distort recent trends.

Rows are expected in the export shape; `raw_summary` is the text PR #709's parser writes ("Start d/m/Y HH:MM AEDT; end ...;
duration N h. Services affected: ... Cause (as stated by the carrier): ... Register reference REF.").
`rows_from_register_html` builds such rows from a rendered register page (offline convenience, used by the fixture tests).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from analytics_common import parse_ts

REGISTER_SOURCES = frozenset({"Optus National Outage Register"})
PROVIDER = "Optus"
LABEL = "retrospective record"

_START = re.compile(r"Start\s+(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}:\d{2}))?")
_END = re.compile(r"end\s+(\d{1,2})/(\d{1,2})/(\d{4})")
_DUR = re.compile(r"duration\s+([\d.]+)\s*h", re.IGNORECASE)
_SERV = re.compile(
    r"Services affected:\s*(.+?)\.\s+Locations:", re.IGNORECASE | re.DOTALL
)
_CAUSE = re.compile(
    r"Cause \(as stated by the carrier\):\s*(.+?)\.\s+Register reference",
    re.IGNORECASE | re.DOTALL,
)
_REF = re.compile(r"Register reference\s+([A-Za-z0-9]+)")


def is_register_row(row):
    return (row.get("source_name") or "") in REGISTER_SOURCES


def parse_entry(row):
    """Entry facts from one register row, or None when the event's own start date cannot be read."""
    text = row.get("raw_summary") or ""
    m = _START.search(text)
    if not m:
        return None
    start = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    dur = _DUR.search(text)
    serv, cause, ref = _SERV.search(text), _CAUSE.search(text), _REF.search(text)
    title = re.sub(r"^Optus outage register:\s*", "", row.get("raw_title") or "")
    return {
        "event_id": row.get("event_id"),
        "reference": ref.group(1) if ref else None,
        "title": title,
        "start": start,
        "duration_h": float(dur.group(1)) if dur else None,
        "services": " ".join(serv.group(1).split()) if serv else "not stated",
        "cause": " ".join(cause.group(1).split()) if cause else "not stated",
    }


def analyse(rows, as_of, window_days=90):
    """Entries whose OWN start date is in the 90-day window (collection/publication dates are ignored)."""
    start = (as_of - timedelta(days=window_days)).date()
    end = as_of.date()
    entries, unreadable = [], 0
    for r in rows:
        if not is_register_row(r):
            continue
        e = parse_entry(r)
        if e is None:
            unreadable += 1
        elif start <= e["start"] <= end:
            entries.append(e)
    entries.sort(key=lambda e: e["start"])
    return {
        "entries": entries,
        "unreadable": unreadable,
        "causes": Counter(e["cause"] for e in entries),
        "by_month": Counter(e["start"].strftime("%Y-%m") for e in entries),
    }


def evidence_lines(result):
    out = []
    for e in result["entries"][-5:][::-1]:
        dur = (
            f"{e['duration_h']:.1f} h"
            if e["duration_h"] is not None
            else "duration not stated"
        )
        out.append(
            f"[{LABEL}] {PROVIDER} outage register {e['reference'] or 'no reference'} ({e['event_id']}): {e['title']}; "
            f"started {e['start']}, {dur}; services: {e['services']}; cause as stated by the carrier: {e['cause']}."
        )
    if result["entries"]:
        out.insert(
            0,
            f"[{LABEL}] {PROVIDER}: {len(result['entries'])} register entries with an outage start date in the window "
            f"(by event date: {', '.join(f'{k} {v}' for k, v in sorted(result['by_month'].items()))}). "
            "The register is published after restoration; entries confirm past outages and are not new incidents.",
        )
    return out


def rows_from_register_html(html, page_url="https://example.invalid/outages"):
    """Export-shaped rows from a rendered register page (same field labels as PR #709's parser)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for block in soup.select('[data-testid^="outage-result-"]'):
        f = {}
        for node in block.find_all(["h3", "p"]):
            lab = node.find("span", class_=lambda c: c and "result-label" in c)
            val = node.find("span", class_=lambda c: c and "result-value" in c)
            if lab and val:
                f[lab.get_text(strip=True).rstrip(":").strip().lower()] = val.get_text(
                    " ", strip=True
                )
        ref, title = f.get("reference"), f.get("outage title")
        if not ref or not title:
            continue
        start = f"{f.get('start date of outage', '?')} {f.get('start time of outage', '')}".strip()
        end = f"{f.get('end date of outage', '?')} {f.get('end time of outage', '')}".strip()
        summary = (
            f"Restored. {f.get('outage type', 'Outage')}. Start {start}; end {end}; duration "
            f"{f.get('duration of outage', '?').strip()} h. Services affected: {f.get('types of services affected', 'unknown')} "
            f"({f.get('number of each type of services affected', '') or 'count not stated'}). "
            f"Locations: {f.get('affected suburbs/towns', 'n/a')} ({f.get('affected states/territories', 'n/a')}). "
            f"Cause (as stated by the carrier): {f.get('cause (high level)', 'unknown')}. Register reference {ref}."
        )
        published = parse_ts(datetime.now(timezone.utc))
        rows.append(
            {
                "event_id": f"register-{ref}",
                "source_name": "Optus National Outage Register",
                "published_at": published.isoformat(),
                "collected_at": published.isoformat(),
                "canonical_url": f"{page_url}#{ref}",
                "raw_title": f"Optus outage register: {title}",
                "raw_summary": summary,
            }
        )
    return rows
