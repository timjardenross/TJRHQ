"""
Read-only markdown loaders.  Each returns a list of plain dicts.
No schema enforcement — downstream code is tolerant of missing keys.
"""

import re
from pathlib import Path
from typing import List, Dict, Any

import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _first_heading(text: str) -> str:
    for m in re.finditer(r"^#+ (.+)", text, re.MULTILINE):
        title = m.group(1).strip()
        # Skip the Context Relationships section heading
        if "context relationship" in title.lower():
            continue
        return title
    return ""


def _field(text: str, *labels: str) -> str:
    """Extract value for the first matching label in 'Label: value' or '**Label:** value' patterns."""
    for label in labels:
        m = re.search(
            rf"(?:\*{{0,2}}{re.escape(label)}\*{{0,2}})\s*[:\-]\s*(.+)",
            text, re.IGNORECASE
        )
        if m:
            val = m.group(1).strip()
            # Strip markdown bold/italic markers and trailing punctuation
            val = re.sub(r"^\*+|\*+$", "", val).strip()
            return val
    return ""


# ---------------------------------------------------------------------------
# Missions
# ---------------------------------------------------------------------------

def load_missions() -> List[Dict[str, Any]]:
    missions = []
    for directory in (config.MISSIONS_ACTIVE, config.MISSIONS_COMPLETE):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")) + sorted(directory.glob("*.txt")):
            # Skip ancillary files (test scenarios, acceptance criteria, implementation plans, etc.)
            skip_suffixes = (
                "acceptance-criteria", "implementation-plan", "risk-control",
                "codex-brief", "test-scenarios", "validation-report",
                "adr-0003", "number-one-assignment-authority-implementation",
            )
            if any(s in path.name.lower() for s in skip_suffixes):
                continue

            text = _read(path)
            if not text.strip():
                continue

            mission_id = _extract_mission_id(path.name, text)
            if not mission_id:
                continue

            missions.append({
                "id": mission_id,
                "title": _first_heading(text) or path.stem,
                "status": _field(text, "Status"),
                "owner": _field(text, "Owner"),
                "priority": _field(text, "Priority"),
                "created": _field(text, "Created", "Created Date"),
                "source_file": str(path),
                "text": text,
                "is_completed": directory == config.MISSIONS_COMPLETE,
            })
    return missions


def _extract_mission_id(filename: str, text: str) -> str:
    # Try filename first
    m = re.search(r"((?:USS-TJR-)?MSN-\d{4}[A-Z]?)", filename, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Try first 20 lines of text
    for line in text.splitlines()[:20]:
        m = re.search(r"((?:USS-TJR-)?MSN-\d{4}[A-Z]?)", line, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return ""


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def load_decisions() -> List[Dict[str, Any]]:
    decisions = []
    for path in sorted(config.DECISIONS_DIR.glob("DECISION-*.md")):
        text = _read(path)
        if not text.strip():
            continue

        dec_id = _extract_decision_id(path.name, text)
        if not dec_id:
            continue

        decisions.append({
            "id": dec_id,
            "title": _first_heading(text) or path.stem,
            "statement": _extract_section(text, "Decision Statement", "Decision"),
            "rationale": _extract_section(text, "Rationale", "Reasoning"),
            "status": _field(text, "Status"),
            "authority": _field(text, "Authority", "Decision Authority"),
            "date": _field(text, "Date", "Decision Date"),
            "source_file": str(path),
            "text": text,
        })
    return decisions


def _extract_decision_id(filename: str, text: str) -> str:
    m = re.search(r"(DEC-\d{8}-\d{3,6})", filename + "\n" + text[:500], re.IGNORECASE)
    return m.group(1).upper() if m else ""


def _extract_section(text: str, *headings: str) -> str:
    for heading in headings:
        m = re.search(
            rf"#+\s+\*{{0,2}}{re.escape(heading)}\*{{0,2}}[^\n]*\n(.*?)(?=\n#+|\Z)",
            text, re.IGNORECASE | re.DOTALL
        )
        if m:
            return m.group(1).strip()[:500]
    return ""


# ---------------------------------------------------------------------------
# ADRs
# ---------------------------------------------------------------------------

def load_adrs() -> List[Dict[str, Any]]:
    adrs = []
    if not config.ADR_DIR.exists():
        return adrs

    seen = set()
    for path in sorted(config.ADR_DIR.glob("ADR-*.txt")) + sorted(config.ADR_DIR.glob("ADR-*.md")):
        # Skip duplicates (the " 2.txt" copies)
        canonical = re.sub(r" 2\.(txt|md)$", r".\1", path.name)
        if canonical in seen:
            continue
        seen.add(canonical)

        text = _read(path)
        if not text.strip():
            continue

        adr_id = _extract_adr_id(path.name, text)
        if not adr_id:
            continue

        adrs.append({
            "id": adr_id,
            "title": _field(text, "Title") or _first_heading(text) or path.stem,
            "status": _field(text, "Status"),
            "decision": _extract_section(text, "Decision"),
            "context": _extract_section(text, "Context"),
            "consequences": _extract_section(text, "Consequences"),
            "source_file": str(path),
            "text": text,
        })
    return adrs


def _extract_adr_id(filename: str, text: str) -> str:
    m = re.search(r"(ADR-\d{3})", filename + "\n" + text[:200], re.IGNORECASE)
    return m.group(1).upper() if m else ""


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

def load_capabilities() -> List[Dict[str, Any]]:
    if not config.CAPABILITY_FILE.exists():
        return []

    text = _read(config.CAPABILITY_FILE)
    capabilities = []

    # Each capability is a ### heading block
    blocks = re.split(r"\n###+ ", text)
    for block in blocks[1:]:  # skip preamble
        lines = block.strip().splitlines()
        if not lines:
            continue

        title_line = lines[0].strip()
        block_text = "\n".join(lines)

        # Try to extract a capability ID (CAP-XXX or numbered reference)
        cap_id_m = re.search(r"\b(CAP-\d{3,})\b", block_text, re.IGNORECASE)
        if not cap_id_m:
            # Synthesise an ID from the block number
            cap_id_m_num = re.search(r"^\d+\.", title_line)
            if cap_id_m_num:
                cap_id = f"CAP-{cap_id_m_num.group(0).rstrip('.')}"
            else:
                continue
        else:
            cap_id = cap_id_m.group(1).upper()

        # Extract mission source
        mission_src = re.search(r"Mission Source[:\s]+([^\n]+)", block_text)

        capabilities.append({
            "id": cap_id,
            "name": re.sub(r"^\d+\.\s*", "", title_line).strip(),
            "maturity": _field(block_text, "Maturity"),
            "status": _field(block_text, "Status"),
            "owner": _field(block_text, "Owner"),
            "mission_source": mission_src.group(1).strip() if mission_src else "",
            "source_file": str(config.CAPABILITY_FILE),
            "text": block_text,
        })

    return capabilities


# ---------------------------------------------------------------------------
# Corpus builder
# ---------------------------------------------------------------------------

def load_missions_from_dir(directory: Path) -> List[Dict[str, Any]]:
    """Load missions from a single flat directory (used for enrichment POC)."""
    missions = []
    for path in sorted(directory.glob("*.md")) + sorted(directory.glob("*.txt")):
        text = _read(path)
        if not text.strip():
            continue
        mission_id = _extract_mission_id(path.name, text)
        if not mission_id:
            # Fallback: use stem as ID
            mission_id = path.stem.upper()
        missions.append({
            "id": mission_id,
            "title": _first_heading(text) or path.stem,
            "status": _field(text, "Status"),
            "owner": _field(text, "Owner"),
            "priority": _field(text, "Priority"),
            "created": _field(text, "Created", "Created Date"),
            "source_file": str(path),
            "text": text,
            "is_completed": False,
        })
    return missions


def load_corpus(missions_override_dir: Path = None) -> Dict[str, Any]:
    """
    Load everything into a single dict keyed by entity type.

    missions_override_dir: if set, load missions from this flat directory
    instead of the default Active/Completed directories.
    """
    if missions_override_dir and missions_override_dir.exists():
        missions = load_missions_from_dir(missions_override_dir)
    else:
        missions = load_missions()

    decisions    = load_decisions()
    adrs         = load_adrs()
    capabilities = load_capabilities()

    return {
        "missions":     {m["id"]: m for m in missions},
        "decisions":    {d["id"]: d for d in decisions},
        "adrs":         {a["id"]: a for a in adrs},
        "capabilities": {c["id"]: c for c in capabilities},
    }
