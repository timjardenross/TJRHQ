#!/usr/bin/env python3
"""Repository source parsers for Notion one-way sync."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".txt"}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def file_date(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def first_heading_or_stem(path: Path, content: str) -> str:
    match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith(("File:", "Purpose:", "Dependencies/Notes:")):
            return line.replace("MISSION:", "").replace("TITLE:", "").strip() or path.stem
    return path.stem.replace("-", " ")


def field(content: str, name: str, default: str = "Unknown") -> str:
    pattern = rf"^{re.escape(name)}\s*:\s*(.+)$"
    match = re.search(pattern, content, flags=re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else default


def mission_id(path: Path, content: str) -> str:
    match = re.search(r"(USS-TJR-MSN-\d{4}[A-Z]?)", content)
    if match:
        return match.group(1)
    match = re.search(r"(USS-TJR-MSN-\d{4}[A-Z]?)", path.name)
    return match.group(1) if match else relative(path)


def mission_records() -> list[dict[str, str]]:
    records = []
    for folder in [ROOT / "Missions", ROOT / "core/missions"]:
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            content = read(path)
            records.append(
                {
                    "mission_id": mission_id(path, content),
                    "title": field(content, "TITLE", first_heading_or_stem(path, content)),
                    "status": field(content, "Status", "Active" if "/Active/" in f"/{relative(path)}" else "Unknown"),
                    "owner": field(content, "Owner", "Unknown"),
                    "priority": field(content, "Priority", "Unknown"),
                    "github_path": relative(path),
                    "last_updated": file_date(path),
                }
            )
    return records


def architecture_id(path: Path) -> str:
    stem = path.stem
    match = re.match(r"([A-Z]+-\d+)", stem)
    return match.group(1) if match else relative(path)


def architecture_records() -> list[dict[str, str]]:
    roots = [
        ROOT / "core/architecture",
        ROOT / "knowledge/architecture",
        ROOT / "core/infrastructure/supabase",
    ]
    records = []
    for folder in roots:
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            content = read(path)
            rel = relative(path)
            records.append(
                {
                    "document_id": architecture_id(path),
                    "title": first_heading_or_stem(path, content),
                    "status": field(content, "status", field(content, "Status", "Active")),
                    "category": category_for_path(rel),
                    "source_path": rel,
                    "last_updated": file_date(path),
                }
            )
    return records


def category_for_path(path: str) -> str:
    if "supabase" in path.lower():
        return "Supabase"
    if "reference-architectures" in path:
        return "Reference Architecture"
    parts = path.split("/")
    return parts[1].replace("-", " ").title() if len(parts) > 1 else "Architecture"


def specialist_records() -> list[dict[str, object]]:
    registry = ROOT / "core/crew/registry/specialist-registry.md"
    content = read(registry)
    records: list[dict[str, object]] = []
    for line in content.splitlines():
        if not line.startswith("|") or "`" not in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"Specialist", "---"}:
            continue
        name = cells[0]
        governance = cells[1].strip("`")
        status = cells[3] if len(cells) == 4 else cells[-2]
        domains = domains_for_specialist(name)
        records.append(
            {
                "source_id": name,
                "name": name,
                "department": department_for_specialist(name),
                "status": status,
                "primary_domain": domains[0] if domains else "Unknown",
                "supporting_domains": domains[1:],
                "governance_folder": governance,
            }
        )
    return records


def domains_for_specialist(name: str) -> list[str]:
    mapping = {
        "Chief of Staff": ["Missions", "Governance", "Prioritisation", "Crew"],
        "Chief Engineer": ["Architecture", "Infrastructure", "Supabase", "GitHub"],
        "Coder Agent": ["Implementation", "Code", "Automation"],
        "QA & Test Officer": ["Testing", "Quality", "Validation"],
        "Knowledge Officer": ["Knowledge Assets", "Documentation", "Institutional Memory"],
        "UX Design Officer": ["User Experience", "Accessibility", "Workflow Design"],
        # MSN-0312: "Design Officer" is the canonical retitle of "UX Design
        # Officer" (same specialist, same registry ID). Same domain list,
        # legacy key kept as a permanent alias per MSN-0064 precedent.
        "Design Officer": ["User Experience", "Accessibility", "Workflow Design"],
    }
    return mapping.get(name, ["Unknown"])


def department_for_specialist(name: str) -> str:
    if "Engineer" in name or "Coder" in name or "QA" in name:
        return "Engineering"
    if "Knowledge" in name:
        return "Knowledge"
    # MSN-0312: "Design Officer" (canonical) does not contain the substring
    # "UX", so it must also be matched on "Design" directly or it would
    # silently fall through to "Future Crew". Checked against every other
    # specialist name in this function/registry (Chief of Staff/Engineer,
    # Coder Agent, Knowledge Officer, QA & Test Officer, Research/Medical/
    # Operations Officer, "Product Designer" future-crew entry) — only
    # "Product Designer" contains "Design", and it already matches via
    # "Designer" today, so adding this substring introduces no new
    # mis-classification.
    if "UX" in name or "Designer" in name or "Design" in name:
        return "Design"
    if "Staff" in name:
        return "Operations"
    return "Future Crew"
