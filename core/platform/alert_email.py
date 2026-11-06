"""Subjects, machine-readable header and routing rules for alert emails.

Alert emails go to a team mailbox that Cowork reads, so every one has:
  - an ASCII subject tag: [EW] [WA] [BOM-HIGH] [UPDATE] [LIFTED] [DIGEST];
  - a fixed "Key: value" block at the top of the body (stable names, one per
    line), then the human text.

Routing rules (revised 2026-11-02: site matching is NOT done here; the mailbox's
reader (Cowork) works out what an alert means for us):
  Emergency Warning   always emails (cannot be silenced).
  Watch and Act       always emails (can be silenced).
  BOM high attention  always emails (can be silenced).
  ADVICE              only for jurisdiction:hazard rules switched on in EMERGENCY_ALERT_ADVICE_EMAIL
                      (off by default; can be silenced; no UPDATE / LIFTED follow-ups).
  UPDATE / LIFTED     follow-ups for alerts already emailed.
  FEED                a source is down or has gone quiet, and when it recovers (not about an alert).
  DIGEST              one team overview a day.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone

EW, WA, BOM_HIGH, UPDATE, LIFTED, DIGEST = "EW", "WA", "BOM-HIGH", "UPDATE", "LIFTED", "DIGEST"
ADVICE, FEED = "ADVICE", "FEED"

TIER_LABEL = {
    "emergency_warning": "Emergency Warning",
    "watch_and_act": "Watch and Act",
    "advice": "Advice",
    "unknown": "BOM high attention",
}
_RANK = {"unknown": 0, "advice": 1, "watch_and_act": 2, "emergency_warning": 3}


def tier_rank(severity: str | None) -> int:
    return _RANK.get(severity or "unknown", 0)


# Local clock for each jurisdiction, so a reader sees "20:00 AEDT" next to the UTC time. Queensland has no daylight
# saving, so it is a fixed AEST (+10) offset: the repo's timezone guard (tests/test_local_timezone.py) bans naming the
# Brisbane zone in code so nothing mistakes it for the platform's own (Melbourne) clock.
JURISDICTION_TZ: dict[str, object] = {
    "NSW": "Australia/Sydney", "ACT": "Australia/Sydney", "VIC": "Australia/Melbourne", "QLD": timezone(timedelta(hours=10), "AEST"),
    "SA": "Australia/Adelaide", "WA": "Australia/Perth", "TAS": "Australia/Hobart", "NT": "Australia/Darwin",
}


def local_time(value: object, jurisdiction: str | None) -> str | None:
    """"2026-11-06 20:00 AEDT" for an ISO timestamp in the jurisdiction's own zone, or None when the value is not
    an offset-aware ISO time (the BOM email passes the bulletin's own text) or the zone data is unavailable."""
    tz_name = JURISDICTION_TZ.get((jurisdiction or "").upper())
    if not tz_name or not value:
        return None
    try:
        from zoneinfo import ZoneInfo

        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        zone = ZoneInfo(tz_name) if isinstance(tz_name, str) else tz_name
        return stamp.astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:  # noqa: BLE001 - a display nicety: any parse or zone problem just omits the local line
        return None


def format_duration(delta) -> str:
    """"3h 20m", "45m" or "under 1m" - for how long an alert was listed."""
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "under 1m"
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = ([f"{days}d"] if days else []) + ([f"{hours}h"] if hours else []) + ([f"{minutes}m"] if minutes or not (days or hours) else [])
    return " ".join(parts)


def parse_advice_rules(spec: str | None) -> list[tuple[str, str]]:
    """EMERGENCY_ALERT_ADVICE_EMAIL="NSW:flood,*:bushfire,QLD:*" -> [("NSW","flood"),("*","bushfire"),("QLD","*")].
    Empty / unset = no Advice emails (the default). Entries without a colon are ignored."""
    rules = []
    for part in (spec or "").split(","):
        if ":" in part:
            jurisdiction, hazard = (x.strip() for x in part.split(":", 1))
            if jurisdiction and hazard:
                rules.append((jurisdiction.upper() if jurisdiction != "*" else "*", hazard.lower()))
    return rules


def advice_matches(rules: list[tuple[str, str]], jurisdiction: str | None, alert_type: str | None) -> bool:
    return any(j in ("*", (jurisdiction or "").upper()) and h in ("*", (alert_type or "").lower()) for j, h in rules)


def build_subject(tag: str, jurisdiction: str, headline: str) -> str:
    """ASCII tag, no emoji: "[EW] NSW - Bushfire Emergency Warning - Katoomba"."""
    return f"[{tag}] {jurisdiction} - {headline}"


# Pages that LIST current incidents/warnings, for sources whose own per-alert link is a
# data record (JSON/XML), not a page a person can read. Only addresses known to exist.
_LIST_PAGES = {
    "nsw_rfs": "https://www.rfs.nsw.gov.au/fire-information/fires-near-me",
    "act_esa": "https://esa.act.gov.au/",
    "sa_cfs": "https://www.cfs.sa.gov.au/warnings-restrictions/warnings/",
}
_DATA_RECORD_SOURCES = {"nsw_rfs", "act_esa"}  # their canonical_url is an API / feed address


def official_links(row: dict) -> tuple[str | None, str | None, str]:
    """(official page, data record, precision) for an alert.

    precision: "direct" = the page is about this warning; "list" = a page listing the
    current ones (find this one on it, or use the record link); "none" = nothing known.
    BOM warnings carry their product page in raw_text (it cannot be canonical_url: that
    column is unique across sources and BOM links are shared by neighbouring states)."""
    source = row.get("source_key") or ""
    url = row.get("canonical_url") or None
    if source.startswith("bom_") and not url:
        for line in reversed((row.get("raw_text") or "").splitlines()):
            if line.strip().startswith("http"):
                url = line.strip()
                break
    if url and url.startswith("http://reg.bom.gov.au/"):
        url = url.replace("http://reg.bom.gov.au/", "https://www.bom.gov.au/", 1)
    elif url and url.startswith("https://reg.bom.gov.au/"):
        url = url.replace("https://reg.bom.gov.au/", "https://www.bom.gov.au/", 1)
    if source in _DATA_RECORD_SOURCES or (source in _LIST_PAGES and not url):
        return _LIST_PAGES.get(source), url if source in _DATA_RECORD_SOURCES else None, "list"
    if url:
        return url, None, "direct"
    return None, None, "none"


def fields_block(tag: str, row: dict, extra: dict[str, object] | None = None) -> str:
    """The fixed header. Order and key names are an interface; do not rename."""
    official, record, precision = official_links(row)
    values: list[tuple[str, object]] = [
        ("Alert-ID", row.get("id")),
        ("Notice", tag),
        ("Tier", TIER_LABEL.get(row.get("severity") or "unknown")),
        ("Jurisdiction", row.get("jurisdiction")),
        ("Headline", row.get("headline")),
        ("Location", row.get("location")),
        ("Issued", row.get("issued_at")),
        ("Official-Link", official),
        ("Source", row.get("source_key")),
        ("Sent-At", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("Link-Precision", precision),
    ]
    if record:
        values.append(("Record-Link", record))
    # CAP fields exactly as the source gave them (SA CFS, VIC warnings, NSW RFS, BoM); only present when the source has them.
    for key, field in (("CAP-Event", "cap_event"), ("CAP-Urgency", "cap_urgency"), ("CAP-Certainty", "cap_certainty"), ("CAP-Severity", "cap_severity")):
        if row.get(field):
            values.append((key, row.get(field)))
    now = datetime.now(timezone.utc)
    for key, value in (("Issued-Local", row.get("issued_at")), ("Sent-At-Local", now)):
        local = local_time(value, row.get("jurisdiction"))
        if local:
            values.append((key, local))
    values += list((extra or {}).items())
    lines = "\n".join(f"{k}: {html.escape(str(v if v not in (None, '') else '-'))}" for k, v in values)
    return f'<pre style="font-family:monospace;white-space:pre-wrap">{lines}</pre>'


def feed_block(row: dict, extra: dict[str, object] | None = None) -> str:
    """Header for [FEED] emails (a source is down / quiet / recovered). About a source, not an alert, so it has its own
    keys: Notice, Source, Jurisdiction, Problem, Since (and Since-Local), plus whatever the caller adds."""
    jurisdiction = row.get("jurisdiction")
    now = datetime.now(timezone.utc)
    values: list[tuple[str, object]] = [
        ("Notice", FEED),
        ("Source", row.get("source_key")),
        ("Jurisdiction", jurisdiction),
        ("Problem", row.get("problem")),
        ("Since", row.get("since")),
        ("Since-Local", local_time(row.get("since"), jurisdiction)),
        ("Sent-At", now.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("Sent-At-Local", local_time(now, jurisdiction)),
    ]
    values += list((extra or {}).items())
    lines = "\n".join(f"{k}: {html.escape(str(v if v not in (None, '') else '-'))}" for k, v in values)
    return f'<pre style="font-family:monospace;white-space:pre-wrap">{lines}</pre>'


_BOM_PRODUCT_ID = re.compile(r"\bID[A-Z]\d{5}\b")
HASH_V2 = "h2:"


def bom_product_id(row: dict) -> str | None:
    """The BOM product ID (e.g. IDN21033) in an alert's text. The same product is listed
    by several state feeds, so this is what identifies one warning across them."""
    match = _BOM_PRODUCT_ID.search(f"{row.get('description') or ''} {row.get('raw_text') or ''}")
    return match.group(0) if match else None


def content_hash(row: dict) -> str:
    """Fingerprint of an alert, for 'material update' detection. A BOM warning is re-issued
    with a new issue time and boilerplate every few hours without meaning anything new, so
    for BOM only the headline (which carries the warning type, level and area) counts."""
    if str(row.get("source_key") or "").startswith("bom_"):
        text = str(row.get("headline") or "")
        prefix = HASH_V2
    else:
        text = " ".join(str(row.get(k) or "") for k in ("headline", "location", "description"))
        prefix = ""
    return prefix + hashlib.sha256(" ".join(text.split()).lower().encode("utf-8")).hexdigest()[:16]


def html_to_text(markup: str) -> str:
    """Plain-text twin of an alert email (sent as the text/plain part). Block
    tags become line breaks, list items become "- " lines, links keep their URL."""
    text = re.sub(r'(?is)<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", markup)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</pre>|</ul>|</div>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
