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


def fields_block(tag: str, row: dict, extra: dict[str, object] | None = None) -> str:
    """The fixed header. Order and key names are an interface; do not rename."""
    values: list[tuple[str, object]] = [
        ("Alert-ID", row.get("id")),
        ("Notice", tag),
        ("Tier", TIER_LABEL.get(row.get("severity") or "unknown")),
        ("Jurisdiction", row.get("jurisdiction")),
        ("Headline", row.get("headline")),
        ("Location", row.get("location")),
        ("Issued", row.get("issued_at")),
        ("Official-Link", row.get("canonical_url")),
        ("Source", row.get("source_key")),
        ("Sent-At", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    ]
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
