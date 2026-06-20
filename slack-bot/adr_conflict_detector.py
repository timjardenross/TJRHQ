"""
ADR Conflict Detector
Owner: Knowledge Officer / Chief Engineer
Date: 2026-06-13
Purpose: Parse Architecture Decision Records for cross-references and potential
         conflicts. Surfaces as a Slack report or command response.

Public API:
    scan_adrs() -> ADRScanResult
    format_conflict_report(result: ADRScanResult) -> str
    check_new_adr_conflicts(new_adr_text: str) -> str
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADR_DIRS = [
    _REPO_ROOT / "core" / "governance" / "architecture-decision-records",
    _REPO_ROOT / "knowledge" / "architecture",
]
_ADR_PATTERN = re.compile(r"\bADR-\d{3}\b", re.IGNORECASE)
_STATUS_PATTERN = re.compile(r"^Status:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_TITLE_PATTERN = re.compile(r"^Title:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_SUPERSEDES_PATTERN = re.compile(r"supersedes?\s+(ADR-\d{3})", re.IGNORECASE)
_CONFLICTS_PATTERN = re.compile(r"conflicts?\s+with\s+(ADR-\d{3})", re.IGNORECASE)

ACTIVE_STATUSES = {"approved", "accepted", "active"}
INACTIVE_STATUSES = {"superseded", "deprecated", "rejected", "withdrawn"}


@dataclass
class ADRRecord:
    adr_id: str
    title: str
    status: str
    path: Path
    references: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    explicit_conflicts: list[str] = field(default_factory=list)
    content: str = ""


@dataclass
class ConflictIssue:
    adr_id: str
    issue_type: str  # "superseded_ref", "explicit_conflict", "orphan_supersession"
    description: str
    severity: str    # "high", "medium", "low"


@dataclass
class ADRScanResult:
    adrs: dict[str, ADRRecord]
    conflicts: list[ConflictIssue]
    total_adrs: int
    active_adrs: int
    inactive_adrs: int


def _iter_adr_files() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for base in _ADR_DIRS:
        if not base.exists():
            continue
        for suffix in ("*.txt", "*.md"):
            for path in sorted(base.glob(suffix)):
                if re.match(r"ADR-\d{3}", path.name, re.IGNORECASE) and path not in seen:
                    seen.add(path)
                    files.append(path)
    return files


def _parse_adr(path: Path) -> ADRRecord | None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Derive ID from filename
    id_match = re.match(r"(ADR-\d{3})", path.name, re.IGNORECASE)
    if not id_match:
        return None
    adr_id = id_match.group(1).upper()

    title_match = _TITLE_PATTERN.search(content)
    title = title_match.group(1).strip() if title_match else path.stem

    status_match = _STATUS_PATTERN.search(content)
    status = status_match.group(1).strip().lower() if status_match else "unknown"

    references = [r.upper() for r in _ADR_PATTERN.findall(content) if r.upper() != adr_id]
    supersedes = [r.upper() for r in _SUPERSEDES_PATTERN.findall(content)]
    explicit_conflicts = [r.upper() for r in _CONFLICTS_PATTERN.findall(content)]

    return ADRRecord(
        adr_id=adr_id,
        title=title,
        status=status,
        path=path,
        references=list(dict.fromkeys(references)),
        supersedes=list(dict.fromkeys(supersedes)),
        explicit_conflicts=list(dict.fromkeys(explicit_conflicts)),
        content=content,
    )


def scan_adrs() -> ADRScanResult:
    """Scan all ADR files and return a structured conflict analysis."""
    files = _iter_adr_files()
    adrs: dict[str, ADRRecord] = {}

    for path in files:
        record = _parse_adr(path)
        if record:
            adrs[record.adr_id] = record

    conflicts: list[ConflictIssue] = []

    for adr_id, record in adrs.items():
        is_active = record.status in ACTIVE_STATUSES

        # Check if this ADR references a superseded/deprecated ADR
        for ref_id in record.references:
            if ref_id not in adrs:
                continue
            ref = adrs[ref_id]
            if ref.status in INACTIVE_STATUSES and is_active:
                conflicts.append(ConflictIssue(
                    adr_id=adr_id,
                    issue_type="superseded_ref",
                    description=f"`{adr_id}` ({record.status}) references `{ref_id}` which is {ref.status}",
                    severity="medium",
                ))

        # Explicit conflict declarations
        for conflict_id in record.explicit_conflicts:
            other = adrs.get(conflict_id)
            other_active = other and other.status in ACTIVE_STATUSES
            if is_active and other_active:
                conflicts.append(ConflictIssue(
                    adr_id=adr_id,
                    issue_type="explicit_conflict",
                    description=f"`{adr_id}` explicitly conflicts with `{conflict_id}` — both are active",
                    severity="high",
                ))

        # Supersession claims — check the superseded ADR's status matches
        for sup_id in record.supersedes:
            other = adrs.get(sup_id)
            if other and other.status not in INACTIVE_STATUSES:
                conflicts.append(ConflictIssue(
                    adr_id=adr_id,
                    issue_type="orphan_supersession",
                    description=(
                        f"`{adr_id}` claims to supersede `{sup_id}`, "
                        f"but `{sup_id}` still has status '{other.status}'"
                    ),
                    severity="high",
                ))

    # Deduplicate by description
    seen_descs: set[str] = set()
    unique_conflicts: list[ConflictIssue] = []
    for c in conflicts:
        if c.description not in seen_descs:
            seen_descs.add(c.description)
            unique_conflicts.append(c)

    unique_conflicts.sort(key=lambda c: ("high", "medium", "low").index(c.severity))

    active_count = sum(1 for r in adrs.values() if r.status in ACTIVE_STATUSES)

    return ADRScanResult(
        adrs=adrs,
        conflicts=unique_conflicts,
        total_adrs=len(adrs),
        active_adrs=active_count,
        inactive_adrs=len(adrs) - active_count,
    )


def format_conflict_report(result: ADRScanResult) -> str:
    lines = [
        "*ADR Conflict Analysis — Starship Endeavour*",
        "",
        f"Scanned {result.total_adrs} ADRs — {result.active_adrs} active, {result.inactive_adrs} inactive.",
        "",
    ]

    if not result.conflicts:
        lines.append(":white_check_mark: No conflicts detected across active ADRs.")
        return "\n".join(lines)

    high = [c for c in result.conflicts if c.severity == "high"]
    medium = [c for c in result.conflicts if c.severity == "medium"]

    if high:
        lines.append(f":red_circle: *High severity ({len(high)}):*")
        for c in high:
            lines.append(f"  • {c.description}")
        lines.append("")

    if medium:
        lines.append(f":large_yellow_circle: *Medium severity ({len(medium)}):*")
        for c in medium:
            lines.append(f"  • {c.description}")
        lines.append("")

    lines.append("_Review these with the Chief Engineer and update ADR statuses to reflect current architecture._")
    return "\n".join(lines)


def check_new_adr_conflicts(new_adr_text: str) -> str:
    """Check a new ADR's text against the existing ADR corpus for potential conflicts.

    Returns a formatted notice, or empty string if none found.
    """
    result = scan_adrs()
    referenced = [r.upper() for r in _ADR_PATTERN.findall(new_adr_text)]
    supersedes = [r.upper() for r in _SUPERSEDES_PATTERN.findall(new_adr_text)]

    warnings: list[str] = []

    for ref_id in referenced:
        rec = result.adrs.get(ref_id)
        if not rec:
            continue
        if rec.status in INACTIVE_STATUSES:
            warnings.append(f":warning: References `{ref_id}` ({rec.title}) which is {rec.status}.")

    for sup_id in supersedes:
        rec = result.adrs.get(sup_id)
        if rec and rec.status not in INACTIVE_STATUSES:
            warnings.append(
                f":warning: Claims to supersede `{sup_id}` ({rec.title}), "
                f"but its status is still '{rec.status}'. Update that ADR's status."
            )
        if not rec:
            warnings.append(f":question: Claims to supersede `{sup_id}` — not found in ADR corpus.")

    if not warnings:
        return ""
    return "\n".join([":mag: *Prior ADR checks for this decision:*"] + warnings)


if __name__ == "__main__":
    result = scan_adrs()
    print(format_conflict_report(result))
