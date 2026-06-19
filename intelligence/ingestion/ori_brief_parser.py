"""
ORI Brief Parser (WP2) — version-detecting, backward-compatible.

Parses Daily Operational Resilience Brief markdown into structured metadata +
candidate intelligence items. Pure functions: no network, no database.

Handles, via a single parse() entrypoint:
  - v1.0  YAML front matter + ## sections (forward standard)
  - v1    ## section headings, no front matter
  - v0    flat "**Key Events:** ..." bold pairs, single H1, no front matter

The parser NEVER rejects a brief: the worst case (v0, no sections) still yields
at least one candidate item plus the full raw document preserved. The filename
date is always authoritative for brief_date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# ─── Section name normalisation (heading / bold-label synonyms → canonical) ────

_SECTION_SYNONYMS = {
    "key incidents": "key_incidents",
    "key events": "key_incidents",
    "incidents": "key_incidents",
    "regulatory context": "regulatory",
    "regulatory": "regulatory",
    "cps 230": "regulatory",
    "cps230": "regulatory",
    "implications and recommendations": "implications",
    "implications": "implications",
    "recommendations": "implications",
    "resilience focus": "implications",
    "sources": "sources",
    "summary": "summary",
}

# Sections whose bullets become candidate intelligence events.
_EVENT_SECTIONS = ("key_incidents", "regulatory")

_FILENAME_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_REGION_KEYWORDS = {
    "AU": ["australia", "australian", "apra", "asic", "rba", "acsc", "vodafone",
           "telstra", "optus", "nbn"],
    "APAC": ["apac", "asia pacific", "asia-pacific", "singapore", "new zealand"],
    "GLOBAL": ["global", "international", "worldwide"],
}
_REGION_TO_GEOGRAPHY = {"australia": "AU", "au": "AU", "apac": "APAC",
                        "asia pacific": "APAC", "global": "GLOBAL",
                        "international": "GLOBAL"}


@dataclass
class ParsedBrief:
    file_name: str
    file_path: str
    brief_date: Optional[date]
    region: str                       # human label, e.g. "Australia"
    geography: str                    # normalised AU | APAC | GLOBAL
    version: str                      # "0" | "1" | "1.0"
    source: str
    classification: str
    front_matter: dict
    sections: dict                    # canonical_name -> list[str] (bullets)
    raw_markdown: str
    warnings: list = field(default_factory=list)

    def candidate_items(self) -> list[dict]:
        """Bullets that should become intelligence events, with their section."""
        items: list[dict] = []
        for section in _EVENT_SECTIONS:
            for bullet in self.sections.get(section, []):
                text = bullet.strip()
                if text:
                    items.append({"text": text, "section": section})
        return items

    def implications_text(self) -> str:
        return " ".join(self.sections.get("implications", []))


# ─── Front matter ──────────────────────────────────────────────────────────────

def split_front_matter(raw: str) -> tuple[dict, str]:
    """Return (front_matter_dict, body). Tolerant: ({}, raw) if absent/invalid."""
    if not raw.lstrip().startswith("---"):
        return {}, raw
    stripped = raw.lstrip()
    # Find the closing fence after the opening one.
    parts = stripped.split("\n", 1)
    if len(parts) < 2:
        return {}, raw
    rest = parts[1]
    end = rest.find("\n---")
    if end == -1:
        return {}, raw
    fm_block = rest[:end]
    body = rest[end + 4:]  # skip "\n---"
    fm: dict = {}
    try:
        import yaml  # available in the platform venv (pyyaml)
        loaded = yaml.safe_load(fm_block)
        if isinstance(loaded, dict):
            fm = loaded
    except Exception:
        # Minimal key: value fallback if PyYAML missing/invalid.
        for line in fm_block.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip()
    return fm, body.lstrip("\n")


# ─── Version detection ─────────────────────────────────────────────────────────

def detect_version(body: str) -> str:
    if re.search(r"^##\s+\w", body, re.MULTILINE):
        return "1"
    return "0"


# ─── Section extraction strategies ─────────────────────────────────────────────

def _canonical_section(label: str) -> Optional[str]:
    key = re.sub(r"[^a-z0-9 ]", "", label.strip().lower())
    key = re.sub(r"\s+", " ", key).strip()
    # try exact, then prefix match against synonyms
    if key in _SECTION_SYNONYMS:
        return _SECTION_SYNONYMS[key]
    for syn, canon in _SECTION_SYNONYMS.items():
        if key.startswith(syn):
            return canon
    return None


def _bullets(block: str) -> list[str]:
    """Extract bullet items from a section body; fall back to non-empty lines."""
    out: list[str] = []
    for line in block.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^[-*+]\s+(.*)$", s)
        if m:
            out.append(m.group(1).strip())
        elif not s.startswith("#") and not s.startswith("**Date"):
            # Non-bullet prose line in an event section still counts as one item.
            out.append(s)
    return out


def _extract_sections_v1(body: str) -> dict:
    """Split on '## ' headings; map heading → canonical section → bullets."""
    sections: dict = {}
    # Split keeping heading text.
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", body)
    # parts[0] is preamble before first heading; then alternating (heading, block)
    for i in range(1, len(parts), 2):
        heading = parts[i]
        block = parts[i + 1] if i + 1 < len(parts) else ""
        canon = _canonical_section(heading)
        if not canon:
            continue
        sections.setdefault(canon, []).extend(_bullets(block))
    return sections


def _extract_sections_v0(body: str) -> dict:
    """Flat '**Label:** value' pairs (and bullets) → canonical sections."""
    sections: dict = {}
    for line in body.splitlines():
        s = line.strip()
        m = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", s)
        if m:
            label = m.group(1).strip()
            canon = _canonical_section(label)
            value = m.group(2).strip()
            if canon and value:
                # Preserve the bold label in the item text — in v0 the label
                # carries meaning (e.g. "CPS 230"), which downstream
                # classification/enrichment needs.
                sections.setdefault(canon, []).append(f"{label}: {value}")
            continue
        bm = re.match(r"^[-*+]\s+(.*)$", s)
        if bm and sections:
            # Append loose bullets to the most recently seen section.
            last = list(sections.keys())[-1]
            sections[last].append(bm.group(1).strip())
    return sections


# ─── Metadata resolution ───────────────────────────────────────────────────────

def _date_from_filename(file_name: str) -> Optional[date]:
    m = _FILENAME_DATE_RE.search(file_name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _resolve_region(fm: dict, body: str) -> tuple[str, str]:
    """Return (region_label, geography)."""
    if fm.get("region"):
        label = str(fm["region"])
        geo = _REGION_TO_GEOGRAPHY.get(label.strip().lower(), "AU")
        return label, geo
    text = body.lower()
    for geo, kws in _REGION_KEYWORDS.items():
        if any(kw in text for kw in kws):
            label = {"AU": "Australia", "APAC": "APAC", "GLOBAL": "Global"}[geo]
            return label, geo
    return "Australia", "AU"  # platform default


# ─── Public entrypoint ─────────────────────────────────────────────────────────

def parse_brief(file_path: str, raw: str) -> ParsedBrief:
    file_name = file_path.rsplit("/", 1)[-1]
    warnings: list[str] = []

    fm, body = split_front_matter(raw)
    version = str(fm.get("version") or detect_version(body))

    # Sections
    if version.startswith("1"):
        sections = _extract_sections_v1(body)
        if not sections:                       # heading detection missed — try v0
            sections = _extract_sections_v0(body)
    else:
        sections = _extract_sections_v0(body)
        if not sections:                       # last resort — treat as v1 shape
            sections = _extract_sections_v1(body)

    # Date — filename is authoritative
    fn_date = _date_from_filename(file_name)
    fm_date = fm.get("date")
    if fm_date is not None and fn_date is not None and str(fm_date) != fn_date.isoformat():
        warnings.append("date_mismatch")
    brief_date = fn_date
    if brief_date is None and fm_date is not None:
        brief_date = _date_from_filename(str(fm_date))
    if brief_date is None:
        warnings.append("no_date")

    region, geography = _resolve_region(fm, body)
    if "region" not in fm:
        warnings.append("region_defaulted")

    source = str(fm.get("source") or "grok")
    classification = str(fm.get("classification") or "public")

    parsed = ParsedBrief(
        file_name=file_name,
        file_path=file_path,
        brief_date=brief_date,
        region=region,
        geography=geography,
        version=version,
        source=source,
        classification=classification,
        front_matter=fm,
        sections=sections,
        raw_markdown=raw,
        warnings=warnings,
    )
    if not parsed.candidate_items():
        warnings.append("no_events")
    return parsed
