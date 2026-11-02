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


def build_subject(tag: str, jurisdiction: str, headline: str, n_sites: int = 0, tier1: int = 0, tier1_names: list[str] | None = None) -> str:
    """ASCII tag, no emoji. The site suffix keeps the wording the team already knows and,
    when given, names up to two Tier 1 sites so the inbox preview says which."""
    sites = ""
    if n_sites:
        names = ""
        if tier1 and tier1_names:
            shown = ", ".join(tier1_names[:2])
            names = f": {shown}{f' +{tier1 - 2}' if tier1 > 2 else ''}"
        sites = f" [{n_sites} site{'s' if n_sites != 1 else ''} possibly affected{f', {tier1} Tier 1{names}' if tier1 else ''}]"
    return f"[{tag}] {jurisdiction} - {headline}{sites}"


def site_label(site: dict) -> str:
    """Name, with the suburb only when it adds something ("Bendigo", not "Bendigo, Bendigo")."""
    name, suburb = str(site.get("name") or ""), str(site.get("suburb") or "")
    return name if not suburb or suburb.lower() in name.lower() else f"{name} ({suburb})"


def sites_banner(sites: list[dict], phrase: str = "possibly affected", *, register_ok: bool = True, fallback: str | None = None, max_names: int = 6) -> str:
    """The first thing in the body: how many of our sites, how many Tier 1, and which.
    Red when a Tier 1 site is in it, amber otherwise. With no site it says so and, for
    a search by location, that this is not proof of safety; `fallback` replaces that
    sentence when something more specific is known (e.g. an unresolved BOM area)."""
    if not register_ok:
        return _banner_box("#5B6770", "#F1F3F5", "Our sites: impact unknown", "The site register could not be read, so no site was checked against this alert.")
    if not sites:
        return _banner_box("#5B6770", "#F1F3F5", "No site matched this alert", fallback or "Matching is by location, so this is not proof that none of our sites are affected.")
    tiers = {"Tier 1": [], "Tier 2": [], "Tier 3": []}
    for s in sites:
        tiers.setdefault(s.get("priority") or "Tier 3", []).append(site_label(s))
    tier1 = len(tiers["Tier 1"])
    n = len(sites)
    head = f"{n} of our sites {phrase}" if n != 1 else f"1 of our sites {phrase}"
    if tier1:
        head += f" - {tier1} Tier 1"
    names, shown = [], 0
    for tier in ("Tier 1", "Tier 2", "Tier 3"):
        if not tiers.get(tier):
            continue
        take = tiers[tier][: max(0, max_names - shown)]
        shown += len(take)
        if take:
            names.append(f"{tier}: " + ", ".join(take))
    more = f" (+{n - shown} more, listed below)" if n > shown else ""
    color, bg = ("#A23A34", "#FBEFEE") if tier1 else ("#8A5A1B", "#FBF3E6")
    return _banner_box(color, bg, head, "; ".join(names) + more)


def _banner_box(color: str, background: str, headline: str, detail: str) -> str:
    return (
        f'<div style="border-left:6px solid {color};background:{background};padding:10px 14px;margin:0 0 14px">'
        f'<div style="font-size:18px;font-weight:bold;color:{color}">{html.escape(headline)}</div>'
        f'<div style="margin-top:4px">{html.escape(detail)}</div></div>'
    )


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


def watch_and_act_should_email(n_sites_matched: int) -> bool:
    return n_sites_matched > 0


def bom_should_email(area_kind: str, state_site_total: int) -> bool:
    """area_kind: matched | none_inside | unparsed (core/platform/bom_areas.py)."""
    if area_kind == "matched":
        return True
    if area_kind == "none_inside":
        return False
    return state_site_total > 0


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
