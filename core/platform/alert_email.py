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
  UPDATE / LIFTED     follow-ups for alerts already emailed.
  DIGEST              one team overview a day.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone

EW, WA, BOM_HIGH, UPDATE, LIFTED, DIGEST = "EW", "WA", "BOM-HIGH", "UPDATE", "LIFTED", "DIGEST"

TIER_LABEL = {
    "emergency_warning": "Emergency Warning",
    "watch_and_act": "Watch and Act",
    "advice": "Advice",
    "unknown": "BOM high attention",
}
_RANK = {"unknown": 0, "advice": 1, "watch_and_act": 2, "emergency_warning": 3}


def tier_rank(severity: str | None) -> int:
    return _RANK.get(severity or "unknown", 0)


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
    values += list((extra or {}).items())
    lines = "\n".join(f"{k}: {html.escape(str(v if v not in (None, '') else '-'))}" for k, v in values)
    return f'<pre style="font-family:monospace;white-space:pre-wrap">{lines}</pre>'


def content_hash(row: dict) -> str:
    """Fingerprint of the words of an alert, for 'material update' detection."""
    text = " ".join(str(row.get(k) or "") for k in ("headline", "location", "description"))
    return hashlib.sha256(" ".join(text.split()).lower().encode("utf-8")).hexdigest()[:16]


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
