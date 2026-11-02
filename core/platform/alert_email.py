"""Subjects, machine-readable header and routing rules for alert emails.

Alert emails go to a team mailbox that Cowork reads, so every one has:
  - an ASCII subject tag: [EW] [WA] [BOM-HIGH] [UPDATE] [LIFTED] [DIGEST];
  - a fixed "Key: value" block at the top of the body (stable names, one per
    line), then the human text.

Routing rules (decided with the Captain, 2026-11-02):
  Emergency Warning   always emails.
  Watch and Act       emails when at least one of our sites matches; otherwise
                      it is left for the daily digest.
  BOM high attention  emails when a site is inside the named area, or when the
                      area cannot be resolved in a state where we have sites
                      (we cannot rule sites out). If the named area is known and
                      none of our sites is inside it, digest only.
"""

from __future__ import annotations

import hashlib
import html

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


def build_subject(tag: str, jurisdiction: str, headline: str, n_sites: int = 0, tier1: int = 0) -> str:
    """ASCII tag, no emoji. The site suffix keeps the wording the team already knows."""
    sites = ""
    if n_sites:
        sites = f" [{n_sites} site{'s' if n_sites != 1 else ''} possibly affected{f', {tier1} Tier 1' if tier1 else ''}]"
    return f"[{tag}] {jurisdiction} - {headline}{sites}"


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
    ]
    values += list((extra or {}).items())
    lines = "\n".join(f"{k}: {html.escape(str(v if v not in (None, '') else '-'))}" for k, v in values)
    return f'<pre style="font-family:monospace;white-space:pre-wrap">{lines}</pre>'


def content_hash(row: dict) -> str:
    """Fingerprint of the words of an alert, for 'material update' detection."""
    text = " ".join(str(row.get(k) or "") for k in ("headline", "location", "description"))
    return hashlib.sha256(" ".join(text.split()).lower().encode("utf-8")).hexdigest()[:16]


def watch_and_act_should_email(n_sites_matched: int) -> bool:
    return n_sites_matched > 0


def bom_should_email(area_kind: str, state_site_total: int) -> bool:
    """area_kind: matched | none_inside | unparsed (core/platform/bom_areas.py)."""
    if area_kind == "matched":
        return True
    if area_kind == "none_inside":
        return False
    return state_site_total > 0
