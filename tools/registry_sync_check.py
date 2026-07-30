#!/usr/bin/env python3
"""Registry sync validation (MSN-0308, Workstream 5).

Checks that the SUOC Platform Registry's Captain Dashboard summary table
stays in sync with each capability's own detailed record — Maturity and
Engineering Confidence specifically, since both have already drifted
silently twice this session (Event Bus, MSN-0305; Attention Engine and
Priority & Opportunity Engine, MSN-0307) without any tooling catching it.

Deliberately lightweight: a regex-based parser over the existing markdown
file, not a schema migration or a new data store — the Registry stays a
hand-authored document; this is a read-only checker a human (or a future
mission) runs before/after editing it, not a live validation gate.

Usage:
    python3 tools/registry_sync_check.py [path/to/SUOC-Platform-Registry.md]

Exit code 0 if no drift found, 1 if any capability's dashboard row
disagrees with its own detailed record.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "SUOC-Platform-Registry.md"


def _parse_dashboard(text: str) -> dict[str, tuple[str, str]]:
    """Extract {capability_name: (maturity, confidence)} from the Captain
    Dashboard table. Maturity/confidence cells may carry markdown bold
    (`**L4**`, `**99%**`) — stripped before returning."""
    dashboard: dict[str, tuple[str, str]] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("## Captain Dashboard"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if not in_table or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        name = cells[0].strip("* ")
        maturity = cells[2].strip("* ")
        confidence = cells[3].strip("* ")
        if name in ("Platform Capability", "---") or set(maturity) <= {"-"}:
            continue
        dashboard[name] = (maturity, confidence)
    return dashboard


def _parse_detail_records(text: str) -> dict[str, tuple[str, str]]:
    """Extract {capability_name: (maturity, confidence)} from each `### Name`
    capability record's own `Current Maturity`/`Engineering Confidence`
    bullet lines."""
    records: dict[str, tuple[str, str]] = {}
    sections = re.split(r"\n### ", text)
    for section in sections[1:]:
        name_line, _, body = section.partition("\n")
        name = name_line.strip()
        maturity_match = re.search(r"\*\*Current Maturity:\*\*\s*(L\d(?:[–-]L\d)?)", body)
        confidence_match = re.search(r"\*\*Engineering Confidence:\*\*\s*(\d+%)", body)
        if maturity_match and confidence_match:
            records[name] = (maturity_match.group(1), confidence_match.group(1))
    return records


def check(path: Path) -> list[str]:
    """Return a list of human-readable drift descriptions (empty = clean)."""
    text = path.read_text(encoding="utf-8")
    dashboard = _parse_dashboard(text)
    records = _parse_detail_records(text)

    findings: list[str] = []
    for name, (dash_maturity, dash_confidence) in dashboard.items():
        record = records.get(name)
        if record is None:
            findings.append(f"'{name}': in Captain Dashboard but no matching '### {name}' detail record found")
            continue
        rec_maturity, rec_confidence = record
        if dash_maturity != rec_maturity:
            findings.append(
                f"'{name}': dashboard maturity '{dash_maturity}' != detail record maturity '{rec_maturity}'"
            )
        if dash_confidence != rec_confidence:
            findings.append(
                f"'{name}': dashboard confidence '{dash_confidence}' != detail record confidence '{rec_confidence}'"
            )
    return findings


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_PATH
    findings = check(path)
    if not findings:
        print(f"OK — no dashboard/detail-record drift found ({path})")
        return 0
    print(f"DRIFT FOUND — {len(findings)} issue(s) in {path}:")
    for f in findings:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
