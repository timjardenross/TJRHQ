"""Parsers for planned-maintenance notices published by Australian government and critical-infrastructure status pages.

Pure functions: HTML or JSON in, plain records out, no network and no database. Each record is shaped for the dated-events
extractor (``tools/intelligence/analytics/dated_events.py``, branch ``claude/forward-dated-2kq``) and for ``IntelligenceItem``:

    {event_id, source_name, published_at, canonical_url, raw_title, raw_summary, window_start, window_end}

Rules (forward-sources-maint-2kq):
  * Only dates the page states are emitted. The window is written into ``raw_summary`` as the page's own words
    ("Scheduled maintenance from Friday 27 November 2026 11:30 pm AEDT to Monday 30 November 2026 7:00 am AEDT"), so the
    extractor can quote it as evidence. ``window_start``/``window_end`` are ISO 8601 conveniences derived from that same text.
  * Recurring weekly windows ("Tuesday 11:30 pm AEDT to Wednesday 7:00 am AEDT") carry no date and are never emitted.
  * No time zone is guessed. A row with a stated abbreviation keeps it; a page that states none gets a dated record with
    ``window_start``/``window_end`` set to a date only.
  * Completed windows are skipped on Statuspage feeds (status ``completed``).

Sources covered: Atlassian Statuspage ``/api/v2/scheduled-maintenances.json`` (ATO osfa/osb/pls), the ATO "System maintenance" page,
the ABR "Scheduled site maintenance" page, the myID "System maintenance" page and the DVS "Upcoming Scheduled Outages" page.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        1,
    )
}
# Abbreviations the Australian pages state next to a time. Offsets are fixed and only used to build the ISO convenience fields.
_TZ_HOURS = {"AEDT": 11, "AEST": 10, "ACDT": 10.5, "ACST": 9.5, "AWST": 8, "NEM": 10}
_TZ_RE = r"(AEDT|AEST|ACDT|ACST|AWST)"
_TIME_RE = r"(?:(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?|(noon|midnight))"
_WHEN_RE = re.compile(
    rf"(?:(?:mon|tues?|wednes|thurs?|fri|sat(?:ur)?|sun)(?:day)?\s*,?\s*)?(\d{{1,2}})\s+([A-Za-z]+)\s+(\d{{4}})"
    rf"(?:\s*,?\s*(?:at\s+)?{_TIME_RE})?(?:\s*{_TZ_RE})?",
    re.IGNORECASE,
)
# "Noon AEDT" sometimes follows the date on its own line, handled by the optional time group above.
_SLASH_RANGE_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::\d{2})?\s*([AP]M)\s+to\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::\d{2})?\s*([AP]M)",
    re.IGNORECASE,
)


def _clean(text) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _parse_when(text: str, default_tz: str | None = None):
    """First full date (with optional time and zone abbreviation) in ``text``.

    Returns ``(label, start_iso)`` where ``label`` is the page's own wording, normalised only for whitespace, or ``None``.
    ``start_iso`` is a datetime ISO string when a time is stated, a date ISO string when it is not.
    """
    m = _WHEN_RE.search(_clean(text))
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = _MONTHS.get(mon) or next(
        (
            v
            for k, v in _MONTHS.items()
            if len(mon) >= 3 and k.startswith(mon.rstrip("."))
        ),
        None,
    )
    if not month:
        return None
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    hh, mm, ap, word, tz = m.group(4), m.group(5), m.group(6), m.group(7), m.group(8)
    tz = (tz or default_tz or "").upper() or None
    label = _clean(m.group(0))
    if word or hh:
        if word:
            hour, minute = (12, 0) if word.lower() == "noon" else (0, 0)
        else:
            hour, minute = int(hh) % 12, int(mm or 0)
            if ap.lower() == "p":
                hour += 12
        if hour > 23 or minute > 59:
            return None
        if tz and tz in _TZ_HOURS:
            off = timezone(timedelta(hours=_TZ_HOURS[tz]))
            iso = datetime(d.year, d.month, d.day, hour, minute, tzinfo=off).isoformat()
        else:
            iso = f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"  # zone not stated: no offset, never assumed
    else:
        iso = d.isoformat()
    if default_tz and not m.group(8) and (word or hh):
        label = f"{label} {default_tz}"
    return label, iso


def _stable_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _record(source_name, url, *, title, window, kind_note, published_at, ident):
    (start_label, start_iso), (end_label, end_iso) = window
    summary = f"Scheduled maintenance from {start_label} to {end_label}"
    if kind_note:
        summary += f" ({kind_note})"
    return {
        "event_id": ident,
        "source_name": source_name,
        "published_at": published_at,
        "canonical_url": f"{url.split('#')[0]}#{ident}",
        "raw_title": f"{title}: scheduled maintenance",
        "raw_summary": summary + ".",
        "window_start": start_iso,
        "window_end": end_iso,
    }


# ---------------------------------------------------------------- Statuspage JSON


def statuspage_maintenance_records(
    payload: dict, source_name: str, page_url: str | None = None
) -> list[dict]:
    """Records from an Atlassian Statuspage ``/api/v2/scheduled-maintenances.json`` payload (or its ``/upcoming.json`` sibling).

    ``scheduled_for`` / ``scheduled_until`` are the structured dates; the last human update body (for ATO: "11:30 pm AEDT
    Tuesday, 24 November 2026 to 7:00 am AEDT Wednesday, 25 November 2026") is kept as supporting text. Only
    ``scheduled``, ``in_progress`` and ``verifying`` maintenances are emitted.
    """
    page_url = (page_url or (payload.get("page") or {}).get("url") or "").rstrip("/")
    records = []
    for m in payload.get("scheduled_maintenances", []) or []:
        if (m.get("status") or "").lower() not in (
            "scheduled",
            "in_progress",
            "verifying",
        ):
            continue
        try:
            start = datetime.fromisoformat(m["scheduled_for"])
            end = datetime.fromisoformat(m["scheduled_until"])
        except (KeyError, TypeError, ValueError):
            continue
        updates = m.get("incident_updates") or []
        body = _clean(
            (updates[0].get("body") if updates else "") or ""
        )  # first update is the newest on Statuspage
        components = sorted(
            {
                c.get("name")
                for u in updates
                for c in (u.get("affected_components") or [])
                if c.get("name")
            }
        )

        def fmt(dt):
            hour = dt.hour % 12 or 12
            tz = {39600: "AEDT", 36000: "AEST"}.get(
                int(dt.utcoffset().total_seconds()), ""
            )
            return f"{dt.day} {dt.strftime('%B %Y')} {hour}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'} {tz}".strip()

        summary = f"Scheduled maintenance from {fmt(start)} to {fmt(end)}."
        if body:
            summary += f" Page text: {body}."
        if components:
            summary += f" Components: {', '.join(components[:12])}{' and more' if len(components) > 12 else ''}."
        ident = m.get("id") or _stable_id(source_name, m.get("scheduled_for"))
        records.append(
            {
                "event_id": ident,
                "source_name": source_name,
                "published_at": m.get("created_at"),
                "canonical_url": f"{page_url}/incidents/{ident}"
                if page_url
                else m.get("shortlink"),
                "raw_title": f"{m.get('name') or 'Maintenance'}: scheduled maintenance",
                "raw_summary": summary,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            }
        )
    return records


# ---------------------------------------------------------------- HTML table pages


def _tables(html: str):
    """Yield ``(heading, caption, header_cells, rows)`` for every table in ``html``. ``heading`` is the nearest preceding h1-h4."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all("table"):
        h = t.find_previous(["h1", "h2", "h3", "h4"])
        cap = t.find("caption")
        rows = []
        for tr in t.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            rows.append([_clean(c.get_text(" ")) for c in cells])
        header, body = (rows[0], rows[1:]) if rows else ([], [])
        yield (
            _clean(h.get_text(" ")) if h else "",
            _clean(cap.get_text(" ")) if cap else "",
            header,
            body,
        )


def _last_updated(html: str) -> str | None:
    """Page's own 'Last updated' / 'Last modified' date, as an ISO date; the publication date for table pages."""
    text = _clean(re.sub(r"<[^>]+>", " ", html))
    m = re.search(
        r"Last (?:updated|modified)\s*:?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    w = _parse_when(m.group(1))
    return w[1] if w else None


def _rows_to_records(
    source_name,
    url,
    html,
    *,
    default_tz=None,
    title_prefix,
    service_col=None,
    type_col=None,
    heading_title=False,
):
    published = _last_updated(html)
    out, seen = [], set()
    for heading, caption, header, rows in _tables(html):
        for cells in rows:
            whens = [(i, _parse_when(c, default_tz)) for i, c in enumerate(cells)]
            whens = [(i, w) for i, w in whens if w]
            if len(whens) < 2:
                continue  # recurring weekly or blank row: no stated date
            (si, start), (ei, end) = whens[0], whens[1]
            others = [c for i, c in enumerate(cells) if i not in (si, ei) and c]
            service = (
                cells[service_col]
                if service_col is not None
                and service_col < len(cells)
                and service_col not in (si, ei)
                else ""
            )
            note = (
                cells[type_col]
                if type_col is not None and type_col < len(cells)
                else (others[-1] if others and not service else "")
            )
            title = " ".join(
                x
                for x in [title_prefix, (heading if heading_title else ""), service]
                if x
            )
            ident = _stable_id(source_name, title, start[1], end[1])
            if ident in seen:
                continue
            seen.add(ident)
            out.append(
                _record(
                    source_name,
                    url,
                    title=title,
                    window=(start, end),
                    kind_note=_clean(note) or None,
                    published_at=published,
                    ident=ident,
                )
            )
    return out


def ato_system_maintenance_records(
    html: str,
    source_name: str = "ATO System Maintenance",
    url: str = "https://www.ato.gov.au/online-services/system-maintenance",
) -> list[dict]:
    """ATO 'System maintenance' page: table Start time / End time / Maintenance type. The weekly table has no dates and is skipped."""
    return _rows_to_records(
        source_name, url, html, title_prefix="ATO online systems", type_col=2
    )


def abr_site_maintenance_records(
    html: str,
    source_name: str = "ATO ABR Scheduled Site Maintenance",
    url: str = "https://www.abr.gov.au/general-information/scheduled-site-maintenance",
) -> list[dict]:
    """ABR 'Scheduled site maintenance': tables under 'ABN system' etc.; recurring or blank tables yield nothing. Times are AEDT per the page."""
    return _rows_to_records(
        source_name,
        url,
        html,
        default_tz="AEDT",
        title_prefix="Australian Business Register",
        heading_title=True,
    )


def myid_maintenance_records(
    html: str,
    source_name: str = "myID System Maintenance",
    url: str = "https://www.myid.gov.au/system-maintenance",
) -> list[dict]:
    """myID 'System maintenance': table Impacted service / Start time / End time."""
    return _rows_to_records(source_name, url, html, title_prefix="myID", service_col=0)


# ---------------------------------------------------------------- DVS (text, not a table)

_DVS_SKIP = {
    "hide",
    "show",
    "document type",
    "date",
    "time",
    "additional information",
    "document type:",
    "date:",
    "time:",
    "additional information:",
}


def dvs_outage_records(
    html_or_text: str,
    source_name: str = "DVS Status Scheduled Outages",
    url: str = "https://dvsstatus.idmatch.gov.au/Home/UpcomingScheduledOutages",
    include_test: bool = False,
) -> list[dict]:
    """DVS 'Upcoming Scheduled Outages' (next 14 days). Dates are D/M/YYYY, rewritten as '26 November 2026' so they cannot be misread as M/D.

    The page states no time zone, so none is attached. Production and Test environments are separate sections; Test is skipped unless asked for.
    """
    text = html_or_text
    if "<" in text and ">" in text:
        from bs4 import BeautifulSoup

        text = BeautifulSoup(text, "html.parser").get_text("\n")
    lines = [_clean(x) for x in text.splitlines()]
    lines = [x for x in lines if x]
    env, out, seen = "", [], set()
    for i, line in enumerate(lines):
        low = line.lower()
        if "production environment" in low:
            env = "production"
            continue
        if "test environment" in low:
            env = "test"
            continue
        m = _SLASH_RANGE_RE.fullmatch(line)
        if not m or not env or (env == "test" and not include_test):
            continue
        g = m.groups()
        try:
            d1, d2 = (
                date(int(g[2]), int(g[1]), int(g[0])),
                date(int(g[8]), int(g[7]), int(g[6])),
            )
        except ValueError:
            continue

        def label(d, hh, mi, ap):
            return f"{d.day} {d.strftime('%B %Y')} {int(hh)}:{mi} {ap.lower()}"

        def iso(d, hh, mi, ap):
            h = int(hh) % 12 + (12 if ap.lower() == "pm" else 0)
            return f"{d.isoformat()}T{h:02d}:{int(mi):02d}:00"  # no zone stated by the page: no offset

        start = (label(d1, g[3], g[4], g[5]), iso(d1, g[3], g[4], g[5]))
        end = (label(d2, g[9], g[10], g[11]), iso(d2, g[9], g[10], g[11]))
        # document type is the nearest earlier line that is not a field label
        doc = next(
            (
                lines[j]
                for j in range(i - 1, max(i - 4, -1), -1)
                if lines[j].lower() not in _DVS_SKIP
                and not _SLASH_RANGE_RE.fullmatch(lines[j])
            ),
            "",
        )
        next(
            (
                lines[j]
                for j in range(i + 1, min(i + 12, len(lines)))
                if lines[j].lower().startswith("additional information:")
            ),
            "",
        )
        title = f"DVS {env} {doc}".strip()
        ident = _stable_id(source_name, env, doc, start[1], end[1])
        if ident in seen:
            continue  # the page repeats each outage in a collapsed card
        seen.add(ident)
        out.append(
            _record(
                source_name,
                url,
                title=title,
                window=(start, end),
                kind_note=None,
                published_at=None,
                ident=ident,
            )
        )
    return out


# Page parsers keyed by registry source_name; used by ScrapeAdapter (inactive until a source row is activated).
PAGE_PARSERS = {
    "ATO System Maintenance": ato_system_maintenance_records,
    "ATO ABR Scheduled Site Maintenance": abr_site_maintenance_records,
    "myID System Maintenance": myid_maintenance_records,
    "DVS Status Scheduled Outages": dvs_outage_records,
}
