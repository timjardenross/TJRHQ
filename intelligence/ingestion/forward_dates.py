"""Forward-dated facts that collected sources state but our adapters used to drop.

Pure functions (no network, no database): each takes a payload or parsed HTML that an adapter has already fetched and returns the
text an item should carry so the dated-events extractor (tools/intelligence/analytics/dated_events.py) can read the date.
A date is only ever written here when the source states it (or, for Microsoft Patch Tuesday, when the documented rule is applied
and the summary says so).

Observed 2026-11-24:
  APRA listing   teaser pill "Open until 3 February 2027" / "Closed 6 November 2026"; news teasers "Published 24 November 2026"
  Treasury list  status + "<open date> - <closing date>" in <time> elements
  ASIC search    "Date closing: 22/01/2027" per open consultation (client-rendered page)
  CISA KEV       JSON field dueDate (adapter used to drop it)
  MSRC           DocumentTitle present; the item had no text and the newest-revised sort surfaced "Mariner Release Notes" from 1999
  endoflife.date v1 /api/v1/products/<slug>: releases[].eolFrom / eoasFrom / eoesFrom
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_NAMED = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})", re.IGNORECASE
)
_SLASH = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])")


def fmt_date(d: date) -> str:
    """'26 November 2026': the form the dated-events extractor reads without ambiguity."""
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def parse_named_date(text: str) -> date | None:
    m = _NAMED.search(text or "")
    if not m:
        return None
    try:
        return date(
            int(m.group(3)), _MONTHS.index(m.group(2).capitalize()) + 1, int(m.group(1))
        )
    except ValueError:
        return None


def parse_slash_date(text: str) -> date | None:
    """Day-first (Australian source)."""
    m = _SLASH.search(text or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el is not None else ""


# ── regulatory consultations ────────────────────────────────────────────────────────────────────────────────────────────


def apra_listing(soup, base: str = "https://www.apra.gov.au") -> list[dict]:
    """APRA teaser rows (consultations, news-and-publications): title, url, summary, status/closing date, 'Published' date.

    The closing date is on the listing itself ("Open until 3 February 2027"); no detail fetch is needed for it. The teaser's
    <time> element is the last official update, not a publication date, so it is not used.
    """
    from urllib.parse import urljoin

    out = []
    for row in soup.select("div.views-row"):
        a = row.select_one("div.search-result__title a[href], h2 a[href]")
        if a is None:
            continue
        title = _text(a)
        if not title:
            continue
        summary_el = row.select_one(".field--name-field-summary")
        summary = _text(summary_el)
        pills = [
            _text(p)
            for p in row.select(".anx-pill__label-first, .anx-pill__label-last")
        ]
        status, status_date = None, None
        for i, p in enumerate(pills):
            if p.lower() in ("open until", "closed") and i + 1 < len(pills):
                status, status_date = p.lower(), parse_named_date(pills[i + 1])
                break
        published = None
        m = re.search(r"Published\s+(\d{1,2}\s+\w+\s+\d{4})", _text(row))
        if m:
            published = parse_named_date(m.group(1))
        facts = []
        if status == "open until" and status_date:
            facts.append(
                f"APRA consultation open until {fmt_date(status_date)} (closing date)."
            )
        elif status == "closed" and status_date:
            facts.append(f"APRA consultation closed {fmt_date(status_date)}.")
        out.append(
            {
                "title": title,
                "url": urljoin(base, a["href"]),
                "summary": " ".join(x for x in [summary, *facts] if x) or None,
                "published_at": _utc(published) if published else None,
                "open": status == "open until",
                "closing_date": status_date if status else None,
            }
        )
    return out


_DETAIL_CUE = re.compile(
    r"submissions? close|closing date|commenc|come[s]? into (?:force|effect)|take[s]? effect|effective from|"
    r"transition(?:al)? period",
    re.IGNORECASE,
)


def apra_detail_sentences(soup, limit: int = 3) -> list[str]:
    """Sentences on an APRA consultation page that pair a deadline or commencement cue with an explicit date."""
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    text = _text(soup)
    found = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        if (
            _DETAIL_CUE.search(s)
            and _NAMED.search(s)
            and len(s) < 400
            and s not in found
        ):
            found.append(s)
        if len(found) >= limit:
            break
    return found


def treasury_listing(soup, base: str = "https://treasury.gov.au") -> list[dict]:
    """Treasury consultation rows: status, title, open date and closing date from the two <time> elements."""
    from urllib.parse import urljoin

    out = []
    for row in soup.select("div.views-row"):
        a = row.select_one("a[href*='/consultation/']")
        times = row.select("time[datetime]")
        if a is None or not times:
            continue
        title = _text(a)
        status_el = row.select_one(".field--name-field-status .field__item")
        status = _text(status_el).lower()
        opened, closes = (
            parse_named_date(_text(times[0])),
            parse_named_date(_text(times[-1])),
        )
        if not title or closes is None:
            continue
        if status == "closed":
            line = f"Treasury consultation closed {fmt_date(closes)}."
        else:
            line = (
                f"Treasury consultation open until {fmt_date(closes)} (closing date)."
            )
        out.append(
            {
                "title": title,
                "url": urljoin(base, a["href"]),
                "summary": line,
                "published_at": _utc(opened) if opened else None,
                "open": status != "closed",
                "closing_date": closes,
            }
        )
    return out


def asic_consultations(soup, base: str = "https://www.asic.gov.au") -> list[dict]:
    """ASIC regulatory-resources search rows for consultation papers: 'Date closing: 22/01/2027' (day-first)."""
    from urllib.parse import urljoin

    out, seen = [], set()
    for a in soup.select("a[href*='/find-a-document/consultations/']"):
        href = a.get("href", "")
        if href in seen:
            continue
        label = _text(a)
        container = a.find_parent(["li", "article", "div"]) or a
        ctext = _text(container)
        m = re.search(r"Date closing:?\s*(\d{1,2}/\d{1,2}/\d{4})", ctext)
        if not m or not label:
            continue  # closed rows say "Date closed" and are not forward-looking
        closes = parse_slash_date(m.group(1))
        if closes is None:
            continue
        seen.add(href)
        out.append(
            {
                "title": label,
                "url": urljoin(base, href),
                "summary": f"ASIC consultation open until {fmt_date(closes)} (closing date).",
                "published_at": None,
                "open": True,
                "closing_date": closes,
            }
        )
    return out


# ── CISA KEV ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def kev_summary(v: dict) -> str | None:
    """shortDescription plus the fields the adapter used to drop: the remediation due date, product and ransomware flag."""
    parts = []
    if v.get("shortDescription"):
        parts.append(str(v["shortDescription"]).strip())
    due = None
    try:
        due = date.fromisoformat(str(v.get("dueDate") or "")[:10])
    except ValueError:
        due = None
    if due:
        parts.append(
            f"CISA remediation due date: {fmt_date(due)} (required-action deadline for US federal agencies)."
        )
    vp = " ".join(x for x in [v.get("vendorProject"), v.get("product")] if x)
    if vp:
        parts.append(f"Affected: {vp}.")
    ransom = v.get("knownRansomwareCampaignUse")
    if ransom and str(ransom).lower() != "unknown":
        parts.append(f"Known ransomware campaign use: {ransom}.")
    return " ".join(parts) or None


# ── Microsoft MSRC ──────────────────────────────────────────────────────────────────────────────────────────────────────


def msrc_is_security_update(u: dict) -> bool:
    """The updates list also holds CBL-Mariner release notes back to 1999, re-touched recently; those are not Patch Tuesday."""
    return "security update" in (u.get("DocumentTitle") or "").lower()


def second_tuesday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(1 - d.weekday()) % 7 + 7)


def next_patch_tuesday(after: date) -> date:
    """First second-Tuesday strictly after `after` (Microsoft's monthly security update release day)."""
    d = second_tuesday(after.year, after.month)
    if d > after:
        return d
    y, m = (after.year + 1, 1) if after.month == 12 else (after.year, after.month + 1)
    return second_tuesday(y, m)


def msrc_summary(u: dict, next_release_from: date | None = None) -> str:
    """Summary for one monthly update. Pass `next_release_from` (today) for the newest update only: the next Patch Tuesday after
    it is then stated. Older months get no forward date (their 'next' release already happened)."""
    init = (u.get("InitialReleaseDate") or "")[:10]
    cur = (u.get("CurrentReleaseDate") or "")[:10]
    parts = []
    try:
        i = date.fromisoformat(init)
        parts.append(
            f"Microsoft monthly security update, initially released {fmt_date(i)}."
        )
        if next_release_from is not None:
            nxt = next_patch_tuesday(max(i, next_release_from))
            parts.append(
                f"Next planned publication: {fmt_date(nxt)} (second Tuesday of the month, Microsoft's published monthly "
                "release cadence; date derived from that rule, not stated in the feed)."
            )
    except ValueError:
        pass
    if cur and cur != init:
        parts.append(f"Last revised {cur}.")
    return " ".join(parts)


# ── endoflife.date ──────────────────────────────────────────────────────────────────────────────────────────────────────

_MILESTONES = [
    ("eolFrom", "end of life", "labels.eol"),
    ("eoasFrom", "end of active support", "labels.eoas"),
    ("eoesFrom", "end of extended security updates", "labels.eoes"),
]

DEFAULT_PRODUCTS = (
    "windows-server",
    "windows",
    "office",
    "cisco-ios-xe",
    "fortios",
    "oracle-jdk",
    "oracle-database",
    "rhel",
    "ubuntu",
    "esxi",
    "dotnet",
    "openssl",
    "postgresql",
    "python",
)


def endoflife_items(payload: dict, today: date, horizon_days: int = 730) -> list[dict]:
    """One record per (release, milestone) whose date falls in [today, today + horizon_days].

    Source: https://endoflife.date/api/v1/products/<slug> (MIT-licensed data). Title is stable per milestone so a re-run does not
    create a new row; the date is stated in both title and summary.
    """
    res = (payload or {}).get("result") or {}
    product = res.get("label") or res.get("name") or ""
    slug = res.get("name") or ""
    policy = (res.get("links") or {}).get("releasePolicy")
    last = today + timedelta(days=horizon_days)
    out = []
    for rel in res.get("releases") or []:
        rname = rel.get("label") or f"{product} {rel.get('name')}"
        for key, phrase, _label in _MILESTONES:
            raw = rel.get(key)
            try:
                d = date.fromisoformat(str(raw)[:10]) if raw else None
            except ValueError:
                d = None
            if d is None or not (today <= d <= last):
                continue
            title = f"{rname}: {phrase} on {fmt_date(d)}"
            summary = (
                f"{rname} reaches {phrase} on {fmt_date(d)} (vendor lifecycle date recorded by endoflife.date"
                + (f"; vendor policy: {policy}" if policy else "")
                + ")."
            )
            out.append(
                {
                    "title": title,
                    "summary": summary,
                    "url": f"https://endoflife.date/{slug}",
                    "date": d,
                    "milestone": key,
                }
            )
    out.sort(key=lambda r: (r["date"], r["title"]))
    return out
